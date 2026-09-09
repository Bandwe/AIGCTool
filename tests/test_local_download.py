import hashlib
import io
import json
import os
import sys
import zipfile

import pytest

from core import autoinstall, downloader


def cookie_file(tmp_path):
    path = tmp_path / "my youtube cookies (3).txt"
    path.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tTEST\tlocal-test\n", encoding="utf-8")
    return path


def ready(monkeypatch, tmp_path):
    monkeypatch.setattr(autoinstall, "find", lambda name: str(tmp_path / name))
    monkeypatch.setattr(autoinstall, "find_js_runtime", lambda: ("node", str(tmp_path / "node executable")))


def test_platform_is_matched_by_hostname():
    assert downloader.detect_platform("https://youtube.com.attacker.example/watch?v=x") == "other"
    assert downloader.detect_platform("https://example.com/?next=youtube.com") == "other"
    assert downloader.detect_platform("https://m.youtube.com/watch?v=x") == "youtube"


def test_new_cookie_with_spaces_is_used_as_one_argument(monkeypatch, tmp_path):
    ready(monkeypatch, tmp_path)
    cookie = downloader.validate_cookie(str(cookie_file(tmp_path)), "youtube")
    args = downloader.build_args("https://youtu.be/example", str(tmp_path), "youtube", cookie, proxy="http://127.0.0.1:7890")
    assert args[args.index("--cookies") + 1] == cookie
    assert args[args.index("--js-runtimes") + 1] == "node:" + str(tmp_path / "node executable")
    assert args[args.index("--format-sort") + 1] == "res,fps"
    assert args[-2:] == ["--", "https://youtu.be/example"]
    assert "--no-playlist" in args


def test_cookie_format_does_not_imply_login_validity(tmp_path):
    cookie = cookie_file(tmp_path)
    cookie.write_text(cookie.read_text().replace("2147483647", "1"), encoding="utf-8")
    assert downloader.validate_cookie(str(cookie), "youtube") == str(cookie)
    with pytest.raises(ValueError, match="该平台"):
        downloader.validate_cookie(str(cookie), "bilibili")


def test_explicit_missing_cookie_never_falls_back(monkeypatch, tmp_path):
    ready(monkeypatch, tmp_path)
    logs = []
    monkeypatch.setattr(downloader, "_run", lambda *args: pytest.fail("No download should start"))
    assert downloader.download(["https://youtu.be/example"], str(tmp_path), cookie=str(tmp_path / "missing.txt"), log=logs.append) == (0, 1)
    assert any("不存在" in line for line in logs)


