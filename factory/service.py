from pathlib import Path

from .common import Options, normalized_format

FORMATS = {
    'documents': ['txt', 'md', 'docx', 'pdf'],
    'tables': ['xlsx', 'csv'],
    'images': ['jpg', 'png', 'webp', 'bmp', 'tiff', 'heic'],
}
INPUT_SUFFIXES = {
    'documents': {'.txt', '.md', '.markdown', '.docx', '.pdf'},
    'tables': {'.xlsx', '.csv'},
    'images': {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.hif', '.avif', '.gif'},
}


def convert(category: str, source: Path, target: str, output: Path, options: Options):
    source = Path(source)
    target = normalized_format(target)
    if category not in FORMATS or target not in FORMATS[category]:
        raise ValueError('请选择支持的输出格式。')
    if source.suffix.lower() not in INPUT_SUFFIXES[category]:
        raise ValueError('该文件不属于当前转换分类，或暂不支持此格式。')
    if normalized_format(source.suffix) == target:
        raise ValueError('输入和输出格式相同，请选择其他格式。')
    if not source.is_file():
        raise ValueError('找不到输入文件，请重新添加。')
    if category == 'images':
        from .images import convert_image
        return convert_image(source, target, output, options)
    if category == 'tables':
        from .tables import convert_table
        return convert_table(source, target, output, options)
    from .documents import convert_document
    return convert_document(source, target, output, options)
