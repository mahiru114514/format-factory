import pytest


@pytest.fixture(scope='session')
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    from factory.text_panel import TextPanel
    widget = TextPanel()
    yield widget
    widget.close()


def test_copy_current_edited_text_preserves_latex(panel, app):
    panel.accept_result('original')
    edited = '修正 αβ\n' + r'\frac{x}{2}'
    panel.result_edit.setPlainText(edited)
    panel.copy_all_button.click()
    assert app.clipboard().text() == edited
    assert panel.state.dirty


def test_copy_selected_only(panel, app):
    from PySide6.QtGui import QTextCursor
    panel.accept_result('甲乙丙丁')
    cursor = panel.result_edit.textCursor()
    cursor.setPosition(1)
    cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
    panel.result_edit.setTextCursor(cursor)
    panel.copy_selected_button.click()
    assert app.clipboard().text() == '乙丙'


def test_empty_actions_disabled(panel):
    assert not panel.copy_all_button.isEnabled()
    assert not panel.save_button.isEnabled()
    panel.accept_result('x')
    panel.result_edit.setPlainText(' \n')
    assert not panel.copy_all_button.isEnabled()
    assert not panel.copy_selected_button.isEnabled()


def test_copy_failure_is_retryable(panel, app):
    panel.accept_result('hello')
    def fail(text):
        raise RuntimeError('clipboard busy')
    panel.clipboard_writer = fail
    panel.copy_all_button.click()
    assert '失败' in panel.status.text()
    assert panel.result_edit.toPlainText() == 'hello'
    assert panel.copy_all_button.isEnabled()
    panel.clipboard_writer = lambda text: app.clipboard().setText(text)
    panel.copy_all_button.click()
    assert app.clipboard().text() == 'hello'


def test_declining_replace_keeps_manual_edits(panel):
    panel.accept_result('original')
    panel.result_edit.setPlainText('手工修正')
    panel.source_edit.setPlainText('new')
    panel.confirm_replace = lambda: False
    panel.start_processing()
    assert panel.result_edit.toPlainText() == '手工修正'
    assert not panel.busy


def test_busy_locks_actions_and_input(panel):
    panel.accept_result('before')
    panel.set_busy(True)
    assert not panel.copy_all_button.isEnabled()
    assert not panel.run_button.isEnabled()
    assert panel.result_edit.isReadOnly()
    panel.set_busy(False)
    assert panel.copy_all_button.isEnabled()


def test_pasting_another_image_preserves_explicit_formula_mode(panel):
    from PIL import Image
    panel.method_combo.setCurrentIndex(panel.method_combo.findData('formula'))
    panel.show_source_image(Image.new('RGB', (300, 100), 'white'))
    assert panel.method_combo.currentData() == 'formula'
    panel.show_source_image(Image.new('RGB', (400, 120), 'black'))
    assert panel.method_combo.currentData() == 'formula'
    assert '单条公式识别' in panel.status.text()


def test_image_text_mode_exposes_formula_action_and_explicit_run_label(panel):
    from PIL import Image
    panel.show_source_image(Image.new('RGB', (300, 100), 'white'))
    assert not panel.image_mode_hint.isHidden()
    assert '识别文字' in panel.run_button.text()
    panel.method_combo.setCurrentIndex(panel.method_combo.findData('formula'))
    assert panel.image_mode_hint.isHidden()
    assert '识别公式' in panel.run_button.text()
    panel.set_busy(True)
    assert not panel.formula_button.isEnabled()
    panel.set_busy(False)
    assert '识别公式' in panel.run_button.text()


def test_formula_action_uses_formula_engine_instead_of_ordinary_ocr(panel, monkeypatch):
    from PIL import Image
    import factory.recognition as recognition
    panel.show_source_image(Image.new('RGB', (300, 100), 'white'))
    calls = []
    monkeypatch.setattr(recognition, 'recognize_formula', lambda image: calls.append('formula') or r'A\iff B')
    monkeypatch.setattr(recognition, 'recognize_image', lambda image: pytest.fail('Formula action must not invoke ordinary OCR'))
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    panel.formula_button.click()
    assert calls == ['formula']
    assert panel.method_combo.currentData() == 'formula'
    assert panel.result_edit.toPlainText().replace(' ', '') == 'A⇔B'


def test_formula_action_declining_replace_keeps_mode_and_manual_edits(panel, monkeypatch):
    from PIL import Image
    panel.show_source_image(Image.new('RGB', (300, 100), 'white'))
    panel.accept_result('old')
    panel.result_edit.setPlainText('手工修改')
    panel.confirm_replace = lambda: False
    monkeypatch.setattr(panel, '_submit', lambda *args: pytest.fail('Declined replacement must not start recognition'))
    panel.formula_button.click()
    assert panel.method_combo.currentData() == 'ocr'
    assert panel.result_edit.toPlainText() == '手工修改'


