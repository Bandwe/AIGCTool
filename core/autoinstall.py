# -*- coding: utf-8 -*-
"""
自动下载 ffmpeg / yt-dlp 到应用工具目录（Mac 使用用户 Application Support）。

逻辑：
1. 先查应用工具目录。
2. 再查 PATH，Mac 也检查标准 Homebrew 路径。
3. 都没有 → 提供下载（由 UI 层触发，这里只做下载逻辑）。

下载源：
  ffmpeg  Win: BtbN/FFmpeg-Builds (GitHub)
          Mac: Martin Riedl 原生 9.0.2 发行包，固定 SHA-256
  yt-dlp  Win: yt-dlp.exe (GitHub releases)
          Mac: yt-dlp_macos (GitHub releases)
"""

import os
import sys
import shutil
import stat
import platform
import zipfile
import io
import urllib.request
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from .version import VERSION

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# 用 GitHub 镜像，兼容全球
_FFMPEG_WIN = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
# Pinned release builds and publisher checksums, not mutable snapshot downloads.
_FFMPEG_MAC_RELEASES = {
    "arm64": ("https://ffmpeg.martin-riedl.de/download/macos/arm64/1789931890_9.0.2/", {
        "ffmpeg": "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924",
        "ffprobe": "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6"}),
    "x86_64": ("https://ffmpeg.martin-riedl.de/download/macos/amd64/1789931006_9.0.2/", {
        "ffmpeg": "7c6b4125b191cbf773832dc51f424cf2b6bb7da43007d1e066f95909e47cacd4",
        "ffprobe": "2322438ed2f6319a691291b247d09c69dcaa3a982460d1f269a7e1af335cfdfd"}),
}
_YTDLP_WIN = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
_YTDLP_MAC = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"


