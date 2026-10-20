from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from .file_panel import FilePanel
from .text_panel import TextPanel
from .theme import app_icon, button, label
from . import __version__

PAGES = [
    ('文档转换', 'DOCUMENT CONVERTER', '在 TXT、Markdown、Word 与 PDF 之间自由转换。'),
    ('表格转换', 'SPREADSHEET CONVERTER', '保留数据细节，让 Excel 与 CSV 轻松互通。'),
    ('图片转换', 'IMAGE CONVERTER', '从 iPhone HEIC 到常见图片格式，一次处理多张照片。'),
    ('文本处理', 'TEXT WORKSPACE', '识别、核对、修改，再一键复制到你需要的地方。'),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'格式转换工厂 {__version__}')
        self.setWindowIcon(app_icon())
        self.resize(1280, 840)
        self.setMinimumSize(1100, 740)
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(206)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 28, 18, 24)
        side.setSpacing(10)
        logo = label('')
        logo.setPixmap(app_icon().pixmap(40, 40))
        side.addWidget(logo)
        side.addSpacing(5)
        side.addWidget(label('格式转换工厂', 'brand'))
        side.addWidget(label('FORMAT FACTORY', 'brandSub'))
        side.addSpacing(34)
        side.addWidget(label('工作空间', 'sideGroup'))
        self.nav_buttons = []
        for index, (title, _, _) in enumerate(PAGES):
            nav = button(title)
            nav.setObjectName('nav')
            nav.setCheckable(True)
            nav.clicked.connect(lambda checked=False, i=index: self.navigate(i))
            self.nav_buttons.append(nav)
            side.addWidget(nav)
        side.addStretch()
        side.addWidget(label('文件留在你的电脑上', 'sideNote'))
        side.addWidget(label('批量处理 · 保留原文件', 'sideNote'))
        side.addSpacing(18)
        self.version_label = label(f'VERSION {__version__}', 'sideGroup')
        side.addWidget(self.version_label)
        root_layout.addWidget(sidebar)

        workspace = QWidget()
        workspace.setObjectName('workspace')
        content = QVBoxLayout(workspace)
        content.setContentsMargins(30, 28, 30, 22)
        content.setSpacing(22)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        headings.setSpacing(6)
        self.eyebrow = label('', 'eyebrow')
        self.title = label('', 'pageTitle')
        self.subtitle = label('', 'subtitle')
        headings.addWidget(self.eyebrow)
        headings.addWidget(self.title)
        headings.addWidget(self.subtitle)
        header.addLayout(headings, 1)
        header.addWidget(label('●  本地运行', 'badge'), alignment=Qt.AlignmentFlag.AlignTop)
        content.addLayout(header)
        self.stack = QStackedWidget()
        for category in ('documents', 'tables', 'images'):
            self.stack.addWidget(FilePanel(category))
        self.stack.addWidget(TextPanel())
        content.addWidget(self.stack, 1)
        root_layout.addWidget(workspace, 1)
        self.setCentralWidget(root)
        self.navigate(0)

    def navigate(self, index):
        self.stack.setCurrentIndex(index)
        title, eyebrow, subtitle = PAGES[index]
        self.title.setText(title)
        self.eyebrow.setText(eyebrow)
        self.subtitle.setText(subtitle)
        for position, nav in enumerate(self.nav_buttons):
            nav.setChecked(position == index)

    def open_formula_workspace(self):
        self.navigate(3)
        panel = self.stack.widget(3)
        panel.method_combo.setCurrentIndex(panel.method_combo.findData('formula'))
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
        panel.source_hint.setText('公式模式已就绪：粘贴 LaTeX 文字可直接转换；截图请导入后框选完整单条公式。')
        panel.status.setText('公式处理已就绪 · 支持文字转换和截图识别，核对后可复制到 Word / WPS。')

    def closeEvent(self, event):
        if any(getattr(self.stack.widget(index), 'busy', False) for index in range(self.stack.count())):
            QMessageBox.information(self, '任务仍在处理', '请等待当前文件处理完成；批量任务可先点击“停止后续任务”。')
            event.ignore()
        else:
            event.accept()
