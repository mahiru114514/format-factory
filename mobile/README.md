# 格式转换工厂 · 手机测试版

这是 Flutter 手机工程，同时包含 Android 与 iOS 原生目录。首版以“本机优先、上传前确认、核对后复制”为核心。Android 安装包与 iPhone 编译状态分别记录，不把 Windows 下的源码检查当作 iPhone 运行验证。

## 使用范围

| 内容 | 本机处理 | 需要服务的情况 |
|---|---|---|
| 文本 | 粘贴、LaTeX 源码保留、常见语法转易读文字、校对编辑、撤销、复制、保存 TXT | 公式图片识别 |
| 文档 | TXT/Markdown、基础 DOCX 输出与文字提取、中文文本 PDF | Word/PDF 互转、复杂排版或图文恢复 |
| 表格 | XLSX/CSV，UTF-8、UTF-16、GBK，长编号/前导零、多工作表 | GB18030 四字节字符、超出手机限制的大表格 |
| 图片 | JPG、PNG、BMP、TIFF；设备编解码支持时处理 HEIC/WebP | 设备不支持目标编码时，用户可选择联网转换 |
| 识别 | 设备上的中文/英文文字识别 | 单条清晰公式识别、复杂识别 |

本机文字 PDF 是基础文本排版；复杂 Word/PDF 版式及识别结果需要人工核对。动画/多页图片的本机转换使用首帧并提示。HEIC 编码能力随手机硬件变化，失败时会明确说明，不会将 JPEG 改扩展名冒充 HEIC，也不会静默上传。

0.1.1 补充 LaTeX 逻辑符号、箭头及大析取/合取符号整理，保留上下界和未识别命令。图片公式识别引擎的修复需要同时更新并重启转换服务；变量字母间距和复杂公式仍需校对。

0.1.2 进一步保留分式整体分组、根号次数、数学粗体及复杂环境，修复转义字符和换行被错误整理的问题。不能可靠转换的结构保留原文。图片识别模型仍可能混淆上下限字符或误生成数组结构，需要人工核对；本轮没有更换模型。

本机单文件上限 50 MiB，Office/结果 ZIP 解压总量上限 200 MiB；联网结果 ZIP 下载上限为独立的 224 MiB，为转换后体积增大和压缩包目录保留余量。表格与图片还有内存保护边界。限制触发会保留原文件并提示。中文 PDF 字体为随附 OFL 授权的 Noto Sans SC。

## Android 构建

当前 Windows 开发环境使用项目内 `.tools` 工具链。运行：

```powershell
./scripts/mobile/build_android.ps1
```

脚本检查依赖、分析代码、运行手机端测试、打包并核对签名与包信息。测试安装包使用开发测试签名，不用于应用商店发布。

部分原生编译器不支持中文 SDK 路径，因此 `scripts/mobile/env.ps1` 会在 F: 空闲时将它临时映射到当前工程；发现 F: 指向其他位置会停止，不会覆盖。文件仍保存在原工程目录。完成开发后可用 `subst F: /D` 解除本工程映射。仅下载公开构建依赖，不上传用户文档。

首次配置的工具准备脚本位于 `scripts/mobile/`，需要 Python 3.13、Java 21、Flutter/Android SDK。其他电脑可使用自己的 Flutter/Android SDK，无需复制数 GB 的 `.tools` 缓存。请保留 `pubspec.lock` 并运行 `flutter pub get`。

手机工程源码包包含客户端与本地分享插件补丁，不包含服务端模型或整套开发缓存。复制到其他开发电脑后，可在 `mobile` 目录依次运行 `flutter pub get`、`flutter analyze`、`flutter test` 和 `flutter build apk --release`。Release 构建应允许 Flutter 自动更新平台插件注册文件，不要沿用设备测试生成的文件。

Android 系统分享已为当前工程修复：通过系统授权的文件流读取，后台复制至独立缓存，支持同名文件；本机持久导入后才清理对应分享缓存。补丁及原作者许可见 `plugins/receive_sharing_intent/FORMAT_FACTORY_PATCH.md`。若在尚未完成导入前强制终止应用，可能需要重新分享原文件。

