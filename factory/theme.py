from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

STYLE = '''
QWidget { font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif; font-size: 13px; color: #24334b; }
QMainWindow, QWidget#workspace { background: #f3f5f9; }
QFrame#sidebar { background: #101f35; border: none; }
QLabel#brand { color: #ffffff; font-size: 20px; font-weight: 700; }
QLabel#brandSub { color: #8294b0; font-size: 10px; letter-spacing: 2px; }
QLabel#sideNote { color: #91a2bd; font-size: 11px; }
QLabel#sideGroup { color: #6e83a4; font-size: 11px; }
QPushButton#nav { border: none; border-radius: 9px; background: transparent; color: #a9b8cf; text-align: left; padding: 14px 18px; font-size: 14px; }
QPushButton#nav:hover { background: #1a304b; color: white; }
QPushButton#nav:checked { color: #ffffff; background: #285df5; font-weight: 600; }
QLabel#pageTitle { font-size: 28px; font-weight: 700; color: #152640; }
QLabel#subtitle { color: #7d899b; font-size: 12px; }
QLabel#eyebrow { font-size: 10px; color: #285df5; font-weight: 700; letter-spacing: 2px; }
QLabel#badge { color: #38816f; background: #e4f2ec; border-radius: 12px; padding: 6px 12px; font-size: 11px; }
QFrame#card { background: #ffffff; border: 1px solid #e3e8f0; border-radius: 12px; }
QFrame#dropArea { background: #f9fbff; border: 1px dashed #bacbe8; border-radius: 11px; }
QLabel#cardTitle { font-size: 14px; font-weight: 600; color: #1d304d; }
QLabel#dropTitle { font-size: 19px; font-weight: 600; color: #273d5c; }
QLabel#hint { color: #8390a3; font-size: 11px; }
QLabel#status { color: #536b90; font-size: 12px; }
QLabel#step { color: #285df5; background: #edf2ff; border-radius: 10px; padding: 4px 8px; font-size: 11px; }
QPushButton { background: #ffffff; border: 1px solid #dce3ee; border-radius: 7px; padding: 8px 13px; color: #344866; }
QPushButton:hover { background: #f0f4ff; border-color: #b4c6f6; }
QPushButton:pressed { background: #e4ebff; }
QPushButton:disabled { color: #a7b2c4; background: #f2f4f8; border-color: #e5e9f1; }
QPushButton#primary { background: #285df5; border: 1px solid #285df5; color: #ffffff; font-weight: 600; }
QPushButton#primary:hover { background: #194cdf; }
QPushButton#primary:disabled { background: #adc0f8; border-color: #adc0f8; color: #ffffff; }
QPushButton#quiet { background: transparent; border: none; color: #6b7c96; padding: 7px 9px; }
QComboBox, QLineEdit, QSpinBox { border: 1px solid #dce3ee; border-radius: 6px; background: #ffffff; padding: 7px 9px; min-height: 18px; selection-background-color: #285df5; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border-color: #7293f9; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #ffffff; selection-background-color: #edf2ff; selection-color: #285df5; border: 1px solid #dce3ee; padding: 4px; }
QPlainTextEdit { background: #ffffff; border: none; padding: 8px; selection-background-color: #dce6ff; selection-color: #142849; font-size: 14px; }
QPlainTextEdit:disabled { background: #f8faff; }
QTableWidget { background: white; alternate-background-color: #f8faff; border: none; gridline-color: #eff2f7; selection-background-color: #edf2ff; selection-color: #1d3456; }
QHeaderView::section { background: #f7f9fc; color: #7d8aa0; border: none; border-bottom: 1px solid #e8edf4; padding: 10px; font-size: 11px; }
QTableWidget::item { padding: 9px; border-bottom: 1px solid #eff2f7; }
QCheckBox { spacing: 7px; font-size: 12px; }
QCheckBox::indicator { width: 15px; height: 15px; }
QProgressBar { border: none; border-radius: 3px; background: #e9eef7; height: 5px; max-height: 5px; }
QProgressBar::chunk { background: #285df5; border-radius: 3px; }
QScrollBar:vertical { width: 9px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: #cbd4e3; border-radius: 3px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QGraphicsView { background: #f5f7fb; border: none; }
QSplitter::handle { background: #e6ebf3; width: 1px; }
QToolTip { background: #172a45; color: white; border: none; padding: 8px; }
QMessageBox { background: #ffffff; }
'''


def apply_theme(application: QApplication):
    # Offscreen rendering and restricted Windows sessions may not enumerate system fonts.
    # Loading the existing local fonts explicitly also makes visual verification reliable.
    from pathlib import Path
    families = set(QFontDatabase.families())
    for family, filename in (('Microsoft YaHei UI', 'msyh.ttc'),
                             ('Microsoft YaHei UI', 'msyhbd.ttc'),
                             ('Segoe UI', 'segoeui.ttf'),
                             ('Segoe UI Symbol', 'seguisym.ttf'),
                             ('Cambria Math', 'cambria.ttc')):
        if family not in families:
            path = Path('C:/Windows/Fonts') / filename
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))
    application.setStyle('Fusion')
    application.setFont(QFont('Microsoft YaHei UI', 10))
    application.setStyleSheet(STYLE)


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setObjectName('primary')
    return widget


def app_icon(size=64):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#285df5'))
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * .22, size * .22)
    painter.setPen(QPen(QColor('white'), max(2, size * .065), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawLine(int(size * .25), int(size * .37), int(size * .75), int(size * .37))
    painter.drawLine(int(size * .63), int(size * .25), int(size * .75), int(size * .37))
    painter.drawLine(int(size * .63), int(size * .49), int(size * .75), int(size * .37))
    painter.drawLine(int(size * .75), int(size * .65), int(size * .25), int(size * .65))
    painter.drawLine(int(size * .37), int(size * .53), int(size * .25), int(size * .65))
    painter.drawLine(int(size * .37), int(size * .77), int(size * .25), int(size * .65))
    painter.end()
    return QIcon(pixmap)
