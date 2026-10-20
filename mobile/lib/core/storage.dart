import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:archive/archive.dart' hide ZLibDecoder;
import 'package:path/path.dart' as p;

import 'models.dart';

const maxInputBytes = 50 * 1024 * 1024;
const maxUnpackedBytes = 200 * 1024 * 1024;
// Results may grow beyond the input size; allow 24 MiB of ZIP overhead while
// retaining the independent 200 MiB unpacked limit and all ZIP safety checks.
const maxResultZipBytes = 224 * 1024 * 1024;

/// Validates the central directory before archive inflation allocates memory.
void validateZip(
  List<int> bytes, {
  int maxCompressed = maxInputBytes,
  int maxUnpacked = maxUnpackedBytes,
}) {
  if (bytes.length > maxCompressed) throw const FormatException('压缩包超过大小限制');
  final data = ByteData.sublistView(Uint8List.fromList(bytes));
  int u16(int i) => data.getUint16(i, Endian.little);
  int u32(int i) => data.getUint32(i, Endian.little);
  var end = -1;
  for (var i = bytes.length - 22; i >= 0 && i >= bytes.length - 65557; i--) {
    if (u32(i) == 0x06054b50 && i + 22 + u16(i + 20) == bytes.length) {
      end = i;
      break;
    }
  }
  if (end < 0) throw const FormatException('无效 ZIP');
  if (u16(end + 4) != 0 || u16(end + 6) != 0 || u16(end + 8) != u16(end + 10)) {
    throw const FormatException('不支持分卷 ZIP');
  }
  final count = u16(end + 10),
      offset = u32(end + 16),
      centralSize = u32(end + 12);
  if (count == 65535 ||
      offset == 0xffffffff ||
      centralSize == 0xffffffff ||
      count > 10000 ||
      offset + centralSize > end) {
    throw const FormatException('ZIP 结构超限');
  }
  var cursor = offset, total = 0;
  final names = <String>{};
  for (var i = 0; i < count; i++) {
    if (cursor + 46 > end || u32(cursor) != 0x02014b50) {
      throw const FormatException('无效 ZIP 目录');
    }
    final compressed = u32(cursor + 20),
        size = u32(cursor + 24),
        nameLen = u16(cursor + 28),
        extraLen = u16(cursor + 30),
        commentLen = u16(cursor + 32);
    if (cursor + 46 + nameLen + extraLen + commentLen > end) {
      throw const FormatException('ZIP 目录截断');
    }
    final name = utf8
        .decode(
          bytes.sublist(cursor + 46, cursor + 46 + nameLen),
          allowMalformed: false,
        )
        .replaceAll('\\', '/');
    final parts = name.endsWith('/')
        ? name.substring(0, name.length - 1).split('/')
        : name.split('/');
    if (name.isEmpty ||
        name.length > 1024 ||
        name.startsWith('/') ||
        name.contains(':') ||
        name.contains('\x00') ||
        parts.any(
          (s) =>
              s.isEmpty ||
              s == '.' ||
              s == '..' ||
              s.length > 255 ||
              s.endsWith('.') ||
              s.endsWith(' ') ||
              RegExp(
                r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',
                caseSensitive: false,
              ).hasMatch(s),
        ) ||
        !names.add(name.toLowerCase())) {
      throw const FormatException('ZIP 路径不安全');
    }
    final unixType = (u32(cursor + 38) >> 16) & 0xf000;
    if (unixType == 0xa000 || (u16(cursor + 8) & 1) != 0) {
      throw const FormatException('不支持链接或加密 ZIP');
    }
    total += size;
    if (total > maxUnpacked ||
        size > maxUnpacked ||
        (size > 1024 * 1024 && size > compressed * 1000)) {
      throw const FormatException('ZIP 解压大小或压缩比超限');
    }
    cursor += 46 + nameLen + extraLen + commentLen;
  }
  if (cursor != offset + centralSize) throw const FormatException('ZIP 目录大小不符');
}

