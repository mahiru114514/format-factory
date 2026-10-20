enum ConversionCategory { documents, tables, images, text }

class ConversionRequest {
  final String inputPath;
  final ConversionCategory category;
  final String target;
  final Map<String, dynamic> options;
  const ConversionRequest({
    required this.inputPath,
    required this.category,
    required this.target,
    this.options = const {},
  });
}

class ConversionResult {
  final List<String> outputPaths;
  final List<String> warnings;
  final String? text;
  final bool viaRemote;
  const ConversionResult({
    required this.outputPaths,
    this.warnings = const [],
    this.text,
    this.viaRemote = false,
  });
}

class LocalUnavailable implements Exception {
  final String message;
  const LocalUnavailable(this.message);
  @override
  String toString() => message;
}

class ConversionCancelled implements Exception {
  const ConversionCancelled();
  @override
  String toString() => '转换已取消，原文件已保留。';
}

class CancelToken {
  bool _cancelled = false;
  bool get isCancelled => _cancelled;
  void cancel() => _cancelled = true;
  void throwIfCancelled() {
    if (_cancelled) throw const ConversionCancelled();
  }
}

class AppSettings {
  final String serverUrl;
  final Map<String, dynamic> preferences;
  const AppSettings({this.serverUrl = '', this.preferences = const {}});
  Map<String, dynamic> toJson() => {
    'serverUrl': serverUrl,
    'preferences': preferences,
  };
  factory AppSettings.fromJson(Map<String, dynamic> json) => AppSettings(
    serverUrl: json['serverUrl'] as String? ?? '',
    preferences: Map<String, dynamic>.from(json['preferences'] as Map? ?? {}),
  );
}

class TaskRecord {
  final String id, inputPath, state;
  final ConversionCategory? category;
  final String? target;
  final Map<String, dynamic> options;

  /// Null means the origin was not stored by an older app version.
  final bool? viaRemote;
  final List<String> outputPaths, warnings;
  final String? error;
  final DateTime? createdAt;
  const TaskRecord({
    required this.id,
    required this.inputPath,
    required this.state,
    this.category,
    this.target,
    this.options = const {},
    this.viaRemote,
    this.outputPaths = const [],
    this.warnings = const [],
    this.error,
    this.createdAt,
  });
  Map<String, dynamic> toJson() => {
    'id': id,
    'inputPath': inputPath,
    'state': state,
    'category': category?.name,
    'target': target,
    'options': options,
    'viaRemote': viaRemote,
    'outputPaths': outputPaths,
    'warnings': warnings,
    'error': error,
    'createdAt': createdAt?.toIso8601String(),
  };
  factory TaskRecord.fromJson(Map<String, dynamic> j) => TaskRecord(
    id: j['id'] as String,
    inputPath: j['inputPath'] as String,
    state: ['running', 'queued'].contains(j['state'])
        ? 'interrupted'
        : j['state'] as String,
    category: ConversionCategory.values
        .where((c) => c.name == j['category'])
        .firstOrNull,
    target: j['target'] as String?,
    options: Map<String, dynamic>.from(j['options'] as Map? ?? {}),
    viaRemote: j['viaRemote'] as bool?,
    outputPaths: List<String>.from(j['outputPaths'] as List? ?? []),
    warnings: List<String>.from(j['warnings'] as List? ?? []),
    error: j['error'] as String?,
    createdAt: DateTime.tryParse(j['createdAt'] as String? ?? ''),
  );

  TaskRecord copyWith({
    String? id,
    String? inputPath,
    String? state,
    ConversionCategory? category,
    String? target,
    Map<String, dynamic>? options,
    bool? viaRemote,
    List<String>? outputPaths,
    List<String>? warnings,
    Object? error = _unchanged,
    DateTime? createdAt,
  }) => TaskRecord(
    id: id ?? this.id,
    inputPath: inputPath ?? this.inputPath,
    state: state ?? this.state,
    category: category ?? this.category,
    target: target ?? this.target,
    options: options ?? this.options,
    viaRemote: viaRemote ?? this.viaRemote,
    outputPaths: outputPaths ?? this.outputPaths,
    warnings: warnings ?? this.warnings,
    error: identical(error, _unchanged) ? this.error : error as String?,
    createdAt: createdAt ?? this.createdAt,
  );
}

const _unchanged = Object();
