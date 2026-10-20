import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:archive/archive.dart';
import 'package:csv/csv.dart';
import 'package:enough_convert/enough_convert.dart';
import 'package:excel/excel.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_image_compress/flutter_image_compress.dart';
import 'package:image/image.dart' as img;
import 'package:path/path.dart' as p;
import 'package:pdf/widgets.dart' as pw;
import 'package:xml/xml.dart';

import 'models.dart';
import 'storage.dart';

const _maxTableCells = 1000000;
const _maxCsvBytes = 8 * 1024 * 1024;

/// Scans CSV structure without allocating a row or cell object for every field.
void validateCsvText(String text, {String delimiter = ','}) {
  if (text.length > _maxCsvBytes) {
    throw const LocalUnavailable('本机 CSV 文本限 8 MiB，请使用服务端。');
  }
  if (delimiter.runes.length != 1 || delimiter == '\r' || delimiter == '\n') {
    throw const FormatException('分隔符必须为一个字符');
  }
  var rows = 1, columns = 1, cells = 1, fieldSize = 0;
  var quoted = false, fieldStart = true;
  void check() {
    if (rows > 100000 || columns > 16384 || cells > _maxTableCells) {
      throw const LocalUnavailable('CSV 超过本机行列或 100 万单元格限制。');
    }
    if (fieldSize > 1024 * 1024) {
      throw const LocalUnavailable('CSV 单元格文本超过本机 1 MiB 限制。');
    }
  }

  for (var i = 0; i < text.length; i++) {
    final unit = text.codeUnitAt(i);
    if (unit == 0) {
      throw const FormatException('CSV 含二进制空字符');
    }
    if (quoted) {
      if (unit == 34) {
        if (i + 1 < text.length && text.codeUnitAt(i + 1) == 34) {
          i++;
          fieldSize++;
        } else {
          quoted = false;
        }
      } else {
        fieldSize++;
      }
    } else if (unit == 34 && fieldStart) {
      quoted = true;
      fieldStart = false;
    } else if (text.startsWith(delimiter, i)) {
      columns++;
      cells++;
      fieldSize = 0;
      fieldStart = true;
      i += delimiter.length - 1;
    } else if (unit == 10 || unit == 13) {
      if (unit == 13 && i + 1 < text.length && text.codeUnitAt(i + 1) == 10) {
        i++;
      }
      rows++;
      cells++;
      columns = 1;
      fieldSize = 0;
      fieldStart = true;
    } else {
      fieldStart = false;
      fieldSize++;
    }
    check();
  }
  if (quoted) {
    throw const FormatException('CSV 引号未闭合');
  }
}

