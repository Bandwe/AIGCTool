# -*- coding: utf-8 -*-
"""
屏幕录制引擎（移植自原 video/recorder.py 的 ScreenRecorder）。

纯引擎，不含界面：用 mss 抓屏、OpenCV 写 mp4。区域选择 UI 在 ui 层。
"""

import os
import time
import threading

import cv2
import numpy as np
import mss


class ScreenRecorder:
    """核心录制引擎：抓取指定区域，按 fps 写入 mp4。"""

    def __init__(self):
        self.recording = False
        self.paused = False
        self.writer = None
        self.region = None
        self.fps = 30
        self.output_path = ""
        self.frame_count = 0
        self.start_time = 0
        self.pause_duration = 0
        self._pause_start = 0
        self._thread = None

    def start(self, region, fps, output_path):
        self.region = region
        self.fps = fps
        self.output_path = output_path
        self.frame_count = 0
        self.pause_duration = 0
        self.recording = True
        self.paused = False

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(
            output_path, fourcc, fps,
            (region["width"], region["height"]),
        )
        self.start_time = time.time()

        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def _record_loop(self):
        interval = 1.0 / self.fps
        with mss.mss() as sct:
            while self.recording:
                if self.paused:
                    time.sleep(0.05)
                    continue
                loop_start = time.time()
                img = sct.grab(self.region)
                frame = np.array(img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                self.writer.write(frame)
                self.frame_count += 1
                sleep_time = interval - (time.time() - loop_start)
                if sleep_time > 0:
                    time.sleep(sleep_time)

    def pause(self):
        if self.recording and not self.paused:
            self.paused = True
            self._pause_start = time.time()

    def resume(self):
        if self.recording and self.paused:
            self.pause_duration += time.time() - self._pause_start
            self.paused = False

    def stop(self):
        self.recording = False
        if self._thread:
            self._thread.join(timeout=2)
        if self.writer:
            self.writer.release()
            self.writer = None

    def get_elapsed(self):
        if not self.recording:
            return 0
        return time.time() - self.start_time - self.pause_duration

    def get_file_size(self):
        if self.output_path and os.path.exists(self.output_path):
            size = os.path.getsize(self.output_path)
            if size < 1024 * 1024:
                return f"{size / 1024:.1f} KB"
            return f"{size / (1024 * 1024):.1f} MB"
        return "0 KB"
