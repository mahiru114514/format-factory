import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;

import 'models.dart';
import 'storage.dart';

Uri validateServerUri(String value) {
  if (value.trim().isEmpty) {
    throw const LocalUnavailable('尚未配置转换服务地址，请先在设置中填写。');
  }
  final uri = Uri.tryParse(value.trim());
  if (uri == null ||
      !uri.hasAuthority ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      !['http', 'https'].contains(uri.scheme)) {
    throw const FormatException('服务地址必须为 HTTPS，不能包含账号、查询参数或片段。');
  }
  if (uri.scheme == 'http') {
    final host = uri.host.replaceAll('[', '').replaceAll(']', '');
    var local = host == '::1';
    final parts = host.split('.');
    if (parts.length == 4 &&
        parts.every(
          (s) =>
              RegExp(r'^(0|[1-9][0-9]{0,2})$').hasMatch(s) &&
              int.parse(s) <= 255,
        )) {
      final octets = parts.map(int.parse).toList();
      local =
          octets[0] == 127 ||
          octets[0] == 10 ||
          (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) ||
          (octets[0] == 192 && octets[1] == 168);
    }
    if (!local) throw const FormatException('HTTP 仅允许明确填写的本机或局域网数字地址。');
  }
  if (uri.pathSegments.any((s) => s == '..' || s == '.')) {
    throw const FormatException('服务地址路径无效');
  }
  return uri.replace(path: uri.path.replaceFirst(RegExp(r'/+$'), ''));
}

class RemoteConversionClient {
  final String serverUrl;
  final FileStorage storage;
  final http.Client _client;
  final Duration timeout, pollInterval;
  RemoteConversionClient({
    required this.serverUrl,
    required this.storage,
    http.Client? client,
    this.timeout = const Duration(minutes: 3),
    this.pollInterval = const Duration(seconds: 1),
  }) : _client = client ?? http.Client();
  void close() => _client.close();
  Uri _url(String route) {
    final base = validateServerUri(serverUrl);
    return base.replace(path: '${base.path}$route');
  }

  void _consent(bool consent) {
    if (!consent) throw const LocalUnavailable('尚未同意上传；文件未发送到服务端。');
  }

  Future<Map<String, dynamic>> capabilities({required bool consent}) async {
    _consent(consent);
    final request = http.Request('GET', _url('/v1/capabilities'))
      ..followRedirects = false;
    final data = await _send(
      request,
      DateTime.now().add(timeout),
      null,
      1024 * 1024,
    );
    if (data.status != 200) throw LocalUnavailable('读取服务能力失败（${data.status}）。');
    return _json(data.bytes);
  }

