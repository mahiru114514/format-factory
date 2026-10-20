# Office Equation Copy Implementation Plan

**Goal:** 核对 LaTeX 后复制为 Word / WPS 可编辑公式。

**Architecture:** `factory/office_math.py` 负责严格本地转换和剪贴板载荷；`factory/text_panel.py` 负责输出模式、编辑来源和异步复制。原有可读文字复制保持原样。

**Tech Stack:** Python / PySide6 / bundled Pandoc / Windows clipboard / Office COM integration verification.

## Tasks

- [x] 探测 Pandoc MathML 及原生 Office 粘贴支持，检查新文档 OMaths 和 DOCX XML；仅关闭测试创建的文档实例。
- [x] `tests/test_office_math.py` 添加分式、根号、上下标、逻辑大算子、矩阵、混合文本和失败不降级测试；运行 `.venv/Scripts/python.exe -m pytest tests/test_office_math.py -q`，确认新模块缺失导致失败。
- [x] 实现 `factory/office_math.py`：标准 MathML / HTML 剪贴板内容，严格错误，按需提供 DOCX 兼容出口；同一转换规则同时用于复制和导出。
- [x] `tests/test_ui.py` 添加 Office 模式原始内容保持、修改后复制、选区复制及模式切换后不得误用旧可读结果的测试；先观察失败。
- [x] 修改 `factory/text.py` / `factory/text_panel.py`，仅匹配实际生成结果的 Office 模式启用结构复制，后台转换完成再主线程写剪贴板，失败保留内容。
- [x] 运行所有桌面及服务测试，真实 Word / WPS 粘贴验证并保存报告；独立代码审查修复实际问题。
- [x] 增加冻结程序烟雾检查，构建 0.1.4 并验证后更新启动入口及说明。

当前目录没有 Git 仓库，不创建虚假提交。所有转换本机完成，不上传文件。
