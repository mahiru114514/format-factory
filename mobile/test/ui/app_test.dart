import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:format_factory_mobile/core/core.dart';
import 'package:format_factory_mobile/platform/native_bridge.dart';
import 'package:format_factory_mobile/ui/app_controller.dart';
import 'package:format_factory_mobile/ui/factory_app.dart';
import 'package:path/path.dart' as p;
import 'package:receive_sharing_intent/receive_sharing_intent.dart';

class FakeBridge extends NativeBridge {
  String? copied;
  Uint8List? saved;
  List<String> acknowledged = [];
  @override
  Future<void> acknowledge(List<String> paths, List<String> texts) async {
    acknowledged.addAll([...paths, ...texts]);
  }

  @override
  Future<void> copyText(String text) async {
    copied = text;
  }

  @override
  Future<bool> saveBytes(
    String name,
    Uint8List bytes, {
    String mimeType = 'application/octet-stream',
  }) async {
    saved = bytes;
    return true;
  }
}

class FormulaController extends AppController {
  final String output;
  bool fail = false;
  FormulaController({
    required super.root,
    required super.bridge,
    required this.output,
  });
  @override
  Future<ConversionResult?> remote(
    ConversionRequest request,
    UploadConsent consent,
  ) async {
    if (!await consent(request, '测试服务的明确保留期限')) return null;
    if (fail) throw const LocalUnavailable('公式服务暂时不可用');
    return ConversionResult(
      outputPaths: [output],
      text: await File(output).readAsString(),
      warnings: const ['请核对上下标'],
      viaRemote: true,
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory root;
  late FakeBridge bridge;
  late AppController c;
  setUp(() async {
    root = await Directory.systemTemp.createTemp('factory-ui-');
    bridge = FakeBridge();
    c = AppController(root: root, bridge: bridge);
    await c.load();
  });
  tearDown(() async {
    await c.flush();
    c.dispose();
    await root.delete(recursive: true);
  });
  test('current edits, selection and saved bytes match exactly', () async {
    c.acceptResult('原文');
    c.editResult('中文\nα 😀');
    await c.copyResult();
    expect(bridge.copied, '中文\nα 😀');
    await c.copyResult(const TextSelection(baseOffset: 0, extentOffset: 2));
    expect(bridge.copied, '中文');
    await c.saveText();
    expect(utf8.decode(bridge.saved!), c.result.text);
    expect(c.acceptResult('替换'), false);
    expect(c.result.text, '中文\nα 😀');
  });
  test('Android acknowledgement sends only durable paths and literal texts without reset', () async {
    const channel = MethodChannel('receive_sharing_intent/messages');
    final calls = <MethodCall>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          return null;
        });
    try {
      await acknowledgeAndroidShares(
        ['/app/cache/factory_shared/share-id/报告.csv'],
        ['已保存文字'],
      );
      expect(calls.map((call) => call.method), ['acknowledgeFiles']);
      expect(calls.single.arguments, {
        'paths': ['/app/cache/factory_shared/share-id/报告.csv'],
        'texts': ['已保存文字'],
      });
    } finally {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
    }
  });
  test('real local csv conversion and durable history recovery', () async {
    final f = File('${root.path}/输入.csv');
    await f.writeAsString('姓名,分数\n小明,98');
    final imported = await c.importFile(f.path);
    c.inputs.add(imported);
    await c.runBatch(
      category: ConversionCategory.tables,
      target: 'xlsx',
      options: {},
      forceRemote: false,
      consent: (_, _) async => false,
    );
    expect(c.history.single.state, 'succeeded');
    expect(await File(c.history.single.outputPaths.single).exists(), true);
    await c.flush();
    final restored = AppController(root: root, bridge: bridge);
    await restored.load();
    expect(restored.history.single.state, 'succeeded');
    restored.dispose();
  });
  test('denied upload retains input and makes no remote conversion', () async {
    final f = File('${root.path}/输入.pdf');
    await f.writeAsString('source');
    c.inputs.add(await c.importFile(f.path));
    c.serverUrl = 'https://example.invalid';
    await c.runBatch(
      category: ConversionCategory.documents,
      target: 'docx',
      options: {},
      forceRemote: true,
      consent: (_, _) async => false,
    );
    expect(c.history.single.state, 'cancelled');
    expect(await File(c.inputs.single).exists(), true);
  });
  testWidgets('four tabs, empty input validation, narrow large text keyboard', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 720);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      FactoryApp(controller: c, textScaler: TextScaler.linear(1.5)),
    );
    await tester.scrollUntilVisible(find.text('开始转换'), 250);
    await tester.tap(find.text('开始转换'));
    await tester.pump();
    expect(find.text('请先选择文件'), findsOneWidget);
    for (final label in ['文本', '任务', '设置', '转换']) {
      await tester.tap(find.text(label).last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), null);
    }
    await tester.tap(find.text('文本').last);
    await tester.pumpAndSettle();
    tester.view.viewInsets = const FakeViewPadding(bottom: 260);
    await tester.pump();
    expect(tester.takeException(), null);
    tester.view.resetViewInsets();
  });
  test(
    'unconfigured server fails clearly and does not delete source',
    () async {
      final f = File('${root.path}/原文.docx');
      await f.writeAsString('original');
      c.inputs.add(await c.importFile(f.path));
      await c.runBatch(
        category: ConversionCategory.documents,
        target: 'pdf',
        options: {},
        forceRemote: true,
        consent: (_, _) async =>
            throw StateError('must not ask consent without a server'),
      );
      expect(c.history.single.error, contains('尚未配置'));
      expect(await File(c.inputs.single).exists(), true);
    },
  );
  test('interrupted task and independent edited draft recover', () async {
    c.history.add(
      const TaskRecord(id: 'recovery', inputPath: 'input', state: 'running'),
    );
    c.changeSource('新原文');
    c.acceptResult('识别原文');
    c.editResult('我的修改');
    await c.flush();
    final recovered = AppController(root: root, bridge: bridge);
    await recovered.load();
    expect(recovered.history.single.state, 'interrupted');
    expect(recovered.source, '新原文');
    expect(recovered.result.text, '我的修改');
    expect(recovered.result.dirty, true);
    recovered.dispose();
  });
  test(
    'shared text is durably imported and duplicate callbacks do not copy twice',
    () async {
      const entries = [SharedInput('分享的中文', isText: true)];
      await c.importShares(entries);
      c.changeSource('期间手动修改的原文');
      c.acceptResult('保留的校对原文');
      c.editResult('保留的校对编辑');
      await c.importShares(entries);
      expect(c.inputs.length, 1);
      expect(c.source, '分享的中文');
      expect(c.result.text, '保留的校对编辑');
      expect(await File(c.inputs.single).readAsString(), '分享的中文');
      expect(bridge.acknowledged, ['分享的中文', '分享的中文']);
      final recovered = AppController(root: root, bridge: bridge);
      await recovered.load();
      await recovered.importShares(entries);
      expect(recovered.inputs.length, 1);
      recovered.dispose();
    },
  );
  test(
    'native text MIME file shares preserve real bytes and original names',
    () async {
      final bytes = <int>[0xff, 0xfe, 0x4c, 0x00, 0x2c, 0x00, 0x31, 0x00];
      for (final extension in ['csv', 'txt', 'md']) {
        final file = File('${root.path}/中文报告.$extension');
        await file.writeAsBytes(bytes);
        final entries = await mapSharedMedia([
          SharedMediaFile(
            path: file.path,
            type: SharedMediaType.text,
            mimeType: extension == 'csv' ? 'text/csv' : 'text/plain',
          ),
        ]);
        expect(entries.single.isText, false);
        await c.importShares(entries);
        expect(p.basename(c.inputs.last), '中文报告.$extension');
        expect(await File(c.inputs.last).readAsBytes(), bytes);
      }
      expect(c.source, isEmpty);
      final missingPath = '${root.path}/这只是文字而非文件.txt';
      final literal = await mapSharedMedia([
        SharedMediaFile(
          path: missingPath,
          type: SharedMediaType.text,
          mimeType: 'text/plain',
        ),
      ]);
      expect(literal.single.isText, true);
      await c.importShares(literal);
      expect(c.source, missingPath);
      expect(await File(c.inputs.last).readAsString(), missingPath);
    },
  );
  test('same native cache path imports changed content while repeated callbacks stay idempotent', () async {
    final file = File('${root.path}/同名报告.csv');
    Future<void> send() async => c.importShares(
      await mapSharedMedia([
        SharedMediaFile(
          path: file.path,
          type: SharedMediaType.text,
          mimeType: 'text/csv',
        ),
      ]),
    );
    await file.writeAsString('A,100');
    await send();
    await send();
    expect(c.inputs.length, 1);
    await file.writeAsString('B,200');
    await send();
    await send();
    expect(c.inputs.length, 2);
    expect(await File(c.inputs[0]).readAsString(), 'A,100');
    expect(await File(c.inputs[1]).readAsString(), 'B,200');
    await c.flush();
    final restored = AppController(root: root, bridge: bridge);
    await restored.load();
    await restored.importShares(
      await mapSharedMedia([
        SharedMediaFile(
          path: file.path,
          type: SharedMediaType.text,
          mimeType: 'text/csv',
        ),
      ]),
    );
    expect(restored.inputs.length, 2);
    restored.dispose();
  });
  test('queued duplicate native snapshot stays idempotent after acknowledgement removes cache', () async {
    final cache = File('${root.path}/native-cache.csv');
    await cache.writeAsString('姓名,分数\n小明,98');
    final snapshot = [SharedInput(cache.path)];
    await c.importShares(snapshot);
    final imported = c.inputs.single;
    await cache.delete();
    await c.importShares(snapshot);
    expect(c.inputs, [imported]);
    expect(c.status, isEmpty);
    expect(await File(imported).readAsString(), '姓名,分数\n小明,98');
    final restored = AppController(root: root, bridge: bridge);
    await restored.load();
    await restored.importShares(snapshot);
    expect(restored.inputs, [imported]);
    expect(restored.status, isEmpty);
    restored.dispose();
  });
  testWidgets('dirty overwrite cancellation preserves source and edits', (
    tester,
  ) async {
    c.source = '新原文';
    c.acceptResult('旧原文');
    c.editResult('已校对内容');
    await tester.runAsync(c.flush);
    await tester.pumpWidget(FactoryApp(controller: c));
    await tester.tap(find.text('文本').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('原文 / LaTeX 原样保留'));
    await tester.tap(find.text('原文 / LaTeX 原样保留'));
    await tester.pumpAndSettle();
    expect(find.text('保留你的编辑？'), findsOneWidget);
    await tester.tap(find.text('取消'));
    await tester.pumpAndSettle();
    expect(c.result.text, '已校对内容');
    expect(c.source, '新原文');
  });
  test(
    'downloaded formula remains in history when dirty replacement is declined',
    () async {
      final input = File('${root.path}/当前页.png');
      await input.writeAsBytes([1, 2, 3]);
      final output = File('${root.path}/公式结果.txt');
      await output.writeAsString(r'\frac{a}{b}');
      c.dispose();
      c = FormulaController(root: root, bridge: bridge, output: output.path);
      await c.load();
      c.acceptResult('旧识别');
      c.editResult('用户校对内容');
      final converted = await c.runFormula(
        input.path,
        consent: (_, _) async => true,
      );
      expect(converted!.text, r'\frac{a}{b}');
      expect(c.acceptResult(converted.text!), false);
      expect(c.result.text, '用户校对内容');
      final record = c.history.single;
      expect(record.state, 'succeeded');
      expect(record.category, ConversionCategory.text);
      expect(record.target, 'txt');
      expect(record.options['method'], 'formula');
      expect(record.viaRemote, true);
      expect(record.outputPaths, [output.path]);
      expect(record.warnings, ['请核对上下标']);
      final restored = AppController(root: root, bridge: bridge);
      await restored.load();
      expect(restored.history.single.outputPaths, [output.path]);
      expect(
        await File(restored.history.single.outputPaths.single).readAsString(),
        converted.text,
      );
      restored.dispose();
    },
  );
  test(
    'formula failure can retry and denied upload records cancellation',
    () async {
      final input = File('${root.path}/裁剪公式.png');
      await input.writeAsBytes([1]);
      final output = File('${root.path}/公式.txt');
      await output.writeAsString('x²');
      c.dispose();
      final formula = FormulaController(
        root: root,
        bridge: bridge,
        output: output.path,
      );
      c = formula;
      await c.load();
      formula.fail = true;
      expect(
        await c.runFormula(input.path, consent: (_, _) async => true),
        null,
      );
      final failed = c.history.single;
      expect(failed.state, 'failed');
      expect(failed.error, contains('暂时不可用'));
      formula.fail = false;
      await c.runBatch(
        category: failed.category!,
        target: failed.target!,
        options: Map.of(failed.options)..remove('_force_remote'),
        forceRemote: true,
        consent: (_, _) async => true,
        files: [failed.inputPath],
      );
      expect(c.history.first.state, 'succeeded');
      expect(
        await c.runFormula(input.path, consent: (_, _) async => false),
        null,
      );
      expect(c.history.first.state, 'cancelled');
      expect(await input.exists(), true);
    },
  );
}