## 受控联网服务

参见 [服务说明](../mobile_server/README.md)。服务默认仅监听电脑本机；手机联调需手机与电脑处于同一可信局域网，将监听地址和 App 设置改为电脑的实际局域网数字地址。不要填写示例或猜测地址。公开服务需要 HTTPS。

每次上传前由用户确认。服务返回真实大小、超时与保留策略；结果完整保存在手机后才确认删除远端任务。未确认或失败任务默认最多保留一小时；下载本身不会删除。App 不包含预设公网服务器，也没有已部署的正式在线服务。

真实客户端联调：

```powershell
. ./scripts/mobile/env.ps1
.venv/Scripts/python.exe scripts/mobile/live_integration.py
```

该脚本仅启动临时回环服务，验证中文 CSV → 服务端 XLSX → 手机本地 CSV，检查长编号，以及客户端持久保存后远端任务删除。

推荐使用已验证的本机 Linux 容器服务：

```powershell
./scripts/mobile/start_service.ps1 -ListenAddress 电脑实际局域网IPv4地址
```

默认省略地址时只允许电脑本机连接。手机与电脑须在同一可信局域网；在 App 设置填写脚本返回的实际地址，查询能力后即可逐次确认上传。停止服务运行 `./scripts/mobile/stop_service.ps1`。首次构建需要下载公开依赖；未改动电脑已有 Docker 镜像代理设置，使用官方公共镜像副本。

本机容器已实测：Python 3.13.16 / LibreOffice 25.2.3.2，真实 Flutter 客户端完成中文 DOCX→PDF→DOCX→TXT、CSV→XLSX→CSV，服务完成 PNG→HEIC→JPEG，结果保存后远端任务目录为空。验证脚本为 `scripts/mobile/docker_integration.py`。

另已实测服务端中文/英文 OCR 和公式图片识别输出 UTF-8 TXT，确认后清理任务。公式样例识别为 `\mathbf{x}+\mathbf{y}=1`，保留模型实际返回的 LaTeX，仍由用户核对。

Windows 原生 LibreOffice 26.8.1 曾在真实转换时超时；推荐使用上述已验证容器，不将“找到安装文件”等同于渲染健康。

## iPhone 编译与安装

Windows 本机不能完成 iPhone 安装包的 Xcode 编译和签名。本工程提供 iOS 15.5+ 的原生源码、CocoaPods 配置、中英文识别依赖和独立 ShareExtension 目标，当前尚未提供已签名 IPA。

在配有 Xcode 的 macOS 上：

1. 安装 Flutter 3.47.7 与 CocoaPods，复制源码，运行 `flutter pub get`。
2. 进入 `ios` 执行 `pod install`，打开 `Runner.xcworkspace`。
3. 为 Runner 和 ShareExtension 选择同一个 Apple Developer Team；将两者的 Bundle ID 改为账号可用标识。
4. 两个目标启用同一个 App Group，并同步更新 `CUSTOM_GROUP_ID`。ShareExtension 的 Bundle ID 应以主 App 标识为前缀。
5. 在 iPhone 上编译运行，实际验证选择文件/相册、中文识别、HEIC、分享输入输出及上传确认。
6. 需要测试分发时再归档、签名和配置 TestFlight。未完成这些步骤前，不声称 iPhone 版已经可安装。

iOS 分享扩展先将所选内容保存在本机共享容器；完成后打开主 App 继续。主 App 持久导入成功才清理对应共享文件，避免处理中断导致内容丢失。

结构检查：`python scripts/mobile/verify_platforms.py`。它只检查工程引用、权限、图标及扩展嵌入，不替代 Xcode 编译或真机测试。

官方依据：[Flutter iOS 设置](https://docs.flutter.dev/platform-integration/ios/setup)、[Flutter UIScene](https://docs.flutter.dev/release/breaking-changes/uiscenedelegate)、[Apple 局域网连接设置](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowslocalnetworking)。
