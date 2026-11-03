# Changelog

## 1.3.0 - Unreleased

- Add a two-stage download workflow for every platform: detect available qualities, then explicitly choose a format for each resource. Detection never downloads media or selects formats on the user's behalf.
- Add NetEase Cloud Music single-song URLs (including hash routes), scoped Netscape Cookie login, and all audio tiers available to the current account, ordered by reported bitrate. Preserve the source audio without transcoding.
- Detect likely preview-only music formats and block them from full-song delivery; verify downloaded audio duration, size, codec, sample rate and bit depth before publishing.
- Pin video/audio format IDs, preserve individual playlist/part choices, and require re-detection after link, Cookie or network changes. Never silently substitute another quality.
- Extend redacted receipts and verified-file reuse to audio, retaining song IDs and exact selected format IDs. Keep the existing five tools and platform-isolated Cookie cleanup.

This source update does not replace the existing v1.2.0 Release installers.

## 1.2.0 - 2026-10-29

- Add a local Douyin single-video adapter using the pinned Apache-2.0 web-signature helper. Keep yt-dlp for Bilibili, YouTube and Xiaohongshu.
- Default to a 720p minimum short edge and single-video scope. Require an explicit lower-resolution option; verify actual media before publication.
- Add automatic/direct/custom network modes, share-text URL extraction, progress/speed logs, cancellation and resumable staging.
- Keep original cookie files read-only; isolate platform cookies and clean temporary copies on normal completion, errors and cancellation.
- Record actual media facts and SHA-256 in redacted per-file receipts. Preserve existing outputs and distinguish partially successful playlists.
- Preserve all five existing tools, including WeChat-compatible conversion. Add download regression CI for Windows/macOS.
- Keep previous builds intact; use `build.py --output-root` for a new build location. Bundle required upstream license/NOTICE files.

- Ship Windows x64, macOS Apple Silicon and macOS Intel archives, each built and smoke-tested on its native runner.
- Package the actual macOS app bundle, collect native TkDND only, and store downloaded Mac tools outside the signed bundle.
- Install checksum-verified native FFmpeg / ffprobe release binaries on both Mac architectures.

Platform support depends on upstream interfaces and the user's access permissions.