def test_malformed_cookie_does_not_echo_contents(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text("not-a-cookie-file secret-value", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        downloader.validate_cookie(str(path), "youtube")
    assert "secret-value" not in str(error.value)


def test_empty_cookie_does_not_pick_up_old_files(monkeypatch, tmp_path):
    ready(monkeypatch, tmp_path)
    cookie_file(tmp_path)
    received = []
    monkeypatch.setattr(downloader, "_run", lambda args, *rest: received.append(args) or downloader.RunResult(1))
    downloader.download(["https://youtu.be/example"], str(tmp_path))
    assert "--cookies" not in received[0]


def test_invalid_inputs_cannot_become_options(tmp_path):
    with pytest.raises(ValueError):
        downloader.build_args("--exec=bad", str(tmp_path), "other")
    with pytest.raises(ValueError):
        downloader.build_args("https://youtu.be/example", str(tmp_path), "youtube", proxy="file:///private")


def test_failed_process_preserves_error_and_never_finishes_progress():
    logs, progress = [], []
    script = "print('[download] 100% of 1MiB'); print('ERROR: Sign in to confirm you are not a bot'); raise SystemExit(1)"
    result = downloader._run([sys.executable, "-u", "-c", script], progress.append, logs.append)
    assert result.returncode == 1
    assert max(progress) < 1
    assert any("not a bot" in line for line in logs)
    assert "重新验证登录" in downloader.failure_hint(result.messages)


def test_signed_links_and_headers_are_redacted():
    result = downloader.safe_message("ERROR: https://user:password@media.example/video?token=secret&expires=123")
    assert "password" not in result and "secret" not in result
    assert "media.example/video" in result
    assert "secret" not in downloader.safe_message("Authorization: Bearer secret")
    assert "secret" not in downloader.safe_message("Cookie: SID=secret")


def test_completed_file_marker_preserves_unicode_and_spaces(tmp_path):
    path = str(tmp_path / "演示 video [id].mp4")
    script = "print(" + repr(downloader._FILE_MARKER + json.dumps(path)) + ")"
    result = downloader._run([sys.executable, "-u", "-c", script])
    assert result.files == [path]


def test_zero_exit_without_a_file_is_not_success(monkeypatch, tmp_path):
    ready(monkeypatch, tmp_path)
    monkeypatch.setattr(downloader, "_run", lambda *args: downloader.RunResult(0))
    progress = []
    assert downloader.download(["https://youtu.be/example"], str(tmp_path), progress_cb=progress.append) == (0, 1)
    assert 1 not in progress


def test_verified_file_is_required_for_success(monkeypatch, tmp_path):
    ready(monkeypatch, tmp_path)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"not actual video")
    monkeypatch.setattr(downloader, "_run", lambda *args: downloader.RunResult(0, [str(path)]))
    monkeypatch.setattr(downloader, "inspect_media", lambda path: (_ for _ in ()).throw(RuntimeError("invalid video")))
    assert downloader.download(["https://youtu.be/example"], str(tmp_path)) == (0, 1)
    monkeypatch.setattr(downloader, "inspect_media", lambda path: {"width": 3840, "height": 2160, "duration": 41, "has_audio": True})
    logs, progress = [], []
    assert downloader.download(["https://youtu.be/example"], str(tmp_path), log=logs.append, progress_cb=progress.append) == (1, 1)
    assert progress[-1] == 1
    assert any("3840×2160" in line for line in logs)


def release_for(payload):
    return {"assets": [{"name": "yt-dlp.exe", "browser_download_url": "https://github.com/yt-dlp/yt-dlp/example", "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}]}


def test_update_checksum_failure_keeps_installed_tool(monkeypatch, tmp_path):
    target = tmp_path / "yt-dlp.exe"
    target.write_bytes(b"working old tool")
    monkeypatch.setattr(autoinstall, "IS_WIN", True)
    monkeypatch.setattr(autoinstall, "IS_MAC", False)
    monkeypatch.setattr(autoinstall, "_ensure_bin", lambda: str(tmp_path))
    monkeypatch.setattr(autoinstall, "_read_url", lambda url: json.dumps(release_for(b"official new tool")))
    def corrupted(url, destination, progress_cb=None):
        with open(destination, "wb") as output:
            output.write(b"incomplete download")
    monkeypatch.setattr(autoinstall, "_download", corrupted)
    with pytest.raises(RuntimeError, match="校验失败"):
        autoinstall.download_ytdlp()
    assert target.read_bytes() == b"working old tool"


def test_verified_update_keeps_previous_version(monkeypatch, tmp_path):
    target = tmp_path / "yt-dlp.exe"
    target.write_bytes(b"working old tool")
    payload = b"official new tool"
    monkeypatch.setattr(autoinstall, "IS_WIN", True)
    monkeypatch.setattr(autoinstall, "IS_MAC", False)
    monkeypatch.setattr(autoinstall, "_ensure_bin", lambda: str(tmp_path))
    monkeypatch.setattr(autoinstall, "_read_url", lambda url: json.dumps(release_for(payload)))
    def correct(url, destination, progress_cb=None):
        with open(destination, "wb") as output:
            output.write(payload)
    monkeypatch.setattr(autoinstall, "_download", correct)
    autoinstall.download_ytdlp()
    assert target.read_bytes() == payload
    assert (tmp_path / "yt-dlp.exe.previous").read_bytes() == b"working old tool"
    monkeypatch.setattr(autoinstall, "_download", lambda *args: pytest.fail("Already current; should not download"))
    autoinstall.download_ytdlp()


def test_runtime_detection_skips_old_node(monkeypatch, tmp_path):
    old = tmp_path / "local" / "node.exe"
    old.parent.mkdir()
    old.write_bytes(b"")
    supported = tmp_path / "supported-node"
    supported.write_bytes(b"")
    monkeypatch.setattr(autoinstall, "bin_dir", lambda: str(old.parent))
    monkeypatch.setattr(autoinstall, "_exe", lambda name: name + ".exe")
    monkeypatch.setattr(autoinstall.shutil, "which", lambda name: str(supported) if name == "node" else None)
    monkeypatch.setattr(autoinstall, "tool_version", lambda path: "v20.0.0" if path == str(old) else "v24.0.0")
    assert autoinstall.find_js_runtime() == ("node", str(supported))


@pytest.mark.parametrize("windows,machine,key,expected", [
    (True, "AMD64", "win-x64-zip", "node-v24.1.0-win-x64"),
    (False, "arm64", "osx-arm64-tar", "node-v24.1.0-darwin-arm64"),
])
def test_node_installer_selects_supported_lts(monkeypatch, windows, machine, key, expected):
    monkeypatch.setattr(autoinstall, "IS_WIN", windows)
    monkeypatch.setattr(autoinstall, "IS_MAC", not windows)
    releases = [{"version": "v26.0.0", "lts": False, "files": [key]},
                {"version": "v24.1.0", "lts": "LTS", "files": [key]}]
    assert autoinstall._node_release(releases, machine)[1] == expected


def test_node_install_copies_only_the_verified_runtime(monkeypatch, tmp_path):
    stem = "node-v24.1.0-win-x64"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(stem + "/node.exe", b"runtime")
        package.writestr("../outside.txt", b"do not extract")
    payload = archive.getvalue()
    monkeypatch.setattr(autoinstall, "IS_WIN", True)
    monkeypatch.setattr(autoinstall, "IS_MAC", False)
    monkeypatch.setattr(autoinstall, "_ensure_bin", lambda: str(tmp_path))
    monkeypatch.setattr(autoinstall, "_node_release", lambda index: ("v24.1.0", stem, ".zip"))
    checksums = hashlib.sha256(payload).hexdigest() + "  " + stem + ".zip"
    monkeypatch.setattr(autoinstall, "_read_url", lambda url: "[]" if url.endswith("index.json") else checksums)
    def download(url, destination, progress_cb=None):
        with open(destination, "wb") as output:
            output.write(payload)
    monkeypatch.setattr(autoinstall, "_download", download)
    monkeypatch.setattr(autoinstall, "tool_version", lambda path: "v24.1.0")
    path = autoinstall.download_node()
    assert open(path, "rb").read() == b"runtime"
    assert not (tmp_path.parent / "outside.txt").exists()