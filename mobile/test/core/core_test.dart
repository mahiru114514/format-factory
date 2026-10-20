import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:archive/archive.dart';
import 'package:excel/excel.dart';
import 'package:image/image.dart' as im;
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:format_factory_mobile/core/core.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory temp;
  late FileStorage storage;
  setUp(() async {
    temp = await Directory.systemTemp.createTemp('factory-core-');
    storage = FileStorage(Directory('${temp.path}/outputs'));
  });
  tearDown(() async {
    await temp.delete(recursive: true);
  });
  Future<String> input(String name, List<int> data) async {
    final f = File('${temp.path}/$name');
    await f.writeAsBytes(data);
    return f.path;
  }

  test(
    'Chinese source name is retained and repeated outputs never overwrite',
    () async {
      final path = await input('原始 文档.txt', utf8.encode('原件'));
      final request = ConversionRequest(
        inputPath: path,
        category: ConversionCategory.documents,
        target: 'md',
      );
      final a = await LocalConversionService(storage).convert(request);
      final b = await LocalConversionService(storage).convert(request);
      expect(a.outputPaths.single, endsWith('原始 文档.md'));
      expect(a.outputPaths.single, isNot(b.outputPaths.single));
      expect(await File(path).readAsString(), '原件');
    },
  );

  test('readable LaTeX retains commands sharing left and right prefixes', () {
    expect(
      latexReadable(r'\leftarrow+\leftcustom{x}+\rightcustom{y}'),
      r'←+\leftcustom{x}+\rightcustom{y}',
    );
  });
  test(
    'plain Chinese text PDF embeds font and contains valid PDF structure',
    () async {
      final path = await input('内容.txt', utf8.encode('中文内容\n第二段 α'));
      final result = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: path,
          category: ConversionCategory.documents,
          target: 'pdf',
        ),
      );
      final bytes = await File(result.outputPaths.single).readAsBytes();
      expect(ascii.decode(bytes.take(8).toList()), startsWith('%PDF-'));
      final source = latin1.decode(bytes);
      expect(RegExp(r'/Type\s*/Catalog').hasMatch(source), true);
      expect(source, contains('/FontFile2'));
      expect(source, contains('%%EOF'));
    },
  );
  test(
    'UTF16 and GBK CSV decode Chinese but GB18030 four-byte stays explicit',
    () async {
      final utf16 = await input('utf16.csv', [
        255,
        254,
        ...'编号,名称\r\n001,中文'.codeUnits.expand((v) => [v & 255, v >> 8]),
      ]);
      final r = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: utf16,
          category: ConversionCategory.tables,
          target: 'xlsx',
        ),
      );
      expect(
        Excel.decodeBytes(await File(r.outputPaths.single).readAsBytes())
            .tables
            .values
            .first
            .rows[1][1]!
            .value,
        TextCellValue('中文'),
      );
      final gb = await input('gb.csv', [
        0xb1,
        0xe0,
        0xba,
        0xc5,
        44,
        0xc3,
        0xfb,
        0xb3,
        0xc6,
        13,
        10,
        48,
        48,
        49,
        44,
        0xd6,
        0xd0,
        0xce,
        0xc4,
      ]);
      final g = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: gb,
          category: ConversionCategory.tables,
          target: 'xlsx',
        ),
      );
      expect(
        Excel.decodeBytes(await File(g.outputPaths.single).readAsBytes())
            .tables
            .values
            .first
            .rows[1][1]!
            .value,
        TextCellValue('中文'),
      );
      final four = await input('four.csv', [0x81, 0x30, 0x81, 0x30]);
      await expectLater(
        LocalConversionService(storage).convert(
          ConversionRequest(
            inputPath: four,
            category: ConversionCategory.tables,
            target: 'xlsx',
          ),
        ),
        throwsA(isA<LocalUnavailable>()),
      );
    },
  );
  test(
    'XLSX multiple sheets retain cached formula and missing-cache source',
    () async {
      final x = Excel.createExcel();
      x['Sheet1'].appendRow([TextCellValue('001')]);
      x['中文'].appendRow([TextCellValue('数据')]);
      final a = ZipDecoder().decodeBytes(x.encode()!);
      final sheet = a.findFile('xl/worksheets/sheet1.xml')!;
      final xml = utf8
          .decode(sheet.content as List<int>)
          .replaceFirst(
            '</sheetData>',
            '<row r="2"><c r="A2"><f>1+2</f><v>3</v></c><c r="B2"><f>A1+1</f></c></row></sheetData>',
          );
      a.removeFile(sheet);
      final data = utf8.encode(xml);
      a.addFile(ArchiveFile(sheet.name, data.length, data));
      final path = await input('sheets.xlsx', ZipEncoder().encode(a)!);
      final result = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: path,
          category: ConversionCategory.tables,
          target: 'csv',
        ),
      );
      expect(result.outputPaths.length, 2);
      final csv = await File(result.outputPaths.first).readAsString();
      expect(csv, contains('3,=A1+1'));
      expect(result.warnings.join(), contains('缺少缓存'));
    },
  );
  test('colored amounts and escaped literals remain numbers while dates stay ISO', () async {
    final workbook = Excel.createExcel();
    workbook['Sheet1'].appendRow([TextCellValue('seed')]);
    final archive = ZipDecoder().decodeBytes(workbook.encode()!);
    final styles =
        '''<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="8">
    <numFmt numFmtId="164" formatCode="0.00;[Red]-0.00"/>
    <numFmt numFmtId="165" formatCode="[Blue][&gt;=0]0.00;[Red][&lt;0]-0.00"/>
    <numFmt numFmtId="166" formatCode="[\$USD-409]0.00"/>
    <numFmt numFmtId="167" formatCode="0.00&amp;quot; days&amp;quot;"/>
    <numFmt numFmtId="168" formatCode="0.00\\d"/>
    <numFmt numFmtId="169" formatCode="[\$-409]yyyy-mm-dd"/>
    <numFmt numFmtId="170" formatCode="[h]:mm:ss"/>
    <numFmt numFmtId="171" formatCode="0.00_i"/>
    </numFmts><cellXfs count="8">${List.generate(8, (i) => '<xf numFmtId="${164 + i}"/>').join()}</cellXfs></styleSheet>'''
            .replaceAll('&amp;quot;', '&quot;');
    final styleBytes = utf8.encode(styles);
    archive.addFile(
      ArchiveFile('xl/styles.xml', styleBytes.length, styleBytes),
    );
    final sheet =
        '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1">${['123.45', '-12.5', '64', '23', '34', '45292', '0.5', '56'].asMap().entries.map((e) => '<c r="${String.fromCharCode(65 + e.key)}1" s="${e.key}"><v>${e.value}</v></c>').join()}</row></sheetData></worksheet>''';
    final sheetBytes = utf8.encode(sheet);
    archive.addFile(
      ArchiveFile('xl/worksheets/sheet1.xml', sheetBytes.length, sheetBytes),
    );
    final path = await input('金额日期.xlsx', ZipEncoder().encode(archive)!);
    final result = await LocalConversionService(storage).convert(
      ConversionRequest(
        inputPath: path,
        category: ConversionCategory.tables,
        target: 'csv',
      ),
    );
    final csv = await File(result.outputPaths.single).readAsString();
    expect(
      csv,
      contains(
        '123.45,-12.5,64,23,34,2024-01-01T00:00:00Z,1899-12-30T12:00:00Z,56',
      ),
    );
  });

  test('ZIP with forged small uncompressed size is rejected', () async {
    final a = Archive()
      ..addFile(ArchiveFile('bomb.txt', 4096, List.filled(4096, 65)));
    final bytes = ZipEncoder().encode(a)!;
    for (var i = 0; i < bytes.length - 28; i++) {
      if (bytes[i] == 80 &&
          bytes[i + 1] == 75 &&
          bytes[i + 2] == 1 &&
          bytes[i + 3] == 2) {
        bytes[i + 24] = 1;
        bytes[i + 25] = 0;
        bytes[i + 26] = 0;
        bytes[i + 27] = 0;
      }
    }
    await expectLater(
      storage.persistZip(bytes),
      throwsA(isA<FormatException>()),
    );
  });
  test('invalid remote ZIP does not acknowledge, input stays intact', () async {
    var deleted = false;
    final path = await input('original.txt', utf8.encode('keep'));
    final a = Archive()..addFile(ArchiveFile('../escape', 1, [65]));
    final client = MockClient((r) async {
      if (r.method == 'POST') {
        return http.Response('{"id":"abc","token":"secret"}', 202);
      }
      if (r.method == 'DELETE') {
        deleted = true;
        return http.Response('', 204);
      }
      if (r.url.path.endsWith('/result')) {
        return http.Response.bytes(ZipEncoder().encode(a)!, 200);
      }
      return http.Response('{"state":"succeeded"}', 200);
    });
    await expectLater(
      RemoteConversionClient(
        serverUrl: 'https://example.com',
        storage: storage,
        client: client,
      ).convert(
        ConversionRequest(
          inputPath: path,
          category: ConversionCategory.text,
          target: 'txt',
        ),
        consent: true,
      ),
      throwsA(isA<FormatException>()),
    );
    expect(deleted, false);
    expect(await File(path).readAsString(), 'keep');
  });
  test(
    'cancel token prevents next remote poll and explicit cancellation deletes',
    () async {
      final token = CancelToken();
      final path = await input('source.txt', [65]);
      var polls = 0, deletes = 0;
      final client = MockClient((r) async {
        if (r.method == 'POST') {
          return http.Response('{"id":"abc","token":"one-job"}', 202);
        }
        if (r.method == 'DELETE') {
          deletes++;
          return http.Response('', 204);
        }
        polls++;
        token.cancel();
        return http.Response('{"state":"running"}', 200);
      });
      await expectLater(
        RemoteConversionClient(
          serverUrl: 'https://example.com',
          storage: storage,
          client: client,
          pollInterval: Duration.zero,
        ).convert(
          ConversionRequest(
            inputPath: path,
            category: ConversionCategory.text,
            target: 'txt',
          ),
          consent: true,
          cancel: token,
        ),
        throwsA(isA<ConversionCancelled>()),
      );
      expect(polls, 1);
      expect(deletes, 1);
    },
  );
  test('editable text protects edits, clamps selection and undoes Unicode', () {
    final e = EditableResult('原文 α');
    e.update('修改😀');
    expect(e.dirty, true);
    expect(e.accept('新结果'), false);
    expect(e.copyText(-8, 999), '修改😀');
    e.undo();
    expect(e.text, '原文 α');
    expect(e.accept('新结果'), true);
  });
  test('latex source remains exact and readable retains unknown commands', () {
    const s = r'\frac{α}{2}+\sqrt{x}+\unknown{保留}';
    expect(latexReadable(s), contains('(α)/(2)'));
    expect(latexReadable(s), contains(r'\unknown{保留}'));
  });
  test(
    'CSV to XLSX preserves identifiers, formulas as literal text and Chinese',
    () async {
      final path = await input('源.csv', [
        239,
        187,
        191,
        ...utf8.encode('编号,文字\r\n00123456789012345678,中文\r\n=SUM(A1),测试'),
      ]);
      final r = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: path,
          category: ConversionCategory.tables,
          target: 'xlsx',
        ),
      );
      final x = Excel.decodeBytes(
        await File(r.outputPaths.single).readAsBytes(),
      );
      final rows = x.tables.values.first.rows;
      expect(rows[1][0]!.value, TextCellValue('00123456789012345678'));
      expect(rows[2][0]!.value, TextCellValue('=SUM(A1)'));
      expect(await File(path).exists(), true);
      final back = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: r.outputPaths.single,
          category: ConversionCategory.tables,
          target: 'csv',
        ),
      );
      expect(
        await File(back.outputPaths.single).readAsString(),
        contains('00123456789012345678'),
      );
    },
  );
  test(
    'image converts real alpha PNG into white JPG without upscaling',
    () async {
      final source = im.Image(width: 8, height: 4, numChannels: 4);
      final path = await input('透明.png', im.encodePng(source));
      final r = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: path,
          category: ConversionCategory.images,
          target: 'jpg',
          options: {'max_size': 100},
        ),
      );
      final decoded = im.decodeJpg(
        await File(r.outputPaths.single).readAsBytes(),
      )!;
      expect(decoded.width, 8);
      expect(decoded.height, 4);
      expect(decoded.getPixel(0, 0).r, greaterThan(245));
    },
  );
  test(
    'EXIF orientation is baked before resize and TIFF output is real',
    () async {
      final source = im.Image(width: 8, height: 4);
      source.exif.imageIfd.orientation = 6;
      final path = await input('rotated.jpg', im.encodeJpg(source));
      final r = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: path,
          category: ConversionCategory.images,
          target: 'tiff',
          options: {'max_size': 4},
        ),
      );
      final decoded = im.decodeTiff(
        await File(r.outputPaths.single).readAsBytes(),
      )!;
      expect(decoded.width, 2);
      expect(decoded.height, 4);
    },
  );
  test(
    'DOCX generated from Chinese text reopens and extracts paragraphs',
    () async {
      final path = await input('中文.txt', utf8.encode('中文第一行\n第二行'));
      final r = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: path,
          category: ConversionCategory.documents,
          target: 'docx',
        ),
      );
      expect(
        ZipDecoder()
            .decodeBytes(await File(r.outputPaths.single).readAsBytes())
            .findFile('word/document.xml'),
        isNotNull,
      );
      final back = await LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: r.outputPaths.single,
          category: ConversionCategory.documents,
          target: 'txt',
        ),
      );
      expect(back.text, contains('中文第一行\n第二行'));
    },
  );
  test('unsafe ZIP paths rejected before writing', () async {
    final zip = Archive()..addFile(ArchiveFile('../escape.txt', 1, [65]));
    await expectLater(
      storage.persistZip(ZipEncoder().encode(zip)!),
      throwsA(isA<FormatException>()),
    );
    expect(File('${temp.path}/escape.txt').existsSync(), false);
  });
  test('history recovers running tasks as interrupted', () async {
    final repo = AppRepository(Directory('${temp.path}/state'));
    await repo.saveSettings(AppSettings(serverUrl: 'https://example.com'));
    await repo.saveHistory([
      TaskRecord(id: '1', inputPath: 'original', state: 'running'),
    ]);
    expect((await repo.loadSettings()).serverUrl, 'https://example.com');
    expect((await repo.loadHistory()).single.state, 'interrupted');
  });

  test(
    'task history retains retry settings and remote origin across recovery',
    () async {
      final repo = AppRepository(Directory('${temp.path}/retry-state'));
      final createdAt = DateTime.utc(2026, 10, 18);
      final record = TaskRecord(
        id: 'retry',
        inputPath: '原始文件.csv',
        state: 'running',
        category: ConversionCategory.tables,
        target: 'xlsx',
        options: const {'encoding': 'utf-16', 'delimiter': ';'},
        viaRemote: true,
        error: 'old failure',
        createdAt: createdAt,
      );
      await repo.saveHistory([record]);
      final restored = (await repo.loadHistory()).single;
      expect(restored.state, 'interrupted');
      expect(restored.category, ConversionCategory.tables);
      expect(restored.target, 'xlsx');
      expect(restored.options, {'encoding': 'utf-16', 'delimiter': ';'});
      expect(restored.viaRemote, true);
      expect(restored.createdAt, createdAt);
      final retried = restored.copyWith(
        state: 'queued',
        error: null,
        viaRemote: false,
        outputPaths: ['local.xlsx'],
        warnings: ['warning'],
      );
      expect(retried.state, 'queued');
      expect(retried.error, isNull);
      expect(retried.viaRemote, false);
      expect(retried.inputPath, restored.inputPath);
      expect(retried.id, restored.id);
      expect(retried.category, restored.category);
      expect(retried.target, restored.target);
      expect(retried.options, restored.options);
      expect(retried.outputPaths, ['local.xlsx']);
      expect(retried.warnings, ['warning']);
      expect(restored.error, 'old failure');
    },
  );

  test(
    'legacy task JSON has unknown conversion origin and remains readable',
    () {
      final record = TaskRecord.fromJson({
        'id': 'legacy',
        'inputPath': 'old.txt',
        'state': 'succeeded',
      });
      expect(record.category, isNull);
      expect(record.target, isNull);
      expect(record.options, isEmpty);
      expect(record.viaRemote, isNull);
      expect(TaskRecord.fromJson(record.toJson()).state, 'succeeded');
      final future = TaskRecord.fromJson({
        'id': 'future',
        'inputPath': 'new.bin',
        'state': 'failed',
        'category': 'future-category',
      });
      expect(future.category, isNull);
    },
  );

  test(
    'actual local persistence failure never acknowledges remote result',
    () async {
      final path = await input('保留原件.txt', utf8.encode('原件保留'));
      final blocked = File('${temp.path}/not-a-directory');
      await blocked.writeAsString('occupied');
      final brokenStorage = FileStorage(Directory(blocked.path));
      final archive = Archive()
        ..addFile(ArchiveFile('result.txt', 6, utf8.encode('结果')));
      var deleted = false;
      final client = MockClient((request) async {
        if (request.method == 'POST') {
          return http.Response(
            '{"id":"disk-failure","token":"only-this-job"}',
            202,
          );
        }
        if (request.method == 'DELETE') {
          deleted = true;
          return http.Response('', 204);
        }
        if (request.url.path.endsWith('/result')) {
          return http.Response.bytes(ZipEncoder().encode(archive)!, 200);
        }
        return http.Response('{"state":"succeeded"}', 200);
      });
      await expectLater(
        RemoteConversionClient(
          serverUrl: 'https://example.com',
          storage: brokenStorage,
          client: client,
        ).convert(
          ConversionRequest(
            inputPath: path,
            category: ConversionCategory.text,
            target: 'txt',
          ),
          consent: true,
        ),
        throwsA(isA<FileSystemException>()),
      );
      expect(deleted, false);
      expect(await File(path).readAsString(), '原件保留');
      expect(await blocked.readAsString(), 'occupied');
    },
  );
  test('small sparse XLSX cannot allocate over one million cells across sheets', () async {
    final book = Excel.createExcel();
    book['Sheet1'].appendRow([TextCellValue('first')]);
    book['Sheet2'].appendRow([TextCellValue('second')]);
    final archive = ZipDecoder().decodeBytes(book.encode()!);
    for (var sheetNumber = 1; sheetNumber <= 2; sheetNumber++) {
      final file = archive.findFile('xl/worksheets/sheet$sheetNumber.xml')!;
      final original = utf8.decode(file.content as List<int>);
      final rows = List.generate(
        31,
        (i) =>
            '<row r="${i + 1}"><c r="XFD${i + 1}" t="inlineStr"><is><t>x</t></is></c></row>',
      ).join();
      final updated = original.replaceFirst(
        RegExp(r'<sheetData(?:\s[^>]*)?>.*?</sheetData>', dotAll: true),
        '<sheetData>$rows</sheetData>',
      );
      expect(updated, contains('XFD31'), reason: original);
      final bytes = utf8.encode(updated);
      archive.addFile(ArchiveFile(file.name, bytes.length, bytes));
    }
    final inputPath = await input('稀疏表格.xlsx', ZipEncoder().encode(archive)!);
    expect(await File(inputPath).length(), lessThan(10000));
    await expectLater(
      LocalConversionService(storage).convert(
        ConversionRequest(
          inputPath: inputPath,
          category: ConversionCategory.tables,
          target: 'csv',
        ),
      ),
      throwsA(isA<LocalUnavailable>()),
    );
    expect(await File(inputPath).exists(), true);
  });

  test(
    'CSV preflight bounds aggregate cells before constructing workbook objects',
    () {
      final row = List.filled(1000, '').join(',');
      final large = List.filled(1001, row).join('\n');
      expect(() => validateCsvText(large), throwsA(isA<LocalUnavailable>()));
      expect(() => validateCsvText('a,b\n"中文,有逗号\n和换行",001'), returnsNormally);
      expect(
        () => validateCsvText('x' * (8 * 1024 * 1024 + 1)),
        throwsA(isA<LocalUnavailable>()),
      );
    },
  );

  test(
    'remote denied consent performs no network, URL rejects public HTTP',
    () async {
      var calls = 0;
      final client = MockClient((r) async {
        calls++;
        return http.Response('{}', 200);
      });
      final remote = RemoteConversionClient(
        serverUrl: 'https://example.com',
        storage: storage,
        client: client,
      );
      await expectLater(
        remote.convert(
          ConversionRequest(
            inputPath: 'absent',
            category: ConversionCategory.text,
            target: 'txt',
          ),
          consent: false,
        ),
        throwsA(isA<LocalUnavailable>()),
      );
      expect(calls, 0);
      expect(
        () => validateServerUri('http://example.com'),
        throwsFormatException,
      );
      expect(
        () => validateServerUri('https://user:secret@example.com'),
        throwsFormatException,
      );
      expect(validateServerUri('http://192.168.1.2:8765').host, '192.168.1.2');
    },
  );
  test(
    'remote authenticates job and persists ZIP before acknowledgement',
    () async {
      final path = await input('source.txt', utf8.encode('original'));
      final zip = Archive()
        ..addFile(ArchiveFile('media/result.txt', 6, utf8.encode('中文')));
      final bytes = ZipEncoder().encode(zip)!;
      final calls = <String>[];
      final client = MockClient((r) async {
        calls.add('${r.method} ${r.url.path}');
        if (r.method == 'POST') {
          return http.Response(
            jsonEncode({'id': 'abc', 'token': 'secret', 'state': 'queued'}),
            202,
          );
        }
        expect(r.headers['authorization'], 'Bearer secret');
        if (r.method == 'DELETE') {
          expect(
            Directory(storage.root.path)
                .listSync(recursive: true)
                .whereType<File>()
                .any((f) => f.path.endsWith('result.txt')),
            true,
          );
          return http.Response('', 204);
        }
        if (r.url.path.endsWith('/result')) {
          return http.Response.bytes(bytes, 200);
        }
        return http.Response(
          jsonEncode({'state': 'succeeded', 'warnings': []}),
          200,
        );
      });
      final r =
          await RemoteConversionClient(
            serverUrl: 'https://example.com',
            storage: storage,
            client: client,
            pollInterval: Duration.zero,
          ).convert(
            ConversionRequest(
              inputPath: path,
              category: ConversionCategory.text,
              target: 'txt',
            ),
            consent: true,
          );
      expect(r.viaRemote, true);
      expect(r.text, '中文');
      expect(calls.last, 'DELETE /v1/jobs/abc');
      expect(await File(path).readAsString(), 'original');
    },
  );
}
