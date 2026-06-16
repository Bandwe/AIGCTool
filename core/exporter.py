# -*- coding: utf-8 -*-
"""
多分辨率高质量导出（移植自原 分辨率锁定/Export-Video.ps1）。

把一个源视频导出为若干分辨率（默认 4K / 1080 / 720），统一锁定 25fps CFR、
16:9、Lanczos 高质量缩放、BT.709 标记。两种编码：

  h265   (默认) H.265/HEVC 交付母版：观感等同 ProRes，体积约 1/10。
                可选 -gpu 用 hevc_nvenc(NVIDIA) 加速。
  prores       Apple ProRes 422 HQ 真母版（体积巨大），用于二剪/调色。

与原 PS 脚本的差异：去掉写死的源文件路径和写死的 ffmpeg.exe 路径，
源文件由界面选择，ffmpeg 统一走 PATH。
"""

import os
from dataclasses import dataclass, field

from .ffmpeg_runner import get_duration, run_with_progress, ffmpeg_path

# 预设分辨率：标签 -> (宽, 高)
SIZES = {
    "4K": (3840, 2160),
    "1080": (1920, 1080),
    "720": (1280, 720),
}

_SWS = "flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp"


@dataclass
class ExportOptions:
    codec: str = "h265"          # "h265" | "prores"
    # H.265
    crf: int = 18
    preset: str = "medium"
    bit: int = 10                # 8 | 10
    gpu: bool = False            # 用 NVIDIA hevc_nvenc
    audio_pcm: bool = False      # H.265 时也用无损 PCM 音频
    mp4: bool = False            # H.265 输出 mp4 而非 mov
    # ProRes
    quality: str = "hq"          # 422 | hq | 4444 | xq
    # 通用
    fps: int = 25
    audio_bits: int = 24         # 16 | 24（PCM 时）
    interpolate: bool = False    # 运动补偿插帧（默认精确重采样）
    no_color_tag: bool = False
    sizes: list = field(default_factory=lambda: ["4K", "1080", "720"])


def _video_args(opts: ExportOptions):
    """返回 (视频编码参数列表, vtag, 容器扩展名)。"""
    if opts.codec == "prores":
        prof, pix, vtag = {
            "422": (2, "yuv422p10le", "ProRes422"),
            "hq": (3, "yuv422p10le", "ProRes422HQ"),
            "4444": (4, "yuv444p10le", "ProRes4444"),
            "xq": (5, "yuv444p10le", "ProRes4444XQ"),
        }[opts.quality]
        return (
            ["-c:v", "prores_ks", "-profile:v", str(prof), "-vendor", "apl0", "-pix_fmt", pix],
            vtag, "mov",
        )

    # H.265 / HEVC
    if opts.bit == 10:
        pix_sw, pix_hw = "yuv420p10le", "p010le"
    else:
        pix_sw, pix_hw = "yuv420p", "yuv420p"

    if opts.gpu:
        vargs = ["-c:v", "hevc_nvenc", "-preset", "p7", "-tune", "hq",
                 "-rc", "vbr", "-cq", str(opts.crf), "-b:v", "0", "-pix_fmt", pix_hw]
        vtag = f"H265-nvenc-cq{opts.crf}-{opts.bit}bit"
    else:
        vargs = ["-c:v", "libx265", "-preset", opts.preset, "-crf", str(opts.crf),
                 "-pix_fmt", pix_sw, "-x265-params", "log-level=error"]
        vtag = f"H265-crf{opts.crf}-{opts.bit}bit"
    vargs += ["-tag:v", "hvc1"]
    ext = "mp4" if opts.mp4 else "mov"
    return vargs, vtag, ext


def _audio_args(opts: ExportOptions):
    if opts.codec == "prores" or opts.audio_pcm:
        acodec = "pcm_s16le" if opts.audio_bits == 16 else "pcm_s24le"
        return ["-c:a", acodec]
    return ["-c:a", "aac", "-b:a", "320k"]


def _filter(opts: ExportOptions, w, h):
    if opts.interpolate:
        return (f"minterpolate=fps={opts.fps}:mi_mode=mci:mc_mode=aobmc:"
                f"me_mode=bidir:vsbmc=1,scale={w}:{h}:{_SWS}")
    return f"fps={opts.fps},scale={w}:{h}:{_SWS}"


def build_ffmpeg_args(source, out_path, w, h, opts: ExportOptions):
    """构建单个分辨率的完整 ffmpeg 参数列表（含 ffmpeg 程序名）。抽出便于单测。"""
    vargs, _vtag, _ext = _video_args(opts)
    args = [
        ffmpeg_path(), "-hide_banner", "-y",
        "-i", source,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", _filter(opts, w, h),
        "-fps_mode", "cfr",
    ] + vargs + _audio_args(opts)
    if opts.codec == "h265":
        args += ["-movflags", "+faststart"]
    if not opts.no_color_tag:
        args += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    args += [out_path]
    return args


def out_filename(name, w, h, opts: ExportOptions):
    _vargs, vtag, ext = _video_args(opts)
    return f"{name}_{w}x{h}_{opts.fps}p_{vtag}.{ext}"


def export(source, out_dir, opts: ExportOptions, log=None, progress_cb=None, name=None):
    """
    把 source 导出为 opts.sizes 指定的各分辨率，输出到 out_dir。
    log(str)：文本日志回调；progress_cb(frac)：0~1 总进度。
    返回每个分辨率的结果 dict 列表。
    """
    log = log or (lambda *_: None)
    name = name or os.path.splitext(os.path.basename(source))[0]
    os.makedirs(out_dir, exist_ok=True)

    sizes = [s for s in opts.sizes if s in SIZES]
    if not sizes:
        raise ValueError("请至少选择一种分辨率。")

    total = 0.0
    try:
        total = get_duration(source)
    except Exception:
        total = 0.0

    results = []
    n = len(sizes)
    for idx, key in enumerate(sizes):
        w, h = SIZES[key]
        out_path = os.path.join(out_dir, out_filename(name, w, h, opts))
        args = build_ffmpeg_args(source, out_path, w, h, opts)
        log(f"[{idx + 1}/{n}] 导出 {w}x{h} → {os.path.basename(out_path)}")

        def cb(frac, i=idx):
            if progress_cb:
                progress_cb((i + frac) / n)

        run_with_progress(args, total, cb)
        mb = round(os.path.getsize(out_path) / (1024 * 1024), 1) if os.path.exists(out_path) else 0
        log(f"      ✓ {mb} MB")
        results.append({"size": f"{w}x{h}", "file": out_path, "mb": mb})

    if progress_cb:
        progress_cb(1.0)
    return results
