import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;

import '../core/core.dart';
import '../platform/native_bridge.dart';

typedef UploadConsent = Future<bool> Function(
  ConversionRequest request,
  String policy,
);
const maxDraftBytes = 2 * 1024 * 1024;

class AppController extends ChangeNotifier {
  final Directory root;
  final NativeBridge bridge;
  late final FileStorage storage = FileStorage(
    Directory(p.join(root.path, 'outputs')),
  );
  late final AppRepository repository = AppRepository(root);
  AppController({required this.root, required this.bridge});
  final inputs = <String>[];
  List<TaskRecord> history = [];
  EditableResult result = EditableResult('');
  String source = '', sourcePath = '', serverUrl = '', theme = 'system';
  int page = 1;
  bool busy = false;
  String status = '';
  Map<String, dynamic>? capabilities;
  String? _capsServer;
  CancelToken? _cancel;
  Future<void> _writes = Future.value();
  Timer? _saveTimer;
  Future<void> _imports = Future.value();
  StreamSubscription<List<SharedInput>>? _subscription;
  final _importedShares = <String>{};
  bool _disposed = false;
  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  Future<void> load() async {
    final settings = await repository.loadSettings();
    serverUrl = settings.serverUrl;
    final prefs = settings.preferences;
    source = prefs['source'] as String? ?? '';
    sourcePath = prefs['sourcePath'] as String? ?? '';
    page = prefs['page'] as int? ?? 1;
    theme = prefs['theme'] as String? ?? 'system';
    _importedShares.addAll(
      List<String>.from(prefs['importedShares'] as List? ?? []),
    );
    result = EditableResult(prefs['original'] as String? ?? '');
    result.update(prefs['current'] as String? ?? result.text);
    inputs.addAll(
      List<String>.from(prefs['inputs'] as List? ?? [])
          .where((s) => File(s).existsSync()),
    );
    history = await repository.loadHistory();
    notifyListeners();
  }

