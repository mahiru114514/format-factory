import 'dart:io';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:path/path.dart' as p;

import '../core/core.dart';
import '../platform/native_bridge.dart';
import 'app_controller.dart';

const categoryNames = {
  ConversionCategory.documents: '文档',
  ConversionCategory.tables: '表格',
  ConversionCategory.images: '图片',
};
const targets = {
  ConversionCategory.documents: ['pdf', 'docx', 'txt', 'md'],
  ConversionCategory.tables: ['xlsx', 'csv'],
  ConversionCategory.images: ['jpg', 'png', 'webp', 'heic', 'bmp', 'tiff'],
};

class FactoryApp extends StatelessWidget {
  final AppController controller;
  final TextScaler? textScaler;
  const FactoryApp({super.key, required this.controller, this.textScaler});
  ThemeData _theme(Brightness brightness) {
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xff2463eb),
      brightness: brightness,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      fontFamily: 'NotoSansSC',
      scaffoldBackgroundColor: brightness == Brightness.light
          ? const Color(0xfff5f7fb)
          : const Color(0xff101722),
      textTheme: Typography.material2021().black
          .apply(
            fontFamily: 'NotoSansSC',
            bodyColor: scheme.onSurface,
            displayColor: scheme.onSurface,
          )
          .copyWith(
            bodyMedium: TextStyle(
              fontSize: 16,
              height: 1.5,
              color: scheme.onSurface,
            ),
            bodyLarge: TextStyle(
              fontSize: 16,
              height: 1.5,
              color: scheme.onSurface,
            ),
            labelLarge: TextStyle(fontSize: 16, color: scheme.onSurface),
          ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
        contentPadding: const EdgeInsets.all(16),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surface,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: scheme.outlineVariant.withValues(alpha: 0.6)),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: controller,
    builder: (context, _) => MaterialApp(
      title: '格式工厂',
      debugShowCheckedModeBanner: false,
      locale: const Locale('zh', 'CN'),
      supportedLocales: const [Locale('zh', 'CN'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      theme: _theme(Brightness.light),
      darkTheme: _theme(Brightness.dark),
      themeMode: switch (controller.theme) {
        'dark' => ThemeMode.dark,
        'light' => ThemeMode.light,
        _ => ThemeMode.system,
      },
      builder: (context, child) => textScaler == null
          ? child!
          : MediaQuery(
              data: MediaQuery.of(context).copyWith(textScaler: textScaler),
              child: child!,
            ),
      home: FactoryHome(controller: controller),
    ),
  );
}

class FactoryHome extends StatefulWidget {
  final AppController controller;
  const FactoryHome({super.key, required this.controller});
  @override
  State<FactoryHome> createState() => _FactoryHomeState();
}

class _FactoryHomeState extends State<FactoryHome> with WidgetsBindingObserver {
  AppController get c => widget.controller;
  int tab = 0;
  ConversionCategory category = ConversionCategory.documents;
  String target = 'pdf', encoding = 'auto', delimiter = ',';
  double quality = 90;
  int maxSize = 0;
  bool keepMetadata = false,
      forceRemote = false,
      working = false,
      previewOpen = false;
  late final TextEditingController source = TextEditingController(
        text: c.source,
      ),
      editor = TextEditingController(text: c.result.text),
      server = TextEditingController(text: c.serverUrl);
  Uint8List? pageBytes;
  int pageCount = 1;
  String? renderedPath;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    c.addListener(refresh);
  }

  void refresh() {
    if (!mounted) return;
    if (source.text != c.source) {
      source.text = c.source;
    }
    if (editor.text != c.result.text) {
      final selection = editor.selection;
      editor.value = TextEditingValue(
        text: c.result.text,
        selection: TextSelection.collapsed(
          offset: selection.extentOffset.clamp(0, c.result.text.length),
        ),
      );
    }
    setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      c.flush();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    c.removeListener(refresh);
    source.dispose();
    editor.dispose();
    server.dispose();
    super.dispose();
  }

