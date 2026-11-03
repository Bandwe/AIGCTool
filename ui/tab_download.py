# -*- coding: utf-8 -*-
"""Two-stage download UI. Detection never starts a media download."""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core import downloader, download_catalog


class DownloadTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master)
        self.ctx = ctx
        self.cancel = threading.Event()
        self.active = False
        self.resources = {}
        self.chosen = {}
        self._probe_key = None
        self._inputs_widgets = []
        self._build()
        ctx.on_busy_change(self._on_busy)
        self._on_busy(False)

    def _build(self):
        pad = {"padx": 8, "pady": 3}
        box = ttk.LabelFrame(self, text="视频 / 音乐链接或分享文本")
        box.pack(fill="x", **pad)
        self.urls = tk.Text(box, height=3, wrap="word")
        self.urls.pack(side="left", fill="both", expand=True, padx=6, pady=4)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.urls.yview)
        self.urls.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._inputs_widgets.append((self.urls, "normal"))
        self.playlist = tk.BooleanVar(value=False)
        scope = ttk.Checkbutton(self, text="检测全部分 P / 播放列表", variable=self.playlist)
        scope.pack(anchor="w", **pad)
        self._inputs_widgets.append((scope, "normal"))

        form = ttk.Frame(self)
        form.pack(fill="x", **pad)
        form.columnconfigure(1, weight=1)
        self.cookie = tk.StringVar()
        self.out_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        for row, (label, variable, command) in enumerate((
                ("Cookie 文件", self.cookie, self._pick_cookie),
                ("保存目录", self.out_dir, self._pick_out))):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            entry = ttk.Entry(form, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", padx=6, pady=3)
            button = ttk.Button(form, text="选择...", command=command)
            button.grid(row=row, column=2, pady=3)
            self._inputs_widgets.extend(((entry, "normal"), (button, "normal")))
        ttk.Label(form, text="网络").grid(row=2, column=0, sticky="w", pady=3)
        network = ttk.Frame(form)
        network.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(6, 0))
        self.network = tk.StringVar(value="自动")
        self.proxy = tk.StringVar()
        modes = ttk.Combobox(network, textvariable=self.network, values=("自动", "直连", "自定义代理"),
                             state="readonly", width=12)
        modes.pack(side="left", pady=3)
        self.proxy_entry = ttk.Entry(network, textvariable=self.proxy, state="disabled")
        self.proxy_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._inputs_widgets.append((modes, "readonly"))

        results = ttk.Frame(self)
        results.pack(fill="both", expand=True, **pad)
        self.table = ttk.Treeview(results, columns=("title", "platform", "duration", "quality"),
                                  show="headings", selectmode="browse", height=5)
        for name, label, width in (("title", "资源", 230), ("platform", "平台", 85),
                                   ("duration", "全长", 60), ("quality", "已选品质", 250)):
            self.table.heading(name, text=label)
            self.table.column(name, width=width, minwidth=45, stretch=name in ("title", "quality"))
        self.table.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(results, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", self._show_choices)
        quality = ttk.Frame(self)
        quality.pack(fill="x", **pad)
        ttk.Label(quality, text="当前条目品质").pack(side="left")
        self.quality = ttk.Combobox(quality, state="disabled")
        self.quality.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.quality.bind("<<ComboboxSelected>>", self._choose)

        actions = ttk.Frame(self)
        actions.pack(pady=5)
        self.probe_btn = ttk.Button(actions, text="检测品质", command=self._detect)
        self.probe_btn.pack(side="left", padx=4)
        self.dl_btn = ttk.Button(actions, text="下载已选（0）", command=self._start, state="disabled")
        self.dl_btn.pack(side="left", padx=4)
        self.cancel_btn = ttk.Button(actions, text="取消", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=4)
        ttk.Button(actions, text="打开保存目录", command=self._open_output).pack(side="left", padx=4)
        for variable in (self.cookie, self.playlist, self.network, self.proxy):
            variable.trace_add("write", self._invalidate)
        self.urls.bind("<<Modified>>", self._text_changed)

    def _text_changed(self, _=None):
        if self.urls.edit_modified():
            self.urls.edit_modified(False)
            self._invalidate()

    def _invalidate(self, *_):
        self._probe_key = None
        self.resources.clear()
        self.chosen.clear()
        self.table.delete(*self.table.get_children())
        self.quality.set("")
        self._refresh()

    def _snapshot(self):
        urls = tuple(downloader.extract_urls(self.urls.get("1.0", "end")))
        cookie = self.cookie.get().strip()
        stat = os.stat(cookie) if cookie else None
        stamp = (stat.st_mtime_ns, stat.st_size) if stat else None
        network = {"自动": "auto", "直连": "direct", "自定义代理": "custom"}[self.network.get()]
        proxy = self.proxy.get().strip() if network == "custom" else ""
        return urls, cookie, stamp, self.playlist.get(), network, proxy

    def _refresh(self):
        busy = self.ctx.busy
        ready = self.ctx.deps.get("yt-dlp", (False, "", ""))[0]
        self.probe_btn.config(state="disabled" if busy or not ready else "normal")
        self.dl_btn.config(text=f"下载已选（{len(self.chosen)}）",
                           state="normal" if self.chosen and not busy and self._probe_key else "disabled")
        self.quality.config(state="readonly" if self.table.selection() and not busy else "disabled")
        self.proxy_entry.config(state="normal" if self.network.get() == "自定义代理" and not busy else "disabled")

    def _on_busy(self, busy):
        if not busy:
            self.active = False
        for widget, state in self._inputs_widgets:
            widget.config(state="disabled" if busy else state)
        self.cancel_btn.config(state="normal" if self.active and busy else "disabled")
        self._refresh()

    def _show_choices(self, _=None):
        selected = self.table.selection()
        if selected and selected[0] in self.resources:
            key = selected[0]
            self.quality.config(values=("不下载",) + tuple(c.label for c in self.resources[key].choices))
            self.quality.set(self.chosen[key].label if key in self.chosen else "不下载")
        self._refresh()

    def _choose(self, _=None):
        selected = self.table.selection()
        if not selected or self.ctx.busy:
            return
        key = selected[0]
        index = self.quality.current()
        if index > 0:
            choice = self.resources[key].choices[index - 1]
            if choice.preview:
                messagebox.showwarning("仅有试听权限", "该品质只有试听片段。请选择有该曲完整权限的 Cookie 后重新检测。")
                self._show_choices()
                return
            self.chosen[key] = choice
        else:
            self.chosen.pop(key, None)
        self.table.set(key, "quality", self.chosen[key].label if key in self.chosen else "未选择")
        self._refresh()

    def _detect(self):
        if self.ctx.busy:
            return
        try:
            key = self._snapshot()
            urls, cookie, _, playlist, network, proxy = key
            if not urls:
                raise ValueError("请输入视频或音乐链接。")
            options = downloader.DownloadOptions(playlist=playlist, network=network)
            options.validate(proxy)
            downloader._validate_proxy(proxy)
        except (ValueError, OSError) as exc:
            messagebox.showwarning("检测设置", str(exc))
            return
        self._invalidate()
        self.cancel.clear()
        self.active = True
        def work():
            try:
                results = download_catalog.probe(urls, cookie, options, proxy, self.ctx.log, self.cancel)
                self.ctx.call_on_ui(lambda: self._show_results(key, results))
            except Exception as exc:
                self.ctx.log(downloader.safe_message(str(exc)))
        self.ctx.run_background(work)

    def _show_results(self, key, results):
        try:
            if self.cancel.is_set() or key != self._snapshot():
                return
        except OSError:
            self.ctx.log("Cookie 文件已变化，请重新选择并检测。")
            return
        self._probe_key = key
        names = {"bilibili": "B站", "youtube": "YouTube", "douyin": "抖音",
                 "xiaohongshu": "小红书", "netease": "网易云音乐"}
        for index, resource in enumerate(results):
            ident = str(index)
            self.resources[ident] = resource
            seconds = int(resource.duration)
            self.table.insert("", "end", iid=ident, values=(resource.title, names.get(resource.platform, resource.platform),
                              f"{seconds // 60}:{seconds % 60:02}" if seconds else "未知", "未选择"))
        if results:
            self.table.selection_set("0")
        self.ctx.log(f"检测结束：{len(results)} 个资源。请选择品质后点击下载。")
        self._refresh()

    def _start(self):
        if self.ctx.busy or not self.chosen:
            return
        try:
            if self._snapshot() != self._probe_key:
                self._invalidate()
                raise ValueError("链接、Cookie 或网络设置已变化，请重新检测品质。")
            _, cookie, _, _, network, proxy = self._probe_key
            base = downloader.DownloadOptions(network=network)
            tasks = [(self.resources[key], self.resources[key].options_for(choice, base)) for key, choice in self.chosen.items()]
        except (ValueError, OSError) as exc:
            messagebox.showwarning("下载设置", str(exc))
            return
        out_dir = self.out_dir.get().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        self.cancel.clear()
        self.active = True
        def work():
            ok = 0
            try:
                for resource, options in tasks:
                    if self.cancel.is_set():
                        break
                    count, _ = downloader.download([resource.url], out_dir, cookie=cookie, log=self.ctx.log,
                        progress_cb=self.ctx.set_progress, proxy=proxy, options=options, cancel=self.cancel)
                    ok += count
                self.ctx.log(f"已选资源完成：{ok}/{len(tasks)}。")
            except Exception as exc:
                self.ctx.log("下载出错：" + downloader.safe_message(str(exc)))
        self.ctx.run_background(work)

    def _pick_cookie(self):
        path = filedialog.askopenfilename(title="选择 Netscape cookies.txt", filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if path:
            self.cookie.set(path)

    def _pick_out(self):
        path = filedialog.askdirectory(title="选择保存目录")
        if path:
            self.out_dir.set(path)

    def _cancel(self):
        self.cancel.set()
        self.cancel_btn.config(state="disabled")
        self.ctx.log("正在取消，等待当前请求结束...")

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
        elif sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
