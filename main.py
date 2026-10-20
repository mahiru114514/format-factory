import os
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    # A local temp folder also keeps temporary documents beside the application.
    temp = root / '.cache' / 'tmp'
    temp.mkdir(parents=True, exist_ok=True)
    os.environ['TEMP'] = os.environ['TMP'] = str(temp)
    tempfile.tempdir = str(temp)
    from PySide6.QtWidgets import QApplication
    from factory.theme import apply_theme, app_icon
    from factory.ui import MainWindow
    application = QApplication(sys.argv)
    application.setApplicationName('格式转换工厂')
    from factory import __version__
    application.setApplicationVersion(__version__)
    application.setOrganizationName('Local Format Factory')
    application.setWindowIcon(app_icon())
    apply_theme(application)
    window = MainWindow()
    if '--formula-workspace' in sys.argv:
        window.open_formula_workspace()
    window.show()
    if '--smoke-test' in sys.argv:
        from PySide6.QtCore import QTimer
        from factory.smoke import run_smoke
        def smoke():
            try:
                report = run_smoke(root, with_word='--with-word' in sys.argv)
                (root / 'smoke-result.txt').write_text(report, encoding='utf-8')
                window.grab().save(str(root / 'smoke-preview.png'))
                application.exit(0)
            except Exception:
                import traceback
                (root / 'smoke-result.txt').write_text(traceback.format_exc(), encoding='utf-8')
                application.exit(1)
        QTimer.singleShot(200, smoke)
    return application.exec()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
        report = root / 'startup-error.txt'
        report.write_text(traceback.format_exc(), encoding='utf-8')
        if '--smoke-test' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f'启动失败，详细信息已保存到：\n{report}', '格式转换工厂', 16)
        raise SystemExit(1)
