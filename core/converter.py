"""Convert local videos to H.264/AAC MP4 with cancellable progress."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import threading

from .ffmpeg_runner import CREATE_NO_WINDOW, FFmpegError, ffmpeg_path, ffprobe_path


class ConversionCancelled(Exception):
    pass


def probe(path):
    result = subprocess.run(
        [ffprobe_path(), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
        capture_output=True, encoding='utf-8', errors='replace', timeout=30,
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise FFmpegError(result.stderr)
    data = json.loads(result.stdout)
    videos = [s for s in data['streams'] if s['codec_type'] == 'video'
              and not s.get('disposition', {}).get('attached_pic')]
    if not videos:
        raise FFmpegError('没有视频轨道')
    return data, videos[0]


def command(source, output, video_index, small=False):
    limit, crf = (1280, 23) if small else (1920, 20)
    vf = (f"scale=w='min({limit},iw)':h='min({limit},ih)':"
          'force_original_aspect_ratio=decrease:force_divisible_by=2,'
          'setsar=1,fps=30,format=yuv420p')
    return [ffmpeg_path(), '-hide_banner', '-nostdin', '-y', '-i', str(source),
            '-map', f'0:{video_index}', '-map', '0:a:0?', '-vf', vf,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', str(crf),
            '-profile:v', 'high', '-level:v', '4.1', '-maxrate', '12M', '-bufsize', '24M',
            '-tag:v', 'avc1', '-c:a', 'aac', '-profile:a', 'aac_low', '-b:a', '160k',
            '-ar', '48000', '-ac', '2', '-map_metadata', '-1', '-movflags', '+faststart',
            '-progress', 'pipe:1', '-nostats', str(output)]


def convert(source, out_dir=None, small=False, cancel=None, progress_cb=None):
    cancel = cancel if cancel is not None else threading.Event()
    if cancel.is_set():
        raise ConversionCancelled()
    source = Path(source).resolve()
    data, video = probe(source)
    if video.get('color_transfer') in ('smpte2084', 'arib-std-b67'):
        raise FFmpegError('HDR视频需要先进行SDR色调映射，暂不支持直接转换。')
    duration = float(data.get('format', {}).get('duration') or 0)
    folder = Path(out_dir) if out_dir else source.parent
    folder.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.wechat_', suffix='.mp4', dir=folder)
    os.close(fd)
    finished = threading.Event()
    proc = None
    watcher = None
    try:
        with tempfile.TemporaryFile(mode='w+b', dir=folder) as error:
            proc = subprocess.Popen(command(source, temp, video['index'], small),
                                    stdout=subprocess.PIPE, stderr=error, text=True,
                                    encoding='utf-8', errors='replace', creationflags=CREATE_NO_WINDOW)

            def watch():
                while not finished.wait(0.1):
                    if cancel.is_set():
                        try:
                            proc.kill()
                        except OSError:
                            pass
                        return

            watcher = threading.Thread(target=watch, daemon=True)
            watcher.start()
            for line in proc.stdout:
                if line.startswith('out_time_us=') and duration > 0 and progress_cb:
                    try:
                        fraction = int(line.partition('=')[2]) / 1e6 / duration
                    except ValueError:
                        continue
                    progress_cb(min(0.99, max(0, fraction)))
            proc.wait()
            if cancel.is_set():
                raise ConversionCancelled()
            if proc.returncode:
                error.seek(0)
                raise FFmpegError(error.read().decode('utf-8', errors='replace')[-4000:])
        check, v = probe(temp)
        audio = [s for s in check['streams'] if s['codec_type'] == 'audio']
        if v['codec_name'] != 'h264' or v.get('pix_fmt') != 'yuv420p' or any(s['codec_name'] != 'aac' for s in audio):
            raise FFmpegError('输出编码验证失败')
        if cancel.is_set():
            raise ConversionCancelled()
        # A hard link publishes the completed file without replacing an existing path.
        number = 0
        while True:
            suffix = f'_{number}' if number else ''
            target = folder / f'{source.stem}_微信兼容{suffix}.mp4'
            try:
                os.link(temp, target)
                break
            except FileExistsError:
                number += 1
            except OSError:
                # FAT/exFAT output volumes do not support hard links.
                try:
                    destination = target.open('xb')
                except FileExistsError:
                    number += 1
                    continue
                try:
                    with destination, open(temp, 'rb') as source_file:
                        shutil.copyfileobj(source_file, destination)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
                break
        if progress_cb:
            progress_cb(1)
        return str(target)
    finally:
        finished.set()
        if proc:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()
        if watcher:
            watcher.join()
        Path(temp).unlink(missing_ok=True)
