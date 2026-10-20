import threading
import time

import pytest


def test_batch_continues_after_corrupt_input(tmp_path, app):
    from PIL import Image
    from factory.workers import BatchTask
    from factory.common import Options
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance()
    assert app is not None
    broken = tmp_path / 'broken.png'
    broken.write_bytes(b'invalid')
    good = tmp_path / 'valid.png'
    Image.new('RGB', (10, 10), 'blue').save(good)
    task = BatchTask('images', [broken, good], 'jpg', tmp_path / 'output', Options())
    errors, outputs, finished = [], [], []
    task.signals.error.connect(lambda i, message: errors.append(i))
    task.signals.result.connect(lambda i, result: outputs.append(result))
    task.signals.finished.connect(lambda *summary: finished.append(summary))
    task.run()
    assert errors == [0]
    assert outputs[0].paths[0].is_file()
    assert finished == [(1, 1, 0)]


def test_cancelled_batch_does_not_start_files(tmp_path, app):
    from factory.workers import BatchTask
    from factory.common import Options
    task = BatchTask('images', [tmp_path / 'not_needed.png'], 'jpg', tmp_path, Options())
    summary = []
    task.signals.finished.connect(lambda *args: summary.append(args))
    task.cancel.set()
    task.run()
    assert summary == [(0, 0, 1)]


@pytest.fixture(scope='module')
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_background_conversion_updates_editor_and_copy(app):
    from factory.text_panel import TextPanel
    widget = TextPanel()
    widget.source_edit.setPlainText(r'$\alpha + \frac{x}{2}$')
    widget.start_processing()
    deadline = time.monotonic() + 10
    while widget.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not widget.busy
    assert 'α' in widget.result_edit.toPlainText()
    widget.result_edit.setPlainText('已校对 α')
    widget.copy_all_button.click()
    assert app.clipboard().text() == '已校对 α'
    widget.close()


def test_real_batch_ui_completion(app, tmp_path):
    from PIL import Image
    from factory.file_panel import FilePanel
    source = tmp_path / 'phone.png'
    Image.new('RGB', (64, 48), 'blue').save(source)
    widget = FilePanel('images')
    widget.add_files([source])
    widget.target.setCurrentIndex(widget.target.findData('heic'))
    widget.output_edit.setText(str(tmp_path / 'output'))
    widget.start_batch()
    deadline = time.monotonic() + 15
    while widget.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not widget.busy
    assert widget.outputs[0][0].suffix == '.heic'
    assert widget.table.item(0, 3).text().startswith('转换完成')
    widget.close()
