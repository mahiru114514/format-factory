from pathlib import Path

import pytest


def test_unique_output_never_overwrites_source(tmp_path):
    from factory.common import unique_path
    original = tmp_path / '中文.txt'
    original.write_text('原文', encoding='utf-8')
    assert unique_path(original) == tmp_path / '中文 (1).txt'
    assert original.read_text(encoding='utf-8') == '原文'


@pytest.mark.parametrize('encoding', ['utf-8-sig', 'gb18030', 'utf-16'])
def test_read_chinese_text(tmp_path, encoding):
    from factory.common import read_text
    file = tmp_path / '文本.txt'
    file.write_text('中文，公式 α\n下一行', encoding=encoding)
    assert read_text(file) == '中文，公式 α\n下一行'


def test_publish_collision_preserves_previous_output(tmp_path):
    from factory.common import publish
    source, destination = tmp_path / 'stage', tmp_path / 'out.txt'
    source.write_bytes(b'new')
    destination.write_bytes(b'old')
    result = publish(source, destination)
    assert result.name == 'out (1).txt'
    assert result.read_bytes() == b'new'
    assert destination.read_bytes() == b'old'


def test_latex_readable_text_preserves_math_meaning():
    from factory.text import latex_to_text
    output = latex_to_text(r'中文 $\frac{a}{b} + \sqrt{x} = \alpha$')
    assert '中文' in output and 'a' in output and 'b' in output
    assert 'α' in output and '\\frac' not in output and '\\sqrt' not in output


def test_plain_text_keeps_backslashes_and_unicode():
    from factory.text import process_source
    original = '中文\n' + r'\frac{α}{β} = 1' + '\n'
    assert process_source(original, 'source') == original


def test_logic_formula_keeps_equivalence_bounds_and_array_index():
    from factory.text import latex_to_text
    source = r'\operatorname{used}[t] \iff \bigvee\limits_{i=0}^{5}(\operatorname{slot}[i]=t)'
    output = latex_to_text(source)
    assert ''.join(output.split()) == 'used[t]⇔⋁_{i=0}^{5}(slot[i]=t)'


@pytest.mark.parametrize('macro,symbol', [('iff', '⇔'), ('implies', '⇒'), ('impliedby', '⇐'),
                                        ('land', '∧'), ('lor', '∨'), ('lnot', '¬')])
def test_readable_logical_aliases_are_not_silently_discarded(macro, symbol):
    from factory.text import latex_to_text
    assert ''.join(latex_to_text('A \\' + macro + ' B').split()) == 'A' + symbol + 'B'


def test_unknown_macros_and_grouped_arguments_survive_readable_conversion():
    from factory.text import latex_to_text
    assert latex_to_text(r'\myrelation{x}{y} + \leftcustom{z}') == r'\myrelation{x}{y} + \leftcustom{z}'


def test_edit_state_copies_current_edits_and_rejects_empty():
    from factory.text import ResultState
    state = ResultState()
    with pytest.raises(ValueError):
        state.copy_text()
    state.accept(r'\frac{x}{2}')
    state.edit('修正 α\n第二行')
    assert state.dirty
    assert state.copy_text() == '修正 α\n第二行'
    assert state.copy_text(3, 4) == 'α'
    state.edit('   \n')
    with pytest.raises(ValueError):
        state.copy_text()


def test_same_format_is_rejected_without_mutation(tmp_path):
    from factory.service import convert
    from factory.common import Options
    source = tmp_path / 'a.txt'
    source.write_text('safe', encoding='utf-8')
    with pytest.raises(ValueError, match='相同'):
        convert('documents', source, 'txt', tmp_path, Options())
    assert source.read_text() == 'safe'
