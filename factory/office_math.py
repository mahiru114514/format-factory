"""Local, structure-preserving Office equations and clipboard representations."""
from __future__ import annotations

import io
import json
import subprocess
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from xml.etree import ElementTree as ET

_BOLD = {}
for _first, _last, _target in [('A', 'Z', 0x1D400), ('a', 'z', 0x1D41A), ('0', '9', 0x1D7CE)]:
    _BOLD.update({chr(code): chr(_target + code - ord(_first)) for code in range(ord(_first), ord(_last) + 1)})
_PLAIN = {value: key for key, value in _BOLD.items()}


def _plain_bold(text):
    if text and any(char in _PLAIN for char in text) and all(char in _PLAIN or not char.isalnum() for char in text):
        return ''.join(_PLAIN.get(char, char) for char in text)
    return None


@dataclass(frozen=True)
class OfficeMath:
    source: str
    html: str
    docx: bytes
    mathml: str | None
    equations: int
    word_html: str | None = None


def _pandoc(source: str, input_format: str, target: str) -> bytes:
    import pypandoc
    command = [pypandoc.get_pandoc_path(), '--from', input_format, '--to', target,
               '--wrap=none', '--fail-if-warnings', '--sandbox']
    if target == 'html':
        command.append('--mathml')
    if target == 'docx':
        command += ['--output', '-']
    try:
        result = subprocess.run(command, input=source.encode('utf-8'), capture_output=True,
                                timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as error:
        raise ValueError('公式转换超时，内容已保留，请缩短内容后重试。') from error
    if result.returncode or result.stderr.strip():
        detail = result.stderr.decode('utf-8', errors='replace')[:700]
        raise ValueError('公式未能完整转换，请检查命令、括号和上下标。\n' + detail)
    return result.stdout


@lru_cache(maxsize=1)
def _api_version() -> list[int]:
    return json.loads(_pandoc('', 'markdown', 'json'))['pandoc-api-version']


def _segments(source: str) -> list[tuple[str, str, str]]:
    from pylatexenc.latexwalker import LatexWalker, LatexMathNode, LatexWalkerParseError
    try:
        nodes, _, _ = LatexWalker(source, tolerant_parsing=False).get_latex_nodes()
    except LatexWalkerParseError as error:
        raise ValueError('LaTeX 不完整，请检查公式定界符和花括号。') from error
    maths = [node for node in nodes if isinstance(node, LatexMathNode)]
    if not maths:
        return [('math', source.strip(), 'DisplayMath')]
    segments = []
    position = 0
    for node in maths:
        if node.pos > position:
            segments.append(('text', source[position:node.pos], ''))
        opening, closing = node.delimiters
        content = source[node.pos+len(opening):node.pos+node.len-len(closing)]
        if not content.strip():
            raise ValueError('发现空公式，请补全内容。')
        segments.append(('math', content, 'DisplayMath' if node.displaytype == 'display' else 'InlineMath'))
        position = node.pos + node.len
    if position < len(source):
        segments.append(('text', source[position:], ''))
    return segments


def _checked_math(source: str) -> str:
    """Bridge known texmath deviations without changing the user's editor text."""
    from pylatexenc.latexwalker import (LatexWalker, LatexCharsNode, LatexMacroNode,
        LatexCommentNode, LatexEnvironmentNode, LatexMathNode, LatexWalkerParseError)
    try:
        nodes, _, _ = LatexWalker(source, tolerant_parsing=False).get_latex_nodes()
    except LatexWalkerParseError as error:
        raise ValueError('LaTeX 不完整，请检查公式括号和上下标。') from error
    edits = []
    unsupported = {'color', 'textcolor', 'hline', 'cline', 'hdashline',
                   'tag', 'tag*', 'label', 'multicolumn', 'multirow'}
    modifiers = {'limits', 'nolimits', 'displaystyle', 'textstyle', 'scriptstyle', 'scriptscriptstyle'}

    def check_macro(node):
        if isinstance(node, LatexMacroNode) and node.macroname in unsupported:
            raise ValueError(f'当前无法可靠保留 \\{node.macroname} 的排版，已取消公式复制。请保留原始 LaTeX。')

    def literal(items):
        for node in items or []:
            check_macro(node)
            if isinstance(node, LatexMathNode):
                walk(node.nodelist)
            elif getattr(node, 'nodelist', None) is not None:
                literal(node.nodelist)
            args = getattr(node, 'nodeargd', None)
            if args:
                for arg in args.argnlist:
                    if arg is not None:
                        literal([arg])

    def walk(items):
        tokens = []
        for node in items or []:
            if isinstance(node, LatexCommentNode):
                continue
            if isinstance(node, LatexMacroNode):
                check_macro(node)
                if node.macroname in modifiers:
                    continue
                # Text inside these macros has literal underscores/carets.
                if node.macroname.startswith('text') or node.macroname == 'operatorname':
                    if node.nodeargd:
                        for arg in node.nodeargd.argnlist:
                            if arg is not None:
                                literal([arg])
                    tokens.append((None, node.pos))
                    continue
            if isinstance(node, LatexEnvironmentNode) and node.environmentname == 'array':
                raise ValueError('当前无法可靠保留 array 的列对齐和分隔线，已取消公式复制。可使用无分隔线的 matrix / pmatrix。')
            if isinstance(node, LatexCharsNode):
                tokens.extend((char, node.pos + index) for index, char in enumerate(node.chars))
            else:
                if getattr(node, 'nodelist', None) is not None:
                    walk(node.nodelist)
                args = getattr(node, 'nodeargd', None)
                if args:
                    for arg in args.argnlist:
                        if arg is not None:
                            walk([arg])
                tokens.append((None, node.pos))
        used = set()
        argument = False
        for char, position in tokens:
            if char is not None and char.isspace():
                continue
            if char in ('^', '_'):
                if argument or char in used:
                    raise ValueError('上下标重复或缺少内容，请使用花括号明确范围，例如 x^{12} 或 x^{1}2。')
                used.add(char)
                argument = True
            elif argument:
                # TeX takes ONE unbraced digit; texmath otherwise collects an
                # entire number. Explicit braces retain the strict TeX scope.
                if char is not None and char.isascii() and char.isdigit():
                    edits.append((position, position + 1, '{' + char + '}'))
                argument = False
            else:
                used.clear()
        if argument:
            raise ValueError('上下标缺少内容，请补全后再复制。')

    walk(nodes)
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return _upright_bold_math(source)


def _upright_bold_math(source: str) -> str:
    """Avoid texmath's bold-italic mapping for LaTeX's upright Latin mathbf."""
    from pylatexenc.latexwalker import LatexWalker, LatexCharsNode, LatexMacroNode
    nodes, _, _ = LatexWalker(source, tolerant_parsing=False).get_latex_nodes()
    translation = str.maketrans(_BOLD)
    resets = {'mathrm', 'mathit', 'mathnormal', 'mathsf', 'mathtt', 'mathbb',
              'mathcal', 'mathscr', 'mathfrak', 'boldsymbol', 'bm', 'operatorname'}
    structural = {'frac', 'dfrac', 'tfrac', 'sqrt', 'left', 'right', 'limits', 'nolimits',
                  'hat', 'widehat', 'vec', 'bar', 'overline', 'underline', 'tilde', 'widetilde',
                  'dot', 'ddot', 'overbrace', 'underbrace'}

    def render(node, bold=False):
        if isinstance(node, LatexCharsNode):
            if bold and any(char.isalnum() and not char.isascii() for char in node.chars):
                raise ValueError('当前无法可靠保留非拉丁字符的粗体，请保留原始 LaTeX。')
            return node.chars.translate(translation) if bold else node.chars
        if isinstance(node, LatexMacroNode) and node.macroname == 'mathbf':
            args = node.nodeargd.argnlist if node.nodeargd else []
            if len(args) != 1 or args[0] is None:
                raise ValueError('粗体命令缺少内容，请补全花括号。')
            # Keep the group scope. Explicit Unicode bold Roman identifiers
            # carry their style in MathML and OMML without changing neighbors.
            return '{' + render(args[0], True) + '}'
        if isinstance(node, LatexMacroNode) and bold:
            if node.macroname in resets or node.macroname.startswith('text'):
                if not node.nodeargd or not node.nodeargd.argnlist:
                    raise ValueError(f'当前无法可靠保留粗体中嵌套的 \\{node.macroname}，请保留原始 LaTeX。')
                bold = False
            elif node.macroname not in structural:
                raise ValueError(f'当前无法可靠保留 \\{node.macroname} 的粗体，请保留原始 LaTeX。')
        children = list(getattr(node, 'nodelist', None) or [])
        args = getattr(node, 'nodeargd', None)
        if args:
            children.extend(arg for arg in args.argnlist if arg is not None)
        text = source[node.pos:node.pos+node.len]
        for child in sorted(children, key=lambda item: item.pos, reverse=True):
            a = child.pos - node.pos
            b = a + child.len
            text = text[:a] + render(child, bold) + text[b:]
        return text

    return ''.join(render(node) for node in nodes)


def _large_logic_docx(data: bytes) -> bytes:
    """Use actual Office large operators for texmath's nested limit notation."""
    from copy import deepcopy
    from lxml import etree
    uri = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
    q = lambda name: '{' + uri + '}' + name
    ns = {'m': uri}

    def visible_text(value):
        return ''.join(char for char in value if not char.isspace()
                       and char not in '\u200b\u200c\u200d\ufeff\u2060')

    def following_operand(operator):
        siblings = list(operator.itersiblings())
        leading = []
        while siblings:
            text = siblings[0].find('m:t', ns)
            if text is None or visible_text(text.text or ''):
                break
            leading.append(siblings.pop(0))
        if not siblings:
            return []
        first = siblings[0]
        text = first.find('m:t', ns)
        value = (text.text or '') if text is not None else ''
        if text is None:
            if first.tag == q('r'):
                return []
            return leading + [first]  # One structured atom: script, fraction, delimiter, etc.
        if visible_text(value) in {'+', '-', '−', '=', '⇔', '⇒', '→', ',', ';', ':', ')', ']', '}', '¬', '∀', '∃'}:
            return []
        pairs = {'(': ')', '[': ']', '{': '}', '⟨': '⟩'}
        if not value or value[0] not in pairs:
            # A function followed by its argument is not a complete single run.
            if len(siblings) > 1:
                next_text = siblings[1].find('m:t', ns)
                if next_text is not None and (next_text.text or '')[:1] in pairs:
                    return []
            return leading + [first]
        stack = []
        selected = list(leading)
        for sibling in siblings:
            selected.append(sibling)
            token = sibling.find('m:t', ns)
            if token is None:
                continue  # Structured atoms contain their own balanced contents.
            content = token.text or ''
            for index, char in enumerate(content):
                if char in pairs:
                    stack.append(pairs[char])
                elif char in pairs.values():
                    if not stack or stack.pop() != char:
                        return []
                    if not stack:
                        # Preserve any following text in the same styled run.
                        if index + 1 < len(content):
                            remainder = deepcopy(sibling)
                            remainder.find('m:t', ns).text = content[index+1:]
                            token.text = content[:index+1]
                            sibling.addnext(remainder)
                        return selected
        return []

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read('word/document.xml'))
        changed = False
        for run in root.iter(q('r')):
            text = run.find('m:t', ns)
            plain = _plain_bold(text.text) if text is not None else None
            if plain is not None:
                text.text = plain
                properties = run.find('m:rPr', ns)
                if properties is None:
                    properties = etree.Element(q('rPr'))
                    run.insert(0, properties)
                style = properties.find('m:sty', ns)
                if style is None:
                    style = etree.SubElement(properties, q('sty'))
                style.set(q('val'), 'b')
                changed = True
        # Only exact large-logic limit trees are changed; ordinary lim/accents
        # and their full expression scopes remain untouched.
        for node in reversed(list(root.iter(q('limLow'), q('limUpp')))):
            if node.getparent() is None or node.getparent().tag == q('e') and node.getparent().getparent().tag in (q('limLow'), q('limUpp')):
                continue
            lower = upper = None
            current = node
            if current.tag == q('limLow'):
                lower = current.find('m:lim', ns)
                bases = list(current.find('m:e', ns))
                if len(bases) == 1 and bases[0].tag == q('limUpp'):
                    current = bases[0]
                    upper = current.find('m:lim', ns)
            else:
                upper = current.find('m:lim', ns)
            base = current.find('m:e', ns)
            if base is None or len(base) != 1 or base[0].tag != q('r'):
                continue
            text = base[0].find('m:t', ns)
            if text is None or text.text not in ('⋁', '⋀'):
                continue
            operands = following_operand(node)
            if not operands:
                # A standalone operator is valid notation. Its original limit
                # layout must not acquire an invented, visible empty slot.
                continue
            nary = etree.Element(q('nary'))
            properties = etree.SubElement(nary, q('naryPr'))
            for name, value in [('chr', text.text), ('limLoc', 'undOvr'), ('grow', '1'),
                                ('subHide', '0' if lower is not None else '1'),
                                ('supHide', '0' if upper is not None else '1')]:
                etree.SubElement(properties, q(name)).set(q('val'), value)
            for name, limit in [('sub', lower), ('sup', upper)]:
                target = etree.SubElement(nary, q(name))
                if limit is not None:
                    for child in limit:
                        target.append(deepcopy(child))
            body = etree.SubElement(nary, q('e'))
            for operand in operands:
                body.append(operand)
            node.getparent().replace(node, nary)
            changed = True
        if not changed:
            return data
        document_xml = etree.tostring(root, encoding='UTF-8', xml_declaration=True)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as result:
            for entry in archive.infolist():
                result.writestr(entry, document_xml if entry.filename == 'word/document.xml' else archive.read(entry))
        return output.getvalue()


