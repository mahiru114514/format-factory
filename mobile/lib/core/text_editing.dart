class EditableResult {
  String originalText;
  String _text;
  final List<String> _undo = [];
  EditableResult(String original) : originalText = original, _text = original;
  String get text => _text;
  String get currentText => _text;
  bool get dirty => _text != originalText;
  void update(String value) {
    if (value == _text) return;
    _undo.add(_text);
    _text = value;
  }

  bool undo() {
    if (_undo.isEmpty) return false;
    _text = _undo.removeLast();
    return true;
  }

  bool accept(String value, {bool discardEdits = false}) {
    if (dirty && !discardEdits) return false;
    originalText = value;
    _text = value;
    _undo.clear();
    return true;
  }

  String copyText([int? start, int? end]) {
    var a = (start ?? 0).clamp(0, _text.length),
        b = (end ?? _text.length).clamp(0, _text.length);
    if (a > b) {
      final t = a;
      a = b;
      b = t;
    }
    // Do not split a UTF-16 surrogate pair when a stale selection is clamped.
    if (a > 0 &&
        a < _text.length &&
        _text.codeUnitAt(a) >= 0xdc00 &&
        _text.codeUnitAt(a) <= 0xdfff) {
      a--;
    }
    if (b > 0 &&
        b < _text.length &&
        _text.codeUnitAt(b) >= 0xdc00 &&
        _text.codeUnitAt(b) <= 0xdfff) {
      b++;
    }
    return _text.substring(a, b);
  }
}

String latexReadable(String source) {
  // Keep structures whose meaning depends on delimiters, annotations or exact
  // literal spelling. A partial regex rewrite is less useful than intact source.
  if (RegExp(r'\\verb\*?(?![a-zA-Z])').hasMatch(source) ||
      RegExp(
        r'\\(?:vec|hat|widehat|bar|over[a-zA-Z]*|under[a-zA-Z]*|tilde|widetilde|dot|ddot|mathbf|boldsymbol|bm)(?![a-zA-Z])',
      ).hasMatch(source) ||
      RegExp(
        r'\\begin\{(?!(?:equation\*?|align\*?|aligned|gather\*?|displaymath)\})',
      ).hasMatch(source)) {
    return source;
  }
  var value = source;
  // Escape literals before interpreting scripts. In particular, \_1 is text,
  // whereas _1 is a subscript. Choose a marker absent from the original input.
  var longestMarkerRun = 0;
  for (final run in RegExp('\uE000+').allMatches(source)) {
    if (run.end - run.start > longestMarkerRun) {
      longestMarkerRun = run.end - run.start;
    }
  }
  final marker = '\uE000' * (longestMarkerRun + 1);
  final literals = <String>[];
  value = value.replaceAllMapped(RegExp(r'\\\\|\\([_%$#{}&])'), (m) {
    literals.add(m[0] == r'\\' ? '\n' : m[1]!);
    return '$marker${literals.length - 1}\uE001';
  });
  var groupDepth = 0;
  for (final code in value.codeUnits) {
    if (code == 123) groupDepth++;
    if (code == 125) groupDepth--;
    if (groupDepth < 0) return source;
  }
  if (groupDepth != 0) return source;
  final greek = {
    'alpha': 'α',
    'beta': 'β',
    'gamma': 'γ',
    'delta': 'δ',
    'epsilon': 'ε',
    'theta': 'θ',
    'lambda': 'λ',
    'mu': 'μ',
    'pi': 'π',
    'sigma': 'σ',
    'phi': 'φ',
    'omega': 'ω',
    'Delta': 'Δ',
    'Sigma': 'Σ',
    'Omega': 'Ω',
    'times': '×',
    'cdot': '·',
    'leq': '≤',
    'geq': '≥',
    'neq': '≠',
    'ne': '≠',
    'infty': '∞',
    'iff': '⇔',
    'implies': '⇒',
    'impliedby': '⇐',
    'land': '∧',
    'wedge': '∧',
    'lor': '∨',
    'vee': '∨',
    'bigvee': '⋁',
    'bigwedge': '⋀',
    'lnot': '¬',
    'neg': '¬',
    'forall': '∀',
    'exists': '∃',
    'in': '∈',
    'notin': '∉',
    'subseteq': '⊆',
    'supseteq': '⊇',
    'sum': '∑',
    'prod': '∏',
    'to': '→',
    'rightarrow': '→',
    'leftarrow': '←',
    'leftrightarrow': '↔',
    'longleftrightarrow': '⟷',
    'Rightarrow': '⇒',
    'Leftarrow': '⇐',
    'Leftrightarrow': '⇔',
    'Longleftrightarrow': '⟺',
  };
  value = value.replaceAllMapped(
    RegExp(r'\\([a-zA-Z]+)'),
    (m) => greek[m[1]] ?? m[0]!,
  );
  // Repeated passes handle common nested fractions without evaluating source.
  for (var n = 0; n < 12; n++) {
    final before = value;
    value = value.replaceAllMapped(
      RegExp(r'\\(?:frac|dfrac|tfrac)\{([^{}]*)\}\{([^{}]*)\}'),
      (m) => '((${m[1]})/(${m[2]}))',
    );
    value = value.replaceAllMapped(
      RegExp(r'\\sqrt(?:\[([^\[\]{}]*)\])?\{([^{}]*)\}'),
      (m) => '√${m[1] == null ? '' : '[${m[1]}]'}(${m[2]})',
    );
    value = value.replaceAllMapped(
      RegExp(r'\\(?:text|mathrm|operatorname\*?)\{([^{}]*)\}'),
      (m) => m[1]!,
    );
    if (before == value) break;
  }
  value = value.replaceAll(
    RegExp(
      r'\\(?:begin|end)\{(?:equation\*?|align\*?|aligned|gather\*?|displaymath)\}',
    ),
    '',
  );
  value = value
      .replaceAll(r'\\', '\n')
      .replaceAll(RegExp(r'\\(?:limits|nolimits)(?![a-zA-Z])'), '')
      .replaceAll(RegExp(r'\\(?:left|right)(?![a-zA-Z])'), '');
  final superDigits = {
    '0': '⁰',
    '1': '¹',
    '2': '²',
    '3': '³',
    '4': '⁴',
    '5': '⁵',
    '6': '⁶',
    '7': '⁷',
    '8': '⁸',
    '9': '⁹',
    '+': '⁺',
    '-': '⁻',
    'n': 'ⁿ',
  };
  final subDigits = {
    '0': '₀',
    '1': '₁',
    '2': '₂',
    '3': '₃',
    '4': '₄',
    '5': '₅',
    '6': '₆',
    '7': '₇',
    '8': '₈',
    '9': '₉',
    '+': '₊',
    '-': '₋',
  };
  value = value.replaceAllMapped(
    RegExp(r'([\^_])(?:\{([0-9+\-n]+)\}|([0-9n]))'),
    (m) {
      final map = m[1] == '^' ? superDigits : subDigits;
      final body = m[2] ?? m[3]!;
      if (body.split('').any((c) => !map.containsKey(c))) return m[0]!;
      return body.split('').map((c) => map[c]).join();
    },
  );
  return value.replaceAllMapped(
    RegExp('${RegExp.escape(marker)}([0-9]+)\uE001'),
    (m) => literals[int.parse(m[1]!)],
  );
}
