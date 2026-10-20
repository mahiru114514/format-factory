from pathlib import Path
import sys

from PySide6.QtCore import Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QHeaderView, QHBoxLayout, QLineEdit, QPlainTextEdit, QProgressBar,
                               QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .common import Options
from .service import FORMATS, INPUT_SUFFIXES
from .theme import button, label
from .workers import BatchTask

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]

HELP = {
    'documents': ('TXT / Markdown / Word / PDF', '复杂 PDF 转 Word 后请核对版式；扫描件请开启文字识别。'),
    'tables': ('XLSX / CSV', 'CSV 导入默认按文本保留前导零和长编号；多工作表会分别导出。'),
    'images': ('JPG / PNG / WebP / TIFF / HEIC 等', '支持 iPhone HEIC。默认清除照片元数据，透明背景转 JPG 时填充白色。'),
}


class FilePanel(QWidget):
    activity_changed = Signal(bool)

    def __init__(self, category):
        super().__init__()
        self.category = category
        self.files = []
        self.outputs = {}
        self.busy = False
        self.task = None
        self._completed = 0
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.locked = []

        card = QFrame()
        card.setObjectName('card')
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(15)
        format_row = QHBoxLayout()
        format_row.addWidget(label('01', 'step'))
        format_row.addWidget(label('选择输出格式', 'cardTitle'))
        format_row.addStretch()
        format_row.addWidget(label('自动保留原文件', 'hint'))
        box.addLayout(format_row)
        format_row = QHBoxLayout()
        format_row.setSpacing(16)
        format_row.addWidget(label(HELP[category][0], 'subtitle'))
        format_row.addStretch()
        format_row.addWidget(label('→', 'subtitle'))
        self.target = QComboBox()
        for fmt in FORMATS[category]:
            self.target.addItem(fmt.upper() if fmt != 'md' else 'Markdown (.md)', fmt)
        self.target.setMinimumWidth(180)
        self.target.setCurrentIndex({'documents': 2, 'tables': 1, 'images': 0}[category])
        format_row.addWidget(self.target)
        box.addLayout(format_row)
        self.locked.append(self.target)

        options_row = QHBoxLayout()
        options_row.setSpacing(12)
        if category == 'images':
            options_row.addWidget(label('质量', 'hint'))
            self.quality = QSpinBox()
            self.quality.setRange(1, 100)
            self.quality.setValue(90)
            self.quality.setSuffix(' %')
            self.quality.setFixedWidth(90)
            options_row.addWidget(self.quality)
            options_row.addWidget(label('最长边', 'hint'))
            self.max_size = QSpinBox()
            self.max_size.setRange(0, 20000)
            self.max_size.setSpecialValueText('保持原尺寸')
            self.max_size.setSuffix(' px')
            self.max_size.setMinimumWidth(135)
            options_row.addWidget(self.max_size)
            self.metadata = QCheckBox('保留照片信息')
            self.metadata.setToolTip('包括拍摄时间、位置及色彩配置等；默认不保留。')
            options_row.addWidget(self.metadata)
            self.locked += [self.quality, self.max_size, self.metadata]
        elif category == 'tables':
            options_row.addWidget(label('CSV 编码', 'hint'))
            self.encoding = QComboBox()
            self.encoding.addItem('UTF-8（兼容 Excel）', 'utf-8-sig')
            self.encoding.addItem('UTF-8（无 BOM）', 'utf-8')
            self.encoding.addItem('GB18030（中文旧文件）', 'gb18030')
            options_row.addWidget(self.encoding)
            options_row.addWidget(label('分隔符', 'hint'))
            self.delimiter = QComboBox()
            for name, value in [('逗号 ,', ','), ('分号 ;', ';'), ('制表符 Tab', '\t')]:
                self.delimiter.addItem(name, value)
            options_row.addWidget(self.delimiter)
            self.locked += [self.encoding, self.delimiter]
        else:
            self.pdf_ocr = QCheckBox('识别扫描 PDF（中文 / 英文）')
            options_row.addWidget(self.pdf_ocr)
            options_row.addStretch()
            self.pdf_engine = QComboBox()
            self.pdf_engine.addItem('PDF：优先保留 Word 排版', 'auto')
            self.pdf_engine.addItem('PDF：基础文字排版', 'basic')
            self.pdf_engine.setToolTip('优先使用本机 Word；不可用时使用基础文字排版并提示。')
            options_row.addWidget(self.pdf_engine)
            self.locked += [self.pdf_ocr, self.pdf_engine]
        options_row.addStretch()
        box.addLayout(options_row)
        layout.addWidget(card)

        file_card = QFrame()
        file_card.setObjectName('card')
        file_layout = QVBoxLayout(file_card)
        file_layout.setContentsMargins(18, 15, 18, 16)
        file_layout.setSpacing(12)
        file_header = QHBoxLayout()
        file_header.addWidget(label('02', 'step'))
        file_header.addWidget(label('待转换文件', 'cardTitle'))
        self.count_label = label('0 个文件', 'hint')
        file_header.addWidget(self.count_label)
        file_header.addStretch()
        self.add_button = button('＋ 添加文件')
        self.add_button.clicked.connect(self.choose_files)
        self.remove_button = button('移除选中')
        self.remove_button.setObjectName('quiet')
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = button('清空')
        self.clear_button.setObjectName('quiet')
        self.clear_button.clicked.connect(self.clear)
        file_header.addWidget(self.add_button)
        file_header.addWidget(self.remove_button)
        file_header.addWidget(self.clear_button)
        file_layout.addLayout(file_header)
        self.locked += [self.add_button, self.remove_button, self.clear_button]

        self.file_stack = QStackedWidget()
        self.empty = QFrame()
        self.empty.setObjectName('dropArea')
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(12)
        arrow = label('↓', 'pageTitle')
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(arrow)
        title = label('拖入文件，开始转换', 'dropTitle')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(title)
        hint = label('支持 ' + HELP[category][0] + '，可一次添加多个文件', 'hint')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(hint)
        pick = button('选择文件', True)
        pick.clicked.connect(self.choose_files)
        pick.setFixedWidth(132)
        empty_layout.addWidget(pick, alignment=Qt.AlignmentFlag.AlignCenter)
        self.locked.append(pick)
        self.file_stack.addWidget(self.empty)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['文件名称', '格式', '大小', '状态 / 提示'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 75)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.open_result)
        self.file_stack.addWidget(self.table)
        file_layout.addWidget(self.file_stack, 1)
        file_layout.addWidget(label(HELP[category][1], 'hint', True))
        layout.addWidget(file_card, 1)

        output_card = QFrame()
        output_card.setObjectName('card')
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(18, 15, 18, 15)
        output_layout.setSpacing(12)
        row = QHBoxLayout()
        row.addWidget(label('03', 'step'))
        row.addWidget(label('保存到', 'cardTitle'))
        self.output_edit = QLineEdit(str(ROOT / '转换结果'))
        row.addWidget(self.output_edit, 1)
        choose = button('更改位置')
        choose.clicked.connect(self.choose_output)
        row.addWidget(choose)
        open_output = button('打开文件夹')
        open_output.clicked.connect(self.open_output)
        row.addWidget(open_output)
        self.locked += [self.output_edit, choose]
        output_layout.addLayout(row)
        row = QHBoxLayout()
        self.status = label('准备就绪 · 同名输出自动编号，不覆盖原文件。', 'status', True)
        row.addWidget(self.status, 1)
        self.cancel_button = button('停止后续任务')
        self.cancel_button.clicked.connect(self.cancel_batch)
        self.cancel_button.hide()
        row.addWidget(self.cancel_button)
        self.start_button = button('开始转换  →', True)
        self.start_button.setMinimumWidth(145)
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_batch)
        row.addWidget(self.start_button)
        output_layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        output_layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(80)
        self.log.hide()
        output_layout.addWidget(self.log)
        layout.addWidget(output_card)

    def choose_files(self):
        if self.busy:
            return
        patterns = ' '.join('*' + suffix for suffix in sorted(INPUT_SUFFIXES[self.category]))
        paths, _ = QFileDialog.getOpenFileNames(self, '选择需要转换的文件', '', f'支持的文件 ({patterns});;所有文件 (*)')
        self.add_files(paths)

    def add_files(self, paths):
        if self.busy:
            return
        rejected = []
        for value in paths:
            path = Path(value).resolve()
            if path.suffix.lower() not in INPUT_SUFFIXES[self.category] or not path.is_file():
                rejected.append(path.name)
            elif path not in self.files:
                self.files.append(path)
        self.refresh_table()
        if rejected:
            self.status.setText('未添加不支持的文件：' + '、'.join(rejected[:5]))
        elif self.files:
            self.status.setText(f'已添加 {len(self.files)} 个文件，选择目标格式后开始转换。')
            if len({path.suffix.lower() for path in self.files}) == 1:
                current = self.target.currentData()
                if self.files[0].suffix.lower().lstrip('.') == current:
                    self.target.setCurrentIndex((self.target.currentIndex() + 1) % self.target.count())

    def refresh_table(self):
        self.table.setRowCount(len(self.files))
        self.outputs.clear()
        for row, path in enumerate(self.files):
            try:
                size = path.stat().st_size
                size_text = f'{size / 1024 / 1024:.1f} MB' if size >= 1024 ** 2 else f'{size / 1024:.1f} KB'
            except OSError:
                size_text = '不可读'
            for column, text in enumerate((path.name, path.suffix[1:].upper(), size_text, '待转换')):
                item = QTableWidgetItem(text)
                item.setToolTip(str(path) if column == 0 else text)
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 46)
        self.file_stack.setCurrentIndex(1 if self.files else 0)
        self.count_label.setText(f'{len(self.files)} 个文件')
        self.start_button.setEnabled(bool(self.files) and not self.busy)

    def remove_selected(self):
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        self.files = [path for index, path in enumerate(self.files) if index not in rows]
        self.refresh_table()

    def clear(self):
        self.files.clear()
        self.refresh_table()
        self.progress.setValue(0)
        self.log.clear()
        self.log.hide()
        self.status.setText('文件列表已清空，已生成的文件仍保留。')

    def choose_output(self):
        directory = QFileDialog.getExistingDirectory(self, '选择输出文件夹', self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)

    def open_output(self):
        directory = Path(self.output_edit.text().strip())
        if directory.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory.resolve())))
        else:
            self.status.setText('输出文件夹尚未生成，转换成功后即可打开。')

    def options(self):
        if self.category == 'images':
            return Options(quality=self.quality.value(), max_size=self.max_size.value(), keep_metadata=self.metadata.isChecked())
        if self.category == 'tables':
            return Options(encoding=self.encoding.currentData(), delimiter=self.delimiter.currentData())
        return Options(pdf_ocr=self.pdf_ocr.isChecked(), pdf_engine=self.pdf_engine.currentData())

    def set_busy(self, busy):
        self.busy = busy
        for widget in self.locked:
            widget.setEnabled(not busy)
        self.start_button.setEnabled(bool(self.files) and not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.start_button.setText('转换中…' if busy else '开始转换  →')
        self.activity_changed.emit(busy)

    def start_batch(self):
        if not self.files or self.busy:
            return
        if not self.output_edit.text().strip():
            self.status.setText('请先选择输出文件夹。')
            return
        self.outputs.clear()
        self.log.clear()
        self.log.hide()
        self._completed = 0
        self.progress.setValue(0)
        self.set_busy(True)
        task = BatchTask(self.category, self.files, self.target.currentData(), Path(self.output_edit.text().strip()), self.options())
        task.signals.status.connect(self.row_status)
        task.signals.result.connect(self.row_result)
        task.signals.error.connect(self.row_error)
        task.signals.finished.connect(self.batch_finished)
        self.task = task
        QThreadPool.globalInstance().start(task)

    def row_status(self, index, status):
        item = self.table.item(index, 3)
        item.setText(status)
        item.setForeground(QColor('#285df5') if status.startswith('转换') else QColor('#8a97aa'))
        self.status.setText(f'正在处理 {index + 1} / {len(self.files)}：{self.files[index].name}')
        if status == '已取消':
            self._completed += 1

    def row_result(self, index, result):
        self._completed += 1
        self.outputs[index] = result.paths
        item = self.table.item(index, 3)
        item.setText('完成 · 有提示' if result.warnings else '转换完成')
        item.setForeground(QColor('#a6771f') if result.warnings else QColor('#27836b'))
        item.setToolTip('\n'.join(str(path) for path in result.paths) + '\n' + '\n'.join(result.warnings))
        for path in result.paths:
            self.log.appendPlainText(f'✓ {self.files[index].name} → {path}')
        for warning in result.warnings:
            self.log.appendPlainText('提示：' + warning)
        if result.warnings:
            self.log.show()
        self.progress.setValue(round(self._completed / len(self.files) * 100))

    def row_error(self, index, message):
        self._completed += 1
        item = self.table.item(index, 3)
        item.setText('失败：' + message[:45])
        item.setToolTip(message)
        item.setForeground(QColor('#c34b50'))
        self.log.appendPlainText(f'✕ {self.files[index].name}：{message}')
        self.log.show()
        self.progress.setValue(round(self._completed / len(self.files) * 100))

    def batch_finished(self, good, bad, skipped):
        self.set_busy(False)
        self.progress.setValue(100)
        self.status.setText(f'已结束 · 成功 {good}，失败 {bad}' + (f'，取消 {skipped}' if skipped else '') + '。双击成功项可打开结果。')
        self.task = None

    def cancel_batch(self):
        if self.task:
            self.task.cancel.set()
            self.cancel_button.setEnabled(False)
            self.status.setText('当前文件完成后停止，尚未开始的任务将取消。')

    def open_result(self, row, column):
        paths = self.outputs.get(row)
        if paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths[0].resolve())))

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.busy:
            self.add_files(url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile())
            event.acceptProposedAction()
