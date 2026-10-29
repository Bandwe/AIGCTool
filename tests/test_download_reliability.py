import json
import os
import sys
import threading
from pathlib import Path

import pytest

from core import downloader, douyin
from core.download_support import (DownloadCancelled, DownloadOptions, canonical_source,
                                   isolated_cookie, publish, reuse_completed, verify_policy, write_json,
                                   inspect_staged_media)


def test_share_text_extracts_urls_and_deduplicates():
    assert downloader.extract_urls("1.74 分享 https://v.douyin.com/abcd/ 视频\nhttps://v.douyin.com/abcd/") == [
        "https://v.douyin.com/abcd/"]
    assert downloader.extract_urls("--exec bad command") == []


@pytest.mark.parametrize("host,expected", [("v.douyin.com", "douyin"), ("www.iesdouyin.com", "douyin"),
                                           ("xhslink.com", "xiaohongshu"), ("douyin.com.evil.example", "other")])
def test_platform_domains(host, expected):
    assert downloader.detect_platform("https://" + host + "/video/123") == expected


def test_quality_and_scope_are_explicit(tmp_path):
    args = downloader.build_args("https://bilibili.com/video/BVexample", str(tmp_path), "bilibili",
                                 options=DownloadOptions(1080, False, True, "direct"))
    assert "--yes-playlist" in args and "--no-playlist" not in args
    assert args[args.index("--proxy") + 1] == ""
    assert "[height>=?1080][width>=?1080]" in args[args.index("-f") + 1]
    assert "%(playlist_index)" in args[args.index("-o") + 1]
    assert args[args.index("--encoding") + 1] == "utf-8"
    args = downloader.build_args("https://youtube.com/watch?v=x&list=RDx", str(tmp_path), "youtube",
                                 options=DownloadOptions(720, True))
    assert "--no-playlist" in args
    assert args[args.index("-f") + 1] == "bv*+ba/b"


def test_proxy_must_be_explicit_in_custom_mode():
    with pytest.raises(ValueError, match="代理"):
        DownloadOptions(network="custom").validate()


def test_cookie_copy_is_scoped_and_original_unchanged_on_failure(tmp_path):
    original = tmp_path / "original.txt"
    contents = ("# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tlocal-test\n"
                ".unrelated.test\tTRUE\t/\tTRUE\t2147483647\tSECRET\tprivate\n")
    original.write_text(contents, encoding="utf-8")
    with pytest.raises(RuntimeError):
        with isolated_cookie(str(original), "youtube", tmp_path) as temporary:
            assert temporary != str(original)
            assert "unrelated" not in Path(temporary).read_text()
            Path(temporary).write_text("downloader rewrote this", encoding="utf-8")
            raise RuntimeError("failed")
    assert not Path(temporary).exists()
    assert original.read_text(encoding="utf-8") == contents


def test_unknown_domain_never_gets_cookie(tmp_path):
    cookie = tmp_path / "cookies.txt"
    cookie.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tvalue\n")
    with pytest.raises(ValueError, match="未知平台"):
        downloader.validate_cookie(str(cookie), "other")


@pytest.mark.parametrize("width,height", [(960, 540), (540, 960), (1920, 480)])
def test_real_short_edge_not_height_or_label(width, height):
    info = dict(width=width, height=height, duration=30, has_audio=True)
    with pytest.raises(RuntimeError, match="低于 720p"):
        verify_policy(info, DownloadOptions())
    assert verify_policy(info, DownloadOptions(720, True))


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf")])
def test_invalid_duration_is_not_verified(duration):
    with pytest.raises(RuntimeError):
        verify_policy(dict(width=1920, height=1080, duration=duration), DownloadOptions())


def test_mismatched_duration_is_not_verified():
    with pytest.raises(RuntimeError, match="时长"):
        verify_policy(dict(width=1920, height=1080, duration=33.1), DownloadOptions(), 30)


