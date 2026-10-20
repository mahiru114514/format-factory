from dataclasses import dataclass


def latex_to_text(source: str) -> str:
    from pylatexenc.latex2text import LatexNodes2Text, MacroTextSpec, get_default_latex_context_db
    from pylatexenc.macrospec import MacroSpec
    from pylatexenc.latexwalker import (LatexWalkerParseError,
                                       get_default_latex_context_db as walker_context)

    class PreservingText(LatexNodes2Text):
        def macro_node_to_text(self, node):
            if (self.latex_context.get_macro_spec(node.macroname) is None
                    or node.macroname in preserved_marks
                    or node.macroname.startswith(('over', 'under'))):
                # An unsupported command may carry mathematical meaning. Retain
                # its spelling and arguments rather than silently deleting it.
                return node.latex_verbatim()
            return super().macro_node_to_text(node)

        def environment_node_to_text(self, node):
            if ((self.latex_context.get_environment_spec(node.environmentname) is None
                 and node.environmentname not in {'aligned', 'split', 'gathered'})
                    or node.environmentname in {'cases', 'vmatrix', 'Vmatrix', 'Bmatrix', 'array'}):
                # Determinants, norms and conditional branches must retain their
                # delimiters; flattening cells into ordinary lines loses meaning.
                return node.latex_verbatim()
            return super().environment_node_to_text(node)

    preserved_marks = {'vec', 'hat', 'widehat', 'bar', 'overline', 'underline',
                       'tilde', 'widetilde', 'dot', 'ddot', 'dddot', 'ddddot',
                       'overbrace', 'underbrace', 'overrightarrow', 'overleftarrow',
                       'overleftrightarrow', 'check', 'breve', 'acute', 'grave', 'mathring', 'not'}

    def argument_text(node, converter, index):
        return converter._groupnodecontents_to_text(node.nodeargd.argnlist[index])

    def fraction(node, l2tobj):
        return f'(({argument_text(node, l2tobj, 0)})/({argument_text(node, l2tobj, 1)}))'

    def root(node, l2tobj):
        degree = node.nodeargd.argnlist[0]
        prefix = f'[{argument_text(node, l2tobj, 0)}]' if degree is not None else ''
        return f'√{prefix}({argument_text(node, l2tobj, 1)})'

    def operator_name(node, l2tobj):
        return argument_text(node, l2tobj, -1)

    symbols = {'iff': '⇔', 'implies': '⇒', 'impliedby': '⇐',
               'land': '∧', 'lor': '∨', 'lnot': '¬', 'ne': '≠'}
    text_context = get_default_latex_context_db()
    text_context.add_context_category('factory-logic', macros=[
        *(MacroTextSpec(name, symbol) for name, symbol in symbols.items()),
        *(MacroTextSpec(name, fraction) for name in ('frac', 'dfrac', 'tfrac')),
        MacroTextSpec('sqrt', root),
        MacroTextSpec('operatorname', operator_name),
        MacroTextSpec('limits', discard=True),
        MacroTextSpec('nolimits', discard=True),
    ], prepend=True)
    parse_context = walker_context()
    parse_context.add_context_category('factory-logic', macros=[
        MacroSpec('operatorname', '*{'),
        *(MacroSpec(name, '{{') for name in ('frac', 'dfrac', 'tfrac')),
    ], prepend=True)
    # Braces delimit the scope of grouped subscripts/superscripts and unknown
    # commands. Built-in fraction/font handlers still consume their own braces.
    try:
        return PreservingText(latex_context=text_context, math_mode='text',
                              keep_braced_groups=True, keep_braced_groups_minlen=0).latex_to_text(
                                  source, latex_context=parse_context, tolerant_parsing=False)
    except LatexWalkerParseError:
        # Incomplete OCR/source must stay inspectable, rather than being silently
        # repaired by the parser and copied as a different mathematical formula.
        return source


def process_source(source: str, mode: str) -> str:
    if not source.strip():
        raise ValueError('请先粘贴文本，或导入图片 / PDF。')
    return source if mode in ('source', 'office') else latex_to_text(source)


@dataclass
class ResultState:
    original: str = ''
    current: str = ''

    @property
    def dirty(self) -> bool:
        return self.current != self.original

    def accept(self, text: str) -> None:
        self.original = self.current = text

    def edit(self, text: str) -> None:
        self.current = text

    def copy_text(self, start: int | None = None, end: int | None = None) -> str:
        text = self.current if start is None else self.current[start:end]
        if not text.strip():
            raise ValueError('没有可复制的文字。')
        return text
