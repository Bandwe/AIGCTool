"""Shared download policy, credentials and verified-file publication."""

import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DOMAINS = {"youtube": "youtube.com", "bilibili": "bilibili.com",
           "douyin": "douyin.com", "xiaohongshu": "xiaohongshu.com"}


class DownloadCancelled(RuntimeError):
    pass


def check_cancel(event):
    if event is not None and event.is_set():
        raise DownloadCancelled("任务已取消；未完成文件保留，可用相同设置重新开始。")


@dataclass(frozen=True)
class DownloadOptions:
    min_resolution: int = 720
    allow_lower: bool = False
    playlist: bool = False
    network: str = "auto"

    def validate(self, proxy=""):
        if self.min_resolution not in (0, 360, 480, 540, 720, 1080, 1440, 2160):
            raise ValueError("画质下限无效。")
        if self.network not in ("auto", "direct", "custom"):
            raise ValueError("网络模式无效。")
        if self.network == "custom" and not proxy:
            raise ValueError("自定义代理模式需要填写代理地址。")


def load_cookies(path, platform):
    jar = MozillaCookieJar()
    if not path:
        return jar
    if not os.path.isfile(path):
        raise ValueError("所选 Cookie 文件不存在，请重新选择；不会自动换用其它文件。")
    source = MozillaCookieJar(path)
    try:
        source.load(ignore_discard=True, ignore_expires=True)
    except (OSError, ValueError) as exc:
        raise ValueError("Cookie 文件格式无法读取，请重新导出 Netscape 格式的 cookies.txt。") from exc
    domain = DOMAINS.get(platform)
    if not domain:
        raise ValueError("未知平台不接受 Cookie，避免把登录数据发给错误的网站。")
    for cookie in source:
        host = cookie.domain.lstrip(".").lower()
        if host == domain or host.endswith("." + domain):
            jar.set_cookie(cookie)
    if not list(jar):
        raise ValueError("Cookie 文件中没有该平台的数据，请选择对应网站导出的文件。")
    return jar


@contextmanager
def isolated_cookie(path, platform, directory):
    """yt-dlp may rewrite its cookie jar; never give it the user's original."""
    if not path:
        yield ""
        return
    jar = load_cookies(path, platform)
    with tempfile.TemporaryDirectory(prefix="credentials-", dir=directory) as tmp:
        target = os.path.join(tmp, "cookies.txt")
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        jar.save(target, ignore_discard=True, ignore_expires=True)
        yield target


def canonical_source(url):
    parsed = urlsplit(url)
    # Only stable public identifiers belong in receipts, never signed parameters.
    params = [(k, v) for k, v in parse_qsl(parsed.query)
              if k in ("v", "p", "list") and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", v)]
    host = parsed.hostname or ""
    if ":" in host:
        host = "[" + host + "]"
    if parsed.port:
        host += f":{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, urlencode(params), ""))


def file_hash(path, cancel=None):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            check_cancel(cancel)
            digest.update(chunk)
    return digest.hexdigest()


def verify_policy(info, options, expected_duration=0):
    width, height = int(info["width"]), int(info["height"])
    duration = float(info["duration"])
    if min(width, height) <= 0 or not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("视频尺寸或时长无效，不能确认下载成功。")
    if expected_duration and abs(duration - expected_duration) > max(2, expected_duration * 0.01):
        raise RuntimeError("视频实际时长与来源不一致，文件保留在暂存目录，未交付。")
    lower = min(width, height) < options.min_resolution
    if lower and not options.allow_lower:
        raise RuntimeError(f"实际分辨率 {width}×{height} 低于 {options.min_resolution}p；"
                           "文件保留在 .aigctool 暂存目录。接受此画质后勾选允许低于下限，再次开始即可。")
    return lower


def inspect_staged_media(path, stage, probe):
    """Keep unreadable bytes as evidence without poisoning the next retry."""
    try:
        return probe(path)
    except Exception:
        source, root = Path(path).resolve(), Path(stage).resolve()
        if source.is_file() and source.is_relative_to(root):
            index = 1
            target = source.with_name(source.name + f".unverified-{index}")
            while target.exists():
                index += 1
                target = source.with_name(source.name + f".unverified-{index}")
            source.rename(target)
        raise


def write_json(path, payload):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish(path, out_dir, source, platform, info, options, cancel=None, expected_duration=0, requested_source=None):
    lower = verify_policy(info, options, expected_duration)
    path, out_dir = Path(path).resolve(), Path(out_dir).resolve()
    if not path.is_relative_to(out_dir) or not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("下载结果不在所选目录中，或文件为空。")
    digest = file_hash(path, cancel)
    target = out_dir / path.name
    suffix = 1
    while target.exists() and target != path:
        if file_hash(target, cancel) == digest:
            break
        target = out_dir / f"{path.stem} ({suffix}){path.suffix}"
        suffix += 1
    check_cancel(cancel)
    if not target.exists():
        # Same-volume rename publishes only a fully downloaded, verified file.
        path.rename(target)
    receipt = {
        "schema": 1, "status": "verified", "source": canonical_source(source),
        "scope": "playlist" if options.playlist else "single",
        "requested_source": canonical_source(requested_source or source),
        "platform": platform, "file": target.name, "bytes": target.stat().st_size,
        "sha256": digest, "media": info,
        "quality": {"minimum_short_edge": options.min_resolution,
                    "below_minimum": lower, "lower_explicitly_allowed": options.allow_lower},
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(str(target) + ".receipt.json", receipt)
    return str(target)


def reuse_completed(out_dir, source, options, probe, cancel=None):
    """A receipt is a hint, not proof: recheck path, bytes, hash and media."""
    if options.playlist:
        return None
    out_dir = Path(out_dir).resolve()
    source = canonical_source(source)
    for receipt in out_dir.glob("*.receipt.json"):
        check_cancel(cancel)
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
            if data.get("schema") != 1 or data.get("status") != "verified":
                continue
            if data.get("scope", "single") != "single":
                continue
            if source not in (data.get("source"), data.get("requested_source")):
                continue
            path = (out_dir / data["file"]).resolve()
            if path.parent != out_dir or not path.is_file() or path.stat().st_size != data["bytes"]:
                continue
            if file_hash(path, cancel) != data["sha256"]:
                continue
            info = probe(str(path))
            verify_policy(info, options)
            return str(path), info
        except DownloadCancelled:
            raise
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            continue
    return None
