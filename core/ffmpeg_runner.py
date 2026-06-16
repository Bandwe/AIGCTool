# -*- coding: utf-8 -*-
"""
通用 ffmpeg / ffprobe 调用层。

- 在 Windows 用 pythonw 启动 GUI 时，避免每次调用弹出黑窗口（CREATE_NO_WINDOW）。
- 统一通过 `-progress pipe:1` 解析进度，供拆分/合并/导出三处共用。
- ffprobe 取时长。
"""

import os
import re
import sys
import subprocess
import tempfile

from . import autoinstall

# pythonw 启动子进程时不弹黑窗口
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_TIME_RE = re.compile(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)")


def ffmpeg_path():
    return autoinstall.find("ffmpeg") or "ffmpeg"


def ffprobe_path():
    return autoinstall.find("ffprobe") or "ffprobe"


class FFmpegError(Exception):
    """ffmpeg / ffprobe 执行失败时抛出，带上 ffmpeg 的错误输出。"""


def get_duration(path):
    """用 ffprobe 取视频总时长（秒，float）。失败抛 FFmpegError。"""
    cmd = [
        ffprobe_path(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        raise FFmpegError("找不到 ffprobe，请确认 ffmpeg 已安装并加入 PATH。")
    val = (out.stdout or "").strip()
    try:
        return float(val)
    except ValueError:
        raise FFmpegError(f"无法读取时长：{path}\n{out.stderr.strip()}")


def run_with_progress(cmd, total_seconds, progress_cb):
    """
    执行 ffmpeg 并通过 -progress pipe:1 解析进度。
    progress_cb(fraction) 取值 0.0~1.0；total_seconds<=0 时不报进度。
    stderr 写入临时文件，失败时读取末尾用于报错。
    """
    err_fd, err_path = tempfile.mkstemp(suffix=".log")
    os.close(err_fd)
    try:
        with open(err_path, "w", encoding="utf-8", errors="replace") as err_f:
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=err_f,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=CREATE_NO_WINDOW,
                )
            except FileNotFoundError:
                raise FFmpegError("找不到 ffmpeg，请确认 ffmpeg 已安装并加入 PATH。")

            for line in proc.stdout:
                m = _TIME_RE.search(line)
                if m and total_seconds and total_seconds > 0 and progress_cb:
                    h, mnt, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
                    cur = h * 3600 + mnt * 60 + sec
                    progress_cb(max(0.0, min(cur / total_seconds, 1.0)))
            proc.wait()

        if proc.returncode != 0:
            with open(err_path, "r", encoding="utf-8", errors="replace") as f:
                tail = f.read().strip().splitlines()[-15:]
            raise FFmpegError("\n".join(tail) or f"ffmpeg 退出码 {proc.returncode}")
        if progress_cb:
            progress_cb(1.0)
    finally:
        try:
            os.remove(err_path)
        except OSError:
            pass
