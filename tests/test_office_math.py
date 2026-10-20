import io
import zipfile
from xml.etree import ElementTree as ET

import pytest

from factory import office_math

M = {'m': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
     'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def test_fraction_radical_and_scripts_preserved():
    result = office_math.convert_office_math(r'\frac{x_1^2}{\sqrt[3]{y}}')
    root = ET.fromstring(result.mathml)
    assert root.find('.//{*}mfrac') is not None
    assert root.find('.//{*}mroot') is not None
    assert root.find('.//{*}msubsup') is not None
    with zipfile.ZipFile(io.BytesIO(result.docx)) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
    assert doc.find('.//m:f', M) is not None
    assert doc.find('.//m:rad/m:deg/m:r/m:t', M).text == '3'


def test_reported_logic_keeps_arrow_operator_and_bounds():
    source = r'used[t]\iff\bigvee_{i=0}^{5}(slot[i]=t)'
    result = office_math.convert_office_math(source)
    root = ET.fromstring(result.mathml)
    assert '⇔' in ''.join(root.itertext())
    operator = root.find('.//{*}munderover')
    assert operator is not None
    assert ''.join(operator[0].itertext()) == '⋁'
    assert ''.join(operator[1].itertext()) == 'i=0'
    assert ''.join(operator[2].itertext()) == '5'
    assert result.source == source
    with zipfile.ZipFile(io.BytesIO(result.docx)) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
    nary = doc.find('.//m:nary', M)
    assert nary is not None
    assert nary.find('m:naryPr/m:chr', M).get('{'+M['m']+'}val') == '⋁'
    assert ''.join(nary.find('m:sub', M).itertext()) == 'i=0'
    assert ''.join(nary.find('m:sup', M).itertext()) == '5'
    assert ''.join(nary.find('m:e', M).itertext()) == '(slot[i]=t)'


@pytest.mark.parametrize(('environment', 'left', 'right'), [('pmatrix', '(', ')'), ('vmatrix', '∣', '∣'), ('bmatrix', '[', ']')])
def test_matrix_retains_delimiters(environment, left, right):
    source = '\\begin{'+environment+'}a&b\\\\c&d\\end{'+environment+'}'
    root = ET.fromstring(office_math.convert_office_math(source).mathml)
    assert root.find('.//{*}mtable') is not None
    delimiters = [node.text for node in root.iter() if node.tag.endswith('}mo')]
    assert delimiters[0] == left and delimiters[-1] == right


@pytest.mark.parametrize('source', [r'\unknown{x}', r'\frac{x}', r'\sqrt{', r'$x', r'文字 $x$ 和 $y'])
def test_invalid_or_unsupported_math_is_rejected(source):
    with pytest.raises(ValueError):
        office_math.convert_office_math(source)


def test_mixed_text_and_math_keep_all_content():
    source = '核对 <script>\n' + r'$\frac{x}{2}$ 和 \(\sqrt{y}\)' + '\n结束'
    result = office_math.convert_office_math(source)
    assert result.mathml is None  # A single MathML clipboard flavor would discard the surrounding text.
    assert result.equations == 2
    assert '&lt;script&gt;' in result.html
    assert '核对' in result.html and '结束' in result.html
    assert result.html.count('<math ') == 2


def test_empty_math_is_rejected():
    with pytest.raises(ValueError):
        office_math.convert_office_math('  ')


def test_clipboard_has_both_office_formats_and_source_fallback():
    result = office_math.convert_office_math(r'\frac{x}{2}')
    mime = office_math.office_mime_data(result)
    assert mime.text() == result.source
    assert mime.hasHtml()
    assert bytes(mime.data('application/x-qt-windows-mime;value="Kingsoft WPS 9.0 Format"')) == result.docx
    raw = bytes(mime.data('application/x-qt-windows-mime;value="MathML"'))
    assert raw.decode('utf-16-le').rstrip('\0') == result.mathml


def test_mixed_clipboard_does_not_advertise_partial_mathml():
    mime = office_math.office_mime_data(office_math.convert_office_math(r'文字 $x^2$'))
    assert not mime.hasFormat('application/x-qt-windows-mime;value="MathML"')
    assert '文字' in mime.html()


@pytest.mark.parametrize('source', [r'x^{a}^{b}', r'x_1_2', r'x_1^2_3', r'\frac{x^a^b}{2}'])
def test_invalid_double_scripts_are_rejected(source):
    with pytest.raises(ValueError, match='上下标'):
        office_math.convert_office_math(source)


@pytest.mark.parametrize('source', [r'\begin{array}{r|l}A&b\end{array}', r'\begin{matrix}a&b\\\hline c&d\end{matrix}', r'\color{red}x'])
def test_known_lossy_features_are_rejected_explicitly(source):
    with pytest.raises(ValueError, match='保留'):
        office_math.convert_office_math(source)


@pytest.mark.parametrize(('source', 'script_tag'), [(r'x^12', 'msup'), (r'x_12', 'msub'), (r'\frac{x}{2}^12', 'msup')])
def test_unbraced_numeric_script_keeps_strict_tex_scope(source, script_tag):
    result = office_math.convert_office_math(source)
    root = ET.fromstring(result.mathml)
    script = root.find('.//{*}'+script_tag)
    assert ''.join(script[-1].itertext()) == '1'
    assert '2' in ''.join(root.find('.//{*}semantics')[0].itertext())
    assert result.source == source


def test_text_macro_is_not_reinterpreted_as_math_scripts():
    result = office_math.convert_office_math(r'\text{x_12_34} + x_{12}')
    root = ET.fromstring(result.mathml)
    assert root.find('.//{*}mtext').text == 'x_12_34'
    assert ''.join(root.find('.//{*}msub')[-1].itertext()) == '12'


@pytest.mark.parametrize('source', [r'\text{a $x_1_2$ b}', r'\text{a $\color{red}x$ b}', r'\text{\color{red}a}'])
def test_nested_math_and_formatting_inside_text_are_checked(source):
    with pytest.raises(ValueError):
        office_math.convert_office_math(source)


def test_numeric_script_inside_text_math_keeps_single_token_scope():
    result = office_math.convert_office_math(r'\text{a $x^12$ b}')
    root = ET.fromstring(result.mathml)
    assert ''.join(root.find('.//{*}msup')[-1].itertext()) == '1'


@pytest.mark.parametrize('source', [r'\mathbf{x}+x', r'\text{a $\mathbf{x}$ b}', r'\mathbf{\frac{x}{2}}'])
def test_upright_bold_latin_keeps_shape_and_scope(source):
    result = office_math.convert_office_math(source)
    root = ET.fromstring(result.mathml)
    content = ''.join(root.find('.//{*}semantics')[0].itertext())
    assert 'x' in content
    assert root.find('.//{*}mi[@mathvariant="bold"]').text == 'x'
    assert '𝒙' not in content
    if source == r'\mathbf{x}+x':
        identifiers = root.findall('.//{*}mi')
        assert content.count('x') == 2
        assert identifiers[-1].get('mathvariant') is None
    with zipfile.ZipFile(io.BytesIO(result.docx)) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
    assert doc.find('.//m:sty[@m:val="b"]', M) is not None


def test_bold_script_scope_and_explicit_roman_reset():
    result = office_math.convert_office_math(r'\mathbf{x^12+\mathrm{y}}')
    root = ET.fromstring(result.mathml)
    assert ''.join(root.find('.//{*}msup')[-1].itertext()) == '1'
    text = ''.join(root.find('.//{*}semantics')[0].itertext())
    assert '2' in text and 'y' in text and '𝐲' not in text


@pytest.mark.parametrize('source', [r'\mathbf{\Gamma}', r'\mathbf{α}', r'\mathbf{\operatorname{foo}}'])
def test_unverified_bold_symbol_combinations_are_rejected(source):
    with pytest.raises(ValueError, match='保留'):
        office_math.convert_office_math(source)


def test_fraktur_font_resets_bold_scope():
    result = office_math.convert_office_math(r'\mathbf{\mathfrak{x}}')
    assert '𝐱' not in result.mathml
    assert 'fraktur' in result.mathml


def test_bold_clipboard_uses_native_word_html_instead_of_lossy_mathml():
    result = office_math.convert_office_math(r'前文 $\mathbf{x}+x$ 后文')
    mime = office_math.office_mime_data(result)
    assert not mime.hasFormat('application/x-qt-windows-mime;value="MathML"')
    assert 'http://schemas.microsoft.com/office/2004/12/omml' in mime.html()
    assert 'font-weight:bold' in mime.html()
    assert '前文' in mime.html() and '后文' in mime.html()
    assert mime.text() == result.source


@pytest.mark.parametrize(('source', 'operand'), [
    (r'\bigvee_{i=0}^{5}(slot[i]=t)+Q', '(slot[i]=t)'),
    (r'\bigwedge_{i=1}^{n}P_i', 'Pi'),
    (r'\bigvee_{i=1}^{n}\frac{a}{b}', 'ab'),
    (r'\bigvee_{i=1}^{n}(P_i\land(Q_i\lor R_i))=S', '(Pi∧(Qi∨Ri))'),
])
def test_large_logic_has_a_real_operand_without_eating_following_terms(source, operand):
    result = office_math.convert_office_math(source)
    with zipfile.ZipFile(io.BytesIO(result.docx)) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
    nary = doc.find('.//m:nary', M)
    assert nary is not None
    assert ''.join(nary.find('m:e', M).itertext()) == operand
    if source.endswith('+Q'):
        assert ''.join(doc.find('.//m:oMath', M).itertext()).endswith('+Q')
        assert 'Q' not in ''.join(nary.find('m:e', M).itertext())


def test_standalone_large_logic_does_not_invent_an_empty_operand():
    result = office_math.convert_office_math(r'\bigvee_{i=0}^{5}')
    with zipfile.ZipFile(io.BytesIO(result.docx)) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
    for nary in doc.findall('.//m:nary', M):
        assert len(nary.find('m:e', M)) > 0


@pytest.mark.parametrize('spacing', [r'\!', r'\hspace{0pt}'])
def test_large_logic_spacing_is_not_an_operand(spacing):
    result = office_math.convert_office_math(r'\bigvee_i' + spacing + 'P_i')
    with zipfile.ZipFile(io.BytesIO(result.docx)) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
    body = doc.find('.//m:nary/m:e', M)
    assert body is not None
    assert ''.join(body.itertext()).replace('\u200b', '') == 'Pi'


@pytest.mark.parametrize('source', [
    r'\bigvee_i{}', r'\bigvee_i(P_i+Q_i', r'\bigvee_i[a,b)',
    r'\bigvee_i\neg P_i', r'\bigvee_i f(i)',
])
def test_large_logic_keeps_original_layout_when_operand_is_uncertain(source):
    result = office_math.convert_office_math(source)
    with zipfile.ZipFile(io.BytesIO(result.docx)) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
    assert doc.find('.//m:nary', M) is None
    assert doc.find('.//m:limLow', M) is not None