def convert_office_math(source: str) -> OfficeMath:
    if not source.strip():
        raise ValueError('没有可复制的公式。')
    if len(source) > 200_000:
        raise ValueError('公式内容过长，请分段转换。')
    segments = _segments(source)
    inlines = []
    for kind, text, display in segments:
        if kind == 'math':
            inlines.append({'t': 'Math', 'c': [{'t': display}, _checked_math(text)]})
        else:
            # Literal text stays literal: no HTML, links, includes or Markdown
            # resources from user input are interpreted by Pandoc.
            for index, line in enumerate(text.split('\n')):
                if index:
                    inlines.append({'t': 'LineBreak'})
                if line:
                    inlines.append({'t': 'Str', 'c': line})
    ast = json.dumps({'pandoc-api-version': _api_version(), 'meta': {},
                      'blocks': [{'t': 'Para', 'c': inlines}]}, ensure_ascii=False)
    html = _pandoc(ast, 'json', 'html').decode('utf-8')
    # Explicit MathML style is essential: Word otherwise infers italic even
    # from Unicode bold Roman glyphs inside <mi>.
    from lxml import etree
    html_root = etree.fromstring(('<root>'+html+'</root>').encode('utf-8'))
    for node in html_root.iter():
        if etree.QName(node).localname in ('mi', 'mn', 'mtext'):
            plain = _plain_bold(node.text)
            if plain is not None:
                node.text = plain
                node.set('mathvariant', 'bold')
    html = ''.join(etree.tostring(node, encoding='unicode') for node in html_root)
    count = sum(kind == 'math' for kind, _, _ in segments)
    # A custom single-equation MathML flavor must never drop surrounding prose
    # or additional equations. Mixed content uses HTML MathML instead.
    standalone = count == 1 and not any(kind == 'text' and text.strip() for kind, text, _ in segments)
    parsed = ET.fromstring('<root>' + html + '</root>')
    math_nodes = parsed.findall('.//{http://www.w3.org/1998/Math/MathML}math')
    if len(math_nodes) != count:
        raise ValueError('公式结构未完整生成，已取消复制。')
    mathml = None
    if standalone:
        start = html.index('<math ')
        mathml = html[start:html.index('</math>', start)+len('</math>')]
    docx = _large_logic_docx(_pandoc(ast, 'json', 'docx'))
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    if len(root.findall('.//{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath')) != count:
        raise ValueError('Office 公式结构未完整生成，已取消复制。')
    return OfficeMath(source, html, docx, mathml, count, _word_bold_html(docx, html))


