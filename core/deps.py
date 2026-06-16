# -*- coding: utf-8 -*-
"""
依赖自检：检测 ffmpeg / ffprobe / yt-dlp。
查找顺序：应用本地 bin/ → 系统 PATH。

结果供顶部状态条和各页面按钮的可用性判断。
"""

from . import autoinstall

INSTALL_HINTS = {
    "ffmpeg": "点击右侧「安装」自动下载，或手动：winget install ffmpeg",
    "ffprobe": "随 ffmpeg 一起安装",
    "yt-dlp": "点击右侧「安装」自动下载，或手动：pip install -U yt-dlp",
}


def check(name):
    """返回 (是否可用, 完整路径或"", 安装提示)。"""
    path = autoinstall.find(name)
    if path:
        return True, path, ""
    return False, "", INSTALL_HINTS.get(name, "")


def check_all():
    """返回 {name: (ok, path, hint)}。"""
    return {n: check(n) for n in ("ffmpeg", "ffprobe", "yt-dlp")}


def status_line(results=None):
    """生成顶部状态条文字。"""
    results = results or check_all()
    return "   ".join(
        f"{name} {'✓' if ok else '✗'}" for name, (ok, _p, _h) in results.items()
    )
