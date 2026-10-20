from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Options:
    encoding: str = 'utf-8-sig'
    delimiter: str = ','
    quality: int = 90
    max_size: int = 0
    keep_metadata: bool = False
    pdf_ocr: bool = False
    pdf_engine: str = 'auto'


@dataclass
class ConversionResult:
    paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def unique_path(requested: Path) -> Path:
    requested = Path(requested)
    result = requested
    count = 1
    while result.exists():
        result = requested.with_name(f'{requested.stem} ({count}){requested.suffix}')
        count += 1
    return result


def publish(staged: Path, requested: Path) -> Path:
    """Copy a completed staged file without replacing an existing file, even in a race."""
    requested = Path(requested)
    requested.parent.mkdir(parents=True, exist_ok=True)
    while True:
        destination = unique_path(requested)
        try:
            output = destination.open('xb')
        except FileExistsError:
            continue
        try:
            with output, Path(staged).open('rb') as source:
                shutil.copyfileobj(source, output)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return destination


def read_text(path: Path, encoding: str = 'auto') -> str:
    data = Path(path).read_bytes()
    if encoding != 'auto':
        return data.decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16').replace('\r\n', '\n').replace('\r', '\n')
    for candidate in ('utf-8-sig', 'gb18030'):
        try:
            return data.decode(candidate).replace('\r\n', '\n').replace('\r', '\n')
        except UnicodeDecodeError:
            continue
    raise ValueError('无法识别文本编码，请另存为 UTF-8 后重试。')


def safe_name(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text).strip('. ') or 'sheet'


def normalized_format(value: str) -> str:
    value = value.lower().lstrip('.')
    return {'jpeg': 'jpg', 'tif': 'tiff', 'heif': 'heic', 'markdown': 'md'}.get(value, value)
