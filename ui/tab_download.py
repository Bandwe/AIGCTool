# -*- coding: utf-8 -*-
"""视频下载标签页（B站 / YouTube，自动识别）。"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core import downloader


class DownloadTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master)
        self.ctx = ctx
        self._buttons = []
        self._build()
        ctx.on_busy_change(self._on_busy)

    def _build(self):
        pad = {"padx": 8, "pady": 4}

        tip = ttk.Label(self, text="每行一个链接，自动识别 B站 / YouTube。"
                                   "B站需要 cookies.txt（否则可能 HTTP 412）。")
        tip.pack(anchor="w", padx=8, pady=(8, 0))

        box = ttk.LabelFrame(self, text="视频链接（每行一个）")
        box.pack(fill="both", expand=True, **pad)
        self.urls = tk.Text(box, height=6, wrap="none")
        self.urls.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.urls.yview)
        self.urls.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        ck = ttk.LabelFrame(self, text="Cookie 文件（B站 / 会员或年龄限制视频需要，留空自动查找）")
        ck.pack(fill="x", **pad)
        self.cookie = tk.StringVar()
        ttk.Entry(ck, textvariable=self.cookie).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(ck, text="选择...", command=self._pick_cookie).pack(side="left", padx=6)

        out = ttk.LabelFrame(self, text="保存目录")
        out.pack(fill="x", **pad)
        self.out_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        ttk.Entry(out, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(out, text="选择...", command=self._pick_out).pack(side="left", padx=6)

        self.dl_btn = ttk.Button(self, text="开始下载", command=self._start)
        self.dl_btn.pack(pady=8)
        self._buttons.append(self.dl_btn)

        if not self.ctx.deps.get("yt-dlp", (True, "", ""))[0]:
            self.dl_btn.config(state="disabled")
            ttk.Label(self, text="⚠ 未检测到 yt-dlp，下载不可用：pip install -U yt-dlp",
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
        if not self.ctx.deps.get("yt-dlp", (True, "", ""))[0]:
            return
        for b in self._buttons:
            b.config(state="disabled" if busy else "normal")

    def _start(self):
        text = self.urls.get("1.0", "end")
        urls = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not urls:
            messagebox.showwarning("提示", "请至少输入一个视频链接。")
            return
        out_dir = self.out_dir.get().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        cookie = self.cookie.get().strip()
        self.ctx.run_background(lambda: self._run(urls, out_dir, cookie))

    def _run(self, urls, out_dir, cookie):
        log, prog = self.ctx.log, self.ctx.set_progress
        try:
            downloader.download(urls, out_dir, cookie=cookie, log=log, progress_cb=prog)
        except Exception as e:
            log(f"✗ 下载出错：{e}")
        finally:
            prog(1.0)
