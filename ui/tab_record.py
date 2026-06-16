# -*- coding: utf-8 -*-
"""屏幕录制标签页（区域框选 + 全局热键 Ctrl+F9 / Ctrl+F10）。"""

import os
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import mss
from pynput import keyboard

from core.recorder import ScreenRecorder


class RegionSelector:
    """全屏半透明窗口，用于框选录制区域。"""

    def __init__(self, parent, callback):
        self.callback = callback
        self.start_x = 0
        self.start_y = 0
        self.rect = None

        self.win = tk.Toplevel(parent)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.3)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        self.win.config(cursor="crosshair")

        self.canvas = tk.Canvas(self.win, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Escape>", lambda e: self._cancel())

        self.canvas.create_text(
            self.win.winfo_screenwidth() // 2, 40,
            text="拖动鼠标选择录制区域  |  ESC 取消",
            fill="white", font=("Microsoft YaHei UI", 16),
        )

    def _on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="red", width=2,
        )

    def _on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def _on_release(self, event):
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        w, h = x2 - x1, y2 - y1
        self.win.destroy()
        if w > 10 and h > 10:
            w = w if w % 2 == 0 else w + 1
            h = h if h % 2 == 0 else h + 1
            self.callback({"left": x1, "top": y1, "width": w, "height": h})
        else:
            self.callback(None)

    def _cancel(self):
        self.win.destroy()
        self.callback(None)


class RecordTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master)
        self.ctx = ctx
        self.root = ctx.root
        self.recorder = ScreenRecorder()
        self.selected_region = None
        self.hotkeys = None

        self._build()
        self._start_hotkeys()
        self._tick()

    def _build(self):
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=12, pady=10)

        area = ttk.LabelFrame(main, text="录制区域")
        area.pack(fill="x", pady=4)
        row = ttk.Frame(area)
        row.pack(fill="x", padx=8, pady=6)
        self.region_label = ttk.Label(row, text="全屏")
        self.region_label.pack(side="left")
        ttk.Button(row, text="选择区域", command=self._select_region).pack(side="right")
        ttk.Button(row, text="全屏", command=self._set_fullscreen).pack(side="right", padx=6)

        param = ttk.LabelFrame(main, text="参数")
        param.pack(fill="x", pady=4)
        r1 = ttk.Frame(param)
        r1.pack(fill="x", padx=8, pady=6)
        ttk.Label(r1, text="帧率 (FPS)").pack(side="left")
        self.fps_var = tk.StringVar(value="30")
        ttk.Combobox(r1, textvariable=self.fps_var, values=["15", "24", "30", "60"],
                     width=6, state="readonly").pack(side="left", padx=8)
        ttk.Label(r1, text="保存到").pack(side="left", padx=(16, 0))
        default_dir = os.path.join(os.path.expanduser("~"), "Videos")
        os.makedirs(default_dir, exist_ok=True)
        self.save_dir = tk.StringVar(value=default_dir)
        ttk.Button(r1, text="浏览...", command=self._choose_dir).pack(side="right")
        self.dir_label = ttk.Label(r1, text=self._short(default_dir))
        self.dir_label.pack(side="right", padx=8)

        timer = ttk.Frame(main)
        timer.pack(fill="x", pady=10)
        self.timer_label = ttk.Label(timer, text="00:00:00", font=("Consolas", 28, "bold"))
        self.timer_label.pack()
        info = ttk.Frame(timer)
        info.pack(fill="x", padx=20)
        self.frames_label = ttk.Label(info, text="帧数: 0")
        self.frames_label.pack(side="left")
        self.size_label = ttk.Label(info, text="大小: 0 KB")
        self.size_label.pack(side="right")

        ctrl = ttk.Frame(main)
        ctrl.pack(fill="x", pady=(6, 4))
        self.record_btn = ttk.Button(ctrl, text="● 开始录制", command=self._toggle_record)
        self.record_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.pause_btn = ttk.Button(ctrl, text="⏸ 暂停", command=self._toggle_pause, state="disabled")
        self.pause_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.status_label = ttk.Label(
            main, text="快捷键: Ctrl+F9 开始/停止  |  Ctrl+F10 暂停/继续",
            foreground="#6b7280")
        self.status_label.pack(pady=(8, 0))

    def _short(self, path, n=30):
        return path if len(path) <= n else "..." + path[-(n - 3):]

    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.save_dir.get())
        if d:
            self.save_dir.set(d)
            self.dir_label.config(text=self._short(d))

    def _set_fullscreen(self):
        self.selected_region = None
        self.region_label.config(text="全屏")

    def _select_region(self):
        self.root.iconify()
        self.root.after(300, self._open_selector)

    def _open_selector(self):
        def on_selected(region):
            self.root.deiconify()
            if region:
                self.selected_region = region
                self.region_label.config(
                    text=f"{region['width']}×{region['height']} @ ({region['left']},{region['top']})")
        RegionSelector(self.root, on_selected)

    def _get_region(self):
        if self.selected_region:
            return self.selected_region
        with mss.mss() as sct:
            mon = sct.monitors[1]
            w = mon["width"] - (mon["width"] % 2)
            h = mon["height"] - (mon["height"] % 2)
            return {"left": mon["left"], "top": mon["top"], "width": w, "height": h}

    def _toggle_record(self):
        if not self.recorder.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        region = self._get_region()
        fps = int(self.fps_var.get())
        filename = f"录制_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        path = os.path.join(self.save_dir.get(), filename)
        self.recorder.start(region, fps, path)
        self.record_btn.config(text="■ 停止录制")
        self.pause_btn.config(state="normal")
        self.status_label.config(text=f"正在录制: {filename}")
        self.ctx.log(f"▶ 开始录制 → {path}")
        self.root.iconify()

    def _stop_recording(self):
        self.recorder.stop()
        path = self.recorder.output_path
        self.record_btn.config(text="● 开始录制")
        self.pause_btn.config(text="⏸ 暂停", state="disabled")
        self.timer_label.config(text="00:00:00")
        self.frames_label.config(text="帧数: 0")
        self.root.deiconify()
        if os.path.exists(path) and os.path.getsize(path) > 0:
            self.status_label.config(text=f"已保存: {os.path.basename(path)}")
            self.ctx.log(f"✓ 录制已保存：{path}")
            if messagebox.askyesno("录制完成", f"视频已保存到:\n{path}\n\n是否打开所在文件夹?"):
                os.startfile(os.path.dirname(path))
        else:
            self.status_label.config(text="录制失败或文件为空")
            self.ctx.log("✗ 录制失败或文件为空")

    def _toggle_pause(self):
        if self.recorder.paused:
            self.recorder.resume()
            self.pause_btn.config(text="⏸ 暂停")
            self.status_label.config(text="继续录制...")
        else:
            self.recorder.pause()
            self.pause_btn.config(text="▶ 继续")
            self.status_label.config(text="已暂停")

    def _tick(self):
        if self.recorder.recording:
            elapsed = self.recorder.get_elapsed()
            h, m, s = int(elapsed // 3600), int((elapsed % 3600) // 60), int(elapsed % 60)
            self.timer_label.config(text=f"{h:02d}:{m:02d}:{s:02d}")
            self.frames_label.config(text=f"帧数: {self.recorder.frame_count}")
            self.size_label.config(text=f"大小: {self.recorder.get_file_size()}")
        self.root.after(500, self._tick)

    def _start_hotkeys(self):
        try:
            self.hotkeys = keyboard.GlobalHotKeys({
                "<ctrl>+<f9>": lambda: self.root.after(0, self._toggle_record),
                "<ctrl>+<f10>": lambda: self.root.after(0, self._toggle_pause),
            })
            self.hotkeys.daemon = True
            self.hotkeys.start()
        except Exception:
            self.hotkeys = None

    def on_close(self):
        if self.recorder.recording:
            self.recorder.stop()
        if self.hotkeys:
            self.hotkeys.stop()
