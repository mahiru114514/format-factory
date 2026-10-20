import 'dart:io';
void main() {
  print('temp: ${Directory.systemTemp.path}');
  for (final path in [Platform.environment['TEMP']!, '.tools/temp-probe']) {
    try {
      final d = Directory(path).createTempSync('dart-probe-');
      print('created ${d.path}');
      d.deleteSync();
    } catch (e) { print(e); }
  }
}