def test_formula_workspace_entry_is_ready_without_replacing_source_or_result(app):
    from factory.ui import MainWindow
    from factory import __version__
    window = MainWindow()
    window.open_formula_workspace()
    assert window.stack.currentIndex() == 3
    assert window.stack.widget(3).method_combo.currentData() == 'formula'
    assert __version__ == '0.1.5'
    assert window.stack.widget(3).mode_combo.currentData() == 'office'
    assert __version__ in window.windowTitle()
    assert window.version_label.text() == 'VERSION ' + __version__
    window.close()


def test_save_writes_current_editor_text(panel, tmp_path):
    panel.accept_result('old')
    panel.result_edit.setPlainText('校对后\n' + r'\alpha')
    destination = tmp_path / '文本.txt'
    panel.save_to(destination)
    assert destination.read_text(encoding='utf-8') == panel.result_edit.toPlainText()


def test_white_transparent_clipboard_formula_is_visible_in_preview(panel):
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (360, 120), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((100, 30, 140, 70), fill='white')
    panel.show_source_image(image)
    assert panel.preview.image.mode == 'RGB'
    assert panel.preview.image.getpixel((0, 0)) == (0, 0, 0)
    assert panel.preview.image.getpixel((120, 50)) == (255, 255, 255)


def test_main_window_all_four_workspaces(app):
    from factory.ui import MainWindow
    window = MainWindow()
    assert window.stack.count() == 4
    for index in range(4):
        window.navigate(index)
        assert window.stack.currentIndex() == index
    window.close()


def test_chinese_and_ascii_fonts_are_available(app):
    from factory.theme import apply_theme
    from PySide6.QtGui import QFontMetrics
    apply_theme(app)
    metrics = QFontMetrics(app.font())
    assert metrics.inFont('中') and metrics.inFont('A')


def test_formula_symbols_render_as_real_glyphs(app):
    from factory.theme import apply_theme
    from PySide6.QtGui import QTextLayout
    apply_theme(app)
    layout = QTextLayout('中文 A ⟷ ⋁ ⇔ ∑ 𝑥 ℝ ℂ ℕ ℤ 𝛼 ∅ ∉ ⊆ ⊇ ∇ ∂ ∮ ∬ ∭ ⊕ ⊗ ⟶ ↦ ⇌ ≃ ≅ ≈ ∝ ℓ ∴ √ ⋀ ∀ ∃ ¬ ∧ ∨ ∏ ∞ ⁵ ₀', app.font())
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    indexes = [index for run in layout.glyphRuns() for index in run.glyphIndexes()]
    assert indexes and 0 not in indexes, 'Formula symbols must not render as missing-glyph boxes'


def test_office_mode_preserves_source_for_editing(panel, monkeypatch):
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    assert panel.mode_combo.currentData() == 'office'
    source = r'\frac{a}{b}+\sqrt[3]{x}'
    panel.source_edit.setPlainText(source)
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    panel.start_processing()
    assert panel.result_edit.toPlainText() == source
    assert panel.result_mode == 'office'
    assert 'Word' in panel.copy_all_button.text()


def test_office_copy_uses_current_edited_source(panel, app, monkeypatch):
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    panel.accept_result(r'\frac{x}{2}')
    edited = r'\frac{y_1}{\sqrt{3}}'
    panel.result_edit.setPlainText(edited)
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    panel.copy_all()
    assert app.clipboard().text() == edited
    assert app.clipboard().mimeData().hasHtml()
    assert 'mfrac' in app.clipboard().mimeData().html()
    assert '可编辑公式' in panel.status.text()


def test_office_copy_selected_does_not_include_unselected_math(panel, app, monkeypatch):
    from PySide6.QtGui import QTextCursor
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    panel.accept_result(r'x^2+\frac{y}{3}')
    cursor = panel.result_edit.textCursor()
    cursor.setPosition(4)
    cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
    panel.result_edit.setTextCursor(cursor)
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    panel.copy_selected()
    assert app.clipboard().text() == r'\frac{y}{3}'
    assert 'mfrac' in app.clipboard().mimeData().html()


def test_switching_output_does_not_reinterpret_existing_readable_result(panel, app):
    panel.accept_result('((x)/(2))')
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    panel.copy_all()
    assert app.clipboard().text() == '((x)/(2))'
    assert not app.clipboard().mimeData().hasHtml()
    assert panel.result_mode == 'readable'


def test_switching_away_keeps_existing_office_result_copyable(panel, app, monkeypatch):
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    panel.accept_result(r'\sqrt{x}')
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('readable'))
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    panel.copy_all()
    assert app.clipboard().mimeData().hasHtml()
    assert panel.result_mode == 'office'


def test_bad_office_copy_preserves_clipboard_and_editor(panel, app, monkeypatch):
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    panel.accept_result(r'\frac{x}')
    app.clipboard().setText('previous clipboard')
    def submit(work, success):
        try:
            success(work())
        except Exception as error:
            panel.processing_failed(str(error))
    monkeypatch.setattr(panel, '_submit', submit)
    panel.copy_all()
    assert app.clipboard().text() == 'previous clipboard'
    assert panel.result_edit.toPlainText() == r'\frac{x}'
    assert '失败' in panel.status.text()


