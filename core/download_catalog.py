"""Read available formats without downloading media, then pin a user's choice."""

import math
import re
import tempfile
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, urlsplit

from . import autoinstall, downloader
from .download_support import DownloadCancelled, DownloadOptions, check_cancel, isolated_cookie


FORMAT_ID = re.compile(r"[A-Za-z0-9_.:-]+")
MUSIC_LEVELS = {"standard": "标准", "higher": "较高", "exhigh": "极高",
                "lossless": "无损", "hires": "Hi-Res", "jyeffect": "高清臻音",
                "jymaster": "超清母带", "sky": "沉浸环绕声"}


def normalize_music_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or parsed.username
            or parsed.port not in (None, 80, 443)
            or (parsed.hostname or "").lower() not in ("music.163.com", "y.music.163.com")):
        raise ValueError("不是有效的网易云音乐链接。")
    route = urlsplit(parsed.fragment) if parsed.fragment.startswith("/") else parsed
    ids = parse_qs(route.query).get("id", [])
    if route.path.rstrip("/") not in ("/song", "/m/song") or len(ids) != 1 or not re.fullmatch(r"[0-9]{1,20}", ids[0]):
        raise ValueError("网易云目前支持单曲链接（song?id=...），可一次粘贴多首；暂不支持歌单、专辑或电台。")
    return "https://music.163.com/song?id=" + ids[0]


def number(value):
    try:
        result = float(value or 0)
        return result if math.isfinite(result) and result > 0 else 0
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class Quality:
    format_id: str
    label: str
    media_kind: str = "video"
    width: int = 0
    height: int = 0
    filesize: int = 0
    preview: bool = False


@dataclass(frozen=True)
class Resource:
    url: str
    platform: str
    title: str
    duration: float
    choices: tuple

    def options_for(self, choice, base):
        if choice not in self.choices:
            raise ValueError("所选品质不属于此检测结果，请重新检测。")
        if choice.preview:
            raise ValueError("该音质只有试听片段，请使用有完整版权限的 Cookie 后重新检测。")
        # A concrete choice is explicit acceptance, including a source below 720p.
        return replace(base, playlist=False, min_resolution=0, allow_lower=False,
                       format_id=choice.format_id, media_kind=choice.media_kind,
                       expected_duration=self.duration, expected_size=choice.filesize if choice.media_kind == "audio" else 0,
                       expected_width=choice.width, expected_height=choice.height)


def qualities(info, platform):
    formats = [f for f in info.get("formats", [])
               if FORMAT_ID.fullmatch(str(f.get("format_id", ""))) and not f.get("has_drm")]
    audio = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]
    audio.sort(key=lambda f: (number(f.get("abr") or f.get("tbr")), number(f.get("asr"))), reverse=True)
    result = []
    if platform == "netease":
        duration = number(info.get("duration"))
        if not duration:
            raise RuntimeError("未取得歌曲完整时长，无法判断是否为试听，请更新下载工具后重试。")
        for f in audio:
            rate, size = number(f.get("abr") or f.get("tbr")), int(number(f.get("filesize")))
            estimate = size / (rate * 125) if size and rate else 0
            preview = bool(estimate and estimate < duration - max(3, duration * .1))
            level = MUSIC_LEVELS.get(f["format_id"], f["format_id"])
            label = f"{level} | {str(f.get('ext', '')).upper()} | {rate:g} kbps"
            if size:
                label += f" | {size / 1048576:.1f} MiB"
            if preview:
                label += f" | 仅试听约 {estimate:.0f} 秒"
            result.append(Quality(f["format_id"], label, "audio", filesize=size, preview=preview))
    else:
        videos = [f for f in formats if f.get("vcodec") != "none" and f.get("ext") not in ("mhtml", "jpg", "png", "webp")]
        videos.sort(key=lambda f: (min(number(f.get("width")), number(f.get("height"))),
                                   number(f.get("fps")), number(f.get("tbr"))), reverse=True)
        for f in videos:
            selector = f["format_id"]
            if f.get("acodec") == "none" and audio:
                selector += "+" + audio[0]["format_id"]
            width, height = int(number(f.get("width"))), int(number(f.get("height")))
            resolution = f"{width}x{height}" if width and height else "分辨率待核验"
            fps = f"{number(f.get('fps')):g} fps" if number(f.get("fps")) else "帧率未知"
            label = f"{resolution} | {fps} | {f.get('ext', '')} | {f.get('vcodec') or '编码待核验'} [{selector}]"
            if f.get("acodec") == "none" and not audio:
                label += " | 无音轨"
            result.append(Quality(selector, label, width=width, height=height))
    return tuple(result)


