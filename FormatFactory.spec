from pathlib import Path
from importlib import metadata
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
datas = [('resources/formula', 'resources/formula'), ('vendor/RapidLaTeXOCR-LICENSE', 'licenses')]
datas += [('resources/examples', 'resources/examples')]
datas += collect_data_files('pypandoc')
datas += collect_data_files('vendor.rapid_latex_ocr')
datas += collect_data_files('reportlab')
datas += copy_metadata('pypandoc-binary')
for distribution in metadata.distributions():
    name = distribution.metadata.get('Name', 'dependency')
    for file in distribution.files or []:
        relative = Path(str(file))
        if any(part.lower() == 'licenses' for part in relative.parts) or relative.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
            actual = Path(distribution.locate_file(file))
            if actual.is_file():
                datas.append((str(actual), str(Path('licenses') / name / relative.parent)))
ocr_data, ocr_bins, ocr_imports = collect_all('rapidocr_onnxruntime')
datas += ocr_data
hidden = ocr_imports + collect_submodules('pdf2docx')
hidden += ['win32com.client', 'pythoncom', 'pywintypes', 'tokenizers', 'PIL.TiffImagePlugin',
           'PIL.JpegImagePlugin', 'PIL.PngImagePlugin', 'PIL.WebPImagePlugin', 'PIL.BmpImagePlugin']
a = Analysis(['main.py'], pathex=[str(root)], binaries=ocr_bins, datas=datas,
             hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
                       'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtPdf', 'tkinter', 'matplotlib',
                       'pytest', 'IPython', 'pandas', 'scipy', 'torch', 'tensorflow'],
             noarchive=False, optimize=0)
# Qt calls the unversioned ICU API supplied by Windows 10/11. A separately
# installed Poppler can expose a version-suffixed ICU DLL on PATH; collecting it
# shadows the Windows DLL and prevents QtWidgets from loading (WinError 127).
# The two files below were confirmed to come solely from that unrelated runtime.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='FormatFactory',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False,
          icon=str(root / 'resources' / 'app.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='FormatFactory')
