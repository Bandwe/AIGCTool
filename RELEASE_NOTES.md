# AIGCTool v1.2.0

## 下载与安装

| 文件 | 适用平台 |
| --- | --- |
| `AIGCTool-Windows-x64.zip` | Windows 64 位，解压整个文件夹后运行 `AIGCTool.exe` |
| `AIGCTool-macOS-arm64.zip` | Apple Silicon（M 系列），解压后将 `AIGCTool.app` 放入 Applications |
| `AIGCTool-macOS-x64.zip` | Intel Mac，解压后将 `AIGCTool.app` 放入 Applications |
| `SHA256SUMS.txt` | 三个发行包的 SHA-256 校验值 |

这些是独立便携包 / macOS 应用包，无需安装 Python。macOS 包在 macOS 15 对应架构构建。
Windows 包没有购买代码签名证书；macOS 包仅做本地完整性签名，未做 Apple Developer ID 签名或公证，系统可能提示无法验证开发者。请遵循系统提示，不要关闭系统安全保护。

首次使用可点击「安装 / 更新下载工具」，工具需要联网下载。Windows 工具保存在应用旁的 `bin/`；macOS 保存在 `~/Library/Application Support/AIGCTool/bin/`，不会修改 `.app` 内容。FFmpeg、yt-dlp、Node.js 不随安装包捆绑。

## 主要更新

- 抖音新增本机单视频下载适配；B站、YouTube、小红书沿用 yt-dlp。
- 默认单视频、至少 720p，以实际分辨率为准；低于下限须明确接受，不自动超分。
- 增加分享文本解析、全部分 P / 播放列表、直连 / 自动 / 自定义代理。
- 支持取消、断点恢复、已完成文件重新核验后复用；保存实际媒体参数及 SHA-256 凭证。
- Cookie 原件只读、临时副本按平台隔离；不向第三方解析服务器提交登录数据。
- 保留拆分/合并、多分辨率导出、微信兼容转换和屏幕录制。
- 修正 Mac 应用打包与工具保存位置，提供原生 Apple Silicon / Intel FFmpeg 安装路线。

## 验证与限制

三个发行包均须通过对应平台自动测试、打包后 GUI 启动检查及包结构/完整性校验才进入 Release 草稿。
抖音目前限可访问的单条视频，不支持直播、图集或账号批量。视频平台接口、Cookie 有效期、代理和账号权限仍可能影响下载。
强制结束进程或断电可能遗留临时 Cookie 副本，分享下载目录前请检查 `.aigctool/`。
