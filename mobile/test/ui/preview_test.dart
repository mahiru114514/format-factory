import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:format_factory_mobile/platform/native_bridge.dart';
import 'package:format_factory_mobile/ui/app_controller.dart';
import 'package:format_factory_mobile/ui/factory_app.dart';

void main() {
  testWidgets('render actual mobile interface screenshots', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final font = FontLoader('NotoSansSC')
      ..addFont(rootBundle.load('assets/NotoSansSC.ttf'));
    await tester.runAsync(font.load);
    final icons = FontLoader('MaterialIcons')
      ..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf'));
    await tester.runAsync(icons.load);
    final root = (await tester.runAsync(
      () => Directory.systemTemp.createTemp('factory-preview-'),
    ))!;
    final c = AppController(root: root, bridge: NativeBridge());
    await tester.runAsync(c.load);
    final key = GlobalKey();
    await tester.pumpWidget(
      RepaintBoundary(
        key: key,
        child: FactoryApp(controller: c),
      ),
    );
    await tester.pumpAndSettle();
    final folder = Directory('../deliverables/mobile/previews');
    await tester.runAsync(() => folder.create(recursive: true));
    Future<void> shot(String name) async {
      await tester.pumpAndSettle();
      final boundary =
          key.currentContext!.findRenderObject() as RenderRepaintBoundary;
      await tester.runAsync(() async {
        final image = await boundary.toImage(pixelRatio: 2);
        final data = await image.toByteData(format: ui.ImageByteFormat.png);
        await File('${folder.path}/$name.png')
            .writeAsBytes(data!.buffer.asUint8List());
        image.dispose();
      });
    }

    await shot('01-convert');
    await tester.tap(find.text('文本').last);
    await shot('02-text');
    await tester.tap(find.text('任务').last);
    await shot('03-tasks');
    await tester.tap(find.text('设置').last);
    await shot('04-settings');
    c.theme = 'dark';
    c.notifyListeners();
    await shot('05-dark');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.runAsync(c.flush);
    c.dispose();
    await tester.runAsync(() => root.delete(recursive: true));
    expect(tester.takeException(), null);
  });
}