class LocalConversionService {
  final FileStorage storage;
  LocalConversionService(this.storage);
  Future<ConversionResult> convert(
    ConversionRequest request, {
    CancelToken? cancel,
  }) async {
    cancel?.throwIfCancelled();
    final input = File(request.inputPath);
    if (await input.length() > maxInputBytes) {
      throw const LocalUnavailable('文件超过本机 50 MiB 限制。');
    }
    var bytes = await input.readAsBytes();
    if (bytes.length > maxInputBytes) {
      throw const LocalUnavailable('文件超过本机 50 MiB 限制。');
    }
    final ext = p
        .extension(request.inputPath)
        .toLowerCase()
        .replaceFirst('.', '');
    final target = request.target.toLowerCase();
    var nativeDecoded = false;
    if (request.category == ConversionCategory.images &&
        ['heic', 'heif'].contains(ext)) {
      _validateHeicSize(bytes);
      try {
        final value = await FlutterImageCompress.compressWithList(
          bytes,
          minWidth: 20000,
          minHeight: 20000,
          format: CompressFormat.png,
          keepExif: false,
        );
        if (!_magic(value, 'png')) throw const LocalUnavailable('系统未能解码 HEIC。');
        bytes = value;
        nativeDecoded = true;
      } on LocalUnavailable {
        rethrow;
      } catch (_) {
        throw const LocalUnavailable('当前设备不支持本机 HEIC 解码，请选择同意后使用服务端。');
      }
    }
    ByteData? font;
    if (request.category == ConversionCategory.documents &&
        target == 'pdf' &&
        ['txt', 'md'].contains(ext)) {
      font = await rootBundle.load('assets/NotoSansSC.ttf');
    }
    final nativeTarget =
        request.category == ConversionCategory.images &&
        ['webp', 'heic'].contains(target);
    final payload = <String, dynamic>{
      'bytes': bytes,
      'ext': nativeDecoded ? 'png' : ext,
      'target': nativeTarget ? 'png' : target,
      'category': request.category.name,
      'options': request.options,
      'font': font?.buffer.asUint8List(font.offsetInBytes, font.lengthInBytes),
    };
    final work = await compute(_convertPure, payload);
    cancel?.throwIfCancelled();
    final outputs = work['outputs'] as List<Map<String, dynamic>>;
    final warnings = List<String>.from(work['warnings'] as List);
    if (nativeDecoded) warnings.add('HEIC 经系统解码，元数据已移除。');
    if (nativeTarget) {
      if (request.options['keep_metadata'] == true) {
        warnings.add('系统 WebP/HEIC 编码不保留原始元数据。');
      }
      final png = outputs.single['bytes'] as Uint8List;
      final size = img.PngDecoder().startDecode(png)!;
      try {
        final encoded = await FlutterImageCompress.compressWithList(
          png,
          minWidth: size.width,
          minHeight: size.height,
          quality: ((request.options['quality'] as num?)?.toInt() ?? 90).clamp(
            1,
            100,
          ),
          format: target == 'webp' ? CompressFormat.webp : CompressFormat.heic,
          keepExif: false,
        );
        if (!_magic(encoded, target)) {
          throw const LocalUnavailable('设备编码器未返回请求的图片格式。');
        }
        outputs.single['bytes'] = encoded;
        outputs.single['name'] = 'result.$target';
      } on LocalUnavailable {
        rethrow;
      } catch (_) {
        throw LocalUnavailable('当前设备不支持本机 $target 编码，请选择同意后使用服务端。');
      }
    }
    cancel?.throwIfCancelled();
    final dir = await storage.createTaskDirectory();
    final paths = <String>[];
    try {
      final sourceStem = p.basenameWithoutExtension(request.inputPath);
      for (final output in outputs) {
        cancel?.throwIfCancelled();
        final generatedName = output['name'] as String;
        final name = generatedName.startsWith('result.')
            ? '$sourceStem${p.extension(generatedName)}'
            : '${sourceStem}_$generatedName';
        final f = File(p.join(dir.path, name));
        await f.writeAsBytes(output['bytes'] as List<int>, flush: true);
        paths.add(f.path);
      }
    } catch (_) {
      await dir.delete(recursive: true);
      rethrow;
    }
    return ConversionResult(
      outputPaths: paths,
      warnings: warnings,
      text: work['text'] as String?,
    );
  }
}

void _validateHeicSize(Uint8List bytes) {
  // HEIF image spatial extents box contains full image dimensions.
  final data = ByteData.sublistView(bytes);
  var found = false;
  for (var i = 4; i + 16 <= bytes.length; i++) {
    if (bytes[i] == 105 &&
        bytes[i + 1] == 115 &&
        bytes[i + 2] == 112 &&
        bytes[i + 3] == 101) {
      final width = data.getUint32(i + 8), height = data.getUint32(i + 12);
      _checkPixels(width, height);
      found = true;
    }
  }
  if (!found) throw const LocalUnavailable('无法安全读取 HEIC 尺寸，请使用服务端。');
}

void _checkPixels(int width, int height) {
  if (width <= 0 ||
      height <= 0 ||
      width > 20000 ||
      height > 20000 ||
      width * height > 40000000) {
    throw const LocalUnavailable('图片尺寸超过本机安全限制（4000 万像素）。');
  }
}

