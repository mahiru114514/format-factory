"""Semantic regressions: readable conversion must not silently change formulas."""
import pytest

from factory.text import latex_to_text


@pytest.mark.parametrize('suffix', ['^2', '!', '_i'])
def test_fraction_postfix_applies_to_the_whole_quotient(suffix):
    assert latex_to_text(r'\frac{a}{b}' + suffix) == '((a)/(b))' + suffix


@pytest.mark.parametrize('source,expected', [
    (r'\frac{a+b}{c+d}', '((a+b)/(c+d))'),
    (r'\frac{1}{1+\frac{x}{y}}', '((1)/(1+((x)/(y))))'),
    (r'\dfrac{a}{b}+\tfrac{c}{d}', '((a)/(b))+((c)/(d))'),
    (r'\sqrt[3]{x+1}', '√[3](x+1)'),
    (r'\sqrt{\frac{a+b}{c}}', '√(((a+b)/(c)))'),
    (r'\operatorname*{argmax}_{x\in X} f(x)', 'argmax_{x∈X} f(x)'),
])
def test_grouping_and_optional_arguments_keep_mathematical_meaning(source, expected):
    assert latex_to_text(source) == expected


@pytest.mark.parametrize('source', [
    r'\vec{x}', r'\hat{x}', r'\bar{z}', r'\overline{AB}',
    r'\underline{x}', r'\widehat{AB}', r'\widetilde{x}',
    r'\dot{x}', r'\ddot{x}', r'\underbrace{a+b}_{n}',
    r'\overbrace{a+b}^{n}',
    r'\underleftarrow{AB}', r'\underrightarrow{AB}', r'\underleftrightarrow{AB}',
    r'\overrightharpoon{x}', r'\overleftharpoon{x}',
    r'\overbracket{a+b}^{n}', r'\underbracket{a+b}_{n}',
    r'\overgroup{a+b}', r'\undergroup{a+b}', r'\mathring{x}',
    r'a\not\subseteq B',
    r'\begin{array}{r|l}A&b\end{array}',
    r'\begin{vmatrix}a&b\\c&d\end{vmatrix}',
    r'\begin{Vmatrix}a&b\\c&d\end{Vmatrix}',
    r'f(x)=\begin{cases}x^2 & x\ge0\\-x & x<0\end{cases}',
    r'\begin{custommath}a&b\\c&d\end{custommath}',
    r'\frac{x}{', r'\sqrt[3]{x', r'\begin{cases}x&x>0',
])
def test_unsupported_or_incomplete_structures_are_preserved(source):
    assert latex_to_text(source) == source


@pytest.mark.parametrize('source,tokens', [
    (r'\forall x\in A,\exists y\notin B:x\ne y', ['∀','∈','∃','∉','≠']),
    (r'A\subseteq B\supseteq C\cup D\cap E', ['⊆','⊇','∪','∩']),
    (r'\sum_{i=0}^{n}x_i+\prod_{j=1}^{m}y_j', ['∑','_{i=0}','^{n}','∏','_{j=1}','^{m}']),
    (r'\int_0^1 x^2\,dx+\iint_D f\,dA', ['∫','_0','^1','∬','_D']),
    (r'\{x\in\mathbb{R}\mid x>0\}', ['{','∈','ℝ','|','}']),
    (r'\begin{pmatrix}a&b\\c&d\end{pmatrix}', ['a','b','c','d',';']),
    (r'\begin{aligned}a&=b+c\\d&=e-f\end{aligned}', ['a','b+c','\n','d','e-f']),
    (r'A\mapsto B\longrightarrow C\hookrightarrow D', ['↦','⟶','↪']),
])
def test_other_common_formula_families_keep_semantic_tokens(source, tokens):
    result = latex_to_text(source)
    assert all(token in result for token in tokens), result
