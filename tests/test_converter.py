import subprocess
import threading

import pytest

from core.converter import convert, probe, ConversionCancelled
from core.ffmpeg_runner import ffmpeg_path


@pytest.mark.parametrize('audio,small', [(False, False), (True, True)])
def test_conversion(tmp_path, audio, small, monkeypatch):
    if small:
        def no_links(*args):
            raise OSError('Hard links unsupported')
        monkeypatch.setattr('core.converter.os.link', no_links)
    source = tmp_path / '中文 video.mp4'
    cmd = [ffmpeg_path(), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=24:duration=1']
    if audio:
        cmd += ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-c:a', 'aac']
    subprocess.run(cmd + ['-c:v', 'libx264', str(source)], check=True)
    original = source.read_bytes()
    progress = []
    first = convert(source, small=small, progress_cb=progress.append)
    second = convert(source, small=small)
    assert first != second
    assert source.read_bytes() == original
    data, video = probe(first)
    assert video['codec_name'] == 'h264'
    assert video['pix_fmt'] == 'yuv420p'
    assert video['r_frame_rate'] == '30/1'
    streams = [s for s in data['streams'] if s['codec_type'] == 'audio']
    assert len(streams) == int(audio)
    if audio:
        assert streams[0]['codec_name'] == 'aac'
    assert progress[-1] == 1
    subprocess.run([ffmpeg_path(), '-v', 'error', '-xerror', '-i', first, '-f', 'null', '-'], check=True)
    assert not list(tmp_path.glob('.wechat_*'))


def test_cancel_and_invalid_input(tmp_path):
    event = threading.Event()
    event.set()
    with pytest.raises(ConversionCancelled):
        convert(tmp_path / 'missing.mp4', cancel=event)
    assert not list(tmp_path.iterdir())


def test_cancel_during_conversion(tmp_path):
    source = tmp_path / 'source.mp4'
    subprocess.run([ffmpeg_path(), '-v', 'error', '-f', 'lavfi', '-i',
                    'testsrc2=size=640x360:rate=30:duration=4', '-c:v', 'libx264', str(source)], check=True)
    event = threading.Event()
    with pytest.raises(ConversionCancelled):
        convert(source, cancel=event, progress_cb=lambda _: event.set())
    assert list(tmp_path.iterdir()) == [source]