  void persist() {
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(milliseconds: 300), _queuePersist);
  }

  void _queuePersist() {
    final settings = AppSettings(
      serverUrl: serverUrl,
      preferences: {
        'source': source,
        'sourcePath': sourcePath,
        'page': page,
        'theme': theme,
        'original': result.originalText,
        'current': result.text,
        'inputs': List.of(inputs),
        'importedShares': _importedShares.toList(),
      },
    );
    final records = List<TaskRecord>.of(history);
    _writes = _writes.catchError((_) {}).then((_) async {
      await repository.saveSettings(settings);
      await repository.saveHistory(records);
    });
  }

  Future<void> flush() async {
    _saveTimer?.cancel();
    _queuePersist();
    await _writes;
  }

  void changeSource(String value) {
    validateDraft(value);
    source = value;
    persist();
  }

  void editResult(String value) {
    validateDraft(value);
    result.update(value);
    persist();
    notifyListeners();
  }

  bool acceptResult(String value, {bool discard = false}) {
    validateDraft(value);
    final ok = result.accept(value, discardEdits: discard);
    if (ok) {
      persist();
      notifyListeners();
    }
    return ok;
  }

  void undo() {
    result.undo();
    persist();
    notifyListeners();
  }

  Future<void> copyResult([TextSelection? selection]) async {
    final text =
        selection != null && selection.isValid && !selection.isCollapsed
        ? result.copyText(selection.start, selection.end)
        : result.text;
    await bridge.copyText(text);
  }

  Future<bool> saveText() => bridge.saveBytes(
    '校对文本.txt',
    Uint8List.fromList(utf8.encode(result.text)),
    mimeType: 'text/plain',
  );
  void validateDraft(String value) {
    if (utf8.encode(value).length > maxDraftBytes) {
      throw const LocalUnavailable('校对文本最多 2 MiB，请分段导入；原文件仍可转换。');
    }
  }

  Future<String> importPicked(PickedInput input) async {
    if ((await input.length() ?? 0) > maxInputBytes) {
      throw const LocalUnavailable('单个文件请控制在 50 MiB 以内');
    }
    final dir = await Directory(p.join(root.path, 'inputs'))
        .create(recursive: true);
    final folder = await dir.createTemp('import-');
    final safe = p
        .basename(input.name)
        .replaceAll(RegExp(r'[<>:"/\\|?*\x00-\x1f]'), '_');
    final file = File(p.join(folder.path, safe.isEmpty ? '文件' : safe));
    var total = 0;
    final sink = file.openWrite();
    try {
      await for (final bytes in input.bytes()) {
        total += bytes.length;
        if (total > maxInputBytes) {
          throw const LocalUnavailable('单个文件请控制在 50 MiB 以内');
        }
        sink.add(bytes);
      }
      await sink.flush();
      await sink.close();
      final durable = await file.open(mode: FileMode.append);
      try {
        await durable.flush();
      } finally {
        await durable.close();
      }
      return file.path;
    } catch (_) {
      await sink.close();
      if (await file.exists()) await file.delete();
      rethrow;
    }
  }

  Future<String> importFile(String path) async {
    final f = File(path);
    return importPicked(
      PickedInput(p.basename(path), f.openRead, () async => f.length()),
    );
  }

  Future<void> pick({bool photos = false}) async {
    final files = await bridge.pickFiles(photos: photos);
    for (final file in files) {
      try {
        inputs.add(await importPicked(file));
      } catch (e) {
        status = friendly(e);
      }
    }
    persist();
    notifyListeners();
  }

  Future<void> startShares() async {
    void consume(List<SharedInput> entries) {
      _imports = _imports.catchError((_) {}).then((_) => importShares(entries));
    }

    try {
      _subscription = bridge.shares.listen(
        consume,
        onError: (Object e) {
          status = friendly(e);
          notifyListeners();
        },
      );
      consume(await bridge.initialShares());
    } catch (e) {
      status = friendly(e);
      notifyListeners();
    }
  }

  Future<void> importShares(List<SharedInput> entries) async {
    final paths = <String>[], texts = <String>[];
    for (final entry in entries) {
      try {
        final String key;
        final String importedPath;
        if (entry.isText) {
          key = 'true:${entry.value}';
          if (_importedShares.contains(key)) {
            source = entry.value;
            await flush();
            texts.add(entry.value);
            continue;
          }
          final text = entry.value;
          validateDraft(text);
          importedPath = await importPicked(
            PickedInput(
              '分享文本.txt',
              () => Stream.value(utf8.encode(text)),
              () async => utf8.encode(text).length,
            ),
          );
          source = text;
        } else {
          // Initial-media and event snapshots can both be queued before the
          // first durable import acknowledges (and deletes) the native cache.
          // Only a known successfully persisted path may skip a missing source;
          // an existing source is always copied and hashed to detect updates.
          if (!await File(entry.value).exists() &&
              _wasImportedFile(entry.value)) {
            paths.add(entry.value);
            continue;
          }
          // Hash the durable snapshot, not mutable picker cache metadata. Native
          // Android can overwrite the same display-name path on the next share.
          importedPath = await importFile(entry.value);
          final copy = File(importedPath);
          final digest = await sha256.bind(copy.openRead()).first;
          key = 'file:${jsonEncode([entry.value, digest.toString()])}';
          if (_importedShares.contains(key)) {
            await copy.delete();
            await copy.parent.delete();
            paths.add(entry.value);
            continue;
          }
        }
        inputs.add(importedPath);
        _importedShares.add(key);
        try {
          await flush();
        } catch (_) {
          _importedShares.remove(key);
          rethrow;
        }
        if (entry.isText) {
          texts.add(entry.value);
        } else {
          paths.add(entry.value);
        }
      } catch (e) {
        status = friendly(e);
      }
    }
    if (paths.isNotEmpty || texts.isNotEmpty) {
      await bridge.acknowledge(paths, texts);
    }
    notifyListeners();
  }

  bool _wasImportedFile(String path) {
    for (final key in _importedShares) {
      if (!key.startsWith('file:')) continue;
      try {
        final parts = jsonDecode(key.substring(5));
        if (parts is List && parts.length == 2 && parts.first == path) {
          return true;
        }
      } on FormatException {
        /* Ignore unknown older deduplication keys. */
      }
    }
    return false;
  }

  void removeInput(String path) {
    inputs.remove(path);
    persist();
    notifyListeners();
  }

  Future<void> setServer(String url) async {
    if (url.trim().isNotEmpty) validateServerUri(url);
    serverUrl = url.trim();
    capabilities = null;
    _capsServer = null;
    await flush();
    notifyListeners();
  }

  Future<Map<String, dynamic>> checkService() async {
    validateServerUri(serverUrl);
    final client = RemoteConversionClient(
      serverUrl: serverUrl,
      storage: storage,
    );
    try {
      capabilities = await client.capabilities(consent: true);
      _capsServer = serverUrl;
      notifyListeners();
      return capabilities!;
    } finally {
      client.close();
    }
  }

  String policyText() {
    final c = capabilities;
    if (c == null || _capsServer != serverUrl) {
      return '服务政策尚未读取。确认后先读取能力与保留期限，再请求你确认上传。';
    }
    return '单文件上限 ${((c['max_upload_bytes'] as num? ?? 0) / 1024 / 1024).toStringAsFixed(0)} MiB；转换超时 ${c['worker_timeout_seconds']} 秒；最长保留 ${c['retention_seconds']} 秒。结果完整保存到本机后请求删除服务副本。';
  }

  void _checkPair(ConversionRequest request) {
    final category =
        (capabilities?['categories'] as Map?)?[request.category.name] as Map?;
    final sourceExt = p
        .extension(request.inputPath)
        .toLowerCase()
        .replaceFirst('.', '');
    final ext =
        const {
          'jpeg': 'jpg',
          'tif': 'tiff',
          'heif': 'heic',
          'hif': 'heic',
          'markdown': 'md',
        }[sourceExt] ??
        sourceExt;
    if (request.options['method'] == 'formula') {
      if (((capabilities?['engines'] as Map?)?['formula'] as Map?)?['ready'] !=
          true) {
        throw const LocalUnavailable('这台服务尚未启用公式识别');
      }
      return;
    }
    final pairs = category?['pairs'] as List? ?? [];
    final matches = pairs.whereType<Map>().where(
      (x) => x['source'] == ext && x['target'] == request.target,
    );
    if (matches.isEmpty) throw const LocalUnavailable('这台服务未提供所选格式组合');
    if (matches.first['ready'] != true) {
      throw LocalUnavailable(
        matches.first['message']?.toString() ?? '这台服务所需引擎尚未就绪',
      );
    }
  }

  Future<ConversionResult?> remote(
    ConversionRequest req,
    UploadConsent consent,
  ) async {
    validateServerUri(serverUrl);
    // No HTTP occurs before this explicit permission, even a metadata request.
    if (capabilities == null || _capsServer != serverUrl) {
      if (!await consent(req, policyText())) return null;
      await checkService();
    }
    _checkPair(req);
    if (!await consent(req, policyText())) return null;
    final client = RemoteConversionClient(
      serverUrl: serverUrl,
      storage: storage,
    );
    try {
      final remoteReq = ConversionRequest(
        inputPath: req.inputPath,
        category: req.category,
        target: req.target,
        options: {
          ...req.options,
          if (req.options['encoding'] == 'gbk') 'encoding': 'gb18030',
        },
      );
      return await client.convert(remoteReq, consent: true, cancel: _cancel);
    } finally {
      client.close();
    }
  }

  Future<void> runBatch({
    required ConversionCategory category,
    required String target,
    required Map<String, dynamic> options,
    required bool forceRemote,
    required UploadConsent consent,
    List<String>? files,
    void Function(ConversionResult result)? onCompleted,
  }) async {
    if (busy) return;
    final queue = List<String>.of(files ?? inputs);
    if (queue.isEmpty) {
      status = '请先选择文件';
      notifyListeners();
      return;
    }
    busy = true;
    _cancel = CancelToken();
    notifyListeners();
    try {
      for (final path in queue) {
        if (_cancel!.isCancelled) break;
        var record = TaskRecord(
          id: DateTime.now().microsecondsSinceEpoch.toString(),
          inputPath: path,
          state: 'running',
          category: category,
          target: target,
          options: {...options, '_force_remote': forceRemote},
          createdAt: DateTime.now(),
        );
        history.insert(0, record);
        persist();
        notifyListeners();
        final req = ConversionRequest(
          inputPath: path,
          category: category,
          target: target,
          options: options,
        );
        ConversionResult? completed;
        try {
          ConversionResult? converted;
          if (forceRemote) {
            converted = await remote(req, consent);
          } else {
            try {
              converted = await LocalConversionService(storage)
                  .convert(req, cancel: _cancel);
            } on LocalUnavailable catch (e) {
              status = e.message;
              converted = await remote(req, consent);
            }
          }
          if (converted == null) {
            record = record.copyWith(
              state: 'cancelled',
              error: '未同意上传，原文件仍在本机',
            );
          } else {
            completed = converted;
            record = record.copyWith(
              state: 'succeeded',
              viaRemote: converted.viaRemote,
              outputPaths: converted.outputPaths,
              warnings: converted.warnings,
              error: null,
            );
          }
        } catch (e) {
          record = record.copyWith(
            state: e is ConversionCancelled ? 'cancelled' : 'failed',
            error: friendly(e),
          );
        }
        final i = history.indexWhere((r) => r.id == record.id);
        history[i] = record;
        status = record.state == 'succeeded'
            ? '转换完成，可在任务中保存或分享'
            : record.error ?? '已取消';
        persist();
        notifyListeners();
        if (completed != null) onCompleted?.call(completed);
      }
    } finally {
      busy = false;
      _cancel = null;
      await flush();
      notifyListeners();
    }
  }

  Future<ConversionResult?> runFormula(
    String imagePath, {
    required UploadConsent consent,
  }) async {
    ConversionResult? result;
    await runBatch(
      category: ConversionCategory.text,
      target: 'txt',
      options: const {'method': 'formula', 'page': 0},
      forceRemote: true,
      consent: consent,
      files: [imagePath],
      onCompleted: (value) => result = value,
    );
    return result;
  }

  void cancel() {
    _cancel?.cancel();
    status = '正在停止，已完成的文件会保留';
    notifyListeners();
  }

  Future<void> clearHistory() async {
    history = [];
    await flush();
    notifyListeners();
  }

  Future<void> attachSource(String path) async {
    sourcePath = path;
    page = 1;
    persist();
    notifyListeners();
  }

  String friendly(Object e) => e.toString().replaceFirst(
    RegExp(r'^(FormatException|Exception|FileSystemException):\s*'),
    '',
  );
  @override
  void dispose() {
    _disposed = true;
    _saveTimer?.cancel();
    _subscription?.cancel();
    _cancel?.cancel();
    super.dispose();
  }
}
