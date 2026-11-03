import json
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from core import autoinstall, downloader, douyin, download_catalog as catalog
from core.download_support import DownloadCancelled, DownloadOptions, canonical_source, isolated_cookie, publish, reuse_completed, verify_policy


def audio_info(duration=164, size=6564093):
    return {"media_type": "audio", "duration": duration, "codec": "mp3", "sample_rate": 44100,
            "channels": 2, "bytes": size, "bit_rate": 320000, "bits_per_sample": 0}


def song_metadata():
    return {"id": "3383908051", "title": "Fixture song", "duration": 164,
            "webpage_url": "https://music.163.com/song?id=3383908051",
            "formats": [{"format_id": "exhigh", "ext": "mp3", "vcodec": "none", "abr": 320, "filesize": 6564093},
                        {"format_id": "jymaster", "ext": "flac", "vcodec": "none", "abr": 5067, "filesize": 103910132}]}


@pytest.mark.parametrize("url", ["https://music.163.com/song?id=3383908051&uct2=private",
                                 "https://music.163.com/#/song?id=3383908051&token=private",
                                 "https://y.music.163.com/m/song?id=3383908051"])
def test_music_links_keep_song_identity_without_credentials(url):
    assert downloader.detect_platform(url) == "netease"
    assert canonical_source(url) == "https://music.163.com/song?id=3383908051"
    assert canonical_source(url) != canonical_source("https://music.163.com/song?id=123")


@pytest.mark.parametrize("url", ["https://music.163.com.evil.test/song?id=1", "https://music.163.com/playlist?id=1",
                                 "https://music.163.com/song?id=1&id=2", "https://music.163.com:123/song?id=1"])
def test_music_invalid_routes(url):
    with pytest.raises(ValueError):
        catalog.normalize_music_url(url)


def test_music_cookie_scoped_and_original_unchanged(tmp_path):
    cookie = tmp_path / "account.txt"
    content = ("# Netscape HTTP Cookie File\n.music.163.com\tTRUE\t/\tFALSE\t2147483647\tMUSIC_U\tfixture\n"
               ".mail.163.com\tTRUE\t/\tFALSE\t2147483647\tMAIL\tprivate\n")
    cookie.write_text(content)
    with isolated_cookie(str(cookie), "netease", tmp_path) as temporary:
        assert "MUSIC_U" in Path(temporary).read_text()
        assert "MAIL" not in Path(temporary).read_text()
    assert cookie.read_text() == content and not Path(temporary).exists()


def test_metadata_never_appears_in_logs():
    logs = []
    data = {"formats": [{"url": "https://cdn.test/audio?token=private", "http_headers": {"Cookie": "private"}}]}
    command = "print(" + repr(downloader._INFO_MARKER + json.dumps(data)) + ")"
    result = downloader._run([sys.executable, "-c", command], log=logs.append)
    assert result.metadata == [data] and not logs


def test_audio_choices_are_sorted_but_never_automatically_selected():
    info = song_metadata()
    choices = catalog.qualities(info, "netease")
    assert [c.format_id for c in choices] == ["jymaster", "exhigh"]
    resource = catalog.Resource(info["webpage_url"], "netease", info["title"], 164, choices)
    options = resource.options_for(choices[1], DownloadOptions(playlist=True))
    assert options.format_id == "exhigh" and options.media_kind == "audio" and options.min_resolution == 0
    assert options.expected_duration == 164 and options.expected_size == 6564093 and not options.playlist
    with pytest.raises(ValueError):
        resource.options_for(catalog.Quality("other", "other"), DownloadOptions())


def test_preview_is_visible_but_cannot_be_selected_as_full_song():
    info = song_metadata()
    info["formats"] = [{"format_id": "standard", "vcodec": "none", "ext": "mp3", "abr": 128, "filesize": 481115}]
    choices = catalog.qualities(info, "netease")
    assert choices[0].preview and "试听" in choices[0].label
    resource = catalog.Resource(info["webpage_url"], "netease", "song", 164, choices)
    with pytest.raises(ValueError, match="试听"):
        resource.options_for(choices[0], DownloadOptions())


