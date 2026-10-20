import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:image/image.dart' as im;
import 'package:path_provider/path_provider.dart';
import 'package:format_factory_mobile/core/core.dart';
import 'package:format_factory_mobile/platform/native_bridge.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('real Android offline Chinese OCR, PDF renderer and WebP codec', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: Center(child: Text('正在验证手机原生功能')))));
    final font = FontLoader('NotoSansSC')..addFont(rootBundle.load('assets/NotoSansSC.ttf'));
    await font.load();
    final root = await (await getTemporaryDirectory()).createTemp('factory-native-');
    final bridge = NativeBridge();
    final storage = FileStorage(Directory('${root.path}/outputs'));
    try {
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder)..drawColor(Colors.white, BlendMode.src);
      final painter = TextPainter(
        text: const TextSpan(text: '中文识别测试\nHello 12345', style: TextStyle(fontFamily: 'NotoSansSC', fontSize: 60, color: Colors.black)),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: 1000);
      painter.paint(canvas, const Offset(40, 40));
      final picture = recorder.endRecording();
      final rendered = await picture.toImage(1100, 280);
      final bytes = (await rendered.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
      rendered.dispose();
      picture.dispose();
      final image = File('${root.path}/识别.png');
      await image.writeAsBytes(bytes, flush: true);
      final recognized = (await bridge.recognize(image.path)).replaceAll(RegExp(r'\s+'), '');
      expect(recognized, contains('中文识别测试'));
      expect(recognized.toLowerCase(), contains('hello12345'));
      final webp = await LocalConversionService(storage).convert(ConversionRequest(inputPath: image.path, category: ConversionCategory.images, target: 'webp', options: {'max_size': 600}));
      final webpBytes = await File(webp.outputPaths.single).readAsBytes();
      expect(ascii.decode(webpBytes.sublist(0, 4)), 'RIFF');
      expect(ascii.decode(webpBytes.sublist(8, 12)), 'WEBP');
      expect(im.decodeWebP(webpBytes)!.width, 600);
      final input = File('${root.path}/分页文本.txt');
      await input.writeAsString(List.generate(150, (i) => '第${i + 1}行，中文 PDF 页面渲染验证 ABC 123。').join('\n'));
      final pdf = await LocalConversionService(storage).convert(ConversionRequest(inputPath: input.path, category: ConversionCategory.documents, target: 'pdf'));
      final preview = await bridge.renderPdf(pdf.outputPaths.single, 2);
      expect(preview.pages, greaterThanOrEqualTo(2));
      expect(preview.bytes.take(4), [137, 80, 78, 71]);
      final report = File('${root.path}/native-result.json');
      await report.writeAsString(jsonEncode({'ocr': recognized, 'webp_width': im.decodeWebP(webpBytes)!.width, 'pdf_pages': preview.pages}));
      debugPrint('NATIVE_VERIFICATION ${await report.readAsString()}');
    } finally {
      await root.delete(recursive: true);
    }
  }, timeout: const Timeout(Duration(minutes: 5)));
}
