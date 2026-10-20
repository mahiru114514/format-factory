"""Validate untrusted bytes before they enter conversion storage."""
import io
import json
import posixpath
import re
import warnings
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

from PIL import Image

ALIASES = {'jpeg': 'jpg', 'tif': 'tiff', 'heif': 'heic', 'hif': 'heic', 'markdown': 'md'}
IMAGE_FORMATS = {'jpg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP', 'bmp': 'BMP', 'tiff': 'TIFF',
                 'heic': 'HEIF', 'avif': 'AVIF', 'gif': 'GIF'}
SOURCES = {'images': list(IMAGE_FORMATS), 'tables': ['csv', 'xlsx'],
           'documents': ['txt', 'md', 'docx', 'pdf'], 'text': [*IMAGE_FORMATS, 'pdf']}
TARGETS = {'images': ['jpg', 'png', 'webp', 'bmp', 'tiff', 'heic'], 'tables': ['csv', 'xlsx'],
           'documents': ['txt', 'md', 'docx', 'pdf'], 'text': ['txt']}


def normalize(value):
    return ALIASES.get(value.lower().lstrip('.'), value.lower().lstrip('.'))


def safe_filename(name):
    if (not name or len(name) > 180 or name in ('.', '..') or
            any(c in name for c in '/\\:\x00') or any(ord(c) < 32 for c in name)):
        raise ValueError('文件名不能包含路径、控制字符或超过 180 个字符。')
    if '.' not in name:
        raise ValueError('文件缺少扩展名。')
    stem, extension = name.rsplit('.', 1)
    if not stem.strip(' .') or stem.endswith((' ', '.')):
        raise ValueError('文件名无效。')
    return stem, normalize(extension)


def validate_options(raw, category):
    try:
        options = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise ValueError('options 必须是 JSON 对象。') from error
    if not isinstance(options, dict):
        raise ValueError('options 必须是 JSON 对象。')
    allowed = {'encoding', 'delimiter', 'quality', 'max_size', 'keep_metadata', 'pdf_ocr', 'page', 'method'}
    if options.keys() - allowed:
        raise ValueError('包含不支持的转换选项。')
    for name, minimum, maximum in [('quality', 1, 100), ('max_size', 0, 20000), ('page', 0, 10000)]:
        if name in options and (type(options[name]) is not int or not minimum <= options[name] <= maximum):
            raise ValueError(f'{name} 超出允许范围。')
    for name in ('keep_metadata', 'pdf_ocr'):
        if name in options and type(options[name]) is not bool:
            raise ValueError(f'{name} 必须为布尔值。')
    if options.get('method', 'ocr') not in ('ocr', 'formula'):
        raise ValueError('method 仅支持 ocr 或 formula。')
    if options.get('encoding', 'utf-8-sig') not in ('utf-8', 'utf-8-sig', 'gb18030', 'utf-16', 'auto'):
        raise ValueError('不支持的文本编码。')
    delimiter = options.get('delimiter', ',')
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n\x00':
        raise ValueError('delimiter 必须是单个有效字符。')
    if category == 'text':
        options.setdefault('method', 'ocr')
        options.setdefault('page', 0)
    return options


def validate_pair(category, source, target):
    if category not in SOURCES or source not in SOURCES[category] or target not in TARGETS[category]:
        raise ValueError('不支持的分类、输入或输出格式。')
    if category != 'text' and source == target:
        raise ValueError('请选择与输入不同的输出格式。')


def decode_text(data, encoding='auto'):
    candidates = ('utf-16',) if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'gb18030')
    if encoding != 'auto':
        candidates = (encoding,)
    for candidate in candidates:
        try:
            text = data.decode(candidate)
            if '\x00' in text or any(ord(c) < 32 and c not in '\r\n\t' for c in text):
                raise ValueError('文本文件包含二进制内容。')
            return text
        except UnicodeError:
            continue
    raise ValueError('文件不是有效的文本，请使用 UTF-8。')


def validate_word_fields(root):
    """Reconstruct instructions within each field, preserving field boundaries."""
    def check(instruction):
        if re.search(r'\b(?:INCLUDETEXT|INCLUDEPICTURE|DDEAUTO|DDE|IMPORT|LINK|DATABASE)\b', instruction, re.I):
            raise ValueError('Word 动态字段可能读取外部内容，已拒绝处理。')

    fields = []
    for element in root.iter():
        local_name = element.tag.rsplit('}', 1)[-1]
        if local_name in ('altChunk', 'object', 'oleObject'):
            raise ValueError('不支持含活动或嵌入对象的 Word 文档。')
        if local_name == 'fldSimple':
            for key, value in element.attrib.items():
                if key.rsplit('}', 1)[-1] == 'instr':
                    check(value)
        elif local_name == 'fldChar':
            kind = next((value for key, value in element.attrib.items()
                         if key.rsplit('}', 1)[-1] == 'fldCharType'), '')
            if kind == 'begin':
                fields.append({'parts': [], 'instruction': True})
            elif kind == 'separate' and fields:
                check(''.join(fields[-1]['parts']))
                fields[-1]['instruction'] = False
            elif kind == 'end' and fields:
                check(''.join(fields.pop()['parts']))
        elif local_name == 'instrText':
            if fields:
                if fields[-1]['instruction']:
                    fields[-1]['parts'].append(element.text or '')
            else:
                check(element.text or '')
    # Incomplete fields must not bypass checking merely by omitting their end.
    for field in fields:
        check(''.join(field['parts']))


