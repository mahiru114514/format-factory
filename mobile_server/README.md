# 手机端转换服务

独立运行的 FastAPI 服务。图片和表格复用现有引擎；文档走 Pandoc `--sandbox` 和 LibreOffice，不使用 Windows Word COM。普通识别与公式识别使用已有本地 ONNX 模型，不把文件转发到其他服务。

## 本机运行

在项目根目录使用 Python 3.13，安装 `mobile_server/requirements.txt`，安装 LibreOffice Writer、中文字体（Linux 推荐 Noto CJK）和 Liberation 字体。Pandoc 已由 `pypandoc-binary` 提供。公式模型须预先位于 `resources/formula/{image_resizer.onnx,encoder.onnx,decoder.onnx,tokenizer.json}`；RapidOCR 安装包须包含三个 OCR 模型。

```powershell
.venv/Scripts/python.exe -m pip install -r mobile_server/requirements.txt
$env:FACTORY_SOFFICE = 'E:\格式转换工厂\.tools\LibreOffice\program\soffice.exe'
.venv/Scripts/python.exe -m uvicorn mobile_server.app:app --host 127.0.0.1 --port 8765 --workers 1 --no-access-log
```

`FACTORY_SOFFICE` 可省略（从 PATH 或标准 Windows 安装目录查找）；Windows 自动优先选择同目录 `soffice.com`。Linux：

```sh
sudo apt-get install libreoffice-writer fonts-noto-cjk fonts-liberation libgl1 libglib2.0-0
python3 -m venv .venv-service
.venv-service/bin/pip install -r mobile_server/requirements.txt
.venv-service/bin/python -m uvicorn mobile_server.app:app --host 127.0.0.1 --port 8765 --workers 1 --no-access-log
```

默认仅监听本机。手机联调需要明确改为本机的局域网数字地址，手机与电脑处于同一可信网络。HTTP 仅供显式配置的回环或局域网联调；公开服务使用 HTTPS。不要将这个测试服务直接作为公开、多租户服务部署。

## 配置

可通过 `create_app(Settings(...))` 或环境变量设置：

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `FACTORY_STORAGE` | `.work/mobile-jobs` | 独占的任务存储目录 |
| `FACTORY_MAX_UPLOAD_BYTES` | `52428800` | 单文件 50 MiB，另允许 64 KiB 表单开销 |
| `FACTORY_WORKER_TIMEOUT_SECONDS` | `120` | 每个任务的实际转换进程超时 |
| `FACTORY_VALIDATION_TIMEOUT_SECONDS` | `15` | 同意上传后文件深度校验的独立进程硬超时 |
| `FACTORY_VALIDATION_MEMORY_BYTES` | `805306368` | 校验进程及其子进程的内存上限（768 MiB） |
| `FACTORY_RETENTION_SECONDS` | `3600` | 从创建起最多保留一小时 |
| `FACTORY_MAX_WORKERS` | `2` | 同时运行的转换进程数量 |
| `FACTORY_MAX_JOBS` | `64` | 包括排队及已完成任务的数量上限 |
| `FACTORY_CLEANUP_INTERVAL_SECONDS` | `30` | 自动清理间隔；访问接口时也清理 |
| `FACTORY_MAX_UNCOMPRESSED_BYTES` | `209715200` | Office 解压总量及结果总量上限 |
| `FACTORY_SOFFICE` | 自动查找 | LibreOffice 启动器路径 |

必须使用一个 ASGI worker，禁止多个服务实例共享同一任务目录。访问令牌只存摘要、只在内存中保存。重启会使令牌失效，并清理带本服务标记的旧任务目录；正常关闭也删除任务。任务正在执行时 DELETE/过期会终止进程树。Windows 使用从暂停状态加入的 Job Object，Linux 使用独立进程组；超时及工作进程退出后嵌套转换进程一同终止。

## HTTP 合同

`GET /v1/capabilities` 无需令牌。返回 `max_upload_bytes`、`worker_timeout_seconds`、`retention_seconds`、`result_format: "zip"`、`result_media_type: "application/zip"`、`engines`、`categories`。分类包含 `sources`、`targets`、`pairs`（`source,target,ready,message`）。`engines` 报告本机引擎和模型文件准备状态；运行时损坏、字体缺失等仍会通过任务失败报告。`text.methods` 单独报告 `ocr` 和 `formula`。

`POST /v1/jobs` 接收 multipart 字段：

| 字段 | 内容 |
| --- | --- |
| `file` | 一个文件，原文件名只用于展示，禁止路径 |
| `category` | `images` / `tables` / `documents` / `text` |
| `target` | 图片 `jpg/png/webp/bmp/tiff/heic`；表格 `csv/xlsx`；文档 `txt/md/docx/pdf`；识别 `txt` |
| `options` | JSON 对象，默认 `{}` |
| `consent` | 必须是字符串 `true`，缺失或拒绝返回 403 |

