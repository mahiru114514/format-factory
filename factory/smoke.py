"""End-to-end checks usable from the frozen executable, without pytest."""
from pathlib import Path
from tempfile import TemporaryDirectory


def run_smoke(root: Path, with_word: bool = False) -> str:
    from PIL import Image, ImageDraw, ImageFont
    from PySide6.QtWidgets import QApplication
    from openpyxl import load_workbook
    from .common import Options
    from .service import convert
    from .recognition import recognize_formula, recognize_image, ROOT as RESOURCE_ROOT
    from .text_panel import TextPanel
    from .text import latex_to_text

    checks = []
    cache = root / '.cache'
    cache.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='smoke-', dir=cache) as folder:
        temp = Path(folder)
        source = temp / 'sample.md'
        source.write_text('# 中文示例\n\n你好世界\n\n|名称|编号|\n|---|---|\n|张三|001|\n', encoding='utf-8')
        docx = convert('documents', source, 'docx', temp, Options()).paths[0]
        assert docx.stat().st_size > 1000
        checks.append('Markdown -> Word: OK')
        md = convert('documents', docx, 'md', temp, Options()).paths[0]
        assert '中文示例' in md.read_text(encoding='utf-8')
        checks.append('Word -> Markdown, Chinese: OK')
        pdf = convert('documents', docx, 'pdf', temp, Options(pdf_engine='basic')).paths[0]
        txt = convert('documents', pdf, 'txt', temp, Options()).paths[0]
        assert '你好世界' in txt.read_text(encoding='utf-8')
        checks.append('Word -> basic PDF -> TXT: OK')
        if with_word:
            native_pdf = convert('documents', docx, 'pdf', temp, Options(pdf_engine='word')).paths[0]
            native_txt = convert('documents', native_pdf, 'txt', temp, Options()).paths[0]
            assert '你好世界' in native_txt.read_text(encoding='utf-8')
            checks.append('Installed Word -> PDF: OK')
        recovered = convert('documents', pdf, 'docx', temp, Options()).paths[0]
        assert recovered.stat().st_size > 1000
        checks.append('PDF -> editable Word: OK')
        image = temp / 'phone.png'
        Image.new('RGB', (64, 48), 'blue').save(image)
        heic = convert('images', image, 'heic', temp, Options()).paths[0]
        png = convert('images', heic, 'png', temp, Options()).paths[0]
        with Image.open(png) as result:
            assert result.size == (64, 48)
        checks.append('PNG -> HEIC -> PNG, no overwrite: OK')
        csv = temp / 'table.csv'
        csv.write_text('姓名,编号\n张三,00123\n', encoding='utf-8-sig')
        xlsx = convert('tables', csv, 'xlsx', temp, Options()).paths[0]
        book = load_workbook(xlsx)
        assert book.active['B2'].value == '00123'
        book.close()
        exported = convert('tables', xlsx, 'csv', temp, Options()).paths[0]
        assert '张三' in exported.read_text(encoding='utf-8-sig')
        checks.append('CSV -> XLSX -> CSV, leading zeros: OK')
        image = Image.new('RGB', (750, 120), 'white')
        draw = ImageDraw.Draw(image)
        draw.text((20, 25), '你好世界 Hello 123', fill='black', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 42))
        assert '123' in recognize_image(image)
        checks.append('Offline Chinese / English OCR: OK')
        formula = Image.new('RGB', (400, 100), 'white')
        ImageDraw.Draw(formula).text((20, 15), 'x + y = 1', fill='black', font=ImageFont.truetype('C:/Windows/Fonts/times.ttf', 48))
        latex = recognize_formula(formula)
        assert 'x' in latex and 'y' in latex and '=' in latex
        checks.append('Offline formula OCR: ' + latex)
        from .office_math import convert_office_math
        assert convert_office_math(latex).equations == 1
        checks.append('Model-generated bold variables -> editable Office equation: OK')
        assert latex_to_text(r'\frac{a+b}{c+d}^2') == '((a+b)/(c+d))^2'
        assert latex_to_text(r'\sqrt[3]{x}') == '√[3](x)'
        for structured in (r'\underleftarrow{AB}', r'\begin{array}{r|l}A&b\end{array}'):
            assert latex_to_text(structured) == structured
        checks.append('Formula grouping, root degree, annotations and matrix boundaries: OK')
        panel = TextPanel()
        # Exercise the user's reported entry path, not only a direct engine call.
        # Ordinary image import initially chooses OCR; the visible formula action
        # must route the real screenshot through the formula model instead.
        import time
        panel.resize(1280, 800)
        with Image.open(RESOURCE_ROOT / 'resources/examples/logic-formula.png') as sample:
            panel.show_source_image(sample)
        assert panel.method_combo.currentData() == 'ocr'
        assert not panel.image_mode_hint.isHidden()
        panel.show()
        panel.formula_button.click()
        deadline = time.monotonic() + 25
        while panel.busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert not panel.busy, 'Formula action timed out'
        result = panel.result_edit.toPlainText()
        compact = ''.join(result.split())
        assert '⋁_{i=0}^{5}' in compact and 'used[t]' in compact and 'slot[i]=t' in compact, result
        assert panel.method_combo.currentData() == 'formula'
        panel.copy_all_button.click()
        assert QApplication.clipboard().text() == result
        panel.save_to(root / 'formula-recognition.txt')
        assert (root / 'formula-recognition.txt').read_text(encoding='utf-8') == result
        QApplication.processEvents()
        panel.grab().save(str(root / 'formula-preview.png'))
        checks.append('Reported screenshot -> formula action -> disjunction, bounds, clipboard/TXT: OK')
        panel.accept_result('original')
        panel.result_edit.setPlainText('已校对 α\n' + r'\frac{x}{2}')
        panel.copy_all_button.click()
        assert QApplication.clipboard().text() == panel.result_edit.toPlainText()
        panel.save_to(temp / 'edited.txt')
        assert (temp / 'edited.txt').read_text(encoding='utf-8') == panel.result_edit.toPlainText()
        panel.close()
        checks.append('Edited result -> clipboard and TXT: OK')
        # Reproduce direct editor paste while the formula entry is selected.
        # This must not reject LaTeX as a missing screenshot (0.1.4 bug).
        pasted = TextPanel()
        pasted.method_combo.setCurrentIndex(pasted.method_combo.findData('formula'))
        pasted.mode_combo.setCurrentIndex(pasted.mode_combo.findData('office'))
        direct_source = r'\frac{a+b}{c+d}'
        QApplication.clipboard().setText(direct_source)
        pasted.source_edit.paste()
        assert '转换' in pasted.run_button.text()
        pasted.run_button.click()
        deadline = time.monotonic() + 15
        while pasted.busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert not pasted.busy and pasted.result_edit.toPlainText() == direct_source, pasted.status.text()
        pasted.copy_all_button.click()
        deadline = time.monotonic() + 15
        while pasted.busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert not pasted.busy and '已复制可编辑公式' in pasted.status.text(), pasted.status.text()
        assert 'mfrac' in QApplication.clipboard().mimeData().html()
        pasted.show()
        QApplication.processEvents()
        pasted.grab().save(str(root / 'direct-latex-paste-preview.png'))
        pasted.close()
        checks.append('Direct LaTeX editor paste in formula mode -> convert -> Office clipboard: OK')
        # Exercise the new Office path with the actual recognized screenshot,
        # then edits, through the same async buttons used in the desktop app.
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
        panel.confirm_replace = lambda: True
        panel.start_processing()
        deadline = time.monotonic() + 30
        while panel.busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert not panel.busy
        assert r'\bigvee' in panel.result_edit.toPlainText()
        assert panel.result_mode == 'office'
        panel.result_edit.setPlainText(r'used[t]\iff\bigvee_{i=0}^{5}(slot[i]=t)+\frac{x_1^2}{\sqrt[3]{y}}')
        panel.copy_all_button.click()
        deadline = time.monotonic() + 30
        while panel.busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert not panel.busy and '已复制可编辑公式' in panel.status.text(), panel.status.text()
        mime = QApplication.clipboard().mimeData()
        assert mime.hasHtml() and 'mfrac' in mime.html() and 'munderover' in mime.html()
        assert QApplication.clipboard().text() == panel.result_edit.toPlainText()
        package = bytes(mime.data('application/x-qt-windows-mime;value="Kingsoft WPS 9.0 Format"'))
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            xml = archive.read('word/document.xml').decode('utf-8')
            assert '<m:nary>' in xml and '<m:f>' in xml and '<m:rad>' in xml
            from xml.etree import ElementTree as ET
            ns = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
            structure = ET.fromstring(xml)
            body = structure.find('.//m:nary/m:e', ns)
            assert body is not None and ''.join(body.itertext()) == '(slot[i]=t)', 'Large operator must have a real operand, not an empty placeholder'
        (root / 'office-clipboard-sample.docx').write_bytes(package)
        panel.show()
        QApplication.processEvents()
        panel.grab().save(str(root / 'office-copy-preview.png'))
        panel.close()
        checks.append('Screenshot -> editable LaTeX -> edited Office clipboard MathML/OMML: OK')
        panel.accept_result(r'\mathbf{x}+x=\frac{\mathbf{y}}{\sqrt{2}}')
        panel.copy_all_button.click()
        deadline = time.monotonic() + 30
        while panel.busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert not panel.busy and '已复制可编辑公式' in panel.status.text(), panel.status.text()
        mime = QApplication.clipboard().mimeData()
        assert 'font-weight:bold' in mime.html() and '2004/12/omml' in mime.html()
        assert not mime.hasFormat('application/x-qt-windows-mime;value="MathML"')
        checks.append('Bold variables -> native Word HTML and WPS editable clipboard: OK')
        # Exact reported combination: formula entry, raw-source output, editor
        # paste, then the explicit editable-equation button (not text copy).
        raw_panel = TextPanel()
        raw_panel.method_combo.setCurrentIndex(raw_panel.method_combo.findData('formula'))
        raw_panel.mode_combo.setCurrentIndex(raw_panel.mode_combo.findData('source'))
        source = r'\frac{a+b}{c+d}'
        QApplication.clipboard().setText(source)
        raw_panel.source_edit.paste()
        raw_panel.run_button.click()
        deadline = time.monotonic() + 15
        while raw_panel.busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert not raw_panel.busy and raw_panel.result_edit.toPlainText() == source
        assert not raw_panel.copy_as_formula_button.isHidden()
        assert raw_panel.copy_all_button.text() == '复制源码'
        raw_panel.copy_as_formula_button.click()
        deadline = time.monotonic() + 15
        while raw_panel.busy and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(.01)
        assert not raw_panel.busy and '已复制可编辑公式' in raw_panel.status.text(), raw_panel.status.text()
        mime = QApplication.clipboard().mimeData()
        assert 'mfrac' in mime.html() and QApplication.clipboard().text() == source
        package = bytes(mime.data('application/x-qt-windows-mime;value="Kingsoft WPS 9.0 Format"'))
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            assert '<m:f>' in archive.read('word/document.xml').decode('utf-8')
        (root / 'source-formula-clipboard.docx').write_bytes(package)
        raw_panel.resize(1280, 800)
        raw_panel.show()
        QApplication.processEvents()
        raw_panel.grab().save(str(root / 'source-formula-copy-preview.png'))
        raw_panel.close()
        checks.append('Reported raw-source output -> direct editor paste -> explicit editable formula copy: OK')
    return '\n'.join(checks) + '\nALL CHECKS PASSED\n'