def test_silent_clipboard_rejection_does_not_announce_success(panel, app, monkeypatch):
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    panel.accept_result(r'\frac{x}{2}')
    app.clipboard().setText('previous clipboard')
    monkeypatch.setattr(app.clipboard(), 'setMimeData', lambda mime: None)
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    panel.copy_all()
    assert '失败' in panel.status.text()
    assert app.clipboard().text() == 'previous clipboard'


def test_office_docx_save_uses_current_edits(panel, tmp_path, monkeypatch):
    import zipfile
    from PySide6.QtWidgets import QFileDialog
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    panel.accept_result(r'\sqrt{x}')
    panel.result_edit.setPlainText(r'\frac{changed}{3}')
    destination = tmp_path / 'edited.docx'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(destination), 'Word 文档 (*.docx)'))
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    panel.choose_save_formula()
    with zipfile.ZipFile(destination) as archive:
        xml = archive.read('word/document.xml').decode('utf-8')
    assert '<m:f>' in xml and '<m:rad>' not in xml
    assert '已保存可编辑公式' in panel.status.text()


@pytest.mark.parametrize('output', ['source', 'office', 'readable'])
def test_direct_latex_paste_in_formula_mode_converts_without_image(panel, monkeypatch, output):
    import factory.recognition as recognition
    from factory.text import process_source
    panel.method_combo.setCurrentIndex(panel.method_combo.findData('formula'))
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(output))
    monkeypatch.setattr(recognition, 'recognize_formula', lambda image: pytest.fail('LaTeX text must not invoke image recognition'))
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    source = r'\frac{a+b}{c+d}'
    panel.source_edit.setPlainText(source)  # Same textChanged path as Ctrl+V.
    assert '转换' in panel.run_button.text()
    panel.run_button.click()
    assert panel.result_edit.toPlainText() == process_source(source, output)
    assert panel.result_mode == output
    assert '需要图片' not in panel.status.text()
    # A later screenshot still uses the user's chosen formula recognizer.
    from PIL import Image
    panel.show_source_image(Image.new('RGB', (300, 100), 'white'))
    assert panel.method_combo.currentData() == 'formula'
    assert '识别公式' in panel.run_button.text()


def test_direct_latex_paste_formula_mode_respects_declined_replace(panel, monkeypatch):
    panel.method_combo.setCurrentIndex(panel.method_combo.findData('formula'))
    panel.accept_result('old')
    panel.result_edit.setPlainText('保留我的修改')
    panel.source_edit.setPlainText(r'\frac{a}{b}')
    panel.confirm_replace = lambda: False
    monkeypatch.setattr(panel, '_submit', lambda *args: pytest.fail('Declined replacement must not run'))
    panel.run_button.click()
    assert panel.result_edit.toPlainText() == '保留我的修改'


def test_source_result_can_copy_editable_formula_with_explicit_button(panel, app, monkeypatch):
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('source'))
    panel.accept_result(r'\frac{a+b}{c+d}')
    edited = r'\frac{a+b+1}{c+d}'
    panel.result_edit.setPlainText(edited)
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    assert not panel.copy_as_formula_button.isHidden()
    assert '源码' in panel.copy_all_button.text()
    panel.copy_as_formula_button.click()
    assert app.clipboard().text() == edited
    assert 'mfrac' in app.clipboard().mimeData().html()
    assert '已复制可编辑公式' in panel.status.text()
    panel.copy_all_button.click()
    assert app.clipboard().text() == edited
    assert not app.clipboard().mimeData().hasHtml()


def test_readable_result_never_reconstructs_formula_from_lossy_text(panel):
    panel.accept_result('((a+b)/(c+d))')
    assert panel.copy_as_formula_button.isHidden()
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('source'))
    assert panel.copy_as_formula_button.isHidden()  # Existing readable result stays readable.


@pytest.mark.parametrize('entry', ['toolbar', 'file', 'word'])
def test_text_import_keeps_formula_preference_for_next_screenshot(panel, app, tmp_path, entry):
    from PIL import Image
    panel.method_combo.setCurrentIndex(panel.method_combo.findData('formula'))
    source = r'\frac{a+b}{c+d}'
    if entry == 'toolbar':
        app.clipboard().setText(source)
        panel.paste_button.click()
    elif entry == 'file':
        path = tmp_path / 'formula.tex'
        path.write_text(source, encoding='utf-8')
        panel.load_source(path)
    else:
        panel.loaded_word(source)
    assert panel.source_edit.toPlainText() == source
    assert panel.method_combo.currentData() == 'formula'
    panel.show_source_image(Image.new('RGB', (300, 100), 'white'))
    assert panel.method_combo.currentData() == 'formula'
    assert '识别公式' in panel.run_button.text()


def test_source_formula_copy_failure_keeps_edits_and_only_offers_visible_actions(panel, monkeypatch):
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('source'))
    panel.accept_result(r'\frac{a}{b}')
    def fail(result):
        raise RuntimeError('clipboard busy')
    panel.office_clipboard_writer = fail
    monkeypatch.setattr(panel, '_submit', lambda work, success: success(work()))
    panel.copy_as_formula_button.click()
    assert '失败' in panel.status.text()
    assert 'DOCX' not in panel.status.text()
    assert panel.result_edit.toPlainText() == r'\frac{a}{b}'
