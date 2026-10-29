# -*- coding: utf-8 -*-
"""
AIGCTool 打包脚本：用 PyInstaller 生成独立可执行文件。

用法：
  python build.py          # 构建当前平台（Windows → .exe，macOS → .app）

输出在 dist/AIGCTool/ 目录下，是一个文件夹（one-folder 模式），
用户解压后双击 AIGCTool.exe (Win) 或 AIGCTool (Mac) 即可运行。
ffmpeg / yt-dlp 不打包，可复用本机工具或用顶部安装按钮下载到 bin/。
"""

import os
import sys
import shutil
import subprocess
import argparse

# Windows CI runners default stdout to cp1252, which can't encode the
# Chinese status messages below and would crash the script with
# UnicodeEncodeError after a successful build. Force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")
NAME = "AIGCTool"

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# tkinterdnd2 的 DLL/dylib 需要带上
def _find_tkdnd_dir():
    try:
        import tkinterdnd2
        pkg = os.path.dirname(tkinterdnd2.__file__)
        tkdnd = os.path.join(pkg, "tkdnd")
        if os.path.isdir(tkdnd):
            return tkdnd
    except ImportError:
        pass
    return None


def build(output_root=None):
    os.chdir(HERE)
    dist = os.path.join(os.path.abspath(output_root), "dist") if output_root else DIST
    work = os.path.join(os.path.abspath(output_root), "build") if output_root else BUILD
    out = os.path.join(dist, NAME)
    if os.path.lexists(out):
        raise FileExistsError("构建目录已存在，不会删除旧版本。请用 --output-root 指定新的版本目录：" + out)
    os.makedirs(work, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", NAME,
        "--distpath", dist, "--workpath", work, "--specpath", work,
        "--windowed",      # 无控制台（pythonw 效果）
        "--contents-directory", "_internal",
        # 收集 hidden imports（PyInstaller 自动分析可能遗漏的）
        "--hidden-import", "tkinterdnd2",
        "--hidden-import", "tkinterdnd2.TkinterDnD",
        "--hidden-import", "pynput.keyboard._win32" if IS_WIN else "pynput.keyboard._darwin",
        "--hidden-import", "pynput.mouse._win32" if IS_WIN else "pynput.mouse._darwin",
        "--hidden-import", "cv2",
        "--hidden-import", "socks",
        "--add-data", f"{os.path.join(HERE, 'licenses')}{os.pathsep}licenses",
        "--add-data", f"{os.path.join(HERE, 'THIRD_PARTY_NOTICES.md')}{os.pathsep}.",
    ]

    # tkinterdnd2 的原生库
    tkdnd = _find_tkdnd_dir()
    if tkdnd:
        dest = "tkinterdnd2/tkdnd" if IS_WIN else "tkinterdnd2/tkdnd"
        cmd += ["--add-data", f"{tkdnd}{os.pathsep}{dest}"]

    # macOS 特定
    if IS_MAC:
        cmd += ["--osx-bundle-identifier", "com.aigctool.app"]

    cmd.append(os.path.join(HERE, "main.py"))

    print(f"=== Building {NAME} for {'Windows' if IS_WIN else 'macOS' if IS_MAC else sys.platform} ===")
    print("Command:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    # 构建成功后，把 README 和使用说明复制进去
    for f in ("README.md", "使用说明.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md"):
        src = os.path.join(HERE, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(out, f))
    shutil.copytree(os.path.join(HERE, "licenses"), os.path.join(out, "licenses"))

    size = _dir_size(out)
    print(f"\n=== Done! Output: {out} ({size:.1f} MB) ===")
    print(f"用户只需解压这个文件夹，双击 {NAME}{'.exe' if IS_WIN else ''} 即可运行。")
    print("ffmpeg / yt-dlp 可复用本机工具；缺少时点击顶部安装按钮。")


def _dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total / (1024 * 1024)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", help="新版本构建目录，保留旧构建")
    build(parser.parse_args().output_root)