服务在受限内存中解析表单，同意验证前不会使用临时磁盘上传文件或创建任务。同意后先建立专用暂存目录，图片/PDF/Office/文本的深度校验全部在受内存限制和硬超时约束的独立进程中执行；Windows 使用 Job Object，Linux 使用 `RLIMIT_AS`。校验成功、拒绝、进程退出或超时都会清理暂存目录，成功后才创建转换任务。图片按真实编码验证；PDF 解析并验证页码；Office 检查结构、解压大小、压缩比和路径。二进制内容不能伪装成 CSV/文本。非法输入或校验进程内存超限返回 400，校验超时 408，过大 413，引擎缺失 503，任务容量已满 429。成功返回 **202**：

```json
{"id":"32位随机十六进制","token":"仅本次返回的随机秘密令牌","state":"queued"}
```

状态可能在响应生成时已成为 `running`。之后所有任务接口都必须带 `Authorization: Bearer <token>`。缺少令牌为 401，错误令牌/其他任务令牌/不存在/已过期统一为 404。

`GET /v1/jobs/{id}` 返回：

```json
{"id":"...","state":"succeeded","error":null,"result_name":"文件名.zip","result_media_type":"application/zip","outputs":["文件名.md","media/media/image1.png"],"warnings":[]}
```

状态依次为 `queued`、`running`、`succeeded` 或 `failed`。失败包含可展示的 `error`，未成功时结果名称/类型为 null。`GET /v1/jobs/{id}/result` 成功返回 ZIP，尚未成功返回 409。**包括文字/公式识别在内，结果始终为 ZIP**。识别 ZIP 内含 UTF-8 TXT；多工作表 CSV 和 DOCX→Markdown 的图片目录也一起打包，图片相对引用保持有效。

下载不会删除文件。客户端完成落盘/解包后才 `DELETE /v1/jobs/{id}` 确认删除（204），识别结果可继续在本地校对。未确认的任务自动到期删除；用户本地原件和已编辑文字不依赖远端任务寿命。

`options` 支持 `quality`（1–100）、`max_size`（0–20000）、`keep_metadata`（布尔）、`encoding`（utf-8 / utf-8-sig / gb18030 / utf-16 / auto）、`delimiter`（一个字符）、`pdf_ocr`（布尔）、`page`（从 **0** 开始）、`method`（`ocr` / `formula`）。识别 `page` 默认 0；文档提取未指定 page 时处理全部页。公式输出为可校对的 LaTeX 文本。未知选项会拒绝。

为避免文件读取和网络资源获取，上传 Markdown 不接受图片引用、原始 HTML/TeX 包含；DOCX 拒绝外部嵌入资源、活动/嵌入对象、SVG、动态读取字段和 XML 实体。普通超链接可保留。图片请内嵌在 DOCX 中。文档→PDF 必须有 LibreOffice，无此引擎会明确提示安装，不降级生成假成功结果。

## 容器（Linux）

```sh
docker build -f mobile_server/Dockerfile -t format-factory-service .
# Linux 本机测试，沿用默认 loopback，仅主机可访问：
docker run --rm --network host --memory 2g --cpus 2 format-factory-service
```

Dockerfile 从项目根目录构建，只复制服务、引擎、vendor 和公式模型，使用非 root 用户。构建需要联网下载公开依赖；运行可由部署者禁用出站网络。跨平台端口映射或反向代理场景必须显式覆盖容器监听地址，并由宿主网络配置限制可访问范围。本机 Linux 容器已完成真实验证：Python 3.13.16 / LibreOffice 25.2.3.2，中文 Word/PDF 双向转换、表格往返、PNG/HEIC/JPEG 与任务确认删除均通过。验证记录见 `.work/mobile-linux-integration.json`，脚本为 `scripts/mobile/docker_integration.py`。

若电脑已配置的 Docker Hub 镜像代理返回 401，可保持原配置，显式使用 Docker Official Images 的公共副本：

```sh
docker build --build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.13-slim -f mobile_server/Dockerfile -t format-factory-service:mobile-test .
```

Windows 受控启动/停止脚本为 `scripts/mobile/start_service.ps1` 和 `stop_service.ps1`。默认仅本机回环；明确传入电脑实际私有 IPv4 地址才能供同一可信局域网的手机联调。不会自动配置公网入口或修改防火墙规则。

## 测试

```powershell
.venv/Scripts/python.exe -m pip install httpx==0.28.1 pytest==9.1.1
.venv/Scripts/python.exe -m pytest mobile_server/tests -q
```

真实测试包含图片、双向表格、Pandoc 文档及媒体、OCR/公式、PDF 第 0 页识别、LibreOffice PDF（可选，未配置则跳过）、令牌隔离、无同意不落盘、类型/大小/压缩包/资源校验、删除与过期、实际子进程超时清理。Windows 受限沙箱若在 `socket._fallback_socketpair` 初始化卡住，应在允许本地回环 socket 的环境运行测试。

当前 Windows 主机验证记录：配置管理解压的 LibreOffice 26.8.1 时，`soffice.com --headless --version` 成功，但真实 DOCX→PDF 在独立命令和服务中均未在 20/30 秒内完成，尚未验证 PDF 渲染成功。输入、输出、临时目录和独立用户配置全部迁移到新目录后仍复现。该环境限制不影响其他转换；任务仍受 120 秒硬超时约束。`engines.libreoffice.readiness_check` 明确为 `executable_present`，表示找到安装文件，不表示已通过真实渲染测试；不要将其当成端到端健康证明。使用前应在目标主机通过本套真实 PDF 集成测试。
