# -*- coding: utf-8 -*-
"""多分辨率导出标签页。"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core import exporter
from core.exporter import ExportOptions


class ExportTab(ttk.Frame):
    def __init__(self, master, ctx):
        super().__init__(master)
        self.ctx = ctx
        self._buttons = []
        self._build()
        ctx.on_busy_change(self._on_busy)

    def _build(self):
        pad = {"padx": 8, "pady": 4}

        # 源文件
        src = ttk.LabelFrame(self, text="源视频")
        src.pack(fill="x", **pad)
        self.source = tk.StringVar()
        ttk.Entry(src, textvariable=self.source).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(src, text="选择...", command=self._pick_source).pack(side="left", padx=6)

        # 分辨率
        res = ttk.LabelFrame(self, text="分辨率（可多选）")
        res.pack(fill="x", **pad)
        self.res_vars = {}
        for key in ("4K", "1080", "720"):
            v = tk.BooleanVar(value=True)
            w, h = exporter.SIZES[key]
            ttk.Checkbutton(res, text=f"{key} ({w}×{h})", variable=v).pack(side="left", padx=10, pady=6)
            self.res_vars[key] = v

        # 编码与参数
        enc = ttk.LabelFrame(self, text="编码")
        enc.pack(fill="x", **pad)
        row1 = ttk.Frame(enc)
        row1.pack(fill="x", padx=6, pady=4)
        ttk.Label(row1, text="编码").pack(side="left")
        self.codec = tk.StringVar(value="h265")
        codec_box = ttk.Combobox(row1, textvariable=self.codec, width=10, state="readonly",
                                 values=["h265", "prores"])
        codec_box.pack(side="left", padx=6)
        codec_box.bind("<<ComboboxSelected>>", lambda e: self._sync_codec())

        ttk.Label(row1, text="帧率").pack(side="left", padx=(16, 0))
        self.fps = tk.StringVar(value="25")
        ttk.Entry(row1, textvariable=self.fps, width=5).pack(side="left", padx=6)

        self.gpu = tk.BooleanVar(value=False)
        self.gpu_chk = ttk.Checkbutton(row1, text="GPU 加速 (NVENC)", variable=self.gpu)
        self.gpu_chk.pack(side="left", padx=(16, 0))

        self.h265_row = ttk.Frame(enc)
        self.h265_row.pack(fill="x", padx=6, pady=4)
        ttk.Label(self.h265_row, text="CRF").pack(side="left")
        self.crf = tk.StringVar(value="18")
        ttk.Entry(self.h265_row, textvariable=self.crf, width=5).pack(side="left", padx=6)
        ttk.Label(self.h265_row, text="preset").pack(side="left", padx=(16, 0))
        self.preset = tk.StringVar(value="medium")
        ttk.Combobox(self.h265_row, textvariable=self.preset, width=10, state="readonly",
                     values=["ultrafast", "veryfast", "faster", "fast", "medium",
                             "slow", "slower", "veryslow"]).pack(side="left", padx=6)

        self.prores_row = ttk.Frame(enc)
        ttk.Label(self.prores_row, text="ProRes 质量").pack(side="left")
        self.quality = tk.StringVar(value="hq")
        ttk.Combobox(self.prores_row, textvariable=self.quality, width=8, state="readonly",
                     values=["422", "hq", "4444", "xq"]).pack(side="left", padx=6)

        # 输出目录
        out = ttk.LabelFrame(self, text="输出目录（留空=源文件旁的 output）")
        out.pack(fill="x", **pad)
        self.out_dir = tk.StringVar()
        ttk.Entry(out, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(out, text="选择...", command=self._pick_out).pack(side="left", padx=6)

        self.export_btn = ttk.Button(self, text="开始导出", command=self._start)
        self.export_btn.pack(pady=8)
        self._buttons.append(self.export_btn)

    def _sync_codec(self):
        if self.codec.get() == "prores":
            self.h265_row.forget()
            self.gpu_chk.state(["disabled"])
            self.prores_row.pack(fill="x", padx=6, pady=4)
        else:
            self.prores_row.forget()
            self.gpu_chk.state(["!disabled"])
            self.h265_row.pack(fill="x", padx=6, pady=4)

    def _pick_source(self):
        f = filedialog.askopenfilename(title="选择源视频")
        if f:
            self.source.set(f)

    def _pick_out(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.out_dir.set(d)

    def _on_busy(self, busy):
        for b in self._buttons:
            b.config(state="disabled" if busy else "normal")

    def _start(self):
        source = self.source.get().strip()
        if not source or not os.path.isfile(source):
            messagebox.showwarning("提示", "请先选择有效的源视频。")
            return
        sizes = [k for k, v in self.res_vars.items() if v.get()]
        if not sizes:
            messagebox.showwarning("提示", "请至少选择一种分辨率。")
            return
        try:
            opts = ExportOptions(
                codec=self.codec.get(),
                crf=int(self.crf.get()),
                preset=self.preset.get(),
                gpu=self.gpu.get(),
                quality=self.quality.get(),
                fps=int(self.fps.get()),
                sizes=sizes,
            )
        except ValueError:
            messagebox.showwarning("提示", "CRF 和帧率必须是整数。")
            return

        out_dir = self.out_dir.get().strip() or os.path.join(os.path.dirname(os.path.abspath(source)), "output")
        self.ctx.run_background(lambda: self._run(source, out_dir, opts))

    def _run(self, source, out_dir, opts):
        log, prog = self.ctx.log, self.ctx.set_progress
        try:
            log(f"导出：{os.path.basename(source)}  → {out_dir}")
            results = exporter.export(source, out_dir, opts, log=log, progress_cb=prog)
            total_mb = round(sum(r["mb"] for r in results), 1)
            log(f"✓ 导出完成：{len(results)} 个文件，共 {total_mb} MB → {out_dir}")
        except Exception as e:
            log(f"✗ 导出失败：{e}")
        finally:
            prog(1.0)