bool _magic(List<int> b, String format) {
  if (b.length < 12) return false;
  switch (format) {
    case 'png':
      return b[0] == 137 && b[1] == 80 && b[2] == 78 && b[3] == 71;
    case 'jpg':
      return b[0] == 255 && b[1] == 216 && b[2] == 255;
    case 'bmp':
      return b[0] == 66 && b[1] == 77;
    case 'tiff':
      return (b[0] == 73 && b[1] == 73 && b[2] == 42) ||
          (b[0] == 77 && b[1] == 77 && b[3] == 42);
    case 'webp':
      return ascii.decode(b.sublist(0, 4), allowInvalid: true) == 'RIFF' &&
          ascii.decode(b.sublist(8, 12), allowInvalid: true) == 'WEBP';
    case 'heic':
      return ascii.decode(b.sublist(4, 8), allowInvalid: true) == 'ftyp' &&
          [
            'heic',
            'heix',
            'hevc',
            'hevx',
            'mif1',
          ].contains(ascii.decode(b.sublist(8, 12), allowInvalid: true));
    default:
      return false;
  }
}

Future<Map<String, dynamic>> _convertPure(Map<String, dynamic> args) async {
  final bytes = args['bytes'] as Uint8List,
      ext = args['ext'] as String,
      target = args['target'] as String,
      options = args['options'] as Map<String, dynamic>;
  final warnings = <String>[];
  final outputs = <Map<String, dynamic>>[];
  String? text;
  void add(String name, List<int> data) =>
      outputs.add({'name': name, 'bytes': Uint8List.fromList(data)});
  switch (args['category']) {
    case 'images':
      final decoder = img.findDecoderForData(bytes);
      final info = decoder?.startDecode(bytes);
      if (info == null) throw const LocalUnavailable('本机无法解码该图片。');
      _checkPixels(info.width, info.height);
      var image = decoder!.decodeFrame(0);
      if (image == null) throw const LocalUnavailable('图片解码失败。');
      image = img.bakeOrientation(image);
      final maxSize = (options['max_size'] as num?)?.toInt() ?? 0;
      if (maxSize < 0 || maxSize > 20000) {
        throw const FormatException('缩放尺寸应为 0–20000');
      }
      if (maxSize > 0 && math.max(image.width, image.height) > maxSize) {
        final scale = maxSize / math.max(image.width, image.height);
        image = img.copyResize(
          image,
          width: math.max(1, (image.width * scale).round()),
          height: math.max(1, (image.height * scale).round()),
        );
      }
      if (info.numFrames > 1) warnings.add('本机输出仅保留第一帧，动画或多页图片请使用服务端。');
      final keep = options['keep_metadata'] == true;
      if (!keep) {
        image.exif = img.ExifData();
        image.iccProfile = null;
        image.textData?.clear();
      } else {
        warnings.add('本机仅尽力保留所支持的元数据；目标格式可能不支持原始字段。');
      }
      final quality = ((options['quality'] as num?)?.toInt() ?? 90).clamp(
        1,
        100,
      );
      List<int> encoded;
      switch (target) {
        case 'jpg':
          final white = img.Image(
            width: image.width,
            height: image.height,
            numChannels: 3,
          );
          img.fill(white, color: img.ColorRgb8(255, 255, 255));
          img.compositeImage(white, image);
          if (keep) white.exif = image.exif;
          encoded = img.encodeJpg(white, quality: quality);
        case 'png':
          encoded = img.encodePng(image);
        case 'bmp':
          encoded = img.encodeBmp(image);
        case 'tiff':
          encoded = img.encodeTiff(image);
        default:
          throw LocalUnavailable('本机不支持输出 $target。');
      }
      if (!_magic(encoded, target)) throw const LocalUnavailable('图片编码结果无效。');
      add('result.$target', encoded);
    case 'tables':
      final encoding = options['encoding'] as String? ?? 'auto';
      final delimiter = options['delimiter'] as String? ?? ',';
      if (delimiter.runes.length != 1 ||
          delimiter == '\n' ||
          delimiter == '\r') {
        throw const FormatException('分隔符必须为一个字符');
      }
      if (ext == 'csv' && target == 'xlsx') {
        if (bytes.length > _maxCsvBytes) {
          throw const LocalUnavailable('本机 CSV 文件限 8 MiB，请使用服务端。');
        }
        final content = _decodeText(bytes, encoding);
        validateCsvText(content, delimiter: delimiter);
        final rows = CsvToListConverter(
          fieldDelimiter: delimiter,
          shouldParseNumbers: false,
          eol: content.contains('\r\n') ? '\r\n' : '\n',
        ).convert(content);
        if (rows.length > 100000 ||
            rows.any((r) => r.length > 16384) ||
            rows.fold<int>(0, (total, row) => total + row.length) >
                _maxTableCells) {
          throw const LocalUnavailable('表格超过本机行列限制。');
        }
        final excel = Excel.createExcel();
        final sheet = excel[excel.getDefaultSheet()!];
        for (final row in rows) {
          sheet.appendRow(row.map((v) => TextCellValue(v.toString())).toList());
        }
        add('result.xlsx', excel.encode()!);
        warnings.add('CSV 所有单元格均按文本保存，以保留前导零、长编号并避免公式执行。');
      } else if (ext == 'xlsx' && target == 'csv') {
        final archive = decodeSafeZip(bytes);
        final tables = _xlsxRows(archive, warnings);
        var index = 0;
        for (final entry in tables.entries) {
          index++;
          final safe = entry.key.replaceAll(
            RegExp(r'[<>:"/\\|?*\x00-\x1f]'),
            '_',
          );
          final content = ListToCsvConverter(fieldDelimiter: delimiter)
              .convert(entry.value);
          add(
            '${index}_$safe.csv',
            _encodeText(content, encoding == 'auto' ? 'utf-8-sig' : encoding),
          );
        }
        if (outputs.isEmpty) throw const FormatException('XLSX 没有工作表');
        warnings.add('CSV 不保存单元格样式、图表或工作簿结构。');
      } else {
        throw const LocalUnavailable('本机表格转换支持 CSV 与 XLSX 互转。');
      }
    case 'documents':
      if (['txt', 'md'].contains(ext)) {
        text = _decodeText(bytes, options['encoding'] as String? ?? 'auto');
      } else if (ext == 'docx' && ['txt', 'md'].contains(target)) {
        text = _docxText(decodeSafeZip(bytes), warnings);
      } else {
        throw const LocalUnavailable('此文档转换需要复杂排版引擎，请同意上传后使用服务端。');
      }
      if (target == 'txt' || target == 'md') {
        add('result.$target', utf8.encode(text));
        if (ext == 'md' && target == 'txt') {
          warnings.add('输出保留 Markdown 源标记，可继续编辑；未执行复杂排版。');
        }
      } else if (target == 'docx' && ['txt', 'md'].contains(ext)) {
        add('result.docx', _buildDocx(text));
        warnings.add('本机 DOCX 仅保留文本段落；Markdown 标记按原文保存。');
      } else if (target == 'pdf' && ['txt', 'md'].contains(ext)) {
        if (bytes.length > 2 * 1024 * 1024) {
          throw const LocalUnavailable('本机基础 PDF 生成限 2 MiB 文本，更大文档请使用服务端。');
        }
        final fontBytes = args['font'] as Uint8List?;
        if (fontBytes == null) throw const LocalUnavailable('缺少本机中文字体。');
        final font = pw.Font.ttf(ByteData.sublistView(fontBytes));
        final pdf = pw.Document();
        final paragraphs = <pw.Widget>[];
        for (final line in text.split('\n')) {
          if (line.isEmpty) {
            paragraphs.add(pw.SizedBox(height: 8));
            continue;
          }
          final runes = line.runes.toList();
          for (var i = 0; i < runes.length; i += 500) {
            paragraphs.add(
              pw.Paragraph(
                text: String.fromCharCodes(
                  runes.sublist(i, math.min(i + 500, runes.length)),
                ),
                style: pw.TextStyle(font: font, fontSize: 11),
              ),
            );
          }
        }
        pdf.addPage(pw.MultiPage(maxPages: 200, build: (_) => paragraphs));
        add('result.pdf', await pdf.save());
        warnings.add('本机 PDF 为基础文本排版，Markdown 标记按原文保存。');
      } else {
        throw const LocalUnavailable('该文档转换需要服务端。');
      }
    case 'text':
      throw const LocalUnavailable('图片识别需要调用设备识别功能；公式识别需在同意后使用服务端。');
    default:
      throw const LocalUnavailable('不支持的转换分类');
  }
  return {'outputs': outputs, 'warnings': warnings, 'text': text};
}