def validate_ooxml(data, source, max_uncompressed):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > max_uncompressed:
                raise ValueError('Office 文件解压后超过安全限制。')
            names = {i.filename for i in infos}
            if len(names) != len(infos):
                raise ValueError('Office 文件包含重复条目。')
            required = 'word/document.xml' if source == 'docx' else 'xl/workbook.xml'
            if required not in names or '[Content_Types].xml' not in names:
                raise ValueError('文件内容与 Office 扩展名不符。')
            for info in infos:
                path = PurePosixPath(info.filename)
                if (path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename or
                        (info.external_attr >> 16) & 0o170000 == 0o120000 or info.flag_bits & 1):
                    raise ValueError('Office 压缩文件含有不安全的路径或加密条目。')
                if info.file_size > 16 * 1024 * 1024 or (info.file_size > 1024 * 1024 and info.file_size > max(1, info.compress_size) * 200):
                    raise ValueError('Office 条目的解压大小或压缩比超过安全限制。')
                lower = info.filename.lower()
                if any(term in lower for term in ('vbaproject', '/embeddings/', '/activex/', 'altchunk')) or lower.endswith('.svg'):
                    raise ValueError('不支持含活动内容、嵌入对象或 SVG 的 Office 文件。')
                if not lower.endswith(('.xml', '.rels')):
                    continue
                xml = archive.read(info)
                markup = xml.replace(b'\x00', b'').upper()
                if b'<!DOCTYPE' in markup or b'<!ENTITY' in markup:
                    raise ValueError('Office XML 不允许 DTD 或实体。')
                root = ElementTree.fromstring(xml)
                if source == 'docx':
                    validate_word_fields(root)
                if lower.endswith('.rels'):
                    # a/b/_rels/document.xml.rels has its base at a/b/.
                    base = posixpath.dirname(posixpath.dirname(info.filename))
                    for rel in root:
                        target = rel.get('Target', '')
                        relation = rel.get('Type', '')
                        if relation.rsplit('/', 1)[-1] in ('aFChunk', 'oleObject', 'package', 'attachedTemplate'):
                            raise ValueError('不支持可能读取外部内容的 Office 对象。')
                        if rel.get('TargetMode', '').lower() == 'external':
                            if relation.endswith('/hyperlink'):
                                continue
                            raise ValueError('Office 文件包含外部嵌入资源，请先将资源嵌入文件。')
                        if target.startswith('\\') or ':' in target or '\\' in target:
                            raise ValueError('Office 资源路径不安全。')
                        # A leading slash means the OOXML package root, not an
                        # operating system path; it still must name a ZIP member.
                        package_target = target.split('#')[0]
                        resolved = (posixpath.normpath(package_target.lstrip('/')) if package_target.startswith('/')
                                    else posixpath.normpath(posixpath.join(base, package_target)))
                        if resolved.startswith('../') or resolved not in names:
                            raise ValueError('Office 资源不存在或超出压缩包。')
    except (zipfile.BadZipFile, ElementTree.ParseError, RuntimeError, KeyError) as error:
        raise ValueError('Office 压缩文件无效或已损坏。') from error


def validate_content(data, source, options, max_uncompressed):
    if not data:
        raise ValueError('文件为空。')
    if source in IMAGE_FORMATS:
        from factory.images import register_codecs
        register_codecs()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != IMAGE_FORMATS[source] or image.width * image.height > 40_000_000:
                        raise ValueError('图片实际格式与扩展名不符，或像素过多。')
                    image.verify()
        except Exception as error:
            raise ValueError('图片无效、格式与扩展名不符或像素过多。') from error
    elif source in ('docx', 'xlsx'):
        validate_ooxml(data, source, max_uncompressed)
    elif source == 'pdf':
        if not data.startswith(b'%PDF-'):
            raise ValueError('文件不是 PDF。')
        import pymupdf
        try:
            with pymupdf.open(stream=data, filetype='pdf') as document:
                if document.needs_pass or not len(document):
                    raise ValueError('PDF 已加密或没有页面。')
                if options.get('page', 0) >= len(document):
                    raise ValueError('PDF 页码超出范围（从 0 开始）。')
        except Exception as error:
            raise ValueError('PDF 无效、已加密或页码超出范围。') from error
    else:
        text = decode_text(data, options.get('encoding', 'auto'))
        if source == 'md':
            if re.search(r'!\s*\[|<\s*(?:[A-Za-z][\w:-]*\b|/)|\\(?:input|include|includegraphics)\b', text, re.I):
                raise ValueError('Markdown 不支持图片引用、原始 HTML 或文件包含；请使用内嵌图片的 DOCX。')
