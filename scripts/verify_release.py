"""Check the complete release set before it can become a GitHub release draft."""

import argparse
import hashlib
import json
import plistlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.version import VERSION


ARCHIVES = {
    "AIGCTool-Windows-x64.zip": ("win32", "x64"),
    "AIGCTool-macOS-arm64.zip": ("darwin", "arm64"),
    "AIGCTool-macOS-x64.zip": ("darwin", "x64"),
}


def verify_archive(path, system, architecture):
    with zipfile.ZipFile(path) as package:
        if package.testzip():
            raise ValueError(f"Archive CRC failed: {path.name}")
        if system == "darwin":
            root = "AIGCTool.app/Contents/"
            metadata = root + "Resources/release.json"
            required = {root + "MacOS/AIGCTool", root + "Info.plist", metadata,
                        root + "Resources/licenses/douyin-api-LICENSE.txt"}
            info = plistlib.loads(package.read(root + "Info.plist"))
            if info.get("CFBundleShortVersionString") != VERSION:
                raise ValueError("Incorrect macOS application version")
        else:
            root = "AIGCTool/"
            metadata = root + "release.json"
            required = {root + "AIGCTool.exe", metadata, root + "licenses/douyin-api-LICENSE.txt"}
        names = set(package.namelist())
        if not required.issubset(names):
            raise ValueError(f"Missing package files: {sorted(required - names)}")
        if any("cookie" in name.lower() and name.lower().endswith(".txt") for name in names):
            raise ValueError("Cookie-like text file found in release archive")
        data = json.loads(package.read(metadata))
        arch = {"AMD64": "x64", "x86_64": "x64", "arm64": "arm64"}.get(data.get("architecture"))
        if data.get("version") != VERSION or data.get("platform") != system or arch != architecture:
            raise ValueError(f"Release metadata mismatch: {path.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.tag and args.tag != "v" + VERSION:
        raise ValueError("Git tag and application version do not match")
    checksums = []
    for filename, (system, architecture) in ARCHIVES.items():
        path = args.directory / filename
        verify_archive(path, system, architecture)
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        checksums.append(f"{digest}  {filename}")
        print(f"Verified {filename}: {path.stat().st_size} bytes")
    (args.directory / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
