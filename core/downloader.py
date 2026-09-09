# -*- coding: utf-8 -*-
"""Local video downloads. Cookie files are selected and used on this computer."""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlsplit

from . import autoinstall

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_PCT_RE = re.compile(r"\[download\]\s+([\d.]+)%")
_FILE_MARKER = "__AIGCTOOL_FILE__:"
_FORMAT_MARKER = "__AIGCTOOL_FORMAT__:"


def _ytdlp_path():
    return autoinstall.find("yt-dlp") or "yt-dlp"


def detect_platform(url):
    host = (urlsplit((url or "").strip()).hostname or "").lower()
    if host == "b23.tv" or host == "bilibili.com" or host.endswith(".bilibili.com"):
        return "bilibili"
    if host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
        return "youtube"
    return "other"


def _cookie_candidates(platform, explicit, script_dir):
    """Legacy opt-in discovery helper; downloads never silently select a cookie."""
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    host = "www.bilibili.com" if platform == "bilibili" else "www.youtube.com"
    return [explicit, os.path.join("D:\\download", f"{host}_cookies.txt"),
            os.path.join(script_dir, "cookies.txt") if script_dir else None,
            os.path.join(downloads, f"{host}_cookies.txt")]


def find_cookie(platform, explicit="", script_dir=""):
    for candidate in _cookie_candidates(platform, explicit, script_dir):
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return ""


def validate_cookie(path, platform):
    """Check file format/domain, not whether a remote login is still valid."""
    if not path:
        return ""
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise ValueError("所选 Cookie 文件不存在，请重新选择；不会自动换用其它文件。")
    jar = MozillaCookieJar(path)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except (OSError, ValueError) as exc:
        raise ValueError("Cookie 文件格式无法读取，请从浏览器重新导出 Netscape 格式的 cookies.txt。") from exc
    domains = {cookie.domain.lstrip(".").lower() for cookie in jar}
    expected = {"youtube": "youtube.com", "bilibili": "bilibili.com"}.get(platform)
    if not domains or (expected and not any(d == expected or d.endswith("." + expected) for d in domains)):
        raise ValueError("Cookie 文件中没有该平台的数据，请选择对应网站导出的文件。")
    return path


