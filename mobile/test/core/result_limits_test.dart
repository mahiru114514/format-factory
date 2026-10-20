import 'dart:collection';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:format_factory_mobile/core/core.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _mib = 1024 * 1024;
const _resultLimit = 224 * _mib;

void main() {
  late Directory temp;
  late FileStorage storage;
  late File source;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('factory-result-limits-');
    storage = FileStorage(Directory('${temp.path}/outputs'));
    source = await File('${temp.path}/original.jpg').writeAsBytes([1, 2, 3]);
  });
  tearDown(() => temp.delete(recursive: true));

  ConversionRequest request([String? path]) => ConversionRequest(
    inputPath: path ?? source.path,
    category: ConversionCategory.images,
    target: 'bmp',
  );

  RemoteConversionClient remote(
    Future<http.StreamedResponse> Function() result, {
    Future<void> Function()? onAck,
  }) {
    final client = MockClient.streaming((r, body) async {
      await body.drain<void>();
      if (r.method == 'POST') {
        return _json('{"id":"large-output","token":"job-secret"}', 202);
      }
      expect(r.headers['Authorization'], 'Bearer job-secret');
      if (r.method == 'DELETE') {
        await onAck?.call();
        return http.StreamedResponse(const Stream.empty(), 204);
      }
      if (r.url.path.endsWith('/result')) return result();
      return _json('{"state":"succeeded"}', 200);
    });
    final service = RemoteConversionClient(
      serverUrl: 'https://example.com',
      storage: storage,
      client: client,
    );
    addTearDown(service.close);
    return service;
  }

  test(
    '51 MiB stored result downloads, persists exact bytes, then acknowledges',
    () async {
      // Method 0 keeps the repeated data physically > 50 MiB in the ZIP.
      final payload = Uint8List(51 * _mib);
      final block = Uint8List.fromList(List.generate(4096, (i) => i % 251));
      for (var i = 0; i < payload.length; i += block.length) {
        payload.setRange(i, i + block.length, block);
      }
      final crc = getCrc32(payload);
      final zip = _storedZip(payload);
      expect(maxResultZipBytes, _resultLimit);
      expect(zip.length, greaterThan(maxInputBytes));
      expect(zip.length, lessThan(_resultLimit));
      expect(() => validateZip(zip), throwsFormatException);
      expect(() => decodeSafeZip(zip), throwsFormatException);
      var acknowledged = false;
      final service = remote(
        () async => http.StreamedResponse(
          Stream.value(zip),
          200,
          contentLength: zip.length,
        ),
        onAck: () async {
          final files = await storage.root
              .list(recursive: true)
              .where((entry) => entry is File)
              .cast<File>()
              .toList();
          expect(files, hasLength(1));
          expect(await files.single.length(), payload.length);
          // Verify all output bytes before acknowledgement, not just file existence.
          expect(getCrc32(await files.single.readAsBytes()), crc);
          acknowledged = true;
        },
      );
      final result = await service.convert(request(), consent: true);
      expect(result.viaRemote, true);
      expect(result.outputPaths.single, endsWith('result.bmp'));
      expect(acknowledged, true);
      expect(await source.readAsBytes(), [1, 2, 3]);
    },
  );

  test(
    'upload and local OOXML inputs still reject files above 50 MiB',
    () async {
      final oversized = File('${temp.path}/too-large.docx');
      final handle = await oversized.open(mode: FileMode.write);
      await handle.truncate(maxInputBytes + 1);
      await handle.close();
      var called = false;
      final client = MockClient((_) async {
        called = true;
        return http.Response('{}', 500);
      });
      final service = RemoteConversionClient(
        serverUrl: 'https://example.com',
        storage: storage,
        client: client,
      );
      addTearDown(service.close);
      await expectLater(
        service.convert(request(oversized.path), consent: true),
        throwsA(isA<LocalUnavailable>()),
      );
      expect(called, false);
      for (final extension in ['docx', 'xlsx']) {
        final path = '${temp.path}/too-large.$extension';
        if (path != oversized.path) await oversized.copy(path);
        await expectLater(
          LocalConversionService(storage).convert(
            ConversionRequest(
              inputPath: path,
              category: extension == 'docx'
                  ? ConversionCategory.documents
                  : ConversionCategory.tables,
              target: extension == 'docx' ? 'txt' : 'csv',
            ),
          ),
          throwsA(isA<LocalUnavailable>()),
        );
      }
    },
  );

  for (final advertised in [true, false]) {
    test(
      'result above 224 MiB is rejected with advertised length $advertised',
      () async {
        var acknowledged = false;
        final block = Uint8List(_mib);
        final service = remote(
          () async => http.StreamedResponse(
            Stream.fromIterable(List.filled(225, block)),
            200,
            contentLength: advertised ? _resultLimit + 1 : null,
          ),
          onAck: () async {
            acknowledged = true;
          },
        );
        await expectLater(
          service.convert(request(), consent: true),
          throwsFormatException,
        );
        expect(acknowledged, false);
        expect(await storage.root.exists(), false);
      },
    );
  }

  test(
    'persisted result independently rejects ZIP bytes above 224 MiB',
    () async {
      // Size is checked before indexing: no 225 MiB allocation is needed.
      await expectLater(
        storage.persistZip(_OversizedBytes(_resultLimit + 1)),
        throwsFormatException,
      );
      expect(await storage.root.exists(), false);
    },
  );

  for (final count in [1, 2]) {
    test(
      'result rejects expansion above 200 MiB across $count entries',
      () async {
        final archive = Archive();
        for (var i = 0; i < count; i++) {
          archive.addFile(ArchiveFile('result$i.bmp', 1, [65]));
        }
        final zip = Uint8List.fromList(ZipEncoder().encode(archive)!);
        final data = ByteData.sublistView(zip);
        var central = data.getUint32(zip.length - 6, Endian.little);
        for (var i = 0; i < count; i++) {
          // Each of two entries is below 200 MiB; only their sum is oversized.
          // Keep the declared ratio below 1000 so this checks expansion limits.
          data
            ..setUint32(central + 20, _mib, Endian.little)
            ..setUint32(
              central + 24,
              count == 1 ? maxUnpackedBytes + 1 : 101 * _mib,
              Endian.little,
            );
          central +=
              46 +
              data.getUint16(central + 28, Endian.little) +
              data.getUint16(central + 30, Endian.little) +
              data.getUint16(central + 32, Endian.little);
        }
        var acknowledged = false;
        final service = remote(
          () async => http.StreamedResponse(Stream.value(zip), 200),
          onAck: () async {
            acknowledged = true;
          },
        );
        await expectLater(
          service.convert(request(), consent: true),
          throwsA(
            isA<FormatException>().having(
              (error) => error.message,
              'message',
              contains('解压大小'),
            ),
          ),
        );
        expect(acknowledged, false);
        expect(await storage.root.exists(), false);
      },
    );
  }
}

http.StreamedResponse _json(String data, int status) =>
    http.StreamedResponse(Stream.value(utf8.encode(data)), status);

Uint8List _storedZip(Uint8List payload) {
  final name = utf8.encode('result.bmp');
  final centralOffset = 30 + name.length + payload.length;
  final centralSize = 46 + name.length;
  final bytes = Uint8List(centralOffset + centralSize + 22);
  final data = ByteData.sublistView(bytes);
  final crc = getCrc32(payload);
  data
    ..setUint32(0, 0x04034b50, Endian.little)
    ..setUint16(4, 20, Endian.little)
    ..setUint32(14, crc, Endian.little)
    ..setUint32(18, payload.length, Endian.little)
    ..setUint32(22, payload.length, Endian.little)
    ..setUint16(26, name.length, Endian.little);
  bytes.setRange(30, 30 + name.length, name);
  bytes.setRange(30 + name.length, centralOffset, payload);
  data
    ..setUint32(centralOffset, 0x02014b50, Endian.little)
    ..setUint16(centralOffset + 4, 20, Endian.little)
    ..setUint16(centralOffset + 6, 20, Endian.little)
    ..setUint32(centralOffset + 16, crc, Endian.little)
    ..setUint32(centralOffset + 20, payload.length, Endian.little)
    ..setUint32(centralOffset + 24, payload.length, Endian.little)
    ..setUint16(centralOffset + 28, name.length, Endian.little);
  bytes.setRange(centralOffset + 46, centralOffset + centralSize, name);
  final end = centralOffset + centralSize;
  data
    ..setUint32(end, 0x06054b50, Endian.little)
    ..setUint16(end + 8, 1, Endian.little)
    ..setUint16(end + 10, 1, Endian.little)
    ..setUint32(end + 12, centralSize, Endian.little)
    ..setUint32(end + 16, centralOffset, Endian.little);
  return bytes;
}

class _OversizedBytes extends ListBase<int> {
  @override
  final int length;
  _OversizedBytes(this.length);
  @override
  set length(int value) => throw UnsupportedError('read only');
  @override
  int operator [](int index) => throw StateError('must reject before reading');
  @override
  void operator []=(int index, int value) =>
      throw UnsupportedError('read only');
}
