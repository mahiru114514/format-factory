import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pytest


def text_image(text='你好世界 Hello 123'):
    image = Image.new('RGB', (750, 120), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((20, 25), text, fill='black', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 42))
    return image


def test_real_chinese_english_ocr():
    from factory.recognition import recognize_image
    output = recognize_image(text_image())
    assert '你好世界' in output.replace(' ', '')
    assert '123' in output


def test_blank_image_has_no_hallucinated_output():
    from factory.recognition import recognize_image
    with pytest.raises(ValueError, match='未识别到'):
        recognize_image(Image.new('RGB', (500, 120), 'white'))


def test_real_printed_formula_ocr():
    from factory.recognition import recognize_formula
    image = Image.new('RGB', (400, 100), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((20, 15), 'x + y = 1', fill='black', font=ImageFont.truetype('C:/Windows/Fonts/times.ttf', 48))
    output = recognize_formula(image)
    assert 'x' in output and 'y' in output and '=' in output and '1' in output


def test_reported_dark_logic_formula_keeps_relation_limits_and_index():
    from factory.recognition import recognize_formula
    image = Image.open(Path(__file__).parent / 'fixtures/logic_formula_dark_frame.png')
    output = recognize_formula(image)
    compact = ''.join(output.split())
    assert r'\bigvee_{i=0}^{5}' in compact
    assert r'\longleftrightarrow' in compact or r'\iff' in compact or r'\Leftrightarrow' in compact
    assert 'used[t]' in compact and 'slot[i]=t' in compact


def test_latest_screenshot_does_not_invert_large_disjunction():
    from factory.recognition import recognize_formula
    output = recognize_formula(Path(__file__).parent / 'fixtures/logic_formula_latest_screenshot.png')
    compact = ''.join(output.split())
    assert r'\bigvee_{i=0}^{5}' in compact
    assert r'\bigwedge' not in output


@pytest.mark.parametrize('direction,expected', [('down', r'\bigvee'), ('up', r'\bigwedge')])
@pytest.mark.parametrize('background,ink', [('black', 'white'), ('white', 'black')])
def test_large_logic_geometry_checks_both_orientations(direction, expected, background, ink):
    from factory.recognition import verify_large_logic_operator
    image = Image.new('RGB', (320, 150), background)
    draw = ImageDraw.Draw(image)
    points = [(130, 30), (160, 115), (190, 30)]
    if direction == 'up':
        points = [(x, 145-y) for x, y in points]
    draw.line(points, fill=ink, width=5)
    draw.text((20, 60), 'x =', fill=ink, font=ImageFont.truetype('C:/Windows/Fonts/times.ttf', 28))
    small = ImageFont.truetype('C:/Windows/Fonts/times.ttf', 16)
    draw.text((155, 4), 'n', fill=ink, font=small)
    draw.text((145, 124), 'i=0', fill=ink, font=small)
    original = r'\bigwedge_{i=0}^n' if direction == 'down' else r'\bigvee_{i=0}^n'
    assert verify_large_logic_operator(image, original) == expected + r'_{i=0}^n'


@pytest.mark.parametrize('text', [r'\bigwedge+\bigvee', r'\bigwedgecustom{x}', r'\sum_i x_i'])
def test_large_logic_geometry_keeps_ambiguous_and_unrelated_commands(text):
    from factory.recognition import verify_large_logic_operator
    assert verify_large_logic_operator(Image.new('RGB', (320, 150), 'white'), text) == text


@pytest.mark.parametrize('shape', ['root', 'cup', 'cap', 'parenthesis', 'corner'])
def test_large_logic_geometry_does_not_guess_from_other_large_shapes(shape):
    from factory.recognition import verify_large_logic_operator
    image = Image.new('RGB', (320, 180), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((10, 70), 'x =', fill='black', font=ImageFont.truetype('C:/Windows/Fonts/times.ttf', 28))
    if shape == 'root':
        draw.line([(110,100),(125,125),(150,25),(230,25)],fill='black',width=5)
    elif shape in ('cup', 'cap'):
        draw.arc((130,25,200,145),0 if shape=='cup' else 180,180 if shape=='cup' else 360,fill='black',width=5)
        draw.line([(130,85),(130,25 if shape=='cup' else 145)],fill='black',width=5)
        draw.line([(200,85),(200,25 if shape=='cup' else 145)],fill='black',width=5)
    elif shape == 'parenthesis':
        draw.arc((130,25,200,145),90,270,fill='black',width=5)
    else:
        draw.line([(130,140),(130,25),(200,25)],fill='black',width=5)
    source = r'\bigwedge_{i=0}^n'
    assert verify_large_logic_operator(image, source) == source


def test_large_logic_geometry_keeps_multiple_shapes_and_isolated_letter():
    from factory.recognition import verify_large_logic_operator
    image = Image.new('RGB', (500, 160), 'white')
    draw = ImageDraw.Draw(image)
    for offset in (0, 140):
        draw.line([(130+offset,30),(160+offset,115),(190+offset,30)],fill='black',width=5)
    draw.text((10,70),'x =',fill='black',font=ImageFont.truetype('C:/Windows/Fonts/times.ttf',28))
    source = r'\bigwedge_i x_i'
    assert verify_large_logic_operator(image, source) == source
    letter = Image.new('RGB', (200,160), 'white')
    ImageDraw.Draw(letter).line([(60,30),(90,115),(120,30)],fill='black',width=5)
    assert verify_large_logic_operator(letter, source) == source


def test_large_logic_geometry_does_not_bind_large_variable_to_small_operator():
    from factory.recognition import verify_large_logic_operator
    image = Image.new('RGB', (500,180), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((10,70),'x = y +',fill='black',font=ImageFont.truetype('C:/Windows/Fonts/times.ttf',28))
    draw.text((210,10),'V',fill='black',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',120))
    draw.line([(350,100),(360,75),(370,100)],fill='black',width=3)
    original = r'V + \bigwedge_{i=0}^n x_i'
    assert verify_large_logic_operator(image, original) == original


def test_large_logic_geometry_treats_small_opposite_wedge_as_ambiguous():
    from factory.recognition import verify_large_logic_operator
    image = Image.new('RGB',(500,180),'white')
    draw = ImageDraw.Draw(image)
    draw.text((10,70),'x = y +',fill='black',font=ImageFont.truetype('C:/Windows/Fonts/times.ttf',28))
    draw.line([(210,30),(240,115),(270,30)],fill='black',width=5)
    draw.line([(320,100),(330,75),(340,100)],fill='black',width=3)
    small=ImageFont.truetype('C:/Windows/Fonts/times.ttf',16)
    draw.text((235,4),'n',fill='black',font=small)
    draw.text((225,124),'i=0',fill='black',font=small)
    original = r'\bigwedge_{i=0}^n x_i'
    assert verify_large_logic_operator(image, original) == original


def test_formula_preparation_keeps_mathematical_side_delimiters():
    from factory.recognition import prepare_formula_image
    image = Image.new('RGB', (360, 120), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 2, 119), fill='black')
    draw.rectangle((357, 0, 359, 119), fill='black')
    draw.text((80, 35), 'a + b', fill='black')
    result = prepare_formula_image(image)
    assert result.size == image.size and result.tobytes() == image.tobytes()


@pytest.mark.parametrize('background,frame', [('black', 'white'), ('white', 'black')])
@pytest.mark.parametrize('border', [1, 3, 5])
def test_formula_preparation_trims_only_frame_for_both_polarities(background, frame, border):
    from factory.recognition import prepare_formula_image
    from PIL import ImageOps
    image = Image.new('RGB', (360, 120), background)
    ImageDraw.Draw(image).text((80, 40), 'x + y = 1', fill=frame)
    framed = ImageOps.expand(image, border=border, fill=frame)
    result = prepare_formula_image(framed)
    assert result.size == image.size and result.tobytes() == image.tobytes()


def test_formula_preparation_leaves_thick_borders_and_content_unchanged():
    from factory.recognition import prepare_formula_image
    from PIL import ImageOps
    image = Image.new('RGB', (360, 120), 'white')
    ImageDraw.Draw(image).text((80, 40), 'x + y = 1', fill='black')
    framed = ImageOps.expand(image, border=20, fill='black')
    result = prepare_formula_image(framed)
    assert result.size == framed.size and result.tobytes() == framed.tobytes()


def test_blank_formula_inside_screenshot_frame_is_rejected():
    from factory.recognition import recognize_formula
    from PIL import ImageOps
    image = ImageOps.expand(Image.new('RGB', (360, 120), 'black'), border=3, fill='#f5f7fb')
    with pytest.raises(ValueError, match='未识别到公式'):
        recognize_formula(image)


@pytest.mark.parametrize('ink', ['white', 'black'])
def test_transparent_formula_keeps_visible_ink(ink):
    from factory.recognition import load_image
    image = Image.new('RGBA', (360, 120), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((20, 20), 'x+y=1', fill=ink,
                              font=ImageFont.truetype('C:/Windows/Fonts/times.ttf', 48))
    result = load_image(image)
    from PIL import ImageStat
    assert result.mode == 'RGB'
    assert ImageStat.Stat(result.convert('L')).stddev[0] > 10


def test_transparent_margins_do_not_turn_normal_document_page_black():
    from factory.recognition import load_image
    image = Image.new('RGBA', (360, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 339, 99), fill='white')
    draw.text((40, 40), 'x+y=1', fill='black')
    assert load_image(image).getpixel((0, 0)) == (255, 255, 255)


def test_scanned_pdf_ocr(tmp_path):
    import pymupdf
    from factory.documents import extract_pdf
    buffer = io.BytesIO()
    text_image().save(buffer, format='PNG')
    doc = pymupdf.open()
    page = doc.new_page(width=750, height=120)
    page.insert_image(page.rect, stream=buffer.getvalue())
    source = tmp_path / 'scan.pdf'
    doc.save(source)
    doc.close()
    assert '123' in extract_pdf(source, ocr=True)


def test_pdf_page_preview(tmp_path):
    import pymupdf
    from factory.recognition import pdf_page_image
    doc = pymupdf.open()
    doc.new_page(width=100, height=200)
    source = tmp_path / 'page.pdf'
    doc.save(source)
    doc.close()
    image, count = pdf_page_image(source, 0)
    assert image.height > image.width and count == 1
    with pytest.raises(ValueError, match='页码'):
        pdf_page_image(source, 1)


def test_scan_with_extractable_page_number_recovers_body(tmp_path):
    import pymupdf
    from factory.documents import extract_pdf, convert_document
    from factory.common import Options
    from docx import Document
    buffer = io.BytesIO()
    text_image().save(buffer, format='PNG')
    doc = pymupdf.open()
    page = doc.new_page(width=750, height=200)
    page.insert_text((20, 20), 'Page 1')
    page.insert_image(pymupdf.Rect(0, 40, 750, 160), stream=buffer.getvalue())
    source = tmp_path / 'mixed-scan.pdf'
    doc.save(source)
    doc.close()
    text = extract_pdf(source, ocr=True)
    assert 'Page 1' in text and '123' in text and '你好世界' in text.replace(' ', '')
    result = convert_document(source, 'docx', tmp_path, Options(pdf_ocr=True))
    recovered = '\n'.join(p.text for p in Document(result.paths[0]).paragraphs)
    assert '123' in recovered and 'Page 1' in recovered
