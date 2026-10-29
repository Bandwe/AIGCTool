"""Small local HTTP/FFmpeg integration test; no accounts or external network."""

import functools
import http.server
import subprocess
import threading

import pytest

from core import autoinstall, downloader


@pytest.mark.skipif(not all(autoinstall.find(name) for name in ("ffmpeg", "ffprobe", "yt-dlp")),
                    reason="Optional local media tools are not installed")
def test_real_download_verify_reuse_and_quality_gate(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    video = source / "fixture.mp4"
    subprocess.run([autoinstall.find("ffmpeg"), "-v", "error", "-f", "lavfi", "-i",
                    "color=c=green:s=960x540:d=1", "-f", "lavfi", "-i",
                    "sine=frequency=400:duration=1", "-c:v", "libx264", "-c:a", "aac",
                    "-shortest", str(video)], check=True, timeout=30, creationflags=downloader.CREATE_NO_WINDOW)
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(source)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}/fixture.mp4"
    output = tmp_path / "output"
    logs = []
    try:
        assert downloader.download([url], str(output), options=downloader.DownloadOptions(network="direct"), log=logs.append) == (0, 1), logs
        assert not list(output.glob("*.mp4"))
        assert list((output / ".aigctool").rglob("*.mp4"))
        accepted = downloader.DownloadOptions(720, True, False, "direct")
        assert downloader.download([url], str(output), options=accepted, log=logs.append) == (1, 1), logs
        assert len(list(output.glob("*.mp4"))) == 1
        assert len(list(output.glob("*.receipt.json"))) == 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    # The verified file is reusable even when its source server is no longer running.
    assert downloader.download([url], str(output), options=accepted, log=logs.append) == (1, 1), logs