  Future<ConversionResult> convert(
    ConversionRequest request, {
    required bool consent,
    CancelToken? cancel,
  }) async {
    _consent(consent);
    cancel?.throwIfCancelled();
    final url = _url('/v1/jobs');
    final deadline = DateTime.now().add(timeout);
    final file = File(request.inputPath);
    if (await file.length() > maxInputBytes) {
      throw const LocalUnavailable('上传文件超过 50 MiB 限制。');
    }
    final bytes = await file.readAsBytes();
    if (bytes.length > maxInputBytes) {
      throw const LocalUnavailable('上传文件超过 50 MiB 限制。');
    }
    cancel?.throwIfCancelled();
    final post = http.MultipartRequest('POST', url)
      ..followRedirects = false
      ..fields.addAll({
        'category': request.category.name,
        'target': request.target,
        'options': jsonEncode(request.options),
        'consent': 'true',
      })
      ..files.add(
        http.MultipartFile.fromBytes(
          'file',
          bytes,
          filename: p.basename(request.inputPath),
        ),
      );
    String? id, token;
    try {
      final created = await _send(post, deadline, cancel, 1024 * 1024);
      if (created.status != 202) {
        throw LocalUnavailable(
          '服务未接收文件（${created.status}）：${_error(created.bytes)}',
        );
      }
      final job = _json(created.bytes);
      id = job['id'] as String?;
      token = job['token'] as String?;
      if (id == null ||
          token == null ||
          !RegExp(r'^[A-Za-z0-9_-]{1,128}$').hasMatch(id) ||
          !RegExp(r'^[A-Za-z0-9_-]{1,256}$').hasMatch(token)) {
        throw const FormatException('服务返回的任务信息无效');
      }
      http.Request auth(String method, String suffix) =>
          http.Request(method, _url('/v1/jobs/$id$suffix'))
            ..followRedirects = false
            ..headers['Authorization'] = 'Bearer $token';
      final warnings = <String>[];
      while (true) {
        cancel?.throwIfCancelled();
        final response = await _send(
          auth('GET', ''),
          deadline,
          cancel,
          1024 * 1024,
        );
        if (response.status != 200) {
          throw LocalUnavailable('任务状态读取失败（${response.status}）。');
        }
        final state = _json(response.bytes);
        if (state['state'] == 'failed') {
          throw LocalUnavailable('服务端转换失败：${state['error'] ?? '未知错误'}');
        }
        if (state['state'] == 'succeeded') {
          warnings.addAll(List<String>.from(state['warnings'] as List? ?? []));
          break;
        }
        if (!['queued', 'running'].contains(state['state'])) {
          throw const FormatException('服务返回未知任务状态');
        }
        await _pause(deadline, cancel);
      }
      final downloaded = await _send(
        auth('GET', '/result'),
        deadline,
        cancel,
        maxResultZipBytes,
      );
      if (downloaded.status != 200) {
        throw LocalUnavailable('结果下载失败（${downloaded.status}）。');
      }
      cancel?.throwIfCancelled();
      // Acknowledgement is deliberately after all durable writes and safe unpacking.
      final paths = await storage.persistZip(downloaded.bytes, cancel: cancel);
      String? text;
      final textPath = paths
          .where((v) => p.extension(v).toLowerCase() == '.txt')
          .firstOrNull;
      if (textPath != null) {
        try {
          text = await File(textPath).readAsString();
        } on FormatException {
          warnings.add('结果文本编码无法识别，原始文件已保留。');
        }
      }
      try {
        final deleted = await _send(
          auth('DELETE', ''),
          deadline,
          null,
          1024 * 1024,
        );
        if (deleted.status != 204) {
          warnings.add('结果已保存在本机；服务端确认删除失败，将按保留期限自动清理。');
        }
      } catch (_) {
        warnings.add('结果已保存在本机；未能确认服务端删除，将按保留期限自动清理。');
      }
      return ConversionResult(
        outputPaths: paths,
        warnings: warnings,
        text: text,
        viaRemote: true,
      );
    } on ConversionCancelled {
      if (id != null && token != null) {
        try {
          final del = http.Request('DELETE', _url('/v1/jobs/$id'))
            ..followRedirects = false
            ..headers['Authorization'] = 'Bearer $token';
          await _send(
            del,
            DateTime.now().add(const Duration(seconds: 5)),
            null,
            1024 * 1024,
          );
        } catch (_) {
          /* retention cleanup remains available */
        }
      }
      rethrow;
    }
  }

  Future<void> _pause(DateTime deadline, CancelToken? cancel) async {
    final until = DateTime.now().add(pollInterval);
    while (DateTime.now().isBefore(until)) {
      cancel?.throwIfCancelled();
      if (DateTime.now().isAfter(deadline)) {
        throw const LocalUnavailable('服务端转换等待超时，原文件仍保存在本机。');
      }
      await Future<void>.delayed(const Duration(milliseconds: 100));
    }
  }

  Future<_Reply> _send(
    http.BaseRequest request,
    DateTime deadline,
    CancelToken? cancel,
    int limit,
  ) async {
    cancel?.throwIfCancelled();
    final remaining = deadline.difference(DateTime.now());
    if (remaining <= Duration.zero) {
      throw const LocalUnavailable('网络请求超时，原文件仍保存在本机。');
    }
    try {
      final streamed = await _client.send(request).timeout(remaining);
      if (streamed.statusCode >= 300 && streamed.statusCode < 400) {
        throw const LocalUnavailable('服务发生重定向，已停止请求以保护任务令牌。');
      }
      if ((streamed.contentLength ?? 0) > limit) {
        throw const FormatException('服务响应超过大小限制');
      }
      final builder = BytesBuilder(copy: false);
      var size = 0;
      Future<Uint8List> read() async {
        await for (final chunk in streamed.stream) {
          cancel?.throwIfCancelled();
          size += chunk.length;
          if (size > limit) throw const FormatException('服务响应超过大小限制');
          builder.add(chunk);
        }
        return builder.takeBytes();
      }

      final bytes = await read().timeout(deadline.difference(DateTime.now()));
      cancel?.throwIfCancelled();
      return _Reply(streamed.statusCode, bytes);
    } on TimeoutException {
      throw const LocalUnavailable('网络请求超时，原文件仍保存在本机。');
    }
  }

  Map<String, dynamic> _json(List<int> bytes) {
    final value = jsonDecode(utf8.decode(bytes));
    if (value is! Map) throw const FormatException('服务响应不是 JSON 对象');
    return Map<String, dynamic>.from(value);
  }

  String _error(List<int> bytes) {
    try {
      final value = _json(bytes);
      return (value['detail'] ?? value['error'] ?? '请求失败').toString();
    } catch (_) {
      return '请求失败';
    }
  }
}

class _Reply {
  final int status;
  final Uint8List bytes;
  _Reply(this.status, this.bytes);
}
