from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt, QThreadPool, Signal
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QMessageBox,
                               QPlainTextEdit, QProgressBar, QSpinBox, QSplitter, QStackedWidget,
                               QVBoxLayout, QWidget)

from .preview import ImagePreview
from .text import ResultState, process_source
from .theme import button, label
from .workers import Task


class TextPanel(QWidget):
    activity_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.state = ResultState()
        self.result_mode = 'readable'
        self.busy = False
        self.source_path = None
        self._tasks = []
        self.clipboard_writer = lambda text: QApplication.clipboard().setText(text)
        self.office_clipboard_writer = self.write_office_clipboard
        self.confirm_replace = self._confirm_replace
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        controls = QFrame()
        controls.setObjectName('card')
        row = QHBoxLayout(controls)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(12)
        row.addWidget(label('处理方式', 'hint'))
        self.method_combo = QComboBox()
        self.method_combo.addItem('LaTeX / 文本整理', 'text')
        self.method_combo.addItem('图片 / PDF 文字识别', 'ocr')
        self.method_combo.addItem('公式（图片识别 / LaTeX 转换）', 'formula')
        self.method_combo.setMinimumWidth(178)
        row.addWidget(self.method_combo)
        row.addWidget(label('输出', 'hint'))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem('可读纯文本', 'readable')
        self.mode_combo.addItem('LaTeX / 原始文本', 'source')
        self.mode_combo.addItem('Word / WPS 可编辑公式', 'office')
        self.mode_combo.setMinimumWidth(160)
        self.mode_combo.setToolTip('切换输出方式后，点击转换生成新结果。已编辑的结果会先询问是否替换。')
        row.addWidget(self.mode_combo)
        row.addStretch()
        self.run_button = button('转换 / 识别  →', True)
        self.run_button.setMinimumWidth(140)
        self.run_button.clicked.connect(self.start_processing)
        row.addWidget(self.run_button)
        layout.addWidget(controls)

        self.image_mode_hint = QFrame()
        self.image_mode_hint.setObjectName('card')
        hint_row = QHBoxLayout(self.image_mode_hint)
        hint_row.setContentsMargins(16, 10, 16, 10)
        hint_row.addWidget(label('当前是普通文字识别，公式的箭头、上下标可能丢失。公式截图请用右侧按钮。', '', True), 1)
        self.formula_button = button('识别这张图中的单条公式', True)
        self.formula_button.clicked.connect(lambda checked=False: self.start_processing(method_override='formula'))
        hint_row.addWidget(self.formula_button)
        self.image_mode_hint.hide()
        layout.addWidget(self.image_mode_hint)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        source_card = QFrame()
        source_card.setObjectName('card')
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(14, 14, 14, 12)
        source_layout.setSpacing(10)
        source_header = QHBoxLayout()
        source_header.addWidget(label('01', 'step'))
        source_header.addWidget(label('原始内容', 'cardTitle'))
        source_header.addStretch()
        self.example_button = button('试试示例')
        self.example_button.setObjectName('quiet')
        self.example_button.clicked.connect(self.load_example)
        source_header.addWidget(self.example_button)
        source_layout.addLayout(source_header)

        tools = QHBoxLayout()
        tools.setSpacing(7)
        self.import_button = button('导入文件')
        self.import_button.clicked.connect(self.choose_source)
        self.paste_button = button('粘贴剪贴板')
        self.paste_button.clicked.connect(self.paste_source)
        self.clear_button = button('清空')
        self.clear_button.setObjectName('quiet')
        self.clear_button.clicked.connect(self.clear_source)
        tools.addWidget(self.import_button)
        tools.addWidget(self.paste_button)
        tools.addStretch()
        tools.addWidget(self.clear_button)
        source_layout.addLayout(tools)

        self.source_stack = QStackedWidget()
        self.source_edit = QPlainTextEdit()
        self.source_edit.setPlaceholderText('在这里粘贴 LaTeX、Markdown 或普通文本…\n\n也可以导入图片、截图或 PDF，\n识别后在右侧核对、修改，再一键复制。\n\n支持 Ctrl+V 粘贴文字。\n截图请点击上方“粘贴剪贴板”。')
        self.source_edit.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.source_stack.addWidget(self.source_edit)
        self.preview = ImagePreview()
        self.source_stack.addWidget(self.preview)
        source_layout.addWidget(self.source_stack, 1)

        self.preview_tools = QWidget()
        preview_tools = QHBoxLayout(self.preview_tools)
        preview_tools.setContentsMargins(0, 0, 0, 0)
        preview_tools.addWidget(label('页码', 'hint'))
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setFixedWidth(65)
        self.page_spin.valueChanged.connect(self.change_page)
        preview_tools.addWidget(self.page_spin)
        self.page_total = label('/ 1', 'hint')
        preview_tools.addWidget(self.page_total)
        preview_tools.addStretch()
        fit = button('适应窗口')
        fit.setObjectName('quiet')
        fit.clicked.connect(self.preview.fit)
        reset = button('清除选区')
        reset.setObjectName('quiet')
        reset.clicked.connect(self.clear_crop)
        preview_tools.addWidget(fit)
        preview_tools.addWidget(reset)
        self.preview_tools.hide()
        source_layout.addWidget(self.preview_tools)
        self.source_hint = label('支持粘贴文本、导入 TXT / TEX / MD / Word / PDF 和图片。', 'hint', True)
        source_layout.addWidget(self.source_hint)
        self.splitter.addWidget(source_card)

        result_card = QFrame()
        result_card.setObjectName('card')
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(14, 14, 14, 12)
        result_layout.setSpacing(10)
        result_header = QHBoxLayout()
        result_header.addWidget(label('02', 'step'))
        result_header.addWidget(label('核对与编辑', 'cardTitle'))
        result_header.addStretch()
        self.count_label = label('0 字', 'hint')
        result_header.addWidget(self.count_label)
        result_layout.addLayout(result_header)
        edit_tools = QHBoxLayout()
        undo = button('撤销')
        undo.setObjectName('quiet')
        redo = button('重做')
        redo.setObjectName('quiet')
        edit_tools.addWidget(undo)
        edit_tools.addWidget(redo)
        edit_tools.addStretch()
        self.edit_badge = label('可直接编辑', 'hint')
        edit_tools.addWidget(self.edit_badge)
        result_layout.addLayout(edit_tools)
        self.result_edit = QPlainTextEdit()
        self.result_edit.setPlaceholderText('转换结果将在这里显示。\n\n对照左侧原文，直接修改错误，\n确认后点击“复制全部”即可使用。\n\n公式、换行和中文都会按编辑内容复制。')
        self.result_edit.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.result_edit.textChanged.connect(self.result_changed)
        self.result_edit.selectionChanged.connect(self.update_actions)
        undo.clicked.connect(self.result_edit.undo)
        redo.clicked.connect(self.result_edit.redo)
        result_layout.addWidget(self.result_edit, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.copy_as_formula_button = button('复制为 Word / WPS 公式', True)
        self.copy_as_formula_button.setToolTip('将右侧全部校对后的 LaTeX 复制为可编辑公式，不是源码文字。')
        self.copy_as_formula_button.clicked.connect(self.copy_as_formula)
        self.copy_all_button = button('复制全部', True)
        self.copy_all_button.clicked.connect(self.copy_all)
        self.copy_selected_button = button('复制选中')
        self.copy_selected_button.clicked.connect(self.copy_selected)
        self.save_button = button('保存 TXT')
        self.save_button.clicked.connect(self.choose_save)
        self.save_formula_button = button('保存公式 DOCX')
        self.save_formula_button.clicked.connect(self.choose_save_formula)
        actions.addWidget(self.copy_as_formula_button)
        actions.addWidget(self.copy_all_button)
        actions.addWidget(self.copy_selected_button)
        actions.addStretch()
        actions.addWidget(self.save_button)
        actions.addWidget(self.save_formula_button)
        result_layout.addLayout(actions)
        self.result_hint = label('复制和保存均使用当前编辑后的文字。识别结果请自行核对。', 'hint', True)
        result_layout.addWidget(self.result_hint)
        self.splitter.addWidget(result_card)
        self.splitter.setSizes([480, 480])
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, 1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = label('准备就绪 · 文字留在本机，核对后即可复制。', 'status', True)
        layout.addWidget(self.status)
        self.mode_combo.currentIndexChanged.connect(self.mode_changed)
        self.method_combo.currentIndexChanged.connect(self.refresh_processing_ui)
        self.source_stack.currentChanged.connect(self.refresh_processing_ui)
        self.source_edit.textChanged.connect(self.refresh_processing_ui)
        self.refresh_processing_ui()
        self.update_actions()

    def refresh_processing_ui(self):
        image_mode = self.source_stack.currentIndex() == 1
        formula_mode = self.method_combo.currentData() == 'formula'
        self.image_mode_hint.setVisible(image_mode and not formula_mode)
        self.formula_button.setEnabled(not self.busy)
        if not self.busy:
            action = ('识别公式' if formula_mode else '识别文字') if image_mode else ('转换公式文本' if formula_mode else '转换文本')
            self.run_button.setText(action + '  →')
        if image_mode:
            self.source_hint.setText('当前：单条公式识别。框选时请包含完整的箭头、上下界和下标。' if formula_mode
                                     else '当前：普通文字识别。公式截图请点击“识别这张图中的单条公式”。')
        else:
            self.source_hint.setText('当前输入为文字，可直接转换 LaTeX；识别截图请导入图片或点击“粘贴剪贴板”。')

    def mode_changed(self):
        if self.result_edit.toPlainText():
            self.status.setText('输出方式已切换。点击“转换 / 识别”生成新结果，当前编辑内容仍保留。')
        elif self.mode_combo.currentData() == 'office':
            self.status.setText('粘贴一条 LaTeX 公式；文字与公式混排时，用 $…$ 或 \\(…\\) 标出公式。')
        self.update_actions()

    def _confirm_replace(self):
        return QMessageBox.question(self, '保留编辑内容', '结果中有你的修改。重新转换会替换这些修改，是否继续？',
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def result_changed(self):
        self.state.edit(self.result_edit.toPlainText())
        self.count_label.setText(f'{len(self.state.current):,} 字')
        self.edit_badge.setText('已编辑 · 复制将包含修改' if self.state.dirty else '可直接编辑')
        self.update_actions()

    def update_actions(self):
        valid = bool(self.result_edit.toPlainText().strip()) and not self.busy
        office = self.result_mode == 'office'
        source = self.result_mode == 'source'
        self.copy_as_formula_button.setVisible(source)
        self.copy_as_formula_button.setEnabled(valid)
        self.copy_all_button.setText('复制到 Word / WPS' if office else ('复制源码' if source else '复制全部'))
        self.copy_selected_button.setText('复制选中公式' if office else ('复制选中源码' if source else '复制选中'))
        name = '' if source else 'primary'
        if self.copy_all_button.objectName() != name:
            self.copy_all_button.setObjectName(name)
            self.copy_all_button.style().unpolish(self.copy_all_button)
            self.copy_all_button.style().polish(self.copy_all_button)
        self.save_formula_button.setVisible(office)
        self.save_formula_button.setEnabled(valid)
        self.result_hint.setText('请用蓝色按钮复制公式，再到 Word / WPS 中按 Ctrl+V。直接在编辑框按 Ctrl+C 复制的是 LaTeX 源码；混排请用 $…$ 标出公式。'
                                 if office else ('要粘贴成可编辑公式，请点“复制为 Word / WPS 公式”；“复制源码”只复制 LaTeX 文字。'
                                                if source else '复制和保存均使用当前编辑后的文字。识别结果请自行核对。'))
        self.copy_all_button.setEnabled(valid)
        self.copy_selected_button.setEnabled(valid and bool(self.result_edit.textCursor().selectedText().strip()))
        self.save_button.setEnabled(valid)

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.run_button, self.import_button, self.paste_button, self.clear_button,
                       self.mode_combo, self.method_combo, self.page_spin, self.example_button, self.preview_tools):
            widget.setEnabled(not busy)
        self.source_edit.setReadOnly(busy)
        self.result_edit.setReadOnly(busy)
        self.progress.setVisible(busy)
        self.run_button.setText('处理中…')
        self.refresh_processing_ui()
        self.update_actions()
        self.activity_changed.emit(busy)

    def accept_result(self, text):
        self.result_mode = self.mode_combo.currentData()
        self.state.accept(text)
        self.result_edit.setPlainText(text)
        self.result_edit.document().clearUndoRedoStacks()
        self.status.setText('转换完成 · 请对照原文核对，可直接编辑后复制。')
        self.update_actions()

    def copy_all(self):
        if self.busy:
            return
        if self.result_mode == 'office':
            self.copy_office(self.state.copy_text())
            return
        try:
            self.clipboard_writer(self.state.copy_text())
            self.status.setText('已复制 LaTeX 源码文字 · 要粘贴成公式，请使用“复制为 Word / WPS 公式”。'
                                if self.result_mode == 'source' else '已复制全部内容 · 包含你刚才的修改。')
        except Exception:
            self.status.setText('复制失败，剪贴板可能正忙。内容已保留，请重试或保存 TXT。')

    def copy_selected(self):
        selected = self.result_edit.textCursor().selectedText().replace('\u2029', '\n').replace('\u2028', '\n')
        if not selected.strip():
            return
        if self.busy:
            return
        if self.result_mode == 'office':
            self.copy_office(selected)
            return
        try:
            self.clipboard_writer(selected)
            self.status.setText('已复制选中的文字。')
        except Exception:
            self.status.setText('复制失败，内容已保留，请重试。')

    def copy_office(self, source):
        from .office_math import convert_office_math
        self.status.setText('正在本机生成可编辑公式…')
        self._submit(lambda: convert_office_math(source), self.office_copy_ready)

    def copy_as_formula(self):
        if self.busy or self.result_mode not in ('source', 'office') or not self.state.current.strip():
            return
        self.copy_office(self.state.copy_text())

    def write_office_clipboard(self, result):
        from .office_math import office_mime_data
        clipboard = QApplication.clipboard()
        clipboard.setMimeData(office_mime_data(result))
        # Qt logs some native clipboard failures instead of raising. Read the
        # native payload back before announcing success.
        if QApplication.platformName() == 'windows':
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                actual = win32clipboard.GetClipboardData(win32clipboard.RegisterClipboardFormat('Kingsoft WPS 9.0 Format'))
            finally:
                win32clipboard.CloseClipboard()
        else:
            mime = clipboard.mimeData()
            actual = bytes(mime.data('application/x-qt-windows-mime;value="Kingsoft WPS 9.0 Format"')) if mime else b''
        if actual != result.docx:
            raise RuntimeError('剪贴板未接受完整公式。')

    def office_copy_ready(self, result):
        try:
            self.office_clipboard_writer(result)
            self.status.setText('已复制可编辑公式 · 在 Word / WPS 中按 Ctrl+V 粘贴，保留公式结构。')
        except Exception:
            self.status.setText('公式复制失败，剪贴板可能正忙。内容已保留，请重试或保存公式 DOCX。'
                                if self.result_mode == 'office' else '公式复制失败，剪贴板可能正忙。内容已保留，请重试或保存 TXT 留存源码。')

    def choose_save_formula(self):
        if self.busy:
            return
        destination, _ = QFileDialog.getSaveFileName(self, '保存可编辑公式', '校对公式.docx', 'Word 文档 (*.docx)')
        if destination:
            from .office_math import convert_office_math
            source = self.state.copy_text()
            def work():
                result = convert_office_math(source)
                Path(destination).write_bytes(result.docx)
                return destination
            self.status.setText('正在本机保存可编辑公式…')
            self._submit(work, lambda path: self.status.setText(f'已保存可编辑公式：{path}'))

    def save_to(self, destination):
        text = self.state.copy_text()
        # User-selected file replacement is confirmed by QFileDialog's native save prompt.
        Path(destination).write_text(text, encoding='utf-8', newline='')
        self.status.setText(f'已保存：{destination}')

    def choose_save(self):
        destination, _ = QFileDialog.getSaveFileName(self, '保存校对后的文本', '校对结果.txt', '纯文本 (*.txt)')
        if destination:
            try:
                self.save_to(destination)
            except Exception as error:
                self.status.setText(f'保存失败：{error}')

    def _submit(self, function, success):
        self.set_busy(True)
        task = Task(function)
        task.signals.success.connect(success)
        task.signals.failure.connect(self.processing_failed)
        task.signals.finished.connect(self.processing_finished)
        self._tasks.append(task)
        QThreadPool.globalInstance().start(task)

    def processing_failed(self, message):
        self.status.setText('处理失败：' + message)

    def processing_finished(self):
        self.set_busy(False)
        self._tasks.clear()

    def start_processing(self, checked=False, *, method_override=None):
        if self.busy:
            return
        if self.state.dirty and not self.confirm_replace():
            return
        if method_override is not None:
            self.method_combo.setCurrentIndex(self.method_combo.findData(method_override))
        mode = self.mode_combo.currentData()
        method = self.method_combo.currentData()
        if self.source_stack.currentIndex() == 1:
            image = self.preview.selected_image()
            if image is None:
                self.status.setText('请先导入图片或 PDF。')
                return
            source = self.source_path
            page = self.page_spin.value() - 1
            crop = self.preview.crop_rect is not None
            def work():
                if method == 'formula':
                    from .recognition import recognize_formula
                    return process_source(recognize_formula(image), mode)
                if source and source.suffix.lower() == '.pdf' and not crop:
                    from .documents import extract_pdf
                    return extract_pdf(source, ocr=True, page=page)
                from .recognition import recognize_image
                return recognize_image(image)
            self.status.setText('正在本地识别… 首次载入模型可能需要几秒钟。')
            self._submit(work, self.accept_result)
        else:
            # Ctrl+V inside the editor does not change the chosen method.
            # Formula mode uses OCR for images and direct conversion for text.
            source = self.source_edit.toPlainText()
            if not source.strip():
                self.status.setText('请先粘贴文本，或导入图片 / PDF。')
                return
            self.status.setText('正在整理文本…')
            self._submit(lambda: process_source(source, mode), self.accept_result)

    def select_text_method(self):
        # Formula mode handles both LaTeX and screenshots. Keep its recognizer
        # preference when text is pasted/imported, just as direct Ctrl+V does.
        if self.method_combo.currentData() != 'formula':
            self.method_combo.setCurrentIndex(self.method_combo.findData('text'))

    def load_example(self):
        self.clear_source()
        self.select_text_method()
        self.source_edit.setPlainText('这是一段包含公式的文字：\n\n' + r'$\frac{a}{b} + \sqrt{x} = \alpha$' + '\n\n转换后，可以在右侧核对并修改，再一键复制。')
        self.status.setText('示例已填入。点击“转换 / 识别”试一试。')

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入文本、图片或 PDF', '',
            '支持的文件 (*.txt *.tex *.md *.markdown *.docx *.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.heic *.heif);;所有文件 (*)')
        if path:
            self.load_source(Path(path))

    def show_source_image(self, image, source=None, pages=1):
        from .recognition import load_image
        image = load_image(image)
        self.source_path = source
        self.preview.set_image(image)
        self.source_stack.setCurrentIndex(1)
        self.preview_tools.show()
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, pages)
        self.page_spin.setValue(1)
        self.page_spin.blockSignals(False)
        self.page_spin.setVisible(bool(source and source.suffix.lower() == '.pdf'))
        self.page_total.setText(f'/ {pages}' if source and source.suffix.lower() == '.pdf' else '')
        if self.method_combo.currentData() != 'formula':
            self.method_combo.setCurrentIndex(1)
        self.source_hint.setText('拖动框选识别区域，滚轮可缩放。公式识别请框选单条印刷公式。')
        method = '单条公式识别' if self.method_combo.currentData() == 'formula' else '文字识别（公式请选择“单条公式识别”）'
        self.status.setText(f'已导入 {source.name if source else "剪贴板截图"} · 当前：{method}。')

    def load_source(self, path):
        if self.busy:
            return
        try:
            suffix = path.suffix.lower()
            if suffix in ('.txt', '.tex', '.md', '.markdown'):
                from .common import read_text
                self.clear_source()
                self.source_edit.setPlainText(read_text(path))
                self.select_text_method()
                self.status.setText(f'已导入 {path.name}，点击转换生成结果。')
            elif suffix == '.docx':
                from .documents import docx_plain
                self.status.setText('正在读取 Word 文本…')
                self._submit(lambda: docx_plain(path), self.loaded_word)
            elif suffix == '.pdf':
                from .recognition import pdf_page_image
                image, count = pdf_page_image(path, 0)
                self.show_source_image(image, path, count)
            else:
                from .recognition import load_image
                self.show_source_image(load_image(path), path)
        except Exception as error:
            self.status.setText(f'导入失败：{error}')

    def loaded_word(self, text):
        self.source_path = None
        self.source_stack.setCurrentIndex(0)
        self.preview_tools.hide()
        self.source_edit.setPlainText(text)
        self.select_text_method()
        self.status.setText('Word 文字已导入，点击转换生成结果。')

    def paste_source(self):
        if self.busy:
            return
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            image = clipboard.image()
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, 'PNG')
            self.show_source_image(Image.open(io.BytesIO(bytes(buffer.data()))).copy())
        elif mime and mime.hasText():
            self.clear_source()
            self.source_edit.setPlainText(clipboard.text())
            self.select_text_method()
            self.status.setText('已粘贴文字，点击转换生成结果。')
        else:
            self.status.setText('剪贴板中没有文字或图片，请先复制内容或截图。')

    def clear_source(self):
        self.source_path = None
        self.source_edit.clear()
        self.source_stack.setCurrentIndex(0)
        self.preview_tools.hide()
        self.source_hint.setText('支持粘贴文本、导入 TXT / TEX / MD / Word / PDF 和图片。')
        self.status.setText('原始内容已清空，右侧编辑结果仍保留。')

    def change_page(self, value):
        if not self.source_path or self.source_path.suffix.lower() != '.pdf' or self.busy:
            return
        try:
            from .recognition import pdf_page_image
            image, _ = pdf_page_image(self.source_path, value - 1)
            self.preview.set_image(image)
            self.status.setText(f'当前第 {value} 页，识别仅处理当前页或框选区域。')
        except Exception as error:
            self.status.setText(f'页面读取失败：{error}')

    def clear_crop(self):
        if self.preview.image:
            self.preview.set_image(self.preview.image)

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.busy:
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
            if paths:
                self.load_source(paths[0])
                event.acceptProposedAction()