def test_short_complete_song_is_not_rejected_as_preview():
    info = song_metadata()
    info["duration"] = 30
    info["formats"] = [{"format_id": "standard", "vcodec": "none", "ext": "mp3", "abr": 128, "filesize": 481115}]
    assert not catalog.qualities(info, "netease")[0].preview


def test_video_choices_pin_video_and_audio_without_fallback():
    info = {"formats": [
        {"format_id": "137", "width": 1920, "height": 1080, "fps": 30, "acodec": "none", "vcodec": "avc1", "ext": "mp4"},
        {"format_id": "136", "width": 1280, "height": 720, "acodec": "none", "vcodec": "avc1", "ext": "mp4"},
        {"format_id": "140", "vcodec": "none", "acodec": "aac", "abr": 128},
        {"format_id": "251", "vcodec": "none", "acodec": "opus", "abr": 160},
        {"format_id": "drm", "width": 3840, "height": 2160, "has_drm": True}]}
    choices = catalog.qualities(info, "youtube")
    assert [c.format_id for c in choices] == ["137+251", "136+251"]
    resource = catalog.Resource("https://youtu.be/example", "youtube", "video", 30, choices)
    options = resource.options_for(choices[1], DownloadOptions())
    args = downloader.build_args(resource.url, ".", "youtube", options=options)
    assert args[args.index("-f") + 1] == "136+251"
    with pytest.raises(RuntimeError, match="所选品质"):
        verify_policy(dict(width=960, height=540, duration=30), options)


def test_audio_download_args_never_merge_to_mp4():
    options = DownloadOptions(format_id="jymaster", media_kind="audio", expected_duration=164)
    args = downloader.build_args("https://music.163.com/song?id=1", ".", "netease", options=options)
    assert args[args.index("-f") + 1] == "jymaster"
    assert "--merge-output-format" not in args and "--extract-audio" not in args
    assert "%(format_id)s" in args[args.index("-o") + 1]


def test_unlabelled_original_video_remains_available_without_invented_resolution():
    choices = catalog.qualities({"formats": [{"format_id": "direct", "ext": "mp4"}]}, "xiaohongshu")
    assert len(choices) == 1 and choices[0].width == 0 and "待核验" in choices[0].label


@pytest.mark.parametrize("duration", [0, 30, 100, float("nan")])
def test_audio_requires_complete_duration(duration):
    with pytest.raises(RuntimeError):
        verify_policy(audio_info(duration), DownloadOptions(media_kind="audio", expected_duration=164))


def test_audio_receipts_and_reuse_pin_quality_and_duration(tmp_path):
    file = tmp_path / "song.mp3"
    file.write_bytes(b"audio")
    options = DownloadOptions(media_kind="audio", format_id="exhigh", expected_duration=164)
    url = "https://music.163.com/#/song?id=1&token=secret"
    publish(file, tmp_path, url, "netease", audio_info(), options)
    receipt = Path(str(file) + ".receipt.json").read_text(encoding="utf-8")
    assert "secret" not in receipt and '"format_id": "exhigh"' in receipt
    assert reuse_completed(tmp_path, url, options, lambda _: audio_info())
    assert not reuse_completed(tmp_path, url, replace(options, format_id="jymaster"), lambda _: audio_info())
    assert not reuse_completed(tmp_path, url, options, lambda _: audio_info(30))
    assert not reuse_completed(tmp_path, "https://music.163.com/song?id=2", options, lambda _: audio_info())


def test_probe_is_simulation_and_preserves_per_entry_choices(monkeypatch):
    commands = []
    monkeypatch.setattr(autoinstall, "find", lambda _: "yt-dlp")
    def run(args, **kwargs):
        commands.append(args)
        return downloader.RunResult(0, metadata=[song_metadata()])
    monkeypatch.setattr(downloader, "_run", run)
    result = catalog.probe(["https://music.163.com/#/song?id=3383908051"], options=DownloadOptions(network="direct"))
    assert len(result) == 1
    assert "--simulate" in commands[0] and "--skip-download" in commands[0] and "--no-playlist" in commands[0]
    assert commands[0][commands[0].index("--proxy") + 1] == ""
    assert "--cookies" not in commands[0]
    assert commands[0][-1] == "https://music.163.com/song?id=3383908051"


