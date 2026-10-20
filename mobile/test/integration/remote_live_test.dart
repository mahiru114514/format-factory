import 'dart:convert';
import 'dart:io';
import 'package:csv/csv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:format_factory_mobile/core/core.dart';

class NetworkTestBinding extends AutomatedTestWidgetsFlutterBinding {
  @override
  bool get overrideHttpClient => false;
}

void main() {
  NetworkTestBinding();
  final server = Platform.environment['FACTORY_TEST_SERVER'];
  test('live service converts Chinese CSV, client persists and acknowledges', () async {
    final directory = await Directory.systemTemp.createTemp('factory-live-');
    final input = File('${directory.path}/中文编号.csv');
    await input.writeAsString('姓名,编号\r\n张三,001234567890123456789\r\n', encoding: utf8);
    final client = RemoteConversionClient(serverUrl: server!, storage: FileStorage(Directory('${directory.path}/outputs')));
    try {
      final capabilities = await client.capabilities(consent: true);
      expect(capabilities['result_format'], 'zip');
      expect(capabilities['max_upload_bytes'], 50 * 1024 * 1024);
      final result = await client.convert(ConversionRequest(inputPath: input.path, category: ConversionCategory.tables, target: 'xlsx'), consent: true);
      expect(result.viaRemote, isTrue);
      // Exercise the app's OOXML reader against the server's openpyxl writer.
      final back = await LocalConversionService(FileStorage(Directory('${directory.path}/roundtrip'))).convert(
        ConversionRequest(inputPath: result.outputPaths.single, category: ConversionCategory.tables, target: 'csv'),
      );
      final csv = (await File(back.outputPaths.single).readAsString()).replaceFirst('\ufeff', '');
      final rows = const CsvToListConverter(shouldParseNumbers: false).convert(csv);
      expect(rows[1][0], '张三');
      expect(rows[1][1], '001234567890123456789');
      expect(await input.readAsString(), contains('001234567890123456789'));
      expect(result.warnings.where((w) => w.contains('删除失败')), isEmpty);
    } finally {
      client.close();
      await directory.delete(recursive: true);
    }
  }, skip: server == null ? 'Run through scripts/mobile/live_integration.py against its isolated local service.' : false);
  test('live Linux service renders Chinese Word to PDF and restores editable Word', () async {
    final directory = await Directory.systemTemp.createTemp('factory-pdf-live-');
    final storage = FileStorage(Directory('${directory.path}/outputs'));
    final input = File('${directory.path}/中文文档.txt');
    await input.writeAsString('格式转换工厂\n中文校对示例 ABC 123\n第二段文字保留。');
    final local = LocalConversionService(storage);
    final remote = RemoteConversionClient(serverUrl: server!, storage: storage);
    try {
      final word = await local.convert(ConversionRequest(inputPath: input.path, category: ConversionCategory.documents, target: 'docx'));
      final pdf = await remote.convert(ConversionRequest(inputPath: word.outputPaths.single, category: ConversionCategory.documents, target: 'pdf'), consent: true);
      expect(utf8.decode((await File(pdf.outputPaths.single).readAsBytes()).take(5).toList()), '%PDF-');
      final restored = await remote.convert(ConversionRequest(inputPath: pdf.outputPaths.single, category: ConversionCategory.documents, target: 'docx'), consent: true);
      final text = await local.convert(ConversionRequest(inputPath: restored.outputPaths.single, category: ConversionCategory.documents, target: 'txt'));
      expect(text.text!.replaceAll(RegExp(r'\s+'), ''), contains('中文校对示例ABC123'));
      expect(text.text!.replaceAll(RegExp(r'\s+'), ''), contains('第二段文字保留。'));
    } finally {
      remote.close();
      await directory.delete(recursive: true);
    }
  }, skip: server == null || Platform.environment['FACTORY_TEST_PDF'] != 'true' ? 'Requires verified Linux LibreOffice test service.' : false);
}
