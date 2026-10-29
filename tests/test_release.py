import hashlib
import io
import json
import plistlib
import sys
import zipfile
from pathlib import Path

import pytest

from core import autoinstall
from core.version import VERSION
from scripts.verify_release import verify_archive


def test_mac_frozen_tools_live_outside_application(monkeypatch, tmp_path):
    monkeypatch.setattr(autoinstall, "IS_MAC", True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/AIGCTool.app/Contents/MacOS/AIGCTool")
    monkeypatch.setattr(autoinstall.os.path, "expanduser", lambda value: str(tmp_path))
    assert Path(autoinstall.bin_dir()) == tmp_path / "Library/Application Support/AIGCTool/bin"


@pytest.mark.parametrize("machine", ["arm64", "x86_64"])
def test_native_mac_installer_verifies_both_archives_before_replacing(monkeypatch, tmp_path, machine):
    payloads = {}
    for name in ("ffmpeg", "ffprobe"):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(name, b"native executable")
            archive.writestr("../outside", b"must not extract")
        payloads[name] = buffer.getvalue()
        (tmp_path / name).write_bytes(b"old executable")
    checksums = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    monkeypatch.setattr(autoinstall.platform, "machine", lambda: machine)
    monkeypatch.setattr(autoinstall, "_FFMPEG_MAC_RELEASES", {machine: ("https://example.test/", checksums)})
    def download(url, target, progress=None):
        name = Path(url).stem
        Path(target).write_bytes(payloads[name])
    monkeypatch.setattr(autoinstall, "_download", download)
    monkeypatch.setattr(autoinstall, "_make_executable", lambda path: None)
    monkeypatch.setattr(autoinstall.subprocess, "run", lambda *args, **kwargs: None)
    autoinstall._download_mac_ffmpeg(str(tmp_path))
    assert (tmp_path / "ffmpeg").read_bytes() == b"native executable"
    assert (tmp_path / "ffprobe.previous").read_bytes() == b"old executable"
    assert not (tmp_path.parent / "outside").exists()
    checksums["ffprobe"] = "0" * 64
    (tmp_path / "ffmpeg").write_bytes(b"keep working executable")
    with pytest.raises(RuntimeError, match="SHA-256"):
        autoinstall._download_mac_ffmpeg(str(tmp_path))
    assert (tmp_path / "ffmpeg").read_bytes() == b"keep working executable"


def fixture_archive(path, system, architecture, version=VERSION):
    with zipfile.ZipFile(path, "w") as archive:
        if system == "darwin":
            root = "AIGCTool.app/Contents/"
            archive.writestr(root + "MacOS/AIGCTool", b"fixture")
            archive.writestr(root + "Info.plist", plistlib.dumps({"CFBundleShortVersionString": version}))
            root += "Resources/"
        else:
            root = "AIGCTool/"
            archive.writestr(root + "AIGCTool.exe", b"fixture")
        archive.writestr(root + "licenses/douyin-api-LICENSE.txt", "Apache-2.0")
        archive.writestr(root + "release.json", json.dumps({"version": version, "platform": system,
                                                           "architecture": architecture}))


@pytest.mark.parametrize("system,machine,architecture", [("win32", "AMD64", "x64"),
                                                        ("darwin", "arm64", "arm64"),
                                                        ("darwin", "x86_64", "x64")])
def test_release_archive_structure_and_architecture(tmp_path, system, machine, architecture):
    archive = tmp_path / "release.zip"
    fixture_archive(archive, system, machine)
    verify_archive(archive, system, architecture)
    with pytest.raises(ValueError, match="metadata mismatch"):
        verify_archive(archive, system, "wrong")


def test_release_rejects_wrong_version_and_cookie_file(tmp_path):
    archive = tmp_path / "release.zip"
    fixture_archive(archive, "darwin", "arm64", "0.0.0")
    with pytest.raises(ValueError, match="version"):
        verify_archive(archive, "darwin", "arm64")
    fixture_archive(archive, "win32", "AMD64")
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("AIGCTool/cookies.txt", "dummy")
    with pytest.raises(ValueError, match="Cookie"):
        verify_archive(archive, "win32", "x64")