def test_probe_playlist_keeps_individual_parts(monkeypatch):
    monkeypatch.setattr(autoinstall, "find", lambda _: "yt-dlp")
    parts = [{"title": f"part {i}", "duration": 10, "webpage_url": f"https://www.bilibili.com/video/BVtest?p={i}",
              "formats": [{"format_id": "1", "width": 1280, "height": 720, "ext": "mp4"}]} for i in (1, 2)]
    monkeypatch.setattr(downloader, "_run", lambda *args, **kwargs: downloader.RunResult(0, metadata=parts))
    result = catalog.probe(["https://www.bilibili.com/video/BVtest"], options=DownloadOptions(playlist=True))
    assert len(result) == 2 and result[0].url != result[1].url
    assert not result[1].options_for(result[1].choices[0], DownloadOptions(playlist=True)).playlist


def test_cancelled_probe_never_starts_process(monkeypatch):
    cancel = threading.Event()
    cancel.set()
    monkeypatch.setattr(downloader, "_run", lambda *a, **kw: pytest.fail("Cancelled"))
    with pytest.raises(DownloadCancelled):
        catalog.probe(["https://music.163.com/song?id=1"], cancel=cancel)


def test_douyin_choices_skip_unlabelled_original_endpoint():
    detail = {"video": {"play_addr": {"uri": "id", "width": 960, "height": 540,
               "url_list": ["https://cdn.example/video"]}}}
    choices = douyin.available_qualities(detail)
    assert len(choices) == 1 and choices[0]["id"] == "play" and choices[0]["height"] == 540


@pytest.mark.skipif(not all(autoinstall.find(name) for name in ("ffmpeg", "ffprobe")), reason="Media tools not installed")
def test_real_audio_probe_and_policy(tmp_path):
    audio = tmp_path / "fixture.flac"
    subprocess.run([autoinstall.find("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "sine=duration=3",
                    "-ar", "48000", "-ac", "2", "-c:a", "flac", str(audio)], check=True, timeout=20,
                   creationflags=downloader.CREATE_NO_WINDOW)
    info = downloader.inspect_media(str(audio), "audio")
    assert info["sample_rate"] == 48000 and info["channels"] == 2 and info["codec"] == "flac"
    assert not verify_policy(info, DownloadOptions(media_kind="audio", expected_duration=3, expected_size=audio.stat().st_size))
    with pytest.raises(RuntimeError):
        downloader.inspect_media(str(audio))


def test_gui_requires_explicit_choice_and_invalidates_cookie_changes():
    import tkinter as tk
    from ui.tab_download import DownloadTab
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("No desktop display")
    root.withdraw()
    class Context:
        busy = False
        deps = {"yt-dlp": (True, "", "")}
        def on_busy_change(self, callback):
            pass
        def log(self, message):
            pass
    try:
        tab = DownloadTab(root, Context())
        tab.pack(fill="both", expand=True)
        tab.urls.insert("1.0", "https://music.163.com/song?id=3383908051")
        root.update()
        key = tab._snapshot()
        resource = catalog.Resource(key[0][0], "netease", "Fixture song", 164, catalog.qualities(song_metadata(), "netease"))
        tab._show_results(key, [resource])
        root.update()
        assert not tab.chosen and str(tab.dl_btn["state"]) == "disabled"
        tab.quality.current(2)
        tab._choose()
        assert tab.chosen["0"].format_id == "exhigh" and str(tab.dl_btn["state"]) == "normal"
        tab.cookie.set("new-cookie.txt")
        assert not tab.chosen and not tab.resources and str(tab.dl_btn["state"]) == "disabled"
    finally:
        root.destroy()
