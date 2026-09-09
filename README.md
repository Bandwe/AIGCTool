# AIGCTool — 视频工具合集

把五个常用视频小工具合并到一个桌面应用里，一个窗口、五个标签页搞定：

| 标签页 | 作用 |
|--------|------|
| **拆分 / 合并** | 把视频**无损**按时长或段数切成多段，或把多段无损拼回一个（ffmpeg 流复制，不重编码，可帧级还原）。支持拖拽、文件夹批量 |
| **多分辨率导出** | 一个源视频一键导出 4K / 1080 / 720 三档，锁 25fps、16:9。默认 H.265 交付版，可选 ProRes 422 HQ 母版、NVENC GPU 加速 |
| **视频下载** | 基于 yt-dlp，自动识别 B站 / YouTube，批量下载并合并为 MP4。支持 cookies.txt |
| **微信兼容转换** | 拖入视频批量转为 H.264 + AAC MP4，支持清晰/体积优先、进度、取消及打开输出目录 |
| **屏幕录制** | 区域框选或全屏录制，FPS 可调，全局热键 Ctrl+F9 开始/停止、Ctrl+F10 暂停/继续 |

所有耗时操作跑在后台线程，底部有共享日志区和进度条。

### 微信兼容转换

打开「微信兼容转换」，拖入视频或文件夹（或点击「添加视频」），选择清晰优先/体积优先，再点击「开始转换」。文件夹和拖放沿用现有文件列表规则；批次开始后新增的文件需下次启动转换。

输出统一为H.264 High、8位yuv420p、30fps、AAC-LC双声道48kHz，并启用MP4 faststart。清晰优先最长边1920、CRF20；体积优先最长边1280、CRF23。默认保存在原视频目录，也可指定统一输出目录；文件名加「_微信兼容」，重名自动编号，原文件不变。支持无音轨视频，暂不支持HDR色调映射。

转换期间可以取消，已完成结果保留，当前临时文件清理。文件均在本机处理。编码兼容不保证微信一定显示视频卡片，卡片形式也取决于发送方式和客户端。

**下载任务在用户自己的电脑上执行。** 用户选择本机的 Cookie 文件和保存目录；本项目不提供 Cookie 上传服务器，也不通过空马服务器中转视频。Cookie 只由本机下载器用于向对应视频网站发起请求。

---

## 下载即用（推荐）

从 [Releases](../../releases) 页面下载对应平台的压缩包：

| 平台 | 文件 | 大小 |
|------|------|------|
| **Windows** | `AIGCTool-Windows.zip` | 以 Release 实际文件为准 |
| **macOS** | `AIGCTool-macOS.zip` | 以 Release 实际文件为准 |

解压后双击 `AIGCTool.exe`（Windows）或 `AIGCTool`（macOS）即可运行。

**不需要安装 Python，不需要命令行。**

### 第一次使用

1. 把整个压缩包解压到可写目录，再打开程序。
2. 点击顶部「安装 / 更新下载工具」。程序联网安装缺少的 ffmpeg / ffprobe、更新 yt-dlp，并为 YouTube 安装缺少的 Node.js LTS 运行环境。已安装且受支持的 Node.js / Deno 可以直接复用。
3. 打开「视频下载」，每行粘贴一个视频链接。需要登录验证时，选择自己从对应网站导出的 `cookies.txt`；留空只尝试公开访问，不会自动读取其它 Cookie 文件。
4. 选择保存目录；需要指定代理时填写自己的代理地址，留空使用系统设置。点击「开始下载」。

下载默认选择最高可用画质和最佳音轨，不限制在 1080p，也不进行超分或重新编码。完成后会检查视频实际分辨率及音轨；源视频最高只有 1080p 时，结果就是 1080p。

下载器已安装时仍可点击同一按钮更新。yt-dlp 和 Node.js 从官方来源下载并校验 SHA-256，更新已有文件前会保留 `.previous` 备份。工具放在应用旁的 `bin/`，不需要手动修改系统 PATH。

**首次安装和下载视频都需要本机网络能够访问相关网站。** 最新下载器不保证旧 Cookie 仍有效；遇到“登录以确认不是机器人”，应先在自己的浏览器确认能播放，再重新导出 Cookie。具体错误会显示在日志中，不会把所有失败都归因于 Cookie。

---

## 从源码运行（开发者）

需要 Python 3.10+（发行包使用 Python 3.12 构建）。

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
│   ├── autoinstall.py     ffmpeg/yt-dlp/JavaScript 环境检测与安装
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
