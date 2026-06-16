# -*- coding: utf-8 -*-
"""共享界面组件：拖拽文件列表 DropList。"""

import os
import tkinter as tk
from tkinter import ttk

from core import splitter

# 拖拽支持（tkinterdnd2）。装不上时自动降级为只用按钮选择。
try:
    from tkinterdnd2 import DND_FILES
    DND_AVAILABLE = True
except Exception:
    DND_FILES = None
    DND_AVAILABLE = False


def expand_paths(paths, only_videos=True):
    """把拖入/选中的混合路径展开成视频文件列表（文件夹自动展开、去重保序）。"""
    result = []
    for p in paths:
        p = p.strip()
        if not p:
            continue
        if os.path.isdir(p):
            result.extend(splitter.find_videos(p))
        elif os.path.isfile(p) and (not only_videos or splitter.is_video(p)):
            result.append(p)
    seen, uniq = set(), []
    for p in result:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


class DropList(ttk.Frame):
    """带拖拽提示的文件列表区：上方拖拽提示 + 下方文件列表。"""

    def __init__(self, master, hint, on_change=None, height=8):
        super().__init__(master)
        self.on_change = on_change
        self.paths = []

        self.drop = tk.Label(
            self, text=hint, height=2, relief="ridge", bd=2,
            bg="#f3f4f6", fg="#374151", cursor="hand2", justify="center",
        )
        self.drop.pack(fill="x", padx=2, pady=(2, 4))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(body, selectmode="extended",
                                  activestyle="none", height=height)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        if DND_AVAILABLE:
            for w in (self.drop, self.listbox):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self._on_drop)
                except Exception:
                    pass

    def _on_drop(self, event):
        paths = self.winfo_toplevel().tk.splitlist(event.data)
        self.add(expand_paths(paths))

    def add(self, paths):
        for p in paths:
            if p not in self.paths:
                self.paths.append(p)
                self.listbox.insert("end", os.path.basename(p))
        if self.on_change:
            self.on_change()

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            del self.paths[i]
            self.listbox.delete(i)
        if self.on_change:
            self.on_change()

    def clear(self):
        self.paths.clear()
        self.listbox.delete(0, "end")
        if self.on_change:
            self.on_change()

    def move(self, delta):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        if delta < 0 and sel[0] == 0:
            return
        if delta > 0 and sel[-1] == len(self.paths) - 1:
            return
        order = sel if delta < 0 else list(reversed(sel))
        for i in order:
            j = i + delta
            self.paths[i], self.paths[j] = self.paths[j], self.paths[i]
            t = self.listbox.get(i)
            self.listbox.delete(i)
            self.listbox.insert(j, t)
        self.listbox.selection_clear(0, "end")
        for i in sel:
            self.listbox.selection_set(i + delta)
        if self.on_change:
            self.on_change()