/// Decode imported TXT/Markdown/LaTeX with the same rules as local converters.
String decodeTextBytes(Uint8List bytes, {String encoding = 'auto'}) =>
    _decodeText(bytes, encoding);

String _decodeText(Uint8List bytes, String encoding) {
  if (encoding == 'gb18030') {
    throw const LocalUnavailable('本机 GBK 编码器不完整支持 GB18030 四字节字符，请使用服务端。');
  }
  if (encoding == 'utf-16' ||
      (bytes.length >= 2 &&
          ((bytes[0] == 255 && bytes[1] == 254) ||
              (bytes[0] == 254 && bytes[1] == 255)))) {
    final bom =
        bytes.length >= 2 &&
        ((bytes[0] == 255 && bytes[1] == 254) ||
            (bytes[0] == 254 && bytes[1] == 255));
    final start = bom ? 2 : 0;
    final little = !bom || bytes[0] == 255;
    if ((bytes.length - start).isOdd) {
      throw const FormatException('UTF-16 字节长度无效');
    }
    final units = <int>[];
    for (var i = start; i < bytes.length; i += 2) {
      units.add(
        little ? bytes[i] + bytes[i + 1] * 256 : bytes[i] * 256 + bytes[i + 1],
      );
    }
    return String.fromCharCodes(units);
  }
  var content = bytes;
  if (bytes.length >= 3 &&
      bytes[0] == 239 &&
      bytes[1] == 187 &&
      bytes[2] == 191) {
    content = bytes.sublist(3);
  }
  if (encoding == 'gbk') {
    _rejectGb18030(content);
    return const GbkCodec().decode(content);
  }
  try {
    return utf8.decode(content);
  } on FormatException {
    if (encoding != 'auto') rethrow;
    _rejectGb18030(content);
    return const GbkCodec().decode(content);
  }
}