def _app_dir():
    """应用根目录：打包后是 exe 所在目录，开发时是 main.py 所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bin_dir():
    """应用本地 bin/ 目录路径。"""
    if IS_MAC and getattr(sys, "frozen", False):
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "AIGCTool", "bin")
    return os.path.join(_app_dir(), "bin")


def _ensure_bin():
    d = bin_dir()
    os.makedirs(d, exist_ok=True)
    return d


def _exe(name):
    return name + ".exe" if IS_WIN else name


def find(name):
    """查找可执行文件：先 bin/，再 PATH。返回完整路径或 None。"""
    local = os.path.join(bin_dir(), _exe(name))
    if os.path.isfile(local):
        return local
    found = shutil.which(name)
    if not found and IS_MAC:
        for directory in ("/opt/homebrew/bin", "/usr/local/bin"):
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return found


def _download(url, dest, progress_cb=None):
    """下载文件到 dest。progress_cb(downloaded_bytes, total_bytes)。"""
    req = urllib.request.Request(url, headers={"User-Agent": "AIGCTool/" + VERSION})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)
    return dest


def _make_executable(path):
    if not IS_WIN:
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def download_ffmpeg(progress_cb=None):
    """下载 ffmpeg + ffprobe 到 bin/。返回 (ffmpeg_path, ffprobe_path)。"""
    d = _ensure_bin()

    if IS_WIN:
        tmp = os.path.join(d, "_ffmpeg.zip")
        _download(_FFMPEG_WIN, tmp, progress_cb)
        with zipfile.ZipFile(tmp) as zf:
            for member in zf.namelist():
                base = os.path.basename(member)
                if base in ("ffmpeg.exe", "ffprobe.exe"):
                    target = os.path.join(d, base)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        os.remove(tmp)
    elif IS_MAC:
        _download_mac_ffmpeg(d, progress_cb)
    else:
        raise RuntimeError(f"不支持的平台：{sys.platform}。请手动安装 ffmpeg。")

    ff = os.path.join(d, _exe("ffmpeg"))
    fp = os.path.join(d, _exe("ffprobe"))
    if not os.path.isfile(ff) or not os.path.isfile(fp):
        raise RuntimeError("ffmpeg / ffprobe 下载后未找到，请手动安装。")
    return ff, fp


def _download_mac_ffmpeg(directory, progress_cb=None):
    release = _FFMPEG_MAC_RELEASES.get(platform.machine().lower())
    if release is None:
        raise RuntimeError("不支持的 Mac 架构，请安装原生 FFmpeg / ffprobe。")
    base, checksums = release
    with tempfile.TemporaryDirectory(prefix="ffmpeg-install-", dir=directory) as temporary:
        for name in ("ffmpeg", "ffprobe"):
            archive = os.path.join(temporary, name + ".zip")
            staged = os.path.join(temporary, name)
            _download(base + name + ".zip", archive, progress_cb)
            _verify_checksum(archive, checksums[name])
            with zipfile.ZipFile(archive) as package:
                members = [member for member in package.infolist()
                           if member.filename == name and not member.is_dir()]
                if len(members) != 1:
                    raise RuntimeError("FFmpeg 发行包结构不符合预期，已停止安装。")
                with package.open(members[0]) as source, open(staged, "wb") as target:
                    shutil.copyfileobj(source, target)
            _make_executable(staged)
            subprocess.run([staged, "-version"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True, timeout=15)
        # Check both downloads before replacing either installed tool.
        for name in ("ffmpeg", "ffprobe"):
            _replace_tool(os.path.join(temporary, name), os.path.join(directory, name))


def download_ytdlp(progress_cb=None):
    """校验官方发行包后更新 yt-dlp，保留原版本供恢复。"""
    d = _ensure_bin()
    target = os.path.join(d, _exe("yt-dlp"))
    if not (IS_WIN or IS_MAC):
        raise RuntimeError(f"不支持的平台：{sys.platform}。请手动安装：pip install yt-dlp")
    name = "yt-dlp.exe" if IS_WIN else "yt-dlp_macos"
    release = json.loads(_read_url("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"))
    assets = {item["name"]: item for item in release["assets"]}
    asset = assets[name]
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:"):
        expected = digest.split(":", 1)[1]
    else:
        expected = _checksum(_read_url(assets["SHA2-256SUMS"]["browser_download_url"]), name)
    if os.path.isfile(target) and _sha256(target) == expected.lower():
        return target
    with tempfile.TemporaryDirectory(prefix="ytdlp-update-", dir=d) as temp:
        staged = os.path.join(temp, name)
        _download(asset["browser_download_url"], staged, progress_cb)
        _verify_checksum(staged, expected)
        _make_executable(staged)
        _replace_tool(staged, target)
    return target


def _read_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AIGCTool/" + VERSION})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum(text, name):
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            if re.fullmatch(r"[a-fA-F0-9]{64}", parts[0]):
                return parts[0].lower()
    raise RuntimeError(f"官方校验列表中没有 {name}，已停止安装。")


def _verify_checksum(path, expected):
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected) or _sha256(path) != expected.lower():
        raise RuntimeError("下载文件的 SHA-256 校验失败，原有工具未被替换。")


def _replace_tool(staged, target):
    if os.path.isfile(target):
        shutil.copy2(target, target + ".previous")
    os.replace(staged, target)


def tool_version(path):
    try:
        result = subprocess.run(
            [path, "--version"], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=5,
            creationflags=0x08000000 if IS_WIN else 0,
        )
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        pass
    return ""


def find_js_runtime():
    """只返回 yt-dlp 支持的 Deno / Node，跳过 PATH 中过旧的版本。"""
    for name, minimum in (("deno", (2, 3, 0)), ("node", (22, 0, 0))):
        candidates = [os.path.join(bin_dir(), _exe(name)), shutil.which(name)]
        for path in dict.fromkeys(p for p in candidates if p and os.path.isfile(p)):
            match = re.search(r"(\d+)\.(\d+)\.(\d+)", tool_version(path))
            if match and tuple(map(int, match.groups())) >= minimum:
                return name, os.path.abspath(path)
    return None


def _node_release(index, machine=None):
    machine = (machine or platform.machine()).lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if not arch or not (IS_WIN or IS_MAC):
        raise RuntimeError("此平台请手动安装 Node.js 22+ 或 Deno 2.3+。")
    file_key = f"win-{arch}-zip" if IS_WIN else f"osx-{arch}-tar"
    for release in index:
        version = release.get("version", "")
        match = re.fullmatch(r"v(\d+)\.\d+\.\d+", version)
        if match and int(match.group(1)) >= 22 and release.get("lts") and file_key in release.get("files", []):
            platform_name = "win" if IS_WIN else "darwin"
            stem = f"node-{version}-{platform_name}-{arch}"
            return version, stem, ".zip" if IS_WIN else ".tar.gz"
    raise RuntimeError("未找到适用的官方 Node.js LTS 发行包。")


def download_node(progress_cb=None):
    """从 Node.js 官方安装便携 LTS 运行时，不改系统 PATH。"""
    d = _ensure_bin()
    version, stem, suffix = _node_release(json.loads(_read_url("https://nodejs.org/dist/index.json")))
    base = f"https://nodejs.org/dist/{version}/"
    filename = stem + suffix
    expected = _checksum(_read_url(base + "SHASUMS256.txt"), filename)
    target = os.path.join(d, _exe("node"))
    with tempfile.TemporaryDirectory(prefix="node-install-", dir=d) as temp:
        archive = os.path.join(temp, filename)
        staged = os.path.join(temp, _exe("node"))
        _download(base + filename, archive, progress_cb)
        _verify_checksum(archive, expected)
        # Only copy the known executable; archive paths are never extracted.
        if IS_WIN:
            with zipfile.ZipFile(archive) as package:
                with package.open(stem + "/node.exe") as src, open(staged, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        else:
            with tarfile.open(archive, "r:gz") as package:
                member = package.getmember(stem + "/bin/node")
                if not member.isfile():
                    raise RuntimeError("Node.js 发行包中的运行时不是普通文件。")
                with package.extractfile(member) as src, open(staged, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            _make_executable(staged)
        if tool_version(staged) != version:
            raise RuntimeError("Node.js 运行检查失败，原有工具未被替换。")
        _replace_tool(staged, target)
    return target
