"""Opt-in native Windows integration check. Uses only dedicated new documents."""
from __future__ import annotations

import json
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from factory.text_panel import TextPanel

NS = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
      'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
CASES = [
    ('fraction-root', r'\frac{x_1^2}{\sqrt[3]{y}}', 1, ['f', 'rad', 'sSubSup']),
    ('reported-logic', r'used[t]\iff\bigvee_{i=0}^{5}(slot[i]=t)', 1, []),
    ('matrix', r'\begin{pmatrix}a&b\\c&d\end{pmatrix}', 1, ['m', 'd']),
    ('mixed', '前文\n' + r'$\frac{x}{2}$ 和 \(\sqrt{y}\)' + '\n后文', 2, ['f', 'rad']),
    ('bold', r'\mathbf{x}+x=\frac{\mathbf{y}}{\sqrt{2}}', 1, ['f', 'rad']),
]


def native_paste(name, path):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    app = doc = None
    owned = False
    try:
        if name == 'wps':
            obj = pythoncom.CoCreateInstance('{000209FF-0000-4b30-A977-D214852036FF}', None,
                    pythoncom.CLSCTX_LOCAL_SERVER | 0x40000, pythoncom.IID_IDispatch)
            app = win32com.client.Dispatch(obj)
        else:
            app = win32com.client.DispatchEx('Word.Application')
        # WPS may reuse an automation server. Never change visibility, add
        # documents or quit if that server already has open user documents.
        if app.Documents.Count:
            raise RuntimeError('Office 返回了已有文档的实例，已跳过测试以保留用户窗口。')
        owned = True
        app.Visible = False
        app.DisplayAlerts = 0
        doc = app.Documents.Add()
        doc.Content.Paste()
        count = doc.OMaths.Count
        doc.SaveAs2(str(path), FileFormat=16)
        doc.ExportAsFixedFormat(str(path.with_suffix('.pdf')), 17)
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
        return count, root
    finally:
        try:
            if doc is not None:
                doc.Close(False)
        finally:
            try:
                if app is not None and owned:
                    app.Quit()
            finally:
                pythoncom.CoUninitialize()


def main():
    output = Path(sys.argv[1] if len(sys.argv) > 1 else '.work/office-verification').resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    panel = TextPanel()
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData('office'))
    reports = []
    with ThreadPoolExecutor(max_workers=1) as executor:
        for name in ('word', 'wps'):
            for case, source, expected, structures in CASES:
                panel.accept_result('x')
                panel.result_edit.setPlainText(source)
                panel.copy_all_button.click()
                deadline = time.monotonic() + 40
                while panel.busy and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                assert not panel.busy and '已复制可编辑公式' in panel.status.text(), panel.status.text()
                path = output / f'{name}-{case}.docx'
                future = executor.submit(native_paste, name, path)
                while not future.done() and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                assert future.done(), f'{name} paste timed out'
                count, root = future.result()
                assert count == expected, (name, case, count)
                for tag in structures:
                    assert root.find('.//m:' + tag, NS) is not None, (name, case, tag)
                if case == 'reported-logic':
                    text = ''.join(node.text or '' for node in root.findall('.//m:t', NS))
                    chars = ''.join(node.get('{'+NS['m']+'}val', '') for node in root.findall('.//m:chr', NS))
                    assert '⇔' in text and '⋁' in text+chars and '5' in text and 'i=0' in text, text
                if case == 'mixed':
                    text = ''.join(node.text or '' for node in root.findall('.//w:t', NS))
                    assert '前文' in text and '后文' in text and '和' in text, text
                if case == 'bold':
                    values = ''.join(node.text or '' for node in root.findall('.//m:t', NS))
                    styles = [node.get('{'+NS['m']+'}val') for node in root.findall('.//m:sty', NS)]
                    assert '𝐱' in values or 'b' in styles
                report = {'app': name, 'case': case, 'equations': count,
                          'structures': structures, 'edited_source_preserved': app.clipboard().text() == source}
                assert report['edited_source_preserved']
                reports.append(report)
                print(json.dumps(report, ensure_ascii=False), flush=True)
    panel.close()
    (output/'report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print('ALL NATIVE OFFICE CHECKS PASSED', flush=True)


if __name__ == '__main__':
    main()