void _rejectGb18030(List<int> bytes) {
  for (var i = 0; i + 3 < bytes.length; i++) {
    if (bytes[i] >= 0x81 &&
        bytes[i] <= 0xfe &&
        bytes[i + 1] >= 0x30 &&
        bytes[i + 1] <= 0x39 &&
        bytes[i + 2] >= 0x81 &&
        bytes[i + 2] <= 0xfe &&
        bytes[i + 3] >= 0x30 &&
        bytes[i + 3] <= 0x39) {
      throw const LocalUnavailable('检测到 GB18030 四字节字符，请使用服务端。');
    }
  }
}

List<int> _encodeText(String value, String encoding) {
  switch (encoding) {
    case 'utf-8':
      return utf8.encode(value);
    case 'utf-8-sig':
      return [239, 187, 191, ...utf8.encode(value)];
    case 'utf-16':
      return [
        255,
        254,
        ...value.codeUnits.expand((u) => [u & 255, u >> 8]),
      ];
    case 'gbk':
      final encoded = const GbkCodec().encode(value);
      if (const GbkCodec().decode(encoded) != value) {
        throw const LocalUnavailable('此文本包含 GBK 无法表示的字符。');
      }
      return encoded;
    case 'gb18030':
      throw const LocalUnavailable('本机不完整支持 GB18030，请使用服务端。');
    default:
      throw const FormatException('不支持的文本编码');
  }
}

XmlDocument _xml(String value) {
  if (RegExp(r'<!DOCTYPE|<!ENTITY', caseSensitive: false).hasMatch(value)) {
    throw const FormatException('不允许 XML 实体');
  }
  return XmlDocument.parse(value);
}

String _archiveText(Archive archive, String name) {
  final file = archive.findFile(name);
  if (file == null) throw FormatException('Office 缺少 $name');
  return utf8.decode(file.content as List<int>);
}

Iterable<XmlElement> _els(XmlNode node, String name) =>
    node.descendants.whereType<XmlElement>().where((e) => e.name.local == name);

