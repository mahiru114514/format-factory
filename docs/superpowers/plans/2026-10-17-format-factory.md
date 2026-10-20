# Format Factory Implementation Plan

> **For agentic workers:** Execute this approved plan inline using executing-plans. Use test-driven-development for conversion behavior and requesting-code-review before completion.

**Goal:** Deliver a runnable Chinese Windows desktop conversion factory with editable, copyable recognition results.

**Architecture:** Python conversion modules run in background workers behind a PySide6 desktop UI. Tasks use unique output names, temporary working directories, and per-file errors. Text recognition is separate from conversion; the editable result is the authoritative source for clipboard and TXT output.

**Tech Stack:** Python 3.13, PySide6, Pillow/pillow-heif, openpyxl, python-docx, Pandoc, PyMuPDF/pdf2docx, Windows Word COM, RapidOCR, RapidLaTeXOCR, PyInstaller.

---

## File map

- `factory/common.py`: safe file allocation, encoding, common errors and options.
- `factory/images.py`: codecs, EXIF rotation, transparency, image resizing.
- `factory/tables.py`: XLSX and CSV with explicit encoding, delimiter and text preservation.
- `factory/text.py`: LaTeX to readable text and editable-result state.
- `factory/documents.py`: TXT/MD/DOCX/PDF adapters, rich Word export and PDF OCR routing.
- `factory/recognition.py`: offline ordinary OCR and cropped-formula recognition, PDF page rendering.
- `factory/service.py`: allowed format routing, cancellation between jobs, progress and isolated failures.
- `factory/ui.py`, `factory/text_panel.py`, `factory/file_panel.py`, `factory/theme.py`: main window, editable text workspace, file batch workspace and shared styling.
- `main.py`, `启动格式转换工厂.vbs`, `启动格式转换工厂.cmd`: desktop entry points.
- `requirements.txt`, `build.ps1`, `README.md`: reproducible setup, desktop packaging and user instructions.
- `tests/`: real round-trip, failure and UI interaction tests.

## Task 1 — runtime and conversion contract

- [x] Create an isolated `.venv`, install the declared packages, inspect OCR and formula APIs and local Word availability.
- [x] Write tests for no-overwrite naming, UTF-8/GB18030 decoding, same-format rejection and the edited-result copy contract; run `python -m pytest tests/test_common_text.py -q` and observe missing implementations.
- [x] Implement `unique_path`, `read_text`, `latex_to_text` and `ResultState`; copy operations must read current edited content and reject empty content. Re-run the tests to pass.

## Task 2 — tables and images

- [x] Write real XLSX→CSV→XLSX tests with Chinese, multiple sheets, leading zeros and long IDs. Add JPEG alpha, EXIF orientation, HEIC round-trip, bounded-size and output collision cases. Run focused tests and observe missing implementations.
- [x] Implement conversion into staged output directories; read cached formula values for CSV and warn when formulas lack cached values; CSV imports default to strings. HEIC output checks encoder support.
- [x] Verify by reopening generated workbooks/images; corrupt inputs must leave no partial output.

## Task 3 — documents and recognition

- [x] Write Markdown→DOCX→Markdown and TXT→PDF→TXT tests with Chinese and tables; add tests for blank PDFs, explicit scan OCR, markup escaping and same-name collisions. Run them before implementations.
- [x] Use bundled Pandoc for rich document conversions; use Word COM `DispatchEx` on a worker thread for DOCX→PDF when available. Keep a documented basic layout fallback for computers without Word. Use pdf2docx for PDF→DOCX and page-aware OCR for scanned PDFs.
- [x] Install and locally prepare OCR/formula models. Recognize a generated Chinese/English image and a cropped printed formula; ensure models can be reused without uploading documents.
- [x] Implement LaTeX-source and readable-text result modes; long PDFs support page selection for recognition.

## Task 4 — desktop UI

- [x] Add UI tests for editing results then copying all/selection, preserving LaTeX backslashes/newlines/Unicode, clipboard retry, disabling empty actions, confirming before overwriting edited output and disabling conflicting operations while busy.
- [x] Build four sidebar workspaces, file drag-and-drop, add/remove/clear, output folder chooser, options, batch progress and readable errors. A cancelled batch finishes its current file and skips remaining tasks.
- [x] Build side-by-side original/result panels, source image/PDF page preview with zoom, paste clipboard image, editable results, copy all/selection, save TXT and undo/redo. Changing output mode requires converting again rather than silently replacing edits.
- [x] Run Qt tests using `QT_QPA_PLATFORM=offscreen`; capture application screenshots and inspect clipping/contrast at desktop and minimum size.

## Task 5 — delivery and review

- [x] Create a no-console Windows launcher, deterministic install/build scripts, sample inputs, and clear Chinese usage notes with conversion limitations and model licenses.
- [x] Run `python -m pytest -q`, compile checks and a complete smoke batch. Request an independent code review; fix high-impact findings and re-run affected tests.
- [x] Package with PyInstaller as a directory-based Windows distribution, launch its executable with an automated smoke flag and verify no dependency files are missing.
- [x] Update this checklist and the approved design status; deliver verified launch paths and any remaining practical limitations.

## Acceptance gates

No source file overwrite. Failures are visible per file. Chinese output remains readable. HEIC actually decodes and encodes. OCR/formula paths perform actual local inference. Edited text, copied text and TXT contents match. A file can fail without stopping its batch. UI remains responsive while conversion runs. Packaging is not claimed successful without launching the packaged executable.
