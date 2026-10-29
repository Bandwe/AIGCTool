# -*- coding: utf-8 -*-
"""Video download controls. All Tk values are captured before starting work."""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core import downloader


class DownloadTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master)
        self.ctx = ctx
        self.cancel = threading.Event()
        self.active = False
        self._buttons = []
        self._build()
        ctx.on_busy_change(self._on_busy)

    def _build(self):
        pad = {"padx": 8, "pady": 4}

        box = ttk.LabelFrame(self, text="视频链接 / 分享文本")
        box.pack(fill="both", expand=True, **pad)
        self.urls = tk.Text(box, height=4, wrap="word")
        self.urls.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.urls.yview)
        self.urls.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        quality = ttk.Frame(self)
        quality.pack(fill="x", **pad)
        ttk.Label(quality, text="画质下限").pack(side="left")
        self.minimum = tk.StringVar(value="720p")
        ttk.Combobox(quality, textvariable=self.minimum, values=("720p", "1080p", "1440p", "2160p"),
                     state="readonly", width=8).pack(side="left", padx=6)
        self.allow_lower = tk.BooleanVar(value=False)
        ttk.Checkbutton(quality, text="允许低于下限（保留源分辨率）", variable=self.allow_lower).pack(side="left")

        scope = ttk.Frame(self)
        scope.pack(fill="x", **pad)
        ttk.Label(scope, text="下载范围").pack(side="left")
        self.playlist = tk.BooleanVar(value=False)
        ttk.Radiobutton(scope, text="单视频", variable=self.playlist, value=False).pack(side="left", padx=6)
        ttk.Radiobutton(scope, text="全部分 P / 播放列表", variable=self.playlist, value=True).pack(side="left")

        ck = ttk.LabelFrame(self, text="Cookie 文件（选择自己的 cookies.txt；留空尝试公开访问）")
        ck.pack(fill="x", **pad)
        self.cookie = tk.StringVar()
        ttk.Entry(ck, textvariable=self.cookie).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(ck, text="选择...", command=self._pick_cookie).pack(side="left", padx=6)

        network = ttk.LabelFrame(self, text="网络")
        network.pack(fill="x", **pad)
        self.proxy = tk.StringVar()
        self.network = tk.StringVar(value="自动")
        modes = ttk.Combobox(network, textvariable=self.network, values=("自动", "直连", "自定义代理"),
                             state="readonly", width=12)
        modes.pack(side="left", padx=6, pady=6)
        self.proxy_entry = ttk.Entry(network, textvariable=self.proxy, state="disabled")
        self.proxy_entry.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        modes.bind("<<ComboboxSelected>>", lambda _: self.proxy_entry.config(
            state="normal" if self.network.get() == "自定义代理" else "disabled"))

        out = ttk.LabelFrame(self, text="保存目录")
        out.pack(fill="x", **pad)
        self.out_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        ttk.Entry(out, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(out, text="选择...", command=self._pick_out).pack(side="left", padx=6)

        actions = ttk.Frame(self)
        actions.pack(pady=6)
        self.dl_btn = ttk.Button(actions, text="开始 / 继续下载", command=self._start)
        self.dl_btn.pack(side="left", padx=4)
        self.cancel_btn = ttk.Button(actions, text="取消", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=4)
        ttk.Button(actions, text="打开保存目录", command=self._open_output).pack(side="left", padx=4)
        self._buttons.append(self.dl_btn)

        if not self.ctx.deps.get("yt-dlp", (True, "", ""))[0]:
            self.dl_btn.config(state="disabled")
            ttk.Label(self, text="请先点击顶部「安装 / 更新下载工具」。",
                      foreground="#b91c1c").pack()

    def _pick_cookie(self):
        f = filedialog.askopenfilename(title="选择 cookies.txt",
                                       filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if f:
            self.cookie.set(f)

    def _pick_out(self):
        d = filedialog.askdirectory(title="选择保存目录")
        if d:
            self.out_dir.set(d)

    def _on_busy(self, busy):
        if not busy:
            self.active = False
        ready = self.ctx.deps.get("yt-dlp", (False, "", ""))[0]
        for b in self._buttons:
            b.config(state="disabled" if busy or not ready else "normal")
        self.cancel_btn.config(state="normal" if self.active and busy else "disabled")

    def _cancel(self):
        self.cancel.set()
        self.cancel_btn.config(state="disabled")
        self.ctx.log("正在取消下载，等待当前网络请求结束并保留续传文件...")

    def on_close(self):
        if self.active:
            if not self.cancel.is_set():
                self._cancel()
            return False
        return True

    def _open_output(self):
        path = os.path.abspath(os.path.expanduser(self.out_dir.get().strip()))
        if not os.path.isdir(path):
            messagebox.showwarning("保存目录", "目录尚不存在。")
            return
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])

    def _start(self):
        if self.ctx.busy:
            return
        text = self.urls.get("1.0", "end")
        urls = downloader.extract_urls(text)
        if not urls:
            messagebox.showwarning("提示", "请至少输入一个视频链接。")
            return
        out_dir = self.out_dir.get().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        cookie = self.cookie.get().strip()
        network = {"自动": "auto", "直连": "direct", "自定义代理": "custom"}[self.network.get()]
        proxy = self.proxy.get().strip() if network == "custom" else ""
        options = downloader.DownloadOptions(int(self.minimum.get()[:-1]), self.allow_lower.get(),
                                             self.playlist.get(), network)
        try:
            options.validate(proxy)
            downloader._validate_proxy(proxy)
        except ValueError as exc:
            messagebox.showwarning("下载设置", str(exc))
            return
        self.cancel.clear()
        self.active = True
        self.ctx.run_background(lambda: self._run(urls, out_dir, cookie, proxy, options))

    def _run(self, urls, out_dir, cookie, proxy, options):
        log, prog = self.ctx.log, self.ctx.set_progress
        try:
            downloader.download(urls, out_dir, cookie=cookie, log=log, progress_cb=prog, proxy=proxy,
                                options=options, cancel=self.cancel)
        except Exception as e:
            log("下载出错：" + downloader.safe_message(str(e)))
