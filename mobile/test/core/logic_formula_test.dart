import 'package:flutter_test/flutter_test.dart';
import 'package:format_factory_mobile/core/core.dart';

void main() {
  test('fraction postfix applies to the whole quotient', () {
    expect(latexReadable(r'\frac{a}{b}^2'), '((a)/(b))²');
    expect(latexReadable(r'\frac{a}{b}!'), '((a)/(b))!');
    expect(latexReadable(r'\frac{a}{b}_i'), '((a)/(b))_i');
  });
  test('logical aliases preserve relation, bounds and indexed identifiers', () {
    expect(
      latexReadable(
        r'\operatorname{used}[t] \iff \bigvee\limits_{i=0}^{5}(\operatorname{slot}[i]=t)',
      ),
      'used[t] ⇔ ⋁_{i=0}⁵(slot[i]=t)',
    );
    expect(latexReadable(r'A\land B\lor\lnot C\implies D'), 'A∧ B∨¬ C⇒ D');
    expect(
      latexReadable(r'\Longleftrightarrow \leftarrow \unknown{x}'),
      r'⟺ ← \unknown{x}',
    );
  });

  test('roots and fraction aliases keep degree and grouping', () {
    expect(latexReadable(r'\sqrt[3]{x+1}'), '√[3](x+1)');
    expect(latexReadable(r'\dfrac{a+b}{c+d}'), '((a+b)/(c+d))');
    expect(latexReadable(r'\tfrac{1}{1+\frac{x}{y}}'), '((1)/(1+((x)/(y))))');
    expect(
      latexReadable(r'\operatorname*{argmax}_{x\in X} f(x)'),
      'argmax_{x∈ X} f(x)',
    );
  });

  test('structured environments retain their original notation', () {
    for (final source in [
      r'\begin{vmatrix}a&b\\c&d\end{vmatrix}',
      r'\begin{cases}x^2&x\ge0\\-x&x<0\end{cases}',
      r'\begin{custommath}x_1&\alpha\\y_2&\beta\end{custommath}',
    ]) {
      expect(latexReadable(source), source);
    }
  });

  test(
    'escaped literal characters are not treated as scripts or line breaks',
    () {
      expect(latexReadable(r'\text{item\_1 and 50\%}'), 'item_1 and 50%');
      expect(latexReadable(r'\verb|x_1\\y^2|'), r'\verb|x_1\\y^2|');
      expect(latexReadable(r'\verb*|x_1\\y^2|'), r'\verb*|x_1\\y^2|');
    },
  );

  test('line breaks do not reinterpret following letters as a command', () {
    expect(latexReadable(r'a\\alpha'), 'a\nalpha');
    expect(latexReadable(r'a\\\alpha'), 'a\nα');
    expect(latexReadable(r'a\\_1'), 'a\n₁');
    expect(
      latexReadable(
        '\uE000 literal '
        r'\_1',
      ),
      '\uE000 literal _1',
    );
  });

  test('incomplete groups stay intact for proofreading', () {
    expect(latexReadable(r'\frac{x}{\alpha'), r'\frac{x}{\alpha');
    expect(latexReadable(r'\sqrt[3]{x'), r'\sqrt[3]{x');
  });

  test(
    'mathematical bold notation is not stripped into ordinary scalar text',
    () {
      expect(latexReadable(r'\mathbf{x}+x'), r'\mathbf{x}+x');
    },
  );
}
