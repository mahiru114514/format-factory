import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';
import 'package:gal/gal.dart';
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';
import 'package:image_cropper/image_cropper.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path/path.dart' as p;
import 'package:pdfx/pdfx.dart';
import 'package:receive_sharing_intent/receive_sharing_intent.dart';
import 'package:share_plus/share_plus.dart';

class PickedInput {
  final String name;
  final Stream<List<int>> Function() bytes;
  final Future<int?> Function() length;
  PickedInput(this.name, this.bytes, this.length);
}

class SharedInput {
  final String value;
  final bool isText;
  const SharedInput(this.value, {this.isText = false});
}

/// Android classifies EXTRA_STREAM by MIME, so a cached CSV/TXT path can carry
/// type `text`. Check the actual local file before interpreting that value.
Future<List<SharedInput>> mapSharedMedia(List<SharedMediaFile> files) async {
  final entries = <SharedInput>[];
  for (final file in files) {
    var localPath = file.path;
    final uri = Uri.tryParse(file.path);
    if (uri != null && uri.scheme == 'file') {
      try {
        localPath = File.fromUri(uri).path;
      } on ArgumentError {
        /* Keep the original value for the literal-text branch. */
      }
    }
    var isFile = false;
    try {
      isFile = await File(localPath).exists();
    } on FileSystemException {
      /* Literal text can contain invalid path characters. */
    }
    entries.add(
      SharedInput(
        isFile ? localPath : file.path,
        isText:
            !isFile &&
            (file.type == SharedMediaType.text ||
                file.type == SharedMediaType.url),
      ),
    );
  }
  return entries;
}

Future<void> acknowledgeAndroidShares(List<String> paths, List<String> texts) =>
    const MethodChannel(
      'receive_sharing_intent/messages',
    ).invokeMethod<void>('acknowledgeFiles', {'paths': paths, 'texts': texts});

class PdfPreview {
  final Uint8List bytes;
  final int pages;
  PdfPreview(this.bytes, this.pages);
}

/// Every native operation is injectable, while the production bridge uses OS UI.
class NativeBridge {
  Future<List<PickedInput>> pickFiles({
    bool photos = false,
    bool text = false,
  }) async {
    final files = await FilePicker.pickFiles(
      type: photos
          ? FileType.image
          : text
          ? FileType.custom
          : FileType.any,
      allowedExtensions: text ? ['txt', 'md', 'tex'] : null,
      compressionQuality: 0,
      darwinOptions: const DarwinOptions(
        assetRepresentationMode: DarwinAssetRepresentationMode.current,
        copyMedia: true,
      ),
    );
    return files
        .map((f) => PickedInput(f.name, f.readAsByteStream, f.length))
        .toList();
  }

  Future<PickedInput?> camera() async {
    final f = await ImagePicker().pickImage(source: ImageSource.camera);
    if (f == null) return null;
    return PickedInput(f.name, f.openRead, () async => f.length());
  }

  Future<String?> crop(String path) async => (await ImageCropper().cropImage(
    sourcePath: path,
    uiSettings: [
      AndroidUiSettings(toolbarTitle: '框选文字或单个公式', lockAspectRatio: false),
      IOSUiSettings(title: '框选文字或单个公式'),
    ],
  ))?.path;
  Future<String> recognize(String path) async {
    final r = TextRecognizer(script: TextRecognitionScript.chinese);
    try {
      return (await r.processImage(InputImage.fromFilePath(path))).text;
    } finally {
      await r.close();
    }
  }

  Future<PdfPreview> renderPdf(String path, int number) async {
    final doc = await PdfDocument.openFile(path);
    try {
      final page = await doc.getPage(number.clamp(1, doc.pagesCount));
      try {
        final ratio = (1600 / page.width).clamp(0.1, 2.0);
        final image = await page.render(
          width: page.width * ratio,
          height: page.height * ratio,
          format: PdfPageImageFormat.png,
        );
        if (image == null) throw const FormatException('这一页无法预览');
        return PdfPreview(image.bytes, doc.pagesCount);
      } finally {
        await page.close();
      }
    } finally {
      await doc.close();
    }
  }

  Future<void> copyText(String text) =>
      Clipboard.setData(ClipboardData(text: text));
  Future<String?> pasteText() async =>
      (await Clipboard.getData(Clipboard.kTextPlain))?.text;
  Future<bool> saveBytes(
    String name,
    Uint8List bytes, {
    String mimeType = 'application/octet-stream',
  }) async =>
      await FilePicker.saveFile(
        fileName: name,
        bytes: bytes,
        mimeType: mimeType,
      ) !=
      null;
  Future<void> share({String? text, String? path, required Rect origin}) async {
    await SharePlus.instance.share(
      ShareParams(
        text: text,
        files: path == null ? null : [XFile(path)],
        sharePositionOrigin: origin,
      ),
    );
  }

  Future<void> saveGallery(String path) async {
    if (!await Gal.hasAccess()) {
      if (!await Gal.requestAccess()) throw const FormatException('尚未允许保存到相册');
    }
    await Gal.putImage(path);
  }

  Future<List<SharedInput>> initialShares() async =>
      mapSharedMedia(await ReceiveSharingIntent.instance.getInitialMedia());
  Stream<List<SharedInput>> get shares =>
      ReceiveSharingIntent.instance.getMediaStream().asyncMap(mapSharedMedia);
  Future<void> acknowledge(List<String> paths, List<String> texts) async {
    if (Platform.isAndroid) {
      await acknowledgeAndroidShares(paths, texts);
      return;
    }
    if (Platform.isIOS) {
      await const MethodChannel('factory/shared_files')
          .invokeMethod('acknowledge', {'paths': paths, 'texts': texts});
    }
    await ReceiveSharingIntent.instance.reset();
  }

  String mime(String path) => switch (p.extension(path).toLowerCase()) {
    '.txt' => 'text/plain',
    '.csv' => 'text/csv',
    '.pdf' => 'application/pdf',
    '.png' => 'image/png',
    '.jpg' || '.jpeg' => 'image/jpeg',
    _ => 'application/octet-stream',
  };
}