  void message(String value) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(value)));
    }
  }

  Future<void> action(Future<void> Function() run) async {
    if (working) return;
    setState(() => working = true);
    try {
      await run();
    } catch (e) {
      message(c.friendly(e));
    } finally {
      if (mounted) setState(() => working = false);
    }
  }

  Future<bool> confirm(String title, String body, {String yes = '继续'}) async =>
      await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(title),
          content: SingleChildScrollView(child: Text(body)),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: Text(yes),
            ),
          ],
        ),
      ) ??
      false;
  Future<bool> consent(ConversionRequest request, String policy) => confirm(
    policy.startsWith('服务政策尚未') ? '读取服务能力？' : '允许上传这个文件？',
    '文件：${p.basename(request.inputPath)}\n用途：${request.options['method'] == 'formula' ? '识别当前页的单个公式' : '转换为 ${request.target.toUpperCase()}'}\n服务：${c.serverUrl}\n\n$policy\n\n原文件会保留在本机。',
    yes: policy.startsWith('服务政策尚未') ? '仅查询政策' : '同意上传',
  );
  Future<void> replaceResult(String value) async {
    try {
      c.validateDraft(value);
    } catch (e) {
      message(c.friendly(e));
      return;
    }
    if (c.result.dirty &&
        !await confirm('保留你的编辑？', '新结果会覆盖当前校对文本。可以取消后先复制或保存。', yes: '覆盖编辑')) {
      return;
    }
    c.acceptResult(value, discard: true);
  }

  Rect origin() {
    final box = context.findRenderObject() as RenderBox?;
    return box == null
        ? const Rect.fromLTWH(0, 0, 1, 1)
        : box.localToGlobal(Offset.zero) & box.size;
  }

  Widget card(Widget child) => Card(
    child: Padding(padding: const EdgeInsets.all(18), child: child),
  );
  Widget title(String title, String detail) => Padding(
    padding: const EdgeInsets.only(bottom: 22),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.headlineMedium
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 8),
        Text(
          detail,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
            height: 1.5,
          ),
        ),
      ],
    ),
  );
  Widget space() => const SizedBox(height: 16);
  Widget page(List<Widget> children) => ListView(
    padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
    children: children,
  );
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      systemOverlayStyle: Theme.of(context).brightness == Brightness.dark
          ? SystemUiOverlayStyle.light
          : SystemUiOverlayStyle.dark,
      title: Row(
        children: [
          Image.asset('assets/appmark.png', width: 30, height: 30),
          const SizedBox(width: 10),
          const Text('格式工厂', style: TextStyle(fontWeight: FontWeight.w700)),
        ],
      ),
      actions: [
        Padding(
          padding: const EdgeInsets.only(right: 16),
          child: Tooltip(
            message: '文件优先在本机处理，上传需逐次确认',
            child: Icon(
              Icons.shield_outlined,
              color: Theme.of(context).colorScheme.primary,
            ),
          ),
        ),
      ],
      backgroundColor: Colors.transparent,
    ),
    body: SafeArea(
      top: false,
      child: Column(
        children: [
          if (working || c.busy) const LinearProgressIndicator(minHeight: 2),
          Expanded(
            child: switch (tab) {
              0 => conversionPage(),
              1 => textPage(),
              2 => taskPage(),
              _ => settingsPage(),
            },
          ),
        ],
      ),
    ),
    bottomNavigationBar: NavigationBar(
      selectedIndex: tab,
      onDestinationSelected: (i) => setState(() => tab = i),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.swap_horiz_rounded),
          label: '转换',
        ),
        NavigationDestination(
          icon: Icon(Icons.text_fields_rounded),
          label: '文本',
        ),
        NavigationDestination(icon: Icon(Icons.task_alt_rounded), label: '任务'),
        NavigationDestination(icon: Icon(Icons.tune_rounded), label: '设置'),
      ],
    ),
  );
  Widget conversionPage() => page([
    title('把文件，变成你需要的样子', '本机优先 · 批量转换 · 原文件始终保留'),
    LayoutBuilder(
      builder: (context, constraints) => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: categoryNames.entries
            .map(
              (entry) => SizedBox(
                width: (constraints.maxWidth - 16) / 3,
                child: ChoiceChip(
                  showCheckmark: false,
                  labelPadding: const EdgeInsets.symmetric(
                    horizontal: 2,
                    vertical: 10,
                  ),
                  label: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(switch (entry.key) {
                        ConversionCategory.documents =>
                          Icons.description_outlined,
                        ConversionCategory.tables => Icons.table_chart_outlined,
                        _ => Icons.photo_outlined,
                      }),
                      const SizedBox(height: 6),
                      Text(entry.value),
                    ],
                  ),
                  selected: category == entry.key,
                  onSelected: c.busy
                      ? null
                      : (_) => setState(() {
                          category = entry.key;
                          target = targets[category]!.first;
                        }),
                ),
              ),
            )
            .toList(),
      ),
    ),
    space(),
    card(
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('1  选择原文件', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: c.busy || working ? null : () => action(() => c.pick()),
            icon: const Icon(Icons.add_rounded),
            label: const Text('选择文件（可多选）'),
          ),
          if (category == ConversionCategory.images) ...[
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: c.busy || working
                  ? null
                  : () => action(() => c.pick(photos: true)),
              icon: const Icon(Icons.photo_library_outlined),
              label: const Text('从相册选择原图'),
            ),
          ],
          if (c.inputs.isEmpty) ...[
            const SizedBox(height: 12),
            const Text(
              '支持单文件 50 MiB。选择后会复制到应用内，离线也能继续。',
              style: TextStyle(height: 1.5),
            ),
          ],
          ...c.inputs.map(
            (path) => ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.insert_drive_file_outlined),
              title: Text(
                p.basename(path),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              subtitle: const Text('已保存在本机'),
              trailing: IconButton(
                tooltip: '从本次列表移除',
                onPressed: c.busy ? null : () => c.removeInput(path),
                icon: const Icon(Icons.close),
              ),
            ),
          ),
        ],
      ),
    ),
    space(),
    card(
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('2  设置输出', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            key: ValueKey(category),
            initialValue: target,
            decoration: const InputDecoration(labelText: '目标格式'),
            items: targets[category]!
                .map(
                  (v) =>
                      DropdownMenuItem(value: v, child: Text(v.toUpperCase())),
                )
                .toList(),
            onChanged: c.busy ? null : (v) => setState(() => target = v!),
          ),
          if (category == ConversionCategory.tables) ...[
            space(),
            DropdownButtonFormField<String>(
              initialValue: encoding,
              decoration: const InputDecoration(labelText: '输入文本编码'),
              items: const [
                DropdownMenuItem(value: 'auto', child: Text('自动识别')),
                DropdownMenuItem(value: 'utf-8', child: Text('UTF-8')),
                DropdownMenuItem(value: 'gbk', child: Text('GBK')),
                DropdownMenuItem(value: 'utf-16', child: Text('UTF-16')),
              ],
              onChanged: (v) => encoding = v!,
            ),
            space(),
            DropdownButtonFormField<String>(
              initialValue: delimiter,
              decoration: const InputDecoration(labelText: 'CSV 分隔符'),
              items: const [
                DropdownMenuItem(value: ',', child: Text('逗号 ,')),
                DropdownMenuItem(value: '\t', child: Text('制表符 TAB')),
                DropdownMenuItem(value: ';', child: Text('分号 ;')),
              ],
              onChanged: (v) => delimiter = v!,
            ),
          ],
          if (category == ConversionCategory.images) ...[
            space(),
            Text('图片质量 ${quality.round()}%'),
            Slider(
              value: quality,
              min: 10,
              max: 100,
              divisions: 18,
              label: '${quality.round()}%',
              onChanged: (v) => setState(() => quality = v),
            ),
            DropdownButtonFormField<int>(
              initialValue: maxSize,
              decoration: const InputDecoration(labelText: '最长边尺寸'),
              items: const [
                DropdownMenuItem(value: 0, child: Text('保留原尺寸')),
                DropdownMenuItem(value: 1920, child: Text('1920 像素')),
                DropdownMenuItem(value: 1280, child: Text('1280 像素')),
              ],
              onChanged: (v) => maxSize = v!,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('尽可能保留元数据'),
              subtitle: const Text('关闭可移除照片位置等信息'),
              value: keepMetadata,
              onChanged: (v) => setState(() => keepMetadata = v),
            ),
          ],
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('使用服务端转换'),
            subtitle: Text(
              c.serverUrl.isEmpty ? '尚未配置服务；可前往设置添加' : '适合复杂排版，逐文件确认上传',
            ),
            value: forceRemote,
            onChanged: (v) => setState(() => forceRemote = v),
          ),
        ],
      ),
    ),
    space(),
    if (c.status.isNotEmpty)
      Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: Semantics(
          liveRegion: true,
          child: Text(
            c.status,
            style: TextStyle(
              color: Theme.of(context).colorScheme.primary,
              height: 1.5,
            ),
          ),
        ),
      ),
    FilledButton.icon(
      onPressed: c.busy
          ? null
          : () => action(
              () => c.runBatch(
                category: category,
                target: target,
                options: {
                  'quality': quality.round(),
                  'max_size': maxSize,
                  'keep_metadata': keepMetadata,
                  'encoding': encoding,
                  'delimiter': delimiter,
                },
                forceRemote: forceRemote,
                consent: consent,
              ),
            ),
      icon: const Icon(Icons.bolt_outlined),
      label: const Text('开始转换'),
    ),
    if (c.busy) TextButton(onPressed: c.cancel, child: const Text('停止后续转换')),
  ]);
  Future<void> importText() async {
    final files = await c.bridge.pickFiles(text: true);
    if (files.isEmpty) return;
    final path = await c.importPicked(files.first);
    final text = decodeTextBytes(await File(path).readAsBytes());
    c.changeSource(text);
    source.text = text;
    await replaceResult(text);
  }

  Future<void> chooseSource({bool camera = false}) async {
    final PickedInput? input;
    if (camera) {
      input = await c.bridge.camera();
    } else {
      input = (await c.bridge.pickFiles()).firstOrNull;
    }
    if (input == null) return;
    final path = await c.importPicked(input);
    await c.attachSource(path);
    pageBytes = null;
    renderedPath = null;
    if (p.extension(path).toLowerCase() == '.pdf') await renderPage();
    setState(() => previewOpen = true);
  }

  Future<void> renderPage() async {
    pageBytes = null;
    renderedPath = null;
    final preview = await c.bridge.renderPdf(c.sourcePath, c.page);
    pageBytes = preview.bytes;
    pageCount = preview.pages;
    final dir = await c.storage.createTaskDirectory();
    final file = File(p.join(dir.path, '第${c.page}页.png'));
    await file.writeAsBytes(preview.bytes, flush: true);
    renderedPath = file.path;
    c.persist();
    if (mounted) setState(() {});
  }

  Future<String> currentImage() async {
    if (c.sourcePath.isEmpty) throw const LocalUnavailable('请先导入图片或 PDF');
    if (p.extension(c.sourcePath).toLowerCase() == '.pdf') {
      if (renderedPath == null) await renderPage();
      return renderedPath!;
    }
    return c.sourcePath;
  }

  Future<void> ocr() async {
    final path = await currentImage();
    final value = await c.bridge.recognize(path);
    if (value.trim().isEmpty) throw const LocalUnavailable('未找到清晰文字，可以先裁剪再识别');
    await replaceResult(value);
  }

  Future<void> formula() async {
    final path = await currentImage();
    final result = await c.runFormula(path, consent: consent);
    if (result?.text != null) await replaceResult(result!.text!);
  }

  Widget textPage() => Column(
    children: [
      Expanded(
        child: page([
          title('识别、校对，然后复制', '原文与结果各自保留，改动由你决定。'),
          if (c.status.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Semantics(liveRegion: true, child: Text(c.status)),
            ),
          if (c.busy)
            TextButton.icon(
              onPressed: c.cancel,
              icon: const Icon(Icons.stop_circle_outlined),
              label: const Text('停止当前任务'),
            ),
          card(
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  '原文 / LaTeX',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 12),
                TextField(
                  key: const Key('sourceText'),
                  inputFormatters: [
                    TextInputFormatter.withFunction(
                      (oldValue, newValue) =>
                          utf8.encode(newValue.text).length > maxDraftBytes
                          ? oldValue
                          : newValue,
                    ),
                  ],
                  controller: source,
                  minLines: 4,
                  maxLines: 9,
                  decoration: const InputDecoration(
                    hintText: '粘贴文字、Markdown 或 LaTeX 原文',
                  ),
                  onChanged: c.changeSource,
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: [
                    TextButton.icon(
                      onPressed: working
                          ? null
                          : () => action(() async {
                              final value = await c.bridge.pasteText();
                              if (value != null) {
                                c.changeSource(value);
                                source.text = value;
                              }
                            }),
                      icon: const Icon(Icons.content_paste),
                      label: const Text('粘贴'),
                    ),
                    TextButton.icon(
                      onPressed: working ? null : () => action(importText),
                      icon: const Icon(Icons.file_open_outlined),
                      label: const Text('导入文本'),
                    ),
                    TextButton(
                      onPressed: () => replaceResult(source.text),
                      child: const Text('原文 / LaTeX 原样保留'),
                    ),
                    TextButton(
                      onPressed: () =>
                          replaceResult(latexReadable(source.text)),
                      child: const Text('转为易读公式'),
                    ),
                  ],
                ),
              ],
            ),
          ),
          space(),
          card(
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  '图片与 PDF 识别',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    OutlinedButton.icon(
                      onPressed: working
                          ? null
                          : () => action(() => chooseSource()),
                      icon: const Icon(Icons.photo_outlined),
                      label: const Text('导入图片 / PDF'),
                    ),
                    OutlinedButton.icon(
                      onPressed: working
                          ? null
                          : () => action(() => chooseSource(camera: true)),
                      icon: const Icon(Icons.camera_alt_outlined),
                      label: const Text('拍照'),
                    ),
                  ],
                ),
                if (c.sourcePath.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(p.basename(c.sourcePath)),
                  ExpansionTile(
                    key: ValueKey('${c.sourcePath}$previewOpen'),
                    initiallyExpanded: previewOpen,
                    tilePadding: EdgeInsets.zero,
                    title: const Text('查看原图 · 双指缩放'),
                    children: [
                      if (p.extension(c.sourcePath).toLowerCase() == '.pdf')
                        Wrap(
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            IconButton(
                              tooltip: '上一页',
                              onPressed: c.page <= 1 || working
                                  ? null
                                  : () => action(() async {
                                      c.page--;
                                      await renderPage();
                                    }),
                              icon: const Icon(Icons.chevron_left),
                            ),
                            Text('第 ${c.page} / $pageCount 页'),
                            IconButton(
                              tooltip: '下一页',
                              onPressed: c.page >= pageCount || working
                                  ? null
                                  : () => action(() async {
                                      c.page++;
                                      await renderPage();
                                    }),
                              icon: const Icon(Icons.chevron_right),
                            ),
                          ],
                        ),
                      SizedBox(
                        height: 240,
                        child: InteractiveViewer(
                          minScale: 0.5,
                          maxScale: 6,
                          child: pageBytes != null
                              ? Image.memory(pageBytes!, fit: BoxFit.contain)
                              : p.extension(c.sourcePath).toLowerCase() ==
                                    '.pdf'
                              ? Center(
                                  child: TextButton(
                                    onPressed: () => action(renderPage),
                                    child: const Text('载入这一页'),
                                  ),
                                )
                              : Image.file(
                                  File(c.sourcePath),
                                  fit: BoxFit.contain,
                                  errorBuilder: (_, error, stack) =>
                                      const Center(
                                        child: Text('此格式无法预览，可转换为 PNG 后查看'),
                                      ),
                                ),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    TextButton.icon(
                      onPressed: working
                          ? null
                          : () => action(() async {
                              final path = await currentImage();
                              final crop = await c.bridge.crop(path);
                              if (crop != null) {
                                await c.attachSource(await c.importFile(crop));
                                pageBytes = null;
                                renderedPath = null;
                                setState(() => previewOpen = true);
                              }
                            }),
                      icon: const Icon(Icons.crop),
                      label: const Text('裁剪当前图 / 页'),
                    ),
                    OutlinedButton(
                      onPressed: working ? null : () => action(ocr),
                      child: const Text('本机识别文字'),
                    ),
                    OutlinedButton(
                      onPressed: working ? null : () => action(formula),
                      child: const Text('服务端识别公式'),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                const Text(
                  '文字识别在设备上完成。单个公式建议先裁剪；公式识别需配置服务并同意上传。',
                  style: TextStyle(height: 1.5),
                ),
              ],
            ),
          ),
          space(),
          card(
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Wrap(
                  alignment: WrapAlignment.spaceBetween,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      c.result.dirty ? '校对结果 · 已编辑' : '校对结果',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    TextButton.icon(
                      onPressed: c.undo,
                      icon: const Icon(Icons.undo),
                      label: const Text('撤销'),
                    ),
                  ],
                ),
                TextField(
                  key: const Key('resultEditor'),
                  inputFormatters: [
                    TextInputFormatter.withFunction(
                      (oldValue, newValue) =>
                          utf8.encode(newValue.text).length > maxDraftBytes
                          ? oldValue
                          : newValue,
                    ),
                  ],
                  controller: editor,
                  minLines: 7,
                  maxLines: 18,
                  decoration: const InputDecoration(
                    hintText: '识别结果会出现在这里，可直接修改',
                  ),
                  onChanged: c.editResult,
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: [
                    TextButton(
                      onPressed: () => action(() async {
                        await c.copyResult(editor.selection);
                        message(
                          editor.selection.isValid &&
                                  !editor.selection.isCollapsed
                              ? '已复制所选文字'
                              : '已复制全文',
                        );
                      }),
                      child: const Text('复制选中'),
                    ),
                    TextButton.icon(
                      onPressed: () => action(() async {
                        if (await c.saveText()) message('已保存当前编辑文本');
                      }),
                      icon: const Icon(Icons.save_alt),
                      label: const Text('保存 TXT'),
                    ),
                    TextButton.icon(
                      onPressed: () => action(
                        () => c.bridge.share(
                          text: c.result.text,
                          origin: origin(),
                        ),
                      ),
                      icon: const Icon(Icons.ios_share),
                      label: const Text('分享文本'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
        child: SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () => action(() async {
              await c.copyResult();
              message('已复制当前全文');
            }),
            icon: const Icon(Icons.copy_all_rounded),
            label: const Text('复制全部'),
          ),
        ),
      ),
    ],
  );
  String stateName(String value) => switch (value) {
    'running' => '转换中',
    'succeeded' => '已完成',
    'interrupted' => '上次转换中断',
    'cancelled' => '已取消',
    'failed' => '未完成',
    _ => '等待中',
  };
  Widget taskPage() => page([
    title('你的转换记录', '结果保存在本机。随时保存、分享，或重新转换。'),
    if (c.busy)
      TextButton.icon(
        onPressed: c.cancel,
        icon: const Icon(Icons.stop_circle_outlined),
        label: const Text('停止当前任务'),
      ),
    if (c.history.isEmpty)
      card(
        const Column(
          children: [
            Icon(Icons.task_alt_outlined, size: 48),
            SizedBox(height: 16),
            Text('还没有转换任务'),
            SizedBox(height: 8),
            Text('选择文件并转换后，结果会保存在这里。', textAlign: TextAlign.center),
          ],
        ),
      ),
    ...c.history.map(
      (r) => Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: card(
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                p.basename(r.inputPath),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text(
                '${stateName(r.state)} · ${r.target?.toUpperCase() ?? ''} · ${r.viaRemote == true
                    ? '服务端'
                    : r.viaRemote == false
                    ? '本机'
                    : '处理方式待确认'}',
              ),
              if (r.createdAt != null)
                Text(
                  r.createdAt!.toLocal().toString().substring(0, 16),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              if (r.error != null) ...[
                const SizedBox(height: 8),
                Text(
                  r.error!,
                  style: TextStyle(
                    color: Theme.of(context).colorScheme.error,
                    height: 1.5,
                  ),
                ),
              ],
              ...r.warnings.map(
                (w) => Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text('提示：$w', style: const TextStyle(height: 1.5)),
                ),
              ),
              ...r.outputPaths.map(
                (path) => Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(p.basename(path)),
                      Wrap(
                        spacing: 4,
                        runSpacing: 4,
                        children: [
                          TextButton.icon(
                            onPressed: () => action(() async {
                              if (await c.bridge.saveBytes(
                                p.basename(path),
                                await File(path).readAsBytes(),
                                mimeType: c.bridge.mime(path),
                              )) {
                                message('已保存文件');
                              }
                            }),
                            icon: const Icon(Icons.save_alt),
                            label: const Text('保存'),
                          ),
                          TextButton.icon(
                            onPressed: () => action(
                              () =>
                                  c.bridge.share(path: path, origin: origin()),
                            ),
                            icon: const Icon(Icons.ios_share),
                            label: const Text('分享'),
                          ),
                          if ([
                            '.png',
                            '.jpg',
                            '.jpeg',
                          ].contains(p.extension(path).toLowerCase()))
                            TextButton(
                              onPressed: () => action(() async {
                                await c.bridge.saveGallery(path);
                                message('已保存到相册');
                              }),
                              child: const Text('存入相册'),
                            ),
                          if ([
                            '.txt',
                            '.md',
                            '.tex',
                            '.csv',
                            '.json',
                          ].contains(p.extension(path).toLowerCase()))
                            TextButton(
                              onPressed: () => action(() async {
                                await replaceResult(
                                  decodeTextBytes(
                                    await File(path).readAsBytes(),
                                  ),
                                );
                                setState(() => tab = 1);
                              }),
                              child: const Text('打开校对'),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              if (r.category != null && r.target != null && !c.busy)
                TextButton.icon(
                  onPressed: () => action(
                    () => c.runBatch(
                      category: r.category!,
                      target: r.target!,
                      options: Map<String, dynamic>.of(r.options)
                        ..remove('_force_remote'),
                      forceRemote:
                          r.options['_force_remote'] == true ||
                          r.viaRemote == true,
                      consent: consent,
                      files: [r.inputPath],
                    ),
                  ),
                  icon: const Icon(Icons.refresh),
                  label: const Text('重新转换'),
                ),
            ],
          ),
        ),
      ),
    ),
    if (c.history.isNotEmpty)
      TextButton(
        onPressed: () => action(() async {
          if (await confirm('清空任务记录？', '仅清空列表，应用内的原文件与转换结果会保留。', yes: '清空记录')) {
            await c.clearHistory();
          }
        }),
        child: const Text('清空任务记录'),
      ),
  ]);
  Widget settingsPage() => page([
    title('按你的方式使用', '无需账号。本机处理无需联网，上传始终由你确认。'),
    card(
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('转换服务', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          const Text('复杂文档、扫描件或公式识别可连接你信任的服务。', style: TextStyle(height: 1.5)),
          space(),
          TextField(
            key: const Key('serverUrl'),
            controller: server,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: '服务地址',
              hintText: 'https://你的服务地址',
            ),
          ),
          space(),
          OutlinedButton(
            onPressed: () => action(() async {
              await c.setServer(server.text);
              message('服务地址已保存');
            }),
            child: const Text('保存地址'),
          ),
          TextButton.icon(
            onPressed: working
                ? null
                : () => action(() async {
                    await c.setServer(server.text);
                    if (await confirm(
                      '检查服务能力？',
                      '仅向 ${c.serverUrl} 查询支持格式、大小和保留期限，不会发送文件。',
                      yes: '查询能力',
                    )) {
                      await c.checkService();
                      message('已读取服务的实际能力');
                    }
                  }),
            icon: const Icon(Icons.wifi_find),
            label: const Text('检查服务能力'),
          ),
          Text(
            c.serverUrl.isEmpty ? '尚未配置：你仍可使用本机转换和文字识别。' : c.policyText(),
            style: const TextStyle(height: 1.6),
          ),
          if (c.capabilities != null)
            ExpansionTile(
              title: const Text('查看实际可用格式'),
              tilePadding: EdgeInsets.zero,
              children: [
                ...((c.capabilities!['categories'] as Map?) ?? {}).entries.map(
                  (e) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      '${categoryNames[ConversionCategory.values.where((v) => v.name == e.key).firstOrNull] ?? '文本'}：${((e.value as Map)['pairs'] as List? ?? []).whereType<Map>().where((pair) => pair['ready'] == true).map((pair) => '${pair['source']} → ${pair['target']}').join('、')}',
                      style: const TextStyle(height: 1.5),
                    ),
                  ),
                ),
              ],
            ),
        ],
      ),
    ),
    space(),
    card(
      Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('外观', style: TextStyle(fontWeight: FontWeight.w700)),
          space(),
          DropdownButtonFormField<String>(
            initialValue: c.theme,
            decoration: const InputDecoration(labelText: '显示模式'),
            items: const [
              DropdownMenuItem(value: 'system', child: Text('跟随系统')),
              DropdownMenuItem(value: 'light', child: Text('浅色')),
              DropdownMenuItem(value: 'dark', child: Text('深色')),
            ],
            onChanged: (value) {
              c.theme = value!;
              c.persist();
              c.notifyListeners();
            },
          ),
        ],
      ),
    ),
    space(),
    card(
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(Icons.privacy_tip_outlined),
            title: Text('文件由你掌控'),
            subtitle: Text(
              '选择的文件与校对草稿保存在应用内。卸载应用会移除本机数据，请先保存重要结果。',
              style: TextStyle(height: 1.5),
            ),
          ),
          TextButton(
            onPressed: () => showLicensePage(
              context: context,
              applicationName: '格式工厂',
              applicationVersion: '0.1.0',
              applicationLegalese: '含 Noto Sans SC · SIL Open Font License',
            ),
            child: const Text('开源许可'),
          ),
        ],
      ),
    ),
  ]);
}