String _dateFormatTokens(String code) {
  final tokens = StringBuffer();
  for (var i = 0; i < code.length; i++) {
    final character = code[i];
    if (character == '"') {
      while (++i < code.length && code[i] != '"') {}
    } else if (character == r'\' || character == '_' || character == '*') {
      i++; // Escaped literals and width/fill characters are not date tokens.
    } else if (character == '[') {
      final end = code.indexOf(']', i + 1);
      if (end < 0) break;
      final bracket = code.substring(i + 1, end);
      if (RegExp(r'^(?:h+|m+|s+)$', caseSensitive: false).hasMatch(bracket)) {
        tokens.write(bracket);
      }
      i = end; // Discard colors, conditions and locale/currency annotations.
    } else {
      tokens.write(character);
    }
  }
  return tokens.toString();
}

Map<String, List<List<String>>> _xlsxRows(
  Archive archive,
  List<String> warnings,
) {
  var allocatedRows = 0, allocatedCells = 0;
  final workbook = _xml(_archiveText(archive, 'xl/workbook.xml'));
  final rels = _xml(_archiveText(archive, 'xl/_rels/workbook.xml.rels'));
  final targets = <String, String>{};
  for (final rel in _els(rels, 'Relationship')) {
    if (rel.getAttribute('TargetMode') == 'External') continue;
    targets[rel.getAttribute('Id')!] = rel.getAttribute('Target')!;
  }
  final shared = <String>[];
  final sharedFile = archive.findFile('xl/sharedStrings.xml');
  if (sharedFile != null) {
    for (final si in _els(
      _xml(utf8.decode(sharedFile.content as List<int>)),
      'si',
    )) {
      shared.add(_els(si, 't').map((e) => e.innerText).join());
    }
  }
  final dateStyles = <int>{};
  final stylesFile = archive.findFile('xl/styles.xml');
  if (stylesFile != null) {
    final styles = _xml(utf8.decode(stylesFile.content as List<int>));
    final custom = <int, String>{};
    for (final f in _els(styles, 'numFmt')) {
      custom[int.parse(f.getAttribute('numFmtId')!)] =
          f.getAttribute('formatCode') ?? '';
    }
    final xfs = _els(styles, 'cellXfs').firstOrNull;
    if (xfs != null) {
      var index = 0;
      for (final xf in xfs.childElements) {
        final id = int.tryParse(xf.getAttribute('numFmtId') ?? '') ?? 0;
        final code = _dateFormatTokens(custom[id] ?? '');
        if ((id >= 14 && id <= 22) ||
            (id >= 45 && id <= 47) ||
            RegExp(r'[ymdhs]', caseSensitive: false).hasMatch(code)) {
          dateStyles.add(index);
        }
        index++;
      }
    }
  }
  final date1904 =
      _els(workbook, 'workbookPr').firstOrNull?.getAttribute('date1904') == '1';
  final result = <String, List<List<String>>>{};
  for (final sheet in _els(workbook, 'sheet')) {
    final id = sheet.attributes
        .where((a) => a.name.local == 'id')
        .firstOrNull
        ?.value;
    final target = targets[id];
    if (target == null) throw const FormatException('工作表关系缺失');
    final path = target.startsWith('/')
        ? target.substring(1)
        : p.posix.normalize(p.posix.join('xl', target));
    if (!path.startsWith('xl/') || path.contains('..')) {
      throw const FormatException('工作表路径不安全');
    }
    final document = _xml(_archiveText(archive, path));
    final rows = <List<String>>[];
    for (final row in _els(document, 'row')) {
      final rowIndex =
          (int.tryParse(row.getAttribute('r') ?? '') ?? rows.length + 1) - 1;
      if (rowIndex < 0 || rowIndex >= 100000) {
        throw const LocalUnavailable('工作表行数超过本机限制');
      }
      final additionalRows = math.max(0, rowIndex + 1 - rows.length);
      if (allocatedRows + additionalRows > _maxTableCells) {
        throw const LocalUnavailable('工作簿空行展开超过本机限制，请使用服务端。');
      }
      allocatedRows += additionalRows;
      while (rows.length <= rowIndex) {
        rows.add([]);
      }
      final values = rows[rowIndex];
      for (final cell in row.childElements.where((e) => e.name.local == 'c')) {
        final ref = cell.getAttribute('r') ?? '';
        var col = 0;
        for (final c
            in RegExp(r'^[A-Za-z]+')
                    .stringMatch(ref)
                    ?.toUpperCase()
                    .codeUnits ??
                <int>[]) {
          col = col * 26 + c - 64;
        }
        col = col == 0 ? values.length : col - 1;
        if (col >= 16384) throw const LocalUnavailable('工作表列数超过本机限制');
        final additionalCells = math.max(0, col + 1 - values.length);
        if (allocatedCells + additionalCells > _maxTableCells) {
          throw const LocalUnavailable('工作簿展开超过本机累计 100 万单元格限制，请使用服务端。');
        }
        allocatedCells += additionalCells;
        while (values.length <= col) {
          values.add('');
        }
        final type = cell.getAttribute('t'),
            cached = _els(cell, 'v').firstOrNull?.innerText,
            formula = _els(cell, 'f').firstOrNull?.innerText;
        var value = cached ?? '';
        if (type == 's') {
          final index = int.tryParse(value);
          if (index == null || index < 0 || index >= shared.length) {
            throw const FormatException('共享文本索引无效');
          }
          value = shared[index];
        } else if (type == 'inlineStr') {
          value = _els(cell, 't').map((e) => e.innerText).join();
        } else if (type == 'b') {
          value = value == '1' ? 'TRUE' : 'FALSE';
        } else if (dateStyles.contains(
              int.tryParse(cell.getAttribute('s') ?? '') ?? 0,
            ) &&
            double.tryParse(value) != null) {
          final serial = double.parse(value);
          final epoch = date1904
              ? DateTime.utc(1904)
              : DateTime.utc(1899, 12, 30);
          final date = epoch.add(
            Duration(milliseconds: (serial * 86400000).round()),
          );
          value = date.toIso8601String().replaceFirst(RegExp(r'\.000Z$'), 'Z');
        }
        if (formula != null && cached == null) {
          value = '=$formula';
          warnings.add('公式缺少缓存值，已保留公式文本：$ref');
        }
        values[col] = value;
      }
    }
    result[sheet.getAttribute('name') ?? 'Sheet${result.length + 1}'] = rows;
  }
  return result;
}

