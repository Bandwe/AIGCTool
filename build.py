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
import plistlib
import json
import platform
from core.version import VERSION

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

def build(output_root=None):
    os.chdir(HERE)
    dist = os.path.join(os.path.abspath(output_root), "dist") if output_root else DIST
    work = os.path.join(os.path.abspath(output_root), "build") if output_root else BUILD
    out = os.path.join(dist, NAME + (".app" if IS_MAC else ""))
    if os.path.lexists(out) or os.path.lexists(os.path.join(dist, NAME)):
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

    # The pinned PyInstaller hook collects only the current architecture's TkDND.
    documents = ("README.md", "使用说明.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md")
    for filename in documents:
        cmd += ["--add-data", f"{os.path.join(HERE, filename)}{os.pathsep}."]

    # macOS 特定
    if IS_MAC:
        cmd += ["--osx-bundle-identifier", "com.aigctool.app"]

    cmd.append(os.path.join(HERE, "main.py"))

    print(f"=== Building {NAME} for {'Windows' if IS_WIN else 'macOS' if IS_MAC else sys.platform} ===")
    print("Command:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    metadata_dir = os.path.join(out, "Contents", "Resources") if IS_MAC else out
    with open(os.path.join(metadata_dir, "release.json"), "w", encoding="utf-8") as target:
        json.dump({"version": VERSION, "platform": sys.platform, "architecture": platform.machine()}, target)
    if IS_MAC:
        info_path = os.path.join(out, "Contents", "Info.plist")
        with open(info_path, "rb") as source:
            info = plistlib.load(source)
        info.update(CFBundleShortVersionString=VERSION, CFBundleVersion=VERSION,
                    NSHighResolutionCapable=True)
        with open(info_path, "wb") as target:
            plistlib.dump(info, target)
        # Ad-hoc signing preserves bundle integrity; it is NOT Developer ID notarization.
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", out], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", out], check=True)
    else:
        for filename in documents:
            shutil.copy2(os.path.join(HERE, filename), os.path.join(out, filename))
        shutil.copytree(os.path.join(HERE, "licenses"), os.path.join(out, "licenses"))

    size = _dir_size(out)
    print(f"\n=== Done! Output: {out} ({size:.1f} MB) ===")
    print(f"用户只需解压，双击 {NAME}{'.exe' if IS_WIN else '.app'} 即可运行。")
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