def test_receipt_has_actual_quality_and_no_signed_parameters(tmp_path):
    stage = tmp_path / ".aigctool"
    stage.mkdir()
    video = stage / "video.mp4"
    video.write_bytes(b"fixture media")
    info = dict(width=960, height=540, duration=30, has_audio=True)
    with pytest.raises(RuntimeError):
        publish(video, tmp_path, "https://douyin.com/video/123?token=secret", "douyin", info, DownloadOptions())
    assert video.exists() and not (tmp_path / "video.mp4").exists()
    result = publish(video, tmp_path, "https://douyin.com/video/123?token=secret", "douyin", info, DownloadOptions(720, True))
    receipt = Path(result + ".receipt.json").read_text(encoding="utf-8")
    data = json.loads(receipt)
    assert "secret" not in receipt and "token" not in receipt
    assert data["media"]["width"] == 960 and data["quality"]["below_minimum"]
    assert len(data["sha256"]) == 64 and data["bytes"] == 13


def test_publication_does_not_overwrite_existing_file(tmp_path):
    (tmp_path / "video.mp4").write_bytes(b"user original")
    stage = tmp_path / "stage"
    stage.mkdir()
    path = stage / "video.mp4"
    path.write_bytes(b"new media")
    output = publish(path, tmp_path, "https://youtu.be/id", "youtube",
                     dict(width=1280, height=720, duration=1), DownloadOptions())
    assert Path(output).name == "video (1).mp4"
    assert (tmp_path / "video.mp4").read_bytes() == b"user original"


def test_cancel_silent_subprocess_does_not_wait_for_stdout():
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    timer.start()
    try:
        with pytest.raises(DownloadCancelled):
            downloader._run([sys.executable, "-c", "import time; time.sleep(30)"], cancel=cancel)
    finally:
        timer.join()


class Response:
    def __init__(self, code=200, headers=None, body=b"abcdef", data=None):
        self.status_code, self.headers, self.body, self.data = code, headers or {}, body, data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise douyin.requests.HTTPError("private signed URL")

    def iter_content(self, size):
        yield self.body

    def json(self):
        return self.data


class Session:
    def __init__(self, response):
        self.response, self.calls = response, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def partial(tmp_path):
    part = tmp_path / "media.part"
    part.write_bytes(b"abc")
    write_json(str(part) + ".json", dict(validator='"entity-1"', total=6, complete=False))
    return part


def test_resume_server_ignores_range_restarts_not_appends(tmp_path):
    part = partial(tmp_path)
    session = Session(Response(headers={"Content-Length": "6", "ETag": '"entity-2"'}))
    douyin._transfer(session, "https://cdn.example/video?secret=value", part)
    assert part.read_bytes() == b"abcdef"
    assert session.calls[0][1]["headers"]["Range"] == "bytes=3-"
    assert "secret" not in Path(str(part) + ".json").read_text()
    assert "Cookie" not in session.calls[0][1]["headers"]


def test_valid_resume_appends_only_expected_bytes(tmp_path):
    part = partial(tmp_path)
    session = Session(Response(206, {"Content-Range": "bytes 3-5/6", "ETag": '"entity-1"'}, b"def"))
    douyin._transfer(session, "https://cdn.example/video", part)
    assert part.read_bytes() == b"abcdef"


