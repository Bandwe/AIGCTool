# -*- coding: utf-8 -*-
"""
自动下载 ffmpeg / yt-dlp 到应用本地 bin/ 目录。

逻辑：
1. 先查 PATH，有就直接用。
2. 再查应用旁的 bin/ 目录。
3. 都没有 → 提供下载（由 UI 层触发，这里只做下载逻辑）。

下载源：
  ffmpeg  Win: BtbN/FFmpeg-Builds (GitHub)
          Mac: evermeet.cx 静态编译
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

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# 用 GitHub 镜像，兼容全球
_FFMPEG_WIN = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
_FFMPEG_MAC = "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
_FFPROBE_MAC = "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"
_YTDLP_WIN = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
_YTDLP_MAC = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"


def _app_dir():
    """应用根目录：打包后是 exe 所在目录，开发时是 main.py 所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bin_dir():
    """应用本地 bin/ 目录路径。"""
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
    return found


def _download(url, dest, progress_cb=None):
    """下载文件到 dest。progress_cb(downloaded_bytes, total_bytes)。"""
    req = urllib.request.Request(url, headers={"User-Agent": "AIGCTool/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        data = bytearray()
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            data.extend(chunk)
            if progress_cb:
                progress_cb(len(data), total)
    with open(dest, "wb") as f:
        f.write(data)
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
        tmp_ff = os.path.join(d, "_ffmpeg.zip")
        _download(_FFMPEG_MAC, tmp_ff, progress_cb)
        with zipfile.ZipFile(tmp_ff) as zf:
            zf.extractall(d)
        os.remove(tmp_ff)
        _make_executable(os.path.join(d, "ffmpeg"))

        tmp_fp = os.path.join(d, "_ffprobe.zip")
        _download(_FFPROBE_MAC, tmp_fp, progress_cb)
        with zipfile.ZipFile(tmp_fp) as zf:
            zf.extractall(d)
        os.remove(tmp_fp)
        _make_executable(os.path.join(d, "ffprobe"))
    else:
        raise RuntimeError(f"不支持的平台：{sys.platform}。请手动安装 ffmpeg。")

    ff = os.path.join(d, _exe("ffmpeg"))
    fp = os.path.join(d, _exe("ffprobe"))
    if not os.path.isfile(ff):
        raise RuntimeError("ffmpeg 下载后未找到，请手动安装。")
    return ff, fp


def download_ytdlp(progress_cb=None):
    """下载 yt-dlp 到 bin/。返回路径。"""
    d = _ensure_bin()
    target = os.path.join(d, _exe("yt-dlp"))

    if IS_WIN:
        _download(_YTDLP_WIN, target, progress_cb)
    elif IS_MAC:
        _download(_YTDLP_MAC, target, progress_cb)
        _make_executable(target)
    else:
        raise RuntimeError(f"不支持的平台：{sys.platform}。请手动安装：pip install yt-dlp")

    if not os.path.isfile(target):
        raise RuntimeError("yt-dlp 下载后未找到，请手动安装。")
    return target
