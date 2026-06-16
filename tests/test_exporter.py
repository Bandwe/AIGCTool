# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import exporter
from core.exporter import ExportOptions


def test_h265_default_args():
    opts = ExportOptions()
    args = exporter.build_ffmpeg_args("src.mp4", "out.mov", 3840, 2160, opts)
    assert "ffmpeg" in args[0].lower()
    assert "libx265" in args
    assert "-crf" in args and "18" in args
    assert "-tag:v" in args and "hvc1" in args
    # H.265 默认应带 faststart 和 BT.709 标记
    assert "+faststart" in args
    assert "bt709" in args
    # 默认 AAC 320k 音频
    assert "aac" in args and "320k" in args
    # 缩放滤镜含目标尺寸与 25fps
    vf = args[args.index("-vf") + 1]
    assert "scale=3840:2160" in vf and "fps=25" in vf


def test_h265_gpu_uses_nvenc():
    opts = ExportOptions(gpu=True)
    args = exporter.build_ffmpeg_args("src.mp4", "out.mov", 1920, 1080, opts)
    assert "hevc_nvenc" in args
    assert "libx265" not in args


def test_prores_args_and_pcm_audio():
    opts = ExportOptions(codec="prores", quality="hq")
    args = exporter.build_ffmpeg_args("src.mp4", "out.mov", 1280, 720, opts)
    assert "prores_ks" in args
    # ProRes 强制无损 PCM 音频，且不加 faststart
    assert any(a.startswith("pcm_") for a in args)
    assert "+faststart" not in args


def test_out_filename_contains_size_and_tag():
    h265 = exporter.out_filename("clip", 3840, 2160, ExportOptions())
    assert "3840x2160" in h265 and h265.endswith(".mov") and "25p" in h265
    mp4 = exporter.out_filename("clip", 1920, 1080, ExportOptions(mp4=True))
    assert mp4.endswith(".mp4")
    prores = exporter.out_filename("clip", 1280, 720, ExportOptions(codec="prores"))
    assert "ProRes422HQ" in prores


def test_no_color_tag_option():
    opts = ExportOptions(no_color_tag=True)
    args = exporter.build_ffmpeg_args("src.mp4", "out.mov", 1280, 720, opts)
    assert "bt709" not in args
