import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from openpyxl import Workbook
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication
from factory.theme import app_icon, apply_theme

root = Path(__file__).resolve().parents[1]
sample = root / '示例文件'
sample.mkdir(exist_ok=True)
(sample / '文档示例.md').write_text('# 格式转换工厂\n\n这是一份 **中文** 测试文档。\n\n- 支持文档转换\n- 支持核对后复制\n\n|姓名|编号|\n|---|---|\n|张三|00123|\n\n公式：$\\frac{x}{2} + \\alpha = 1$\n', encoding='utf-8')
(sample / 'LaTeX示例.txt').write_text('这是一段包含公式的文字：\n\n$\\frac{a}{b} + \\sqrt{x} = \\alpha$\n\n核对并修改结果后，可以直接复制。\n', encoding='utf-8')
(sample / '表格示例.csv').write_text('姓名,编号,长编号\n张三,00123,123456789012345678\n李四,00008,987654321098765432\n', encoding='utf-8-sig')
book = Workbook()
book.active.title = '名单'
book.active.append(['姓名', '编号'])
book.active.append(['张三', '00123'])
book.create_sheet('第二张表').append(['另一张表', '独立导出'])
book.save(sample / '多工作表示例.xlsx')
image = Image.new('RGB', (750, 120), 'white')
ImageDraw.Draw(image).text((20, 25), '你好世界 Hello 123', fill='black', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 42))
image.save(sample / '文字识别示例.png')
image = Image.new('RGB', (400, 100), 'white')
ImageDraw.Draw(image).text((20, 15), 'x + y = 1', fill='black', font=ImageFont.truetype('C:/Windows/Fonts/times.ttf', 48))
image.save(sample / '公式识别示例.png')
app = QApplication([])
apply_theme(app)
buffer = QBuffer()
buffer.open(QIODevice.OpenModeFlag.WriteOnly)
app_icon(256).pixmap(256, 256).save(buffer, 'PNG')
Image.open(io.BytesIO(bytes(buffer.data()))).save(root / 'resources' / 'app.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('Samples and desktop icon ready.')
