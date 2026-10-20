import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory.common import Options
from factory.documents import convert_document

root = Path(__file__).resolve().parents[1] / 'artifacts' / 'word-smoke'
root.mkdir(parents=True, exist_ok=True)
source = root / '排版示例.md'
source.write_text('# 中文标题\n\n你好，世界！\n\n|姓名|代码|\n|---|---|\n|张三|001|\n\n公式：$x^2+y^2=1$\n', encoding='utf-8')
result = convert_document(source, 'pdf', root, Options(pdf_engine='word'))
import pymupdf
with pymupdf.open(result.paths[0]) as document:
    text = '\n'.join(page.get_text() for page in document)
    assert '中文标题' in text and '张三' in text
    document[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(root / 'word-pdf-preview.png')
print('Word PDF export verified:', result.paths[0])
