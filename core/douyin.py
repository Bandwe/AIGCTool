"""Local Douyin single-video adapter. Credentials never go to media CDNs."""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import requests

from .download_support import check_cancel, load_cookies, write_json, inspect_staged_media
from .vendor.douyin_websign import pick_uifid, sign


USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
API = "https://www.douyin.com/aweme/v1/web/aweme/detail/"


def session_for(network, proxy):
    session = requests.Session()
    session.trust_env = network == "auto"
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    if network == "custom" or (network == "auto" and proxy):
        session.proxies.update(http=proxy, https=proxy)
    return session


def _douyin_host(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return (parsed.scheme in ("http", "https") and not parsed.username
            and parsed.port in (None, 80, 443)
            and any(host == d or host.endswith("." + d) for d in ("douyin.com", "iesdouyin.com")))


def resolve_id(url, session, cancel=None):
    for _ in range(6):
        check_cancel(cancel)
        if not _douyin_host(url):
            raise ValueError("抖音分享链接跳转到了非抖音域名，已停止解析。")
        parsed = urlsplit(url)
        match = re.search(r"/(?:video|share/video)/(\d{10,25})(?:/|$)", parsed.path)
        if match:
            return match.group(1)
        modal = parse_qs(parsed.query).get("modal_id", [""])[0]
        if re.fullmatch(r"\d{10,25}", modal):
            return modal
        with session.get(url, timeout=(10, 20), stream=True, allow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            raise RuntimeError("无法解析抖音分享链接；请在浏览器打开后复制 /video/ 视频地址。")
    raise RuntimeError("抖音分享链接跳转次数过多。")


def fetch_detail(video_id, cookie, options, proxy="", cancel=None):
    check_cancel(cancel)
    jar = load_cookies(cookie, "douyin")
    cookies = {c.name: c.value for c in jar if not c.is_expired()}
    uifid = pick_uifid(cookies)
    if not uifid:
        raise ValueError("抖音需要当前浏览器导出的 Cookie（缺少有效 UIFID）；请播放视频后重新导出。")
    pairs = [("device_platform", "webapp"), ("aid", "6383"), ("channel", "channel_pc_web"),
             ("pc_client_type", "1"), ("version_code", "190500"), ("version_name", "19.5.0"),
             ("cookie_enabled", "true"), ("aweme_id", video_id)]
    fingerprint = cookies.get("s_v_web_id")
    if fingerprint:
        pairs.extend((("verifyFp", fingerprint), ("fp", fingerprint)))
    query, _, headers = sign(pairs, uifid)
    headers.update(Referer=f"https://www.douyin.com/video/{video_id}", Origin="https://www.douyin.com")
    with session_for(options.network, proxy) as session:
        session.cookies.update(jar)
        # Redirects are forbidden here: this request carries account credentials.
        with session.get(API + "?" + query, headers=headers, timeout=(10, 25), allow_redirects=False) as response:
            if response.status_code != 200:
                raise RuntimeError(f"抖音解析返回 HTTP {response.status_code}；请检查登录状态和网络。")
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("抖音没有返回视频数据，可能需要重新验证登录。") from exc
    detail = data.get("aweme_detail") or {}
    if data.get("status_code") != 0 or str(detail.get("aweme_id")) != video_id:
        raise RuntimeError("抖音返回的视频编号不匹配或视频不可访问，已停止下载。")
    if not detail.get("video"):
        raise RuntimeError("该抖音链接不是可下载的视频作品；暂不支持图集、直播和私密内容。")
    return detail


def media_candidates(detail):
    video = detail["video"]
    original = (video.get("play_addr") or {}).get("uri")
    result = []
    if original:
        result.append(("original", "https://www.douyin.com/aweme/v1/play/?" +
                       urlencode({"video_id": original, "ratio": "default"})))
    rates = sorted(video.get("bit_rate") or [], key=lambda item: (
        min((item.get("play_addr") or {}).get("width") or 0,
            (item.get("play_addr") or {}).get("height") or 0), item.get("bit_rate") or 0), reverse=True)
    for index, rate in enumerate(rates[:3]):
        for mirror, url in enumerate((rate.get("play_addr") or {}).get("url_list", [])[:2]):
            result.append((f"rate-{index}-{mirror}", url))
    for index, url in enumerate((video.get("play_addr") or {}).get("url_list", [])[:2]):
        result.append((f"play-{index}", url))
    # download_addr can contain watermarks and a different duration; don't silently substitute it.
    seen = set()
    return [(name, url) for name, url in result if not (url in seen or seen.add(url))]


def _transfer(session, url, part, cancel=None, progress=None, log=None):
    """Resume only a validated HTTP range of the same entity; never append a 200."""
    part = Path(part)
    meta_path = Path(str(part) + ".json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    offset = part.stat().st_size if part.exists() else 0
    if meta.get("complete") and offset and offset == meta.get("total"):
        return
    validator = meta.get("validator")
    headers = {"Referer": "https://www.douyin.com/"}
    if offset and validator:
        headers.update(Range=f"bytes={offset}-", **{"If-Range": validator})
    else:
        offset = 0
    check_cancel(cancel)
    with session.get(url, headers=headers, stream=True, timeout=(10, 20)) as response:
        response.raise_for_status()
        if response.status_code == 206:
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
            current_validator = response.headers.get("ETag") or response.headers.get("Last-Modified")
            if (not match or int(match[1]) != offset or int(match[2]) < offset
                    or int(match[2]) + 1 != int(match[3])
                    or (offset and current_validator != validator)
                    or (offset and meta.get("total") != int(match[3]))):
                raise RuntimeError("续传响应不匹配，未追加数据；删除该任务的 .part 暂存文件后重试。")
            total = int(match[3])
        elif response.status_code == 200:
            offset = 0
            total = int(response.headers.get("Content-Length", 0))
        else:
            raise RuntimeError(f"视频服务器返回不支持的状态 {response.status_code}。")
        validator = response.headers.get("ETag") or response.headers.get("Last-Modified")
        if validator and validator.startswith("W/"):
            validator = None
        done, started, last_log = offset, time.monotonic(), 0
        with part.open("ab" if offset else "wb") as output:
            # Truncate a replaced entity before publishing its new validator.
            # A crash must never associate old bytes with the new entity's ETag.
            write_json(meta_path, {"validator": validator, "total": total, "complete": False})
            for chunk in response.iter_content(256 * 1024):
                check_cancel(cancel)
                output.write(chunk)
                done += len(chunk)
                elapsed = max(time.monotonic() - started, 0.001)
                if progress and total:
                    progress(min(done / total, 0.99))
                if log and elapsed - last_log >= 3:
                    speed = (done - offset) / elapsed
                    eta = f"，剩余约 {(total - done) / speed:.0f} 秒" if total and speed else ""
                    log(f"下载 {done / 1048576:.1f} MiB，{speed / 1048576:.2f} MiB/s{eta}")
                    last_log = elapsed
            output.flush()
            os.fsync(output.fileno())
        if not done or (total and done != total):
            raise RuntimeError("下载长度不完整；已保留暂存文件供重试。")
        write_json(meta_path, {"validator": validator, "total": done, "complete": True})


def download_video(url, directory, cookie, options, probe, proxy="", cancel=None, progress=None, log=None):
    from .download_support import DownloadCancelled, verify_policy
    log = log or (lambda *_: None)
    try:
        with session_for(options.network, proxy) as session:
            video_id = resolve_id(url, session, cancel)
        detail = fetch_detail(video_id, cookie, options, proxy, cancel)
        title = re.split(r"\s+#", detail.get("desc") or video_id)[0]
        title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)[:80].strip(" .") or video_id
        expected = float(detail["video"].get("duration") or 0) / 1000
        errors = []
        for route, media_url in media_candidates(detail):
            check_cancel(cancel)
            folder = Path(directory) / video_id / route
            folder.mkdir(parents=True, exist_ok=True)
            part = folder / f"{title} [{video_id}].mp4.part"
            complete = part.with_suffix("")
            try:
                log(f"抖音 {video_id}：读取 {route} 视频流，实际画质以下载后核验为准。")
                if not complete.exists():
                    # A new media session has no account cookies, even after redirects.
                    with session_for(options.network, proxy) as session:
                        _transfer(session, media_url, part, cancel, progress, log)
                    part.rename(complete)
                info = inspect_staged_media(str(complete), folder, probe)
                verify_policy(info, options, expected)
                return str(complete), f"https://www.douyin.com/video/{video_id}", info
            except DownloadCancelled:
                raise
            except (requests.RequestException, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                # Request exceptions can include signed URLs. Only expose local policy messages.
                message = type(exc).__name__ if isinstance(exc, requests.RequestException) else str(exc)
                errors.append(message)
                log("该视频流未完成：" + message)
        raise RuntimeError("抖音没有取得符合要求的视频：" + (errors[-1] if errors else "没有可用视频流。"))
    except requests.RequestException as exc:
        raise RuntimeError("抖音网络请求失败（" + type(exc).__name__ + "），请检查网络模式和代理。") from None
