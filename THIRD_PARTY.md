# Third-party components

This is a local source-available desktop application. Upstream components retain their licenses. Keep license files with any redistribution and review each upstream license for that use.

| Component | Purpose | Upstream license / source |
|---|---|---|
| PySide6 / Qt | Desktop UI | LGPLv3 / GPLv3 / commercial; https://www.qt.io/qt-for-python |
| Pandoc / pypandoc | Markdown / Word conversion | Pandoc GPL-2.0-or-later; pypandoc MIT; https://pandoc.org/ |
| PyMuPDF / MuPDF | PDF extraction / rendering | AGPL-3.0 or commercial; https://pymupdf.readthedocs.io/ |
| pdf2docx | Editable PDF to Word | MIT; https://github.com/ArtifexSoftware/pdf2docx |
| python-docx | DOCX processing | MIT; https://github.com/python-openxml/python-docx |
| openpyxl | XLSX processing | MIT; https://openpyxl.readthedocs.io/ |
| Pillow | Image processing | HPND; https://python-pillow.org/ |
| pillow-heif / libheif | HEIC / HEIF codecs | pillow-heif BSD-3-Clause; libheif LGPL-3.0; bundled codec libraries have separate licenses; https://github.com/bigcat88/pillow_heif |
| RapidOCR | Local Chinese / English recognition | Apache-2.0; https://github.com/RapidAI/RapidOCR |
| RapidLaTeXOCR | Local formula recognition | Wheel license Apache-2.0, preserved verbatim in vendor/RapidLaTeXOCR-LICENSE; https://github.com/RapidAI/RapidLaTeXOCR |
| ONNX Runtime | CPU inference | MIT; https://github.com/microsoft/onnxruntime |
| pylatexenc | Readable LaTeX text | MIT; https://github.com/phfaist/pylatexenc |
| ReportLab | Basic PDF rendering | BSD; https://www.reportlab.com/ |
| PyInstaller | Windows packaging | GPL-2.0 with bootloader exception; https://pyinstaller.org/ |

Formula model assets are downloaded from RapidAI/RapidLaTeXOCR release v0.0.0. They derive from the upstream LaTeX-OCR project; consult that project's model and data terms for redistribution. The application does not claim ownership of the models. Their download origin and SHA-256 hashes are recorded in resources/formula.

Windows system fonts and Microsoft Word are used from the local machine and are not redistributed. Word integration starts a separate hidden application instance and closes it after export.

The build includes installed component metadata and available license files under `_internal/licenses`. Full Python dependencies can be inspected with `.venv/Scripts/python.exe -m pip freeze`.
