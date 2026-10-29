# AIGCTool — 视频工具合集

把五个常用视频小工具合并到一个桌面应用里，一个窗口、五个标签页搞定：

| 标签页 | 作用 |
|--------|------|
| **拆分 / 合并** | 把视频**无损**按时长或段数切成多段，或把多段无损拼回一个（ffmpeg 流复制，不重编码，可帧级还原）。支持拖拽、文件夹批量 |
| **多分辨率导出** | 一个源视频一键导出 4K / 1080 / 720 三档，锁 25fps、16:9。默认 H.265 交付版，可选 ProRes 422 HQ 母版、NVENC GPU 加速 |
| **视频下载** | B站 / YouTube / 小红书使用 yt-dlp，抖音使用本机适配器；画质下限、单条/合集、网络模式、取消续传和实际媒体核验 |
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
| **Windows x64** | `AIGCTool-Windows-x64.zip` | 以 Release 实际文件为准 |
| **macOS Apple Silicon** | `AIGCTool-macOS-arm64.zip` | 以 Release 实际文件为准 |
| **macOS Intel** | `AIGCTool-macOS-x64.zip` | 以 Release 实际文件为准 |

Windows 解压整个文件夹后运行 `AIGCTool.exe`；macOS 将解压后的 `AIGCTool.app` 放入 Applications。Mac 两个版本在 macOS 15 对应架构构建。发行包暂未做 Windows 开发者证书签名或 Apple Developer ID 公证，系统可能提示开发者未验证；请遵循系统提示，不要关闭系统安全保护。

**不需要安装 Python，不需要命令行。**

### 第一次使用

1. 把整个压缩包解压到可写目录，再打开程序。
2. 点击顶部「安装 / 更新下载工具」。程序联网安装缺少的 ffmpeg / ffprobe、更新 yt-dlp，并为 YouTube 安装缺少的 Node.js LTS 运行环境。已安装且受支持的 Node.js / Deno 可以直接复用。
3. 打开「视频下载」，粘贴链接或含链接的分享文本。默认单视频、至少 720p；下载 B站全部分 P 或播放列表时明确选择合集。需要登录时选择对应网站的 Netscape `cookies.txt`；抖音需要包含有效 UIFID 的当前 Cookie。
4. 选择保存目录及网络模式：自动沿用环境设置、直连忽略代理、自定义使用填写的代理。点击「开始 / 继续下载」。不会修改系统代理或硬编码某个代理端口。

下载选择符合要求的最高可用画质，不进行超分。**以 ffprobe 读取的实际短边像素数为准**，不相信接口标注的“720p/原画”，竖屏和横屏按相同标准处理。只有主动勾选「允许低于下限」才交付低清源；不满足下限的暂存视频不会计入成功。

每个完成视频旁有 `.receipt.json`：真实尺寸、时长、音轨、字节数、SHA-256 和来源公开链接，不含 Cookie、代理凭证或 CDN 签名地址。相同文件名但不同内容自动编号，不覆盖原文件。单视频默认避免误下载 YouTube Radio 整个列表。

取消后保留 `.aigctool/` 中的临时文件；相同链接、范围和保存目录再次开始可尝试续传。抖音只在服务器支持且对象校验一致时追加，否则重新下载；合集部分成功时已核验文件保留，但不报告整条链接全部成功。关闭窗口会先取消下载并清理临时 Cookie，网络请求有超时，因此关闭可能短暂等待。

Cookie 原件只读；yt-dlp 使用按平台筛选的临时副本，任务正常结束、失败或取消时清理。抖音登录数据只发送给抖音详情接口，媒体 CDN 使用独立无登录 Cookie 的会话。强制结束进程或断电可能留下临时副本，分享目录前请检查 `.aigctool/`；不要提交任何登录凭证。

### 支持边界

- 抖音适配当前支持公开可访问的单条视频和分享短链接，不支持图集、直播、账号批量或绕过访问权限。网站接口变化可能使适配暂时失效，不能保证任何链接永远可下载。
- B站、YouTube、小红书等由 yt-dlp 处理，是否有高清源取决于来源与账号权限；更新下载器不等于登录恢复。
- “已核验”表示文件容器可读取、尺寸和时长有效、画质符合本次选择，并记录音轨与哈希；不等于逐帧解码或创意质量验收。无音轨视频会明确标记，不自动补音轨。
- MP4 中的源编码可能仍是 HEVC、VP9 或 AV1。需要微信兼容时，另用「微信兼容转换」，下载阶段不自动重编码。

下载器已安装时仍可点击同一按钮更新。yt-dlp 和 Node.js 从官方来源下载并校验 SHA-256，更新已有文件前会保留 `.previous` 备份。Windows 工具放在应用旁的 `bin/`；Mac 放在 `~/Library/Application Support/AIGCTool/bin/`，不修改 `.app`。Mac FFmpeg 使用 Martin Riedl 提供的固定 9.0.2 原生发行包及发布者 SHA-256，不需要 Rosetta 转译。

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
pip install -r requirements-build.txt
python build.py
# 保留旧版本，构建到独立目录
python build.py --output-root /path/to/new-version
```

Windows 输出为 `dist/AIGCTool/`；macOS 输出为 `dist/AIGCTool.app`。Mac 压缩包必须保留 `.app` 的符号链接，使用 `ditto` 打包。
已有成品目录不会被自动删除；再次构建请指定新的 `--output-root`。许可证随包分发，来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

GitHub 推送与 `core/version.py` 一致的 tag（如 `v1.2.0`）会触发 Windows x64、Mac arm64 和 Mac x64 原生构建。三端测试、打包后 GUI 启动检查、包结构检查全部成功后，才创建包含完整包和 SHA256SUMS 的 Release 草稿；维护者确认后发布。

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
│   ├── downloader.py      平台路由、yt-dlp、取消和完成核验
│   ├── download_support.py 画质策略、Cookie 隔离、哈希凭证
│   ├── douyin.py          抖音本机解析与可验证续传
│   └── recorder.py        屏幕录制引擎
├── ui/                界面层
│   ├── widgets.py         拖拽列表等共享组件
│   └── tab_*.py           五个标签页
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
