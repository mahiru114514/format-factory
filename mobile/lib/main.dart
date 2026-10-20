import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'platform/native_bridge.dart';
import 'ui/app_controller.dart';
import 'ui/factory_app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final directory = await getApplicationDocumentsDirectory();
  final controller = AppController(
    root: Directory(p.join(directory.path, '格式工厂')),
    bridge: NativeBridge(),
  );
  await controller.load();
  runApp(FactoryApp(controller: controller));
  await controller.startShares();
}
