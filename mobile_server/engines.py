"""Portable engines. Never call the desktop Word COM conversion path."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

from .validation import SOURCES, TARGETS, decode_text


def available(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def pandoc_path():
    if executable := shutil.which('pandoc'):
        return executable
    try:
        import pypandoc
        executable = pypandoc.get_pandoc_path()
        if os.name == 'nt' and Path(executable + '.exe').is_file():
            return executable + '.exe'
        return executable if Path(executable).is_file() else None
    except (ImportError, OSError):
        return None


def libreoffice_path():
    def launcher(path):
        path = Path(path).resolve()
        if os.name == 'nt' and path.with_suffix('.com').is_file():
            path = path.with_suffix('.com')
        return str(path) if path.is_file() else None
    if configured := os.getenv('FACTORY_SOFFICE'):
        return launcher(configured)
    if executable := shutil.which('libreoffice') or shutil.which('soffice'):
        return launcher(executable)
    if os.name == 'nt':
        for environment in ('ProgramFiles', 'ProgramFiles(x86)'):
            if directory := os.getenv(environment):
                executable = Path(directory) / 'LibreOffice/program/soffice.exe'
                if executable.is_file():
                    return launcher(executable)
    return None


def engine_status():
    root = Path(__file__).resolve().parents[1]
    formula_models = root / 'resources/formula'
    formula = (available('onnxruntime') and available('tokenizers') and
               all((formula_models / n).is_file() for n in
                   ('image_resizer.onnx', 'encoder.onnx', 'decoder.onnx', 'tokenizer.json')))
    pandoc = pandoc_path()
    libreoffice = libreoffice_path()
    ocr = False
    if available('rapidocr_onnxruntime') and available('onnxruntime'):
        spec = importlib.util.find_spec('rapidocr_onnxruntime')
        model_dir = Path(spec.origin).parent / 'models'
        ocr = all((model_dir / name).is_file() for name in
                  ('ch_PP-OCRv3_det_infer.onnx', 'ch_PP-OCRv3_rec_infer.onnx', 'ch_ppocr_mobile_v2.0_cls_infer.onnx'))
    return {
        'images': {'ready': available('PIL') and available('pillow_heif')},
        'tables': {'ready': available('openpyxl')},
        'pdf': {'ready': available('pymupdf')},
        'pdf_to_docx': {'ready': available('pdf2docx') and available('docx')},
        'pandoc': {'ready': bool(pandoc), 'path': pandoc},
        'libreoffice': {'ready': bool(libreoffice), 'path': libreoffice,
                        'readiness_check': 'executable_present',
                        'message': None if libreoffice else '请安装 LibreOffice，并将 soffice 加入 PATH。'},
        'ocr': {'ready': ocr},
        'formula': {'ready': formula},
    }


def required_engines(category, source, target, options):
    if category in ('images', 'tables'):
        return [category]
    if category == 'text':
        return [options.get('method', 'ocr'), 'images'] + (['pdf'] if source == 'pdf' else [])
    if source == 'pdf':
        return ['pdf'] + (['pdf_to_docx'] if target == 'docx' else []) + (['ocr'] if options.get('pdf_ocr') else [])
    if source == 'docx' and target == 'pdf':
        return ['libreoffice']
    if source == 'txt' and target == 'md':
        return []
    engines = ['pandoc']
    if target == 'pdf':
        engines.append('libreoffice')
    return engines


def readiness(category, source, target, options, engines=None):
    engines = engines or engine_status()
    missing = [name for name in required_engines(category, source, target, options) if not engines[name]['ready']]
    message = None
    if missing:
        message = ('请安装 LibreOffice，并将 soffice 加入 PATH。' if 'libreoffice' in missing else
                   '转换引擎未准备好：' + ', '.join(missing))
    return not missing, message


def capabilities(settings):
    engines = engine_status()
    categories = {}
    for category, sources in SOURCES.items():
        pairs = []
        for source in sources:
            for target in TARGETS[category]:
                if category != 'text' and source == target:
                    continue
                ready, message = readiness(category, source, target, {}, engines)
                pairs.append({'source': source, 'target': target, 'ready': ready, 'message': message})
        categories[category] = {'sources': sources, 'targets': TARGETS[category], 'pairs': pairs}
    categories['text']['methods'] = {name: engines[name] for name in ('ocr', 'formula')}
    return {'max_upload_bytes': settings.max_upload_bytes,
            'worker_timeout_seconds': settings.worker_timeout_seconds,
            'retention_seconds': settings.retention_seconds, 'result_format': 'zip',
            'result_media_type': 'application/zip', 'categories': categories, 'engines': engines}


def command(args, cwd):
    # The outer worker owns an enforceable process-tree timeout.
    process = subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=115,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if process.returncode:
        raise ValueError('文档引擎转换失败：' + process.stderr.decode('utf-8', errors='replace')[:1000])
    return process.stdout


def safe_pandoc(source, target, destination, output, extract=False):
    input_format = 'docx' if source.suffix == '.docx' else 'markdown-raw_html-raw_tex-raw_attribute-yaml_metadata_block'
    args = [pandoc_path(), '--sandbox', '--from=' + input_format, '--to=' + target, '--wrap=none',
            str(source.resolve()), '--output=' + str(destination.resolve())]
    if extract:
        args += ['--extract-media=media']
    command(args, output)


def convert_document(source, target, output, options):
    from factory.common import ConversionResult
    from factory.documents import extract_pdf, literal_markdown, pdf_word
    destination = output / f'{source.stem}.{target}'
    warnings = []
    if source.suffix == '.pdf':
        if target == 'docx':
            if 'page' in options:
                import pymupdf
                with pymupdf.open(source) as document:
                    selected = pymupdf.open()
                    selected.insert_pdf(document, from_page=options['page'], to_page=options['page'])
                    narrowed = output / 'selected-page.pdf'
                    selected.save(narrowed)
                    selected.close()
                try:
                    warnings.extend(pdf_word(narrowed, destination, options.get('pdf_ocr', False)))
                finally:
                    narrowed.unlink(missing_ok=True)
            else:
                warnings.extend(pdf_word(source, destination, options.get('pdf_ocr', False)))
        else:
            text = extract_pdf(source, ocr=options.get('pdf_ocr', False), page=options.get('page'))
            destination.write_text(literal_markdown(text) if target == 'md' else text, encoding='utf-8')
            warnings.append('PDF 文字导出不恢复原始版式。')
    elif source.suffix == '.txt' and target == 'md':
        destination.write_text(literal_markdown(decode_text(source.read_bytes(), options.get('encoding', 'auto'))), encoding='utf-8')
    else:
        prepared = source
        if source.suffix == '.txt':
            prepared = source.parent / 'literal.md'
            prepared.write_text(literal_markdown(decode_text(source.read_bytes(), options.get('encoding', 'auto'))), encoding='utf-8')
        elif source.suffix == '.md':
            prepared = source.parent / 'normalized.md'
            prepared.write_text(decode_text(source.read_bytes(), options.get('encoding', 'auto')), encoding='utf-8')
        if prepared.suffix == '.md':
            # Inspect the parsed document too: references and alternate Markdown
            # syntax must never turn into a file or HTTP read by a writer.
            ast = json.loads(command([pandoc_path(), '--sandbox', '--from=markdown-raw_html-raw_tex-raw_attribute-yaml_metadata_block',
                                      '--to=json', str(prepared.resolve())], output))
            def reject_images(node):
                if isinstance(node, dict):
                    if node.get('t') == 'Image':
                        raise ValueError('Markdown 图片引用被禁用，请上传内嵌图片的 DOCX。')
                    for value in node.values():
                        reject_images(value)
                elif isinstance(node, list):
                    for item in node:
                        reject_images(item)
            reject_images(ast)
        if target == 'pdf':
            intermediate = source if source.suffix == '.docx' else source.parent / 'render.docx'
            if intermediate != source:
                safe_pandoc(prepared, 'docx', intermediate, output)
            # Every task gets an isolated user profile, with no reuse of a desktop
            # office session. External objects were rejected at upload validation.
            profile = (source.parent / 'lo-profile').resolve().as_uri()
            command([libreoffice_path(), '-env:UserInstallation=' + profile, '--headless', '--nologo',
                     '--nodefault', '--norestore', '--convert-to', 'pdf:writer_pdf_Export',
                     '--outdir', str(output.resolve()), str(intermediate.resolve())], output)
            generated = output / (intermediate.stem + '.pdf')
            if not generated.is_file():
                raise ValueError('LibreOffice 未生成 PDF，请检查引擎与字体安装。')
            if generated != destination:
                generated.replace(destination)
        else:
            safe_pandoc(prepared, {'txt': 'plain', 'md': 'markdown', 'docx': 'docx'}[target],
                        destination, output, extract=source.suffix == '.docx' and target == 'md')
    return ConversionResult([destination], warnings)


def recognize_text(source, options):
    from factory.recognition import pdf_page_image, recognize_formula, recognize_image
    prepared = pdf_page_image(source, options.get('page', 0))[0] if source.suffix == '.pdf' else source
    return recognize_formula(prepared) if options.get('method', 'ocr') == 'formula' else recognize_image(prepared)


def convert(category, source, target, output, options):
    from factory.common import ConversionResult, Options
    output.mkdir(parents=True, exist_ok=True)
    if category == 'text':
        destination = output / (source.stem + '.txt')
        destination.write_text(recognize_text(source, options), encoding='utf-8')
        return ConversionResult([destination], ['识别结果请人工校对。'])
    if category == 'documents':
        return convert_document(source, target, output, options)
    kwargs = {k: v for k, v in options.items() if k in Options.__dataclass_fields__}
    if kwargs.get('encoding') == 'auto':
        # Auto is supported for reading; CSV output needs an explicit codec.
        if target == 'csv':
            kwargs['encoding'] = 'utf-8-sig'
    if category == 'images':
        from factory.images import convert_image
        return convert_image(source, target, output, Options(**kwargs))
    from factory.tables import convert_table
    return convert_table(source, target, output, Options(**kwargs))