String _docxText(Archive archive, List<String> warnings) {
  final doc = _xml(_archiveText(archive, 'word/document.xml'));
  final paragraphs = <String>[];
  for (final paragraph in _els(doc, 'p')) {
    final out = StringBuffer();
    for (final node in paragraph.descendants.whereType<XmlElement>()) {
      switch (node.name.local) {
        case 't':
          out.write(node.innerText);
        case 'tab':
          out.write('\t');
        case 'br':
        case 'cr':
          out.write('\n');
      }
    }
    paragraphs.add(out.toString());
  }
  warnings.add('本机提取文本段落，表格按阅读顺序展开；样式、图片、页眉页脚和复杂布局不保留。');
  return paragraphs.join('\n');
}

List<int> _buildDocx(String text) {
  final builder = XmlBuilder();
  builder.processing('xml', 'version="1.0" encoding="UTF-8"');
  builder.element(
    'w:document',
    namespaces: {
      'http://schemas.openxmlformats.org/wordprocessingml/2006/main': 'w',
    },
    nest: () {
      builder.element(
        'w:body',
        nest: () {
          for (final line in text.split('\n')) {
            builder.element(
              'w:p',
              nest: () {
                builder.element(
                  'w:r',
                  nest: () {
                    builder.element(
                      'w:t',
                      attributes: {'xml:space': 'preserve'},
                      nest: line,
                    );
                  },
                );
              },
            );
          }
          builder.element('w:sectPr');
        },
      );
    },
  );
  final files = {
    '[Content_Types].xml': '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
    '_rels/.rels': '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
    'word/document.xml': builder.buildDocument().toXmlString(),
  };
  final archive = Archive();
  for (final entry in files.entries) {
    final data = utf8.encode(entry.value);
    archive.addFile(ArchiveFile(entry.key, data.length, data));
  }
  return ZipEncoder().encode(archive)!;
}
