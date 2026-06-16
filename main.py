# -*- coding: utf-8 -*-
"""
AIGCTool —— 视频工具合集（拆分合并 / 多分辨率导出 / 下载 / 屏幕录制）。

一个 Tkinter 单窗口应用，顶部四个标签页，底部共享日志区 + 进度条。
所有耗时操作跑在后台线程，通过队列回传日志/进度，UI 不卡死。
"""

import os
import sys
import queue
import threading
import traceback

import tkinter as tk
from tkinter import ttk

# 允许从本目录导入 core / ui
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import deps, autoinstall

try:
    from tkinterdnd2 import TkinterDnD
    _DND = True
except Exception:
    _DND = False


class AppContext:
    """传给各标签页的运行时上下文：日志、进度、后台任务、忙碌状态、依赖。"""

    def __init__(self, root):
        self.root = root
        self.deps = deps.check_all()
        self.busy = False
        self._q = queue.Queue()
        self._busy_listeners = []
        self.log_widget = None
        self.progress_widget = None

    # ---- 供标签页调用（线程安全：只入队） ----
    def log(self, msg):
        self._q.put(("log", str(msg)))

    def set_progress(self, frac):
        self._q.put(("progress", frac))

    def run_background(self, fn):
        """在后台线程跑 fn；忙碌时拒绝并提示。返回是否已启动。"""
        if self.busy:
            self.log("⚠ 已有任务在运行，请等它完成。")
            return False
        self._set_busy(True)

        def wrap():
            try:
                fn()
            except Exception:
                self._q.put(("log", "✗ 任务异常：\n" + traceback.format_exc()))
            finally:
                self._q.put(("done", None))

        threading.Thread(target=wrap, daemon=True).start()
        return True

    def on_busy_change(self, cb):
        self._busy_listeners.append(cb)

    def _set_busy(self, busy):
        self.busy = busy
        for cb in self._busy_listeners:
            try:
                cb(busy)
            except Exception:
                pass

    # ---- 主线程轮询队列，更新 UI ----
    def drain(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "log" and self.log_widget:
                    self.log_widget.config(state="normal")
                    self.log_widget.insert("end", payload + "\n")
                    self.log_widget.see("end")
                    self.log_widget.config(state="disabled")
                elif kind == "progress" and self.progress_widget:
                    self.progress_widget["value"] = max(0.0, min(payload, 1.0)) * 1000
                elif kind == "done":
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self.drain)


def build(root):
    root.title("AIGCTool — 视频工具合集")
    root.geometry("760x680")
    root.minsize(640, 560)

    # DPI 感知：让录制框选坐标准确
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    ctx = AppContext(root)

    # 顶部依赖状态条
    top = ttk.Frame(root)
    top.pack(fill="x", padx=8, pady=(6, 0))
    dep_label = ttk.Label(top, text="依赖：")
    dep_label.pack(side="left")
    dep_status = ttk.Label(top, text=deps.status_line(ctx.deps), font=("Consolas", 9))
    dep_status.pack(side="left")

    missing = [n for n, (ok, _p, _h) in ctx.deps.items() if not ok]
    if missing:
        def _install_deps():
            """一键下载缺失的 ffmpeg / yt-dlp 到应用本地 bin/ 目录。"""
            install_btn.config(state="disabled", text="正在下载...")
            ctx.run_background(lambda: _do_install(install_btn, dep_status, ctx))

        def _do_install(btn, label, ctx):
            log = ctx.log
            need_ff = not ctx.deps["ffmpeg"][0]
            need_yt = not ctx.deps["yt-dlp"][0]
            try:
                if need_ff:
                    log("正在下载 ffmpeg（约 80-120 MB，请耐心等待）...")
                    autoinstall.download_ffmpeg(
                        progress_cb=lambda done, total: ctx.set_progress(
                            done / total * 0.7 if total else 0))
                    log("✓ ffmpeg 已安装到 bin/ 目录")
                if need_yt:
                    log("正在下载 yt-dlp...")
                    autoinstall.download_ytdlp(
                        progress_cb=lambda done, total: ctx.set_progress(
                            0.7 + done / total * 0.3 if total else 0.7))
                    log("✓ yt-dlp 已安装到 bin/ 目录")
                ctx.deps = deps.check_all()
                ctx.root.after(0, lambda: label.config(text=deps.status_line(ctx.deps)))
                ctx.root.after(0, lambda: btn.pack_forget())
                log("✓ 所有依赖已就绪！")
            except Exception as e:
                log(f"✗ 下载失败：{e}\n  请检查网络或手动安装。")
                ctx.root.after(0, lambda: btn.config(state="normal", text="重试安装"))

        install_btn = ttk.Button(top, text="一键安装缺失依赖", command=_install_deps)
        install_btn.pack(side="left", padx=8)

    # 四个标签页
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8, pady=6)

    from ui.tab_split import SplitTab
    from ui.tab_export import ExportTab
    from ui.tab_download import DownloadTab
    from ui.tab_record import RecordTab

    nb.add(SplitTab(nb, ctx), text="  拆分 / 合并  ")
    nb.add(ExportTab(nb, ctx), text="  多分辨率导出  ")
    nb.add(DownloadTab(nb, ctx), text="  视频下载  ")
    record_tab = RecordTab(nb, ctx)
    nb.add(record_tab, text="  屏幕录制  ")

    # 底部共享日志 + 进度
    logf = ttk.LabelFrame(root, text="日志")
    logf.pack(fill="both", expand=False, padx=8, pady=(0, 6))
    log = tk.Text(logf, height=8, state="disabled", wrap="word")
    ls = ttk.Scrollbar(logf, orient="vertical", command=log.yview)
    log.configure(yscrollcommand=ls.set)
    log.pack(side="left", fill="both", expand=True)
    ls.pack(side="right", fill="y")
    ctx.log_widget = log

    progress = ttk.Progressbar(root, mode="determinate", maximum=1000)
    progress.pack(fill="x", padx=8, pady=(0, 8))
    ctx.progress_widget = progress

    def on_close():
        try:
            record_tab.on_close()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    ctx.drain()
    return ctx


def main():
    try:
        root = TkinterDnD.Tk() if _DND else tk.Tk()
        build(root)
        root.mainloop()
    except Exception:
        info = traceback.format_exc()
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(info)
        except Exception:
            log_path = "crash.log"
        try:
            from tkinter import messagebox
            messagebox.showerror("启动失败", f"{info}\n\n详细已写入 {log_path}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