def _validate_url(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
            raise ValueError
    except ValueError as exc:
        raise ValueError("请粘贴完整的 http/https 视频链接。") from exc


def _validate_proxy(proxy):
    if not proxy:
        return
    try:
        parsed = urlsplit(proxy)
        if parsed.scheme not in ("http", "https", "socks5", "socks5h") or not parsed.hostname:
            raise ValueError
        parsed.port
    except ValueError as exc:
        raise ValueError("代理地址格式不正确，例如 http://127.0.0.1:7890；不需要时留空。") from exc


def build_args(url, out_dir, platform, cookie="", has_ffmpeg_flag=True, proxy=""):
    _validate_url(url)
    _validate_proxy(proxy)
    args = [_ytdlp_path(), "--ignore-config", "--no-playlist", "--newline",
            "--progress", "--progress-delta", "0.5",
            "--no-simulate", "--continue", "--no-overwrites", "--socket-timeout", "30",
            "--retries", "3", "--fragment-retries", "3",
            "-o", os.path.join(out_dir, "%(title).180B [%(id)s].%(ext)s"),
            "--print", "before_dl:" + _FORMAT_MARKER + "%(id)s | %(resolution)s | %(fps)s fps | %(format_id)s",
            "--print", "after_move:" + _FILE_MARKER + "%(filepath)j"]
    if cookie:
        args += ["--cookies", cookie]
    if proxy:
        args += ["--proxy", proxy]
    if platform == "youtube":
        args += ["-f", "bv*+ba/b", "--format-sort", "res,fps"]
        runtime = autoinstall.find_js_runtime()
        if runtime:
            args += ["--js-runtimes", f"{runtime[0]}:{runtime[1]}"]
    ffmpeg = autoinstall.find("ffmpeg")
    if ffmpeg and has_ffmpeg_flag:
        args += ["--ffmpeg-location", os.path.dirname(ffmpeg), "--merge-output-format", "mp4"]
    # End options so pasted input can never become a yt-dlp command-line option.
    return args + ["--", url]


def has_ffmpeg_available():
    return autoinstall.find("ffmpeg") is not None


def safe_message(message):
    """Keep useful diagnostics without showing credentials or signed URL queries."""
    if re.search(r"(?i)(?:^|\s)(?:cookie|authorization|set-cookie)\s*:", message):
        return "[已隐藏身份验证数据]"
    def redact_url(match):
        value = match.group(0)
        try:
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            if parsed.port:
                host += f":{parsed.port}"
            return f"{parsed.scheme}://{host}{parsed.path}" + ("?[已隐藏参数]" if parsed.query else "")
        except ValueError:
            return "[已隐藏链接]"
    return re.sub(r"(?:https?|socks5h?)://[^\s<>\"']+", redact_url, str(message))[:2000]


def failure_hint(messages):
    text = "\n".join(messages).lower()
    if "not a bot" in text or "cookies are no longer valid" in text or "sign in to confirm" in text:
        return "YouTube 要求重新验证登录。请先在本机浏览器确认能播放，再重新导出并选择 Cookie；更新工具不会自动修复失效的登录状态。"
    if any(word in text for word in ("javascript runtime", "js runtime", "challenge solving", "n challenge", "signature solving")):
        return "YouTube 的 JavaScript 验证未完成，请点击「安装 / 更新下载工具」检查下载器和运行环境。"
    if any(word in text for word in ("timed out", "proxyerror", "connection refused", "unable to connect", "name resolution")):
        return "网络连接失败。请确认本机能访问视频网站，并检查下载页中的代理设置。"
    if "403" in text:
        return "视频服务器拒绝请求（403）。请检查本机网络和 Cookie，并更新下载工具后重试；这不一定是 Cookie 过期。"
    return "请查看上方具体错误；可以更新下载工具，或检查视频访问权限、Cookie 和本机网络。"


@dataclass
class RunResult:
    returncode: int
    files: list = field(default_factory=list)
    messages: list = field(default_factory=list)


def _run(args, progress_cb=None, log=None):
    log = log or (lambda *_: None)
    files, messages = [], []
    proc = subprocess.Popen(
        args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    for raw in proc.stdout:
        line = raw.strip()
        if line.startswith(_FILE_MARKER):
            try:
                path = json.loads(line[len(_FILE_MARKER):])
                if isinstance(path, str):
                    files.append(path)
            except ValueError:
                pass
        elif line.startswith(_FORMAT_MARKER):
            log("所选视频：" + safe_message(line[len(_FORMAT_MARKER):]))
        elif _PCT_RE.search(line):
            if progress_cb:
                progress_cb(min(float(_PCT_RE.search(line).group(1)) / 100, 0.99))
        elif line:
            safe = safe_message(line)
            messages.append(safe)
            messages = messages[-30:]
            log(safe)
    proc.stdout.close()
    return RunResult(proc.wait(), files, messages)


def inspect_media(path):
    probe = autoinstall.find("ffprobe")
    if not probe:
        raise RuntimeError("缺少 ffprobe，无法核验下载文件，请先安装下载工具。")
    proc = subprocess.run(
        [probe, "-v", "error", "-show_entries",
         "format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate",
         "-of", "json", path], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace", timeout=30, creationflags=CREATE_NO_WINDOW,
    )
    if proc.returncode:
        raise RuntimeError("下载文件无法读取：" + safe_message(proc.stderr))
    info = json.loads(proc.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video or not video.get("width") or not video.get("height"):
        raise RuntimeError("下载文件中没有可识别的视频画面。")
    return {"width": video["width"], "height": video["height"],
            "fps": video.get("avg_frame_rate", ""),
            "has_audio": any(s.get("codec_type") == "audio" for s in info["streams"]),
            "duration": float(info.get("format", {}).get("duration", 0))}


def download(urls, out_dir, cookie="", log=None, progress_cb=None, script_dir="", proxy=""):
    """Download on this machine and return (verified successes, requested URLs)."""
    log = log or (lambda *_: None)
    urls = [u.strip() for u in urls if u and u.strip()]
    if not urls:
        raise ValueError("请至少输入一个视频链接。")
    missing = [name for name in ("yt-dlp", "ffmpeg", "ffprobe") if not autoinstall.find(name)]
    if missing:
        raise RuntimeError("缺少 " + ", ".join(missing) + "，请点击「安装 / 更新下载工具」。")
    _validate_proxy(proxy)
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    total, ok = len(urls), 0
    for idx, url in enumerate(urls, 1):
        if progress_cb:
            progress_cb(0)
        platform = detect_platform(url)
        log(f"\n[{idx}/{total}] {safe_message(url)}")
        try:
            _validate_url(url)
            cpath = validate_cookie(cookie, platform)
            if platform == "youtube" and not autoinstall.find_js_runtime():
                raise RuntimeError("YouTube 下载需要 Node.js 22+ 或 Deno 2.3+，请点击「安装 / 更新下载工具」。")
            log("使用所选 Cookie（仅供本机下载）" if cpath else "未选择 Cookie，尝试公开访问；需要登录时请重新导出并选择文件。")
            result = _run(build_args(url, out_dir, platform, cpath, True, proxy), progress_cb, log)
            if result.returncode:
                log("✗ " + failure_hint(result.messages))
                continue
            if not result.files:
                raise RuntimeError("下载器没有返回完成文件，不能确认下载成功。")
            for path in dict.fromkeys(result.files):
                path = os.path.abspath(path)
                if os.path.commonpath([path, out_dir]) != out_dir or not os.path.isfile(path):
                    raise RuntimeError("下载结果不在所选目录中，或文件不存在。")
                info = inspect_media(path)
                log(f"✓ 已核验 {info['width']}×{info['height']}，{info['duration']:.1f} 秒，"
                    + ("含音轨" if info['has_audio'] else "无音轨") + f"：{path}")
            ok += 1
            if progress_cb:
                progress_cb(1)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            log("✗ " + safe_message(str(exc)))
    log(f"\n下载完成：成功 {ok}/{total}。")
    return ok, total