def probe(urls, cookie="", options=None, proxy="", log=None, cancel=None):
    """Return per-entry choices. Signed URLs and cookies stay inside the process."""
    options = options or DownloadOptions()
    options.validate(proxy)
    downloader._validate_proxy(proxy)
    sink = log or (lambda *_: None)
    log = lambda value: sink(downloader.safe_message(value))
    resources, seen = [], set()
    for url in urls:
        check_cancel(cancel)
        try:
            downloader._validate_url(url)
            platform = downloader.detect_platform(url)
            if platform == "netease":
                url = normalize_music_url(url)
            cpath = downloader.validate_cookie(cookie, platform)
            log("检测：" + url)
            if platform == "douyin":
                from . import douyin
                if options.playlist:
                    raise ValueError("抖音暂不支持合集，请选择单条范围。")
                with douyin.session_for(options.network, proxy) as session:
                    video_id = douyin.resolve_id(url, session, cancel)
                detail = douyin.fetch_detail(video_id, cpath, options, proxy, cancel)
                choices = tuple(Quality(item["id"], item["label"], width=item["width"], height=item["height"])
                                for item in douyin.available_qualities(detail))
                records = [Resource(f"https://www.douyin.com/video/{video_id}", platform,
                                    detail.get("desc") or video_id,
                                    number(detail["video"].get("duration")) / 1000, choices)]
            else:
                tool = autoinstall.find("yt-dlp")
                if not tool:
                    raise RuntimeError("缺少 yt-dlp，请先安装 / 更新下载工具。")
                args = [tool, "--ignore-config", "--no-cache-dir", "--no-warnings", "--encoding", "utf-8",
                        "--simulate", "--skip-download", "--socket-timeout", "20", "--retries", "2",
                        "--yes-playlist" if options.playlist and platform != "netease" else "--no-playlist",
                        "--print", "video:" + downloader._INFO_MARKER
                        + "%(.{id,title,duration,webpage_url,formats})j"]
                if options.network == "direct":
                    args += ["--proxy", ""]
                elif proxy:
                    args += ["--proxy", proxy]
                if platform == "youtube":
                    runtime = autoinstall.find_js_runtime()
                    if not runtime:
                        raise RuntimeError("YouTube 需要 JavaScript 运行环境，请先安装 / 更新下载工具。")
                    args += ["--js-runtimes", f"{runtime[0]}:{runtime[1]}"]
                with tempfile.TemporaryDirectory(prefix="aigctool-probe-") as stage:
                    with isolated_cookie(cpath, platform, stage) as temporary:
                        command = args + (["--cookies", temporary] if temporary else []) + ["--", url]
                        result = downloader._run(command, log=log, cancel=cancel)
                if result.returncode:
                    log("部分或全部检测失败：" + downloader.failure_hint(result.messages))
                records = []
                for info in result.metadata:
                    source = info.get("webpage_url") or url
                    downloader._validate_url(source)
                    if downloader.detect_platform(source) != platform:
                        raise RuntimeError("检测返回了不同平台的链接，已拒绝。")
                    if platform == "netease":
                        source = normalize_music_url(source)
                    duration = number(info.get("duration")) or max(
                        (number(f.get("duration")) for f in info.get("formats", [])), default=0)
                    records.append(Resource(source, platform, str(info.get("title") or info.get("id")),
                                            duration, qualities(info, platform)))
            for resource in records:
                if not resource.choices:
                    log("没有可选品质：" + resource.title)
                elif resource.url not in seen:
                    seen.add(resource.url)
                    resources.append(resource)
                    log(f"已检测 {resource.title}：{len(resource.choices)} 种品质，等待选择。")
        except DownloadCancelled:
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            log("检测失败：" + str(exc))
    return resources
