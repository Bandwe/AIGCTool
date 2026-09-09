"""WeChat compatible video conversion tab."""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog

from core.converter import convert, ConversionCancelled
from .widgets import DropList, expand_paths


class ConvertTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master)
        self.ctx = ctx
        self.cancel = threading.Event()
        self.finished = threading.Event()
        self.finished.set()
        self.active = False
        self.last_dir = None
        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=8, pady=6)
        self.add_btn = ttk.Button(bar, text='添加视频', command=self.pick)
        self.add_btn.pack(side='left')
        self.files = DropList(self, '拖入视频或文件夹', height=7)
        self.clear_btn = ttk.Button(bar, text='清空列表', command=self.files.clear)
        self.clear_btn.pack(side='left', padx=6)
        ttk.Button(bar, text='打开输出目录', command=self.open_output).pack(side='right')
        self.files.pack(fill='both', expand=True, padx=8)
        self.mode = tk.StringVar(value='清晰优先（最长边1920）')
        self.mode_box = ttk.Combobox(self, textvariable=self.mode, state='readonly',
                                    values=['清晰优先（最长边1920）', '体积优先（最长边1280）'])
        self.mode_box.pack(fill='x', padx=8, pady=6)
        row = ttk.Frame(self)
        row.pack(fill='x', padx=8, pady=4)
        ttk.Label(row, text='输出目录（留空为源视频目录）').pack(side='left')
        self.output = tk.StringVar()
        ttk.Entry(row, textvariable=self.output).pack(side='left', fill='x', expand=True, padx=6)
        ttk.Button(row, text='选择', command=self.pick_output).pack(side='right')
        actions = ttk.Frame(self)
        actions.pack(pady=6)
        self.start_btn = ttk.Button(actions, text='开始转换', command=self.start)
        self.start_btn.pack(side='left', padx=4)
        self.cancel_btn = ttk.Button(actions, text='取消任务', command=self.cancel.set, state='disabled')
        self.cancel_btn.pack(side='left', padx=4)
        self.status = tk.StringVar(value='就绪')
        ttk.Label(self, textvariable=self.status).pack(pady=4)
        ctx.on_busy_change(self.on_busy)

    def pick(self):
        self.files.add(expand_paths(filedialog.askopenfilenames(title='选择视频')))

    def pick_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output.set(path)

    def open_output(self):
        path = self.last_dir or self.output.get() or (os.path.dirname(self.files.paths[0]) if self.files.paths else '')
        if not os.path.isdir(path):
            return
        if sys.platform == 'win32':
            os.startfile(path)
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])

    def on_busy(self, busy):
        for button in (self.start_btn, self.add_btn, self.clear_btn):
            button.configure(state='disabled' if busy else 'normal')
        self.cancel_btn.configure(state='normal' if busy and self.active else 'disabled')
        self.mode_box.configure(state='disabled' if busy else 'readonly')

    def start(self):
        if self.ctx.busy:
            return
        paths = list(dict.fromkeys(os.path.normcase(os.path.abspath(p)) for p in self.files.paths))
        if not paths:
            self.status.set('请添加视频')
            return
        out_dir = self.output.get().strip() or None
        small = self.mode.get().startswith('体积')
        self.cancel.clear()
        self.active = True
        self.finished.clear()
        self.ctx.set_progress(0)

        def work():
            done = failed = 0
            try:
                for i, path in enumerate(paths):
                    if self.cancel.is_set():
                        break
                    self.ctx.call_on_ui(lambda i=i: self.status.set(f'正在转换 {i+1}/{len(paths)}'))
                    try:
                        result = convert(path, out_dir, small, self.cancel,
                                         lambda f, i=i: self.ctx.set_progress((i+f)/len(paths)))
                        done += 1
                        self.ctx.log(f'转换完成：{result}')
                        self.ctx.call_on_ui(lambda r=result: setattr(self, 'last_dir', os.path.dirname(r)))
                    except ConversionCancelled:
                        break
                    except Exception as exc:
                        failed += 1
                        self.ctx.log(f'转换失败：{path}\n{exc}')
            finally:
                text = f'{"已取消" if self.cancel.is_set() else "处理完成"}：成功 {done}，失败 {failed}'
                self.ctx.call_on_ui(lambda: self.status.set(text))
                self.ctx.call_on_ui(lambda: setattr(self, 'active', False))
                self.finished.set()
        if not self.ctx.run_background(work):
            self.active = False
            self.finished.set()

    def on_close(self):
        self.cancel.set()
        if self.active:
            self.finished.wait(3)
