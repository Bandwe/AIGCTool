# -*- coding: utf-8 -*-
"""
视频下载（移植自原 bili-download.ps1 + youtube-download.ps1）。

包装 yt-dlp：按链接自动识别 B站 / YouTube，套用各自参数；
自动查找 cookie 文件；解析 yt-dlp 输出的下载百分比驱动进度条。
"""

import os
import re
import sys
import subprocess

from . import autoinstall
from .ffmpeg_runner import ffmpeg_path

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _ytdlp_path():
    return autoinstall.find("yt-dlp") or "yt-dlp"

# yt-dlp 进度行：[download]  45.2% of ...
_PCT_RE = re.compile(r"\[download\]\s+([\d.]+)%")


def detect_platform(url):
    """根据链接识别平台。"""
    u = (url or "").lower()
    if "bilibili.com" in u or "b23.tv" in u:
        return "bilibili"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return "other"


def _cookie_candidates(platform, explicit, script_dir):
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    host = "www.bilibili.com" if platform == "bilibili" else "www.youtube.com"
    return [
        explicit,
        os.path.join("D:\\download", f"{host}_cookies.txt"),
        os.path.join(script_dir, "cookies.txt") if script_dir else None,
        "cookies.txt",
        os.path.join(downloads, f"{host}_cookies.txt"),
        os.path.join(downloads, "cookies.txt"),
    ]


def find_cookie(platform, explicit="", script_dir=""):
    """按候选顺序查找存在的 cookie 文件，返回路径或 ""。"""
    for cand in _cookie_candidates(platform, explicit, script_dir):
        if cand and os.path.isfile(cand):
            return os.path.abspath(cand)
    return ""


def build_args(url, out_dir, platform, cookie="", has_ffmpeg_flag=True):
    """构建单个链接的 yt-dlp 参数列表（含程序名）。抽出便于单测。"""
    template = os.path.join(out_dir, "%(title)s.%(ext)s")
    ytdlp = _ytdlp_path()
    args = [ytdlp, url, "-o", template]
    if cookie:
        args += ["--cookies", cookie]
    if platform == "youtube":
        args += ["-f", "bv*+ba/b"]
    ff = autoinstall.find("ffmpeg")
    if ff and has_ffmpeg_flag:
        args += ["--ffmpeg-location", os.path.dirname(ff)]
        args += ["--merge-output-format", "mp4"]
    return args


def has_ffmpeg_available():
    return autoinstall.find("ffmpeg") is not None


def download(urls, out_dir, cookie="", log=None, progress_cb=None, script_dir=""):
    """
    依次下载多个链接。log(str) 文本回调；progress_cb(frac) 单条进度 0~1。
    返回 (成功数, 总数)。
    """
    log = log or (lambda *_: None)
    urls = [u.strip() for u in urls if u and u.strip()]
    if not urls:
        raise ValueError("请至少输入一个视频链接。")

    os.makedirs(out_dir, exist_ok=True)
    ff = has_ffmpeg_available()
    if not ff:
        log("⚠ 未找到 ffmpeg：将以原始格式保存，无法合并为 MP4")

    total = len(urls)
    ok = 0
    for idx, url in enumerate(urls, 1):
        platform = detect_platform(url)
        pname = {"bilibili": "B站", "youtube": "YouTube"}.get(platform, "其它")
        cpath = cookie or find_cookie(platform, script_dir=script_dir)

        log(f"\n[{idx}/{total}] {pname}：{url}")
        if platform == "bilibili" and not cpath:
            log("  ⚠ B站未提供 Cookie，可能返回 HTTP 412。请在下方选择 cookies.txt。")
        if cpath:
            log(f"  Cookie: {cpath}")

        args = build_args(url, out_dir, platform, cpath, ff)
        try:
            code = _run(args, progress_cb)
        except FileNotFoundError:
            log("  ✗ 找不到 yt-dlp，请先安装：pip install -U yt-dlp")
            break
        if code == 0:
            ok += 1
            log("  ✓ 完成")
        else:
            log("  ✗ 下载失败：Cookie 过期 / 需大会员 / 网络问题，请检查后重试。")

    log(f"\n下载完成：成功 {ok}/{total}。")
    return ok, total


def _run(args, progress_cb):
    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    for line in proc.stdout:
        m = _PCT_RE.search(line)
        if m and progress_cb:
            try:
                progress_cb(min(float(m.group(1)) / 100.0, 1.0))
            except ValueError:
                pass
    proc.wait()
    if progress_cb:
        progress_cb(1.0)
    return proc.returncode