Archive decodeSafeZip(List<int> bytes, {int maxCompressed = maxInputBytes}) {
  validateZip(bytes, maxCompressed: maxCompressed);
  final data = ByteData.sublistView(Uint8List.fromList(bytes));
  int u16(int i) => data.getUint16(i, Endian.little);
  int u32(int i) => data.getUint32(i, Endian.little);
  var end = bytes.length - 22;
  while (end >= 0 &&
      (u32(end) != 0x06054b50 || end + 22 + u16(end + 20) != bytes.length)) {
    end--;
  }
  var cursor = u32(end + 16);
  final archive = Archive();
  for (var index = 0; index < u16(end + 10); index++) {
    final compressed = u32(cursor + 20),
        expected = u32(cursor + 24),
        method = u16(cursor + 10),
        local = u32(cursor + 42);
    final nameLength = u16(cursor + 28),
        extra = u16(cursor + 30),
        comment = u16(cursor + 32);
    final name = utf8
        .decode(bytes.sublist(cursor + 46, cursor + 46 + nameLength))
        .replaceAll('\\', '/');
    if (local + 30 > bytes.length ||
        u32(local) != 0x04034b50 ||
        u16(local + 8) != method ||
        (u16(local + 6) & 1) != 0) {
      throw const FormatException('ZIP 本地条目无效');
    }
    final offset = local + 30 + u16(local + 26) + u16(local + 28);
    if (offset + compressed > u32(end + 16)) {
      throw const FormatException('ZIP 数据越界');
    }
    final sink = _BoundedZipSink(expected);
    if (method == 0) {
      sink.add(bytes.sublist(offset, offset + compressed));
      sink.close();
    } else if (method == 8) {
      final decoder = ZLibDecoder(raw: true).startChunkedConversion(sink);
      for (var i = offset; i < offset + compressed; i += 1024) {
        decoder.add(bytes.sublist(i, (i + 1024).clamp(0, offset + compressed)));
      }
      decoder.close();
    } else {
      throw const FormatException('不支持该 ZIP 压缩方式');
    }
    final content = sink.bytes;
    if (content.length != expected || getCrc32(content) != u32(cursor + 16)) {
      throw const FormatException('ZIP 大小或校验不符');
    }
    archive.addFile(
      ArchiveFile(name, content.length, content)..isFile = !name.endsWith('/'),
    );
    cursor += 46 + nameLength + extra + comment;
  }
  return archive;
}

class _BoundedZipSink extends ByteConversionSinkBase {
  final int expected;
  final BytesBuilder _builder = BytesBuilder(copy: false);
  var _size = 0;
  _BoundedZipSink(this.expected);
  Uint8List get bytes => _builder.takeBytes();
  @override
  void add(List<int> chunk) {
    _size += chunk.length;
    if (_size > expected || _size > maxUnpackedBytes) {
      throw const FormatException('ZIP 实际解压大小超限');
    }
    _builder.add(chunk);
  }

  @override
  void close() {}
}

class FileStorage {
  final Directory root;
  FileStorage(this.root);
  Future<Directory> createTaskDirectory() async {
    await root.create(recursive: true);
    return root.createTemp('task-');
  }

  Future<List<String>> persistZip(
    List<int> bytes, {
    CancelToken? cancel,
  }) async {
    cancel?.throwIfCancelled();
    final entries = await Isolate.run(() => _unpackEntries(bytes));
    cancel?.throwIfCancelled();
    final dir = await createTaskDirectory();
    final paths = <String>[];
    try {
      for (final entry in entries) {
        cancel?.throwIfCancelled();
        final file = File(
          p.joinAll([dir.path, ...(entry['name'] as String).split('/')]),
        );
        await file.parent.create(recursive: true);
        await file.writeAsBytes(entry['bytes'] as List<int>, flush: true);
        paths.add(file.path);
      }
      if (paths.isEmpty) throw const FormatException('结果压缩包为空');
      return paths;
    } catch (_) {
      await dir.delete(recursive: true);
      rethrow;
    }
  }
}

List<Map<String, dynamic>> _unpackEntries(List<int> bytes) =>
    decodeSafeZip(bytes, maxCompressed: maxResultZipBytes).files
        .where((f) => f.isFile)
        .map((f) => {'name': f.name, 'bytes': f.content as List<int>})
        .toList();

class AppRepository {
  final Directory root;
  AppRepository(this.root);
  Future<void> _write(String name, Object data) async {
    await root.create(recursive: true);
    final pending = File(p.join(root.path, '$name.pending'));
    await pending.writeAsString(jsonEncode(data), flush: true);
    final file = File(p.join(root.path, name));
    if (await file.exists()) {
      final backup = File('${file.path}.backup');
      if (await backup.exists()) await backup.delete();
      await file.rename(backup.path);
    }
    await pending.rename(file.path);
  }

  Future<dynamic> _read(String name) async {
    for (final suffix in ['', '.pending', '.backup']) {
      final f = File(p.join(root.path, '$name$suffix'));
      if (await f.exists()) {
        try {
          return jsonDecode(await f.readAsString());
        } on FormatException {
          continue;
        }
      }
    }
    return null;
  }

  Future<AppSettings> loadSettings() async {
    final j = await _read('settings.json');
    return j is Map
        ? AppSettings.fromJson(Map<String, dynamic>.from(j))
        : const AppSettings();
  }

  Future<void> saveSettings(AppSettings settings) =>
      _write('settings.json', settings.toJson());
  Future<List<TaskRecord>> loadHistory() async {
    final j = await _read('history.json');
    return j is List
        ? j
              .map(
                (e) => TaskRecord.fromJson(Map<String, dynamic>.from(e as Map)),
              )
              .toList()
        : [];
  }

  Future<void> saveHistory(List<TaskRecord> records) =>
      _write('history.json', records.map((e) => e.toJson()).toList());
  Future<void> clearHistory() => saveHistory([]);
}
