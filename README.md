# AIGCTool — 视频工具合集

把四个常用视频小工具合并到一个桌面应用里，一个窗口、四个标签页搞定：

| 标签页 | 作用 |
|--------|------|
| **拆分 / 合并** | 把视频**无损**按时长或段数切成多段，或把多段无损拼回一个（ffmpeg 流复制，不重编码，可帧级还原）。支持拖拽、文件夹批量 |
| **多分辨率导出** | 一个源视频一键导出 4K / 1080 / 720 三档，锁 25fps、16:9。默认 H.265 交付版，可选 ProRes 422 HQ 母版、NVENC GPU 加速 |
| **视频下载** | 基于 yt-dlp，自动识别 B站 / YouTube，批量下载并合并为 MP4。支持 cookies.txt |
| **屏幕录制** | 区域框选或全屏录制，FPS 可调，全局热键 Ctrl+F9 开始/停止、Ctrl+F10 暂停/继续 |

所有耗时操作跑在后台线程，底部有共享日志区和进度条。

---

## 下载即用（推荐）

从 [Releases](../../releases) 页面下载对应平台的压缩包：

| 平台 | 文件 | 大小 |
|------|------|------|
| **Windows** | `AIGCTool-Windows.zip` | ~63 MB |
| **macOS** | `AIGCTool-macOS.zip` | ~65 MB |

解压后双击 `AIGCTool.exe`（Windows）或 `AIGCTool`（macOS）即可运行。

**不需要安装 Python，不需要命令行。**

### ffmpeg / yt-dlp 怎么办？

首次启动时，顶部会显示 ffmpeg / yt-dlp 是否就绪。如果缺失，点击「一键安装缺失依赖」按钮即可自动下载到应用旁的 `bin/` 目录——全程自动，无需手动配置 PATH 或环境变量。

---

## 从源码运行（开发者）

需要 Python 3.9+。

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python main.py

# 或 Windows 双击
启动.bat
```

### 构建发行包

```bash
pip install pyinstaller
python build.py
```

输出在 `dist/AIGCTool/`，是一个独立文件夹，可直接压缩分发。

GitHub 推送 tag（如 `v1.0.0`）会自动触发 CI 构建 Windows + macOS 两个平台的发行包并附到 Release。

---

## 目录结构

```
AIGCTool/
├── main.py            入口
├── core/              纯逻辑（与界面无关，可单测）
│   ├── autoinstall.py     ffmpeg/yt-dlp 自动检测 + 下载
│   ├── deps.py            依赖状态
│   ├── ffmpeg_runner.py   ffmpeg 调用 + 进度解析
│   ├── splitter.py        拆分/合并
│   ├── exporter.py        多分辨率导出
│   ├── downloader.py      yt-dlp 包装
│   └── recorder.py        屏幕录制引擎
├── ui/                界面层
│   ├── widgets.py         拖拽列表等共享组件
│   └── tab_*.py           四个标签页
├── tests/             单元测试
├── build.py           PyInstaller 打包脚本
├── .github/workflows/ CI：自动构建 Win + Mac
├── requirements.txt
├── 启动.bat           源码运行快捷入口（Windows）
├── README.md
└── 使用说明.md
```

## 测试

```bash
pip install pytest
python -m pytest tests/ -q
```

## 使用说明

详见 [使用说明.md](使用说明.md)：各功能操作步骤、无损切分原理、cookies.txt 导出方法、常见问题。
