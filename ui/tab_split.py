# -*- coding: utf-8 -*-
"""拆分 / 合并标签页。"""

import os
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core import splitter
from .widgets import DropList, expand_paths, DND_AVAILABLE


class SplitTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master)
        self.ctx = ctx
        self._buttons = []

        inner = ttk.Notebook(self)
        inner.pack(fill="both", expand=True, padx=4, pady=4)
        self._build_split(inner)
        self._build_merge(inner)

        ctx.on_busy_change(self._on_busy)

    # ---------- 拆分 ----------
    def _build_split(self, nb):
        tab = ttk.Frame(nb)
        nb.add(tab, text="  拆分  ")

        hint = "把视频文件或文件夹拖到这里" if DND_AVAILABLE else "（拖拽不可用，请用下方按钮选择）"
        self.split_list = DropList(tab, hint)
        self.split_list.pack(fill="both", expand=True, padx=4, pady=4)

        btns = ttk.Frame(tab)
        btns.pack(fill="x", padx=4)
        ttk.Button(btns, text="选择文件", command=self._pick_split_files).pack(side="left")
        ttk.Button(btns, text="选择文件夹", command=self._pick_split_folder).pack(side="left", padx=4)
        ttk.Button(btns, text="移除所选", command=self.split_list.remove_selected).pack(side="left")
        ttk.Button(btns, text="清空", command=self.split_list.clear).pack(side="left", padx=4)

        opt = ttk.Frame(tab)
        opt.pack(fill="x", padx=4, pady=8)
        self.mode = tk.StringVar(value="duration")
        ttk.Radiobutton(opt, text="按固定时长", variable=self.mode,
                        value="duration", command=self._sync_mode).pack(side="left")
        ttk.Radiobutton(opt, text="按段数", variable=self.mode,
                        value="count", command=self._sync_mode).pack(side="left", padx=(8, 16))
        self.value = tk.StringVar(value="30")
        ttk.Entry(opt, textvariable=self.value, width=8).pack(side="left")
        self.unit = ttk.Label(opt, text="秒/段")
        self.unit.pack(side="left", padx=6)

        self.split_btn = ttk.Button(tab, text="开始拆分", command=self._start_split)
        self.split_btn.pack(pady=4)
        self._buttons.append(self.split_btn)

    def _sync_mode(self):
        self.unit.config(text="秒/段" if self.mode.get() == "duration" else "段")

    def _pick_split_files(self):
        files = filedialog.askopenfilenames(title="选择视频文件")
        if files:
            self.split_list.add(expand_paths(files))

    def _pick_split_folder(self):
        folder = filedialog.askdirectory(title="选择文件夹（批量处理里面所有视频）")
        if folder:
            vids = splitter.find_videos(folder)
            if not vids:
                messagebox.showinfo("提示", "该文件夹里没有找到视频文件。")
            self.split_list.add(vids)

    # ---------- 合并 ----------
    def _build_merge(self, nb):
        tab = ttk.Frame(nb)
        nb.add(tab, text="  合并  ")

        hint = ("把要合并的视频拖到这里（按列表从上到下的顺序拼接）"
                if DND_AVAILABLE else "（拖拽不可用，请用下方按钮选择）")
        self.merge_list = DropList(tab, hint)
        self.merge_list.pack(fill="both", expand=True, padx=4, pady=4)

        btns = ttk.Frame(tab)
        btns.pack(fill="x", padx=4)
        ttk.Button(btns, text="选择文件", command=self._pick_merge_files).pack(side="left")
        ttk.Button(btns, text="选择文件夹", command=self._pick_merge_folder).pack(side="left", padx=4)
        ttk.Button(btns, text="↑ 上移", command=lambda: self.merge_list.move(-1)).pack(side="left")
        ttk.Button(btns, text="↓ 下移", command=lambda: self.merge_list.move(1)).pack(side="left", padx=4)
        ttk.Button(btns, text="移除所选", command=self.merge_list.remove_selected).pack(side="left")
        ttk.Button(btns, text="清空", command=self.merge_list.clear).pack(side="left", padx=4)

        self.merge_btn = ttk.Button(tab, text="开始合并", command=self._start_merge)
        self.merge_btn.pack(pady=10)
        self._buttons.append(self.merge_btn)

    def _pick_merge_files(self):
        files = filedialog.askopenfilenames(title="选择要合并的视频")
        if files:
            self.merge_list.add(expand_paths(files))

    def _pick_merge_folder(self):
        folder = filedialog.askdirectory(title="选择文件夹（按文件名顺序合并里面所有视频）")
        if folder:
            self.merge_list.add(splitter.find_videos(folder))

    # ---------- 执行 ----------
    def _on_busy(self, busy):
        state = "disabled" if busy else "normal"
        for b in self._buttons:
            b.config(state=state)

    def _start_split(self):
        files = list(self.split_list.paths)
        if not files:
            messagebox.showwarning("提示", "请先添加要拆分的视频。")
            return
        try:
            num = float(self.value.get())
        except ValueError:
            messagebox.showwarning("提示", "请输入有效的数字。")
            return
        if num <= 0:
            messagebox.showwarning("提示", "数值必须大于 0。")
            return
        mode = self.mode.get()
        self.ctx.run_background(lambda: self._run_split(files, mode, num))

    def _run_split(self, files, mode, num):
        total = len(files)
        ok = 0
        log, prog = self.ctx.log, self.ctx.set_progress
        try:
            for idx, f in enumerate(files, 1):
                name = os.path.basename(f)
                cb = lambda fr, i=idx: prog(((i - 1) + fr) / total)
                if mode == "duration":
                    log(f"[{idx}/{total}] 按 {num:g} 秒拆分：{name}")
                    parts = splitter.split_by_duration(f, num, progress_cb=cb)
                else:
                    log(f"[{idx}/{total}] 拆成 {int(num)} 段：{name}")
                    parts = splitter.split_by_count(f, int(num), progress_cb=cb)
                out_dir = os.path.dirname(parts[0]) if parts else ""
                log(f"      ✓ 生成 {len(parts)} 段 → {out_dir}")
                ok += 1
        except Exception as e:
            log(f"      ✗ 出错：{e}")
        finally:
            prog(1.0)
            log(f"拆分完成：成功 {ok}/{total} 个文件。")

    def _start_merge(self):
        files = list(self.merge_list.paths)
        if len(files) < 2:
            messagebox.showwarning("提示", "请至少添加 2 个视频再合并。")
            return
        ext = os.path.splitext(files[0])[1] or ".mp4"
        out = filedialog.asksaveasfilename(
            title="保存合并后的视频", defaultextension=ext,
            initialfile="合并结果" + ext, initialdir=os.path.dirname(files[0]),
        )
        if not out:
            return
        self.ctx.run_background(lambda: self._run_merge(files, out))

    def _run_merge(self, files, out):
        log, prog = self.ctx.log, self.ctx.set_progress
        try:
            log(f"按顺序合并 {len(files)} 个视频：")
            for i, f in enumerate(files, 1):
                log(f"   {i}. {os.path.basename(f)}")
            splitter.merge(files, out, progress_cb=prog)
            log(f"✓ 合并完成 → {out}")
        except Exception as e:
            log(f"✗ 合并失败：{e}")
        finally:
            prog(1.0)