def _word_bold_html(docx: bytes, html: str) -> str | None:
    """Word's native HTML math format avoids its MathML bold->italic import."""
    from lxml import etree
    math_uri = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
    legacy = 'http://schemas.microsoft.com/office/2004/12/omml'
    ns = {'m': math_uri}
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        document = etree.fromstring(archive.read('word/document.xml'))
    if not document.findall('.//m:sty[@m:val="b"]', ns):
        return None

    def legacy_node(node):
        name = etree.QName(node)
        uri = legacy if name.namespace == math_uri else name.namespace
        result = etree.Element('{'+uri+'}'+name.localname, nsmap={'m': legacy})
        for key, value in node.attrib.items():
            attr = etree.QName(key)
            result.set('{'+legacy+'}'+attr.localname if attr.namespace == math_uri else key, value)
        result.text = node.text
        for child in node:
            if child.tag == '{'+math_uri+'}t':
                if len(result):
                    result[-1].tail = (result[-1].tail or '') + (child.text or '')
                else:
                    result.text = (result.text or '') + (child.text or '')
            else:
                result.append(legacy_node(child))
        if name.localname == 'r' and name.namespace == math_uri:
            style = node.find('m:rPr/m:sty', ns)
            value = style.get('{'+math_uri+'}val') if style is not None else ('p' if node.find('m:rPr/m:nor', ns) is not None else 'i')
            span = etree.Element('span')
            span.set('style', 'font-family:"Cambria Math";font-weight:'+('bold' if value in ('b', 'bi') else 'normal')+
                     ';font-style:'+('italic' if value in ('i', 'bi') else 'normal'))
            span.append(result)
            return span
        return result

    parsed = etree.fromstring(('<root>'+html+'</root>').encode('utf-8'))
    maths = parsed.findall('.//{http://www.w3.org/1998/Math/MathML}math')
    office = document.findall('.//m:oMath', ns)
    if len(maths) != len(office):
        raise ValueError('粗体公式的剪贴板结构不完整，已取消复制。')
    for math, equation in zip(maths, office):
        xml = etree.tostring(legacy_node(equation), encoding='unicode')
        replacement = etree.Comment('[if gte msEquation 12]>'+xml+'<![endif]')
        replacement.tail = math.tail
        math.getparent().replace(math, replacement)
    fragment = ''.join(etree.tostring(node, encoding='unicode') for node in parsed)
    return '<html xmlns:m="'+legacy+'"><head><meta charset="utf-8"></head><body>'+fragment+'</body></html>'


def office_mime_data(result: OfficeMath):
    from PySide6.QtCore import QMimeData
    mime = QMimeData()
    # WPS 12.1.0.28043 accepts an OOXML package directly in this clipboard
    # flavor. Verified by pasting in a fresh WPS document and checking OMaths.
    # No opaque descriptors or process-specific object handles are needed.
    mime.setData('application/x-qt-windows-mime;value="Kingsoft WPS 9.0 Format"', result.docx)
    if result.mathml and not result.word_html:
        data = result.mathml.encode('utf-16-le') + b'\0\0'
        for name in ('MathML', 'MathML Presentation'):
            mime.setData(f'application/x-qt-windows-mime;value="{name}"', data)
    mime.setHtml(result.word_html or result.html)
    mime.setText(result.source)
    return mime
