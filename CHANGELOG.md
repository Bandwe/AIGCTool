# Changelog

## 1.2 V01 (review build)

- Add a local Douyin single-video adapter using the pinned Apache-2.0 web-signature helper. Keep yt-dlp for Bilibili, YouTube and Xiaohongshu.
- Default to a 720p minimum short edge and single-video scope. Require an explicit lower-resolution option; verify actual media before publication.
- Add automatic/direct/custom network modes, share-text URL extraction, progress/speed logs, cancellation and resumable staging.
- Keep original cookie files read-only; isolate platform cookies and clean temporary copies on normal completion, errors and cancellation.
- Record actual media facts and SHA-256 in redacted per-file receipts. Preserve existing outputs and distinguish partially successful playlists.
- Preserve all five existing tools, including WeChat-compatible conversion. Add download regression CI for Windows/macOS.
- Keep previous builds intact; use `build.py --output-root` for a new build location. Bundle required upstream license/NOTICE files.

This is a comparison build, not a promise of permanent platform compatibility.
No official release or merge into the main branch is implied.