def test_resume_journal_failure_cannot_pair_old_bytes_with_new_etag(tmp_path, monkeypatch):
    part = partial(tmp_path)
    monkeypatch.setattr(douyin, "write_json", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        douyin._transfer(Session(Response(headers={"Content-Length": "6", "ETag": '"new"'})),
                         "https://cdn.example/video", part)
    assert part.read_bytes() == b""


def test_native_api_uses_scoped_cookie_jar_and_forbids_redirect(tmp_path, monkeypatch):
    cookie = tmp_path / "cookie.txt"
    cookie.write_text("# Netscape HTTP Cookie File\n.douyin.com\tTRUE\t/\tTRUE\t2147483647\tUIFID\tdummy-id\n"
                      ".other.test\tTRUE\t/\tTRUE\t2147483647\tPRIVATE\tother-secret\n")
    video_id = "1234567890123456789"
    class APISession(Session):
        cookies = douyin.requests.cookies.RequestsCookieJar()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    session = APISession(Response(data={"status_code": 0, "aweme_detail": {
        "aweme_id": video_id, "video": {"duration": 1000}}}))
    monkeypatch.setattr(douyin, "session_for", lambda *args: session)
    assert douyin.fetch_detail(video_id, str(cookie), DownloadOptions())["aweme_id"] == video_id
    assert session.calls[0][1]["allow_redirects"] is False
    assert [c.name for c in session.cookies] == ["UIFID"]
    assert session.calls[0][0].startswith(douyin.API + "?")


@pytest.mark.parametrize("headers", [{"Content-Range": "bytes 0-5/6", "ETag": '"entity-1"'},
                                     {"Content-Range": "bytes 3-5/6", "ETag": '"other-entity"'},
                                     {"Content-Range": "bytes 3-6/7", "ETag": '"entity-1"'}])
def test_bad_resume_never_appends(tmp_path, headers):
    part = partial(tmp_path)
    with pytest.raises(RuntimeError, match="续传"):
        douyin._transfer(Session(Response(206, headers)), "https://cdn.example/video", part)
    assert part.read_bytes() == b"abc"


def test_short_response_is_not_complete(tmp_path):
    part = tmp_path / "media.part"
    with pytest.raises(RuntimeError, match="不完整"):
        douyin._transfer(Session(Response(headers={"Content-Length": "100"})), "https://cdn.example/video", part)
    assert not json.loads(Path(str(part) + ".json").read_text())["complete"]


def test_shortlink_cannot_redirect_off_platform():
    session = Session(Response(302, {"Location": "https://evil.example/video/7695986073658250879"}))
    with pytest.raises(ValueError, match="非抖音"):
        douyin.resolve_id("https://v.douyin.com/example/", session)
    assert len(session.calls) == 1


def test_canonical_douyin_link_needs_no_network():
    assert douyin.resolve_id("https://www.douyin.com/video/7695986073658250879", None) == "7695986073658250879"


def test_network_modes_do_not_modify_global_environment():
    before = dict(os.environ)
    with douyin.session_for("direct", "http://ignored:7890") as session:
        assert not session.trust_env and not session.proxies and not session.cookies
    with douyin.session_for("custom", "socks5h://localhost:7890") as session:
        assert not session.trust_env and session.proxies["https"] == "socks5h://localhost:7890"
    assert dict(os.environ) == before


def test_native_api_requires_cookie_before_network():
    with pytest.raises(ValueError, match="UIFID"):
        douyin.fetch_detail("7695986073658250879", "", DownloadOptions())


def test_receipt_source_keeps_public_video_id_not_access_token():
    assert canonical_source("https://youtube.com/watch?v=abc&token=private&list=RDabc#secret") == (
        "https://youtube.com/watch?v=abc&list=RDabc")


def test_completed_cache_rechecks_hash_policy_and_scope(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fixture")
    info = dict(width=960, height=540, duration=30)
    source = "https://www.douyin.com/video/123"
    publish(video, tmp_path, source, "douyin", info, DownloadOptions(720, True))
    assert reuse_completed(tmp_path, source, DownloadOptions(720, True), lambda _: info)
    assert reuse_completed(tmp_path, source, DownloadOptions(), lambda _: info) is None
    video.write_bytes(b"changed")
    assert reuse_completed(tmp_path, source, DownloadOptions(720, True), lambda _: info) is None
    publish(video, tmp_path, source, "douyin", info, DownloadOptions(720, True, True))
    assert reuse_completed(tmp_path, source, DownloadOptions(720, True), lambda _: info) is None


def test_cache_source_keeps_port_identity():
    assert canonical_source("http://localhost:8123/video.mp4") != canonical_source("http://localhost:8124/video.mp4")


def test_unreadable_staged_file_does_not_poison_retry(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    file = stage / "video.mp4"
    file.write_bytes(b"truncated")
    def fail(path):
        raise RuntimeError("unreadable")
    with pytest.raises(RuntimeError):
        inspect_staged_media(str(file), stage, fail)
    assert not file.exists()
    assert (stage / "video.mp4.unverified-1").read_bytes() == b"truncated"
    original = tmp_path / "original.mp4"
    original.write_bytes(b"user original")
    with pytest.raises(RuntimeError):
        inspect_staged_media(str(original), stage, fail)
    assert original.exists()
