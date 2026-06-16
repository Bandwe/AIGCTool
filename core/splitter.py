# -*- coding: utf-8 -*-
"""
视频拆分 / 合并核心逻辑（移植自原 视频拆分/ffmpeg_utils.py）。

全部使用无损流复制 (-c copy)：不重新编码，关键帧处切分，
所有片段可以原样拼回，逐帧对应原视频。
"""

import os
import re
import tempfile

from .ffmpeg_runner import get_duration, run_with_progress, ffmpeg_path, FFmpegError

# 识别为视频的扩展名
VIDEO_EXTS = {
    ".mp4", ".mkv", ".mov", ".avi", ".flv", ".ts", ".webm",
    ".m4v", ".mpg", ".mpeg", ".wmv", ".3gp", ".m2ts", ".vob",
}


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def natural_key(s):
    """自然排序键，让 2 排在 10 前面 (001, 002, ..., 010, ...)。"""
    name = os.path.basename(s)
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def find_videos(folder):
    """返回文件夹内（仅一层）所有视频文件，按自然顺序排序。"""
    items = []
    for name in os.listdir(folder):
        full = os.path.join(folder, name)
        if os.path.isfile(full) and is_video(full):
            items.append(full)
    items.sort(key=natural_key)
    return items


def default_out_dir(input_path):
    base = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(os.path.dirname(os.path.abspath(input_path)), base + "_片段")


def _segment(input_path, segment_time, out_dir, progress_cb):
    """用 segment 复用器按目标时长切分（关键帧对齐，无损）。"""
    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(input_path)[1] or ".mp4"
    pattern = os.path.join(out_dir, "%03d" + ext)
    total = get_duration(input_path)
    cmd = [
        ffmpeg_path(), "-hide_banner", "-y",
        "-i", input_path,
        "-map", "0", "-c", "copy",
        "-f", "segment",
        "-segment_time", f"{segment_time:.3f}",
        "-reset_timestamps", "1",
        "-segment_start_number", "1",
        "-progress", "pipe:1", "-nostats",
        pattern,
    ]
    run_with_progress(cmd, total, progress_cb)
    produced = [os.path.join(out_dir, n) for n in os.listdir(out_dir)
                if os.path.isfile(os.path.join(out_dir, n))]
    produced.sort(key=natural_key)
    return produced


def seg_time_for_count(total, count):
    """按段数均分时，每段的目标时长（秒）。抽出来便于单测。"""
    count = int(count)
    if count <= 0:
        raise ValueError("段数必须是大于 0 的整数。")
    return max(total / count, 0.05)


def split_by_duration(input_path, seconds, out_dir=None, progress_cb=None):
    """按固定时长（秒）切分。返回生成的片段路径列表。"""
    if seconds <= 0:
        raise ValueError("每段时长必须大于 0 秒。")
    out_dir = out_dir or default_out_dir(input_path)
    return _segment(input_path, float(seconds), out_dir, progress_cb)


def split_by_count(input_path, count, out_dir=None, progress_cb=None):
    """
    按段数均分。段长 = 总时长 / 段数。
    由于必须在关键帧处下刀（保证可帧级还原），实际段数可能与目标略有出入。
    """
    total = get_duration(input_path)
    seg_time = seg_time_for_count(total, count)
    out_dir = out_dir or default_out_dir(input_path)
    return _segment(input_path, seg_time, out_dir, progress_cb)


def _concat_escape(path):
    p = os.path.abspath(path).replace("\\", "/")
    return p.replace("'", "'\\''")


def merge(input_paths, output_path, progress_cb=None):
    """按给定顺序无损合并多个视频为一个文件 (concat demuxer + -c copy)。"""
    if len(input_paths) < 2:
        raise ValueError("至少需要 2 个视频才能合并。")

    total = 0.0
    for p in input_paths:
        try:
            total += get_duration(p)
        except FFmpegError:
            total = 0.0
            break

    list_fd, list_path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(list_fd, "w", encoding="utf-8") as f:
            for p in input_paths:
                f.write(f"file '{_concat_escape(p)}'\n")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        cmd = [
            ffmpeg_path(), "-hide_banner", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-map", "0", "-c", "copy",
            "-progress", "pipe:1", "-nostats",
            output_path,
        ]
        run_with_progress(cmd, total, progress_cb)
        return output_path
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass
