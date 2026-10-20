package com.kasem.receive_sharing_intent

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.Parcelable
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.MethodChannel.MethodCallHandler
import io.flutter.plugin.common.MethodChannel.Result
import io.flutter.plugin.common.PluginRegistry.NewIntentListener
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLConnection
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

// Local Format Factory Android patch of Kasem Jaffer's Apache-2.0 plugin 1.8.1.
private const val MESSAGES_CHANNEL = "receive_sharing_intent/messages"
private const val EVENTS_CHANNEL_MEDIA = "receive_sharing_intent/events-media"
private const val EVENTS_CHANNEL_TEXT = "receive_sharing_intent/events-text"

class ReceiveSharingIntentPlugin : FlutterPlugin, ActivityAware, MethodCallHandler,
    EventChannel.StreamHandler, NewIntentListener {
    // Channel callbacks and all pending-state changes occur only on the main thread.
    // Resolver queries, provider/cloud reads and writes use one ordered worker.
    private val main = Handler(Looper.getMainLooper())
    private lateinit var worker: ExecutorService
    private lateinit var applicationContext: Context
    private var attached = false
    private var initialScanPending = true
    private val initialWaiters = mutableListOf<Result>()
    private val acknowledgementWaiters = mutableSetOf<Result>()
    private var engineGeneration = 0
    private val pendingMedia = mutableListOf<JSONObject>()
    private var latestError: String? = null
    private var eventSinkMedia: EventChannel.EventSink? = null
    private var binding: ActivityPluginBinding? = null
    private lateinit var messages: MethodChannel
    private lateinit var eventsMedia: EventChannel
    private lateinit var eventsText: EventChannel

    private fun setupCallbackChannels(messenger: BinaryMessenger) {
        messages = MethodChannel(messenger, MESSAGES_CHANNEL).also { it.setMethodCallHandler(this) }
        eventsMedia = EventChannel(messenger, EVENTS_CHANNEL_MEDIA).also { it.setStreamHandler(this) }
        eventsText = EventChannel(messenger, EVENTS_CHANNEL_TEXT).also { it.setStreamHandler(this) }
    }

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        applicationContext = binding.applicationContext
        attached = true
        engineGeneration += 1
        initialScanPending = true
        worker = Executors.newSingleThreadExecutor { task ->
            Thread(task, "factory-share-import").apply { isDaemon = true }
        }
        setupCallbackChannels(binding.binaryMessenger)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        attached = false
        this.binding?.removeOnNewIntentListener(this)
        this.binding = null
        worker.shutdownNow()
        initialWaiters.toList().forEach { it.error("SHARE_ENGINE_DETACHED", "分享导入已中断，请重新打开应用", null) }
        initialWaiters.clear()
        acknowledgementWaiters.toList().forEach { it.error("SHARE_ENGINE_DETACHED", "分享缓存未清理，下次启动可重试", null) }
        acknowledgementWaiters.clear()
        eventSinkMedia = null
        messages.setMethodCallHandler(null)
        eventsMedia.setStreamHandler(null)
        eventsText.setStreamHandler(null)
    }

    override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
        eventSinkMedia = events
        // A cold import may finish before Dart subscribes. Replay unacknowledged
        // entries, which the app durably deduplicates before acknowledging them.
        publish()
    }

    override fun onCancel(arguments: Any?) { eventSinkMedia = null }

    override fun onMethodCall(call: MethodCall, result: Result) {
        if (!attached) {
            result.error("SHARE_ENGINE_DETACHED", "分享导入已中断，请重新打开应用", null)
            return
        }
        when (call.method) {
            "getInitialMedia" -> {
                if (initialScanPending) initialWaiters.add(result) else replySnapshot(result)
            }
            "acknowledgeFiles" -> acknowledge(call, result)
            "reset" -> {
                // Compatibility only: reset must never delete unacknowledged files.
                pendingMedia.clear()
                latestError = null
                result.success(null)
            }
            else -> result.notImplemented()
        }
    }

    private fun snapshot(): String? = if (pendingMedia.isEmpty()) null else JSONArray(pendingMedia).toString()

    private fun replySnapshot(result: Result) {
        if (pendingMedia.isEmpty() && latestError != null) result.error("SHARE_IMPORT_FAILED", latestError, null)
        else result.success(snapshot())
    }

    private fun finishInitial() {
        initialScanPending = false
        val waiters = initialWaiters.toList()
        initialWaiters.clear()
        waiters.forEach { replySnapshot(it) }
    }

    private fun publish() {
        latestError?.let { eventSinkMedia?.error("SHARE_IMPORT_FAILED", it, null) }
        snapshot()?.let { eventSinkMedia?.success(it) }
    }

    private fun handleIntent(intent: Intent, initial: Boolean): Boolean {
        if (intent.action !in listOf(Intent.ACTION_SEND, Intent.ACTION_SEND_MULTIPLE, Intent.ACTION_VIEW)) {
            if (initial) finishInitial()
            return false
        }
        val copy = Intent(intent)
        val generation = engineGeneration
        worker.execute {
            val loaded = try { loadMedia(copy) } catch (error: Exception) {
                Loaded(emptyList(), listOf(error.message ?: "无法读取分享内容"))
            }
            main.post {
                if (attached && engineGeneration == generation) {
                    pendingMedia.addAll(loaded.media)
                    latestError = loaded.errors.takeIf { it.isNotEmpty() }?.joinToString("；")
                    if (initial) finishInitial()
                    publish()
                }
            }
        }
        return true
    }

    private data class Loaded(val media: List<JSONObject>, val errors: List<String>)

    private fun loadMedia(intent: Intent): Loaded {
        val uris = when (intent.action) {
            Intent.ACTION_VIEW -> listOfNotNull(intent.data)
            Intent.ACTION_SEND -> listOfNotNull(intent.parcelable<Uri>(Intent.EXTRA_STREAM))
            Intent.ACTION_SEND_MULTIPLE -> intent.parcelableArrayList<Uri>(Intent.EXTRA_STREAM) ?: emptyList()
            else -> emptyList()
        }.ifEmpty {
            val clip = intent.clipData
            if (clip == null) emptyList() else {
                if (clip.itemCount > ShareCacheIo.MAX_ITEMS) throw IllegalArgumentException("一次最多分享 20 个文件")
                (0 until clip.itemCount).mapNotNull { clip.getItemAt(it).uri }
            }
        }.distinct()
        if (uris.size > ShareCacheIo.MAX_ITEMS) throw IllegalArgumentException("一次最多分享 20 个文件")
        if (uris.isEmpty()) {
            val text = intent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString()
                ?: intent.clipData?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.text?.toString()
            return Loaded(if (text == null) emptyList() else listOf(json(text, "text", intent.type)), emptyList())
        }
        val media = mutableListOf<JSONObject>()
        val errors = mutableListOf<String>()
        val mimeTypes = intent.getStringArrayExtra(Intent.EXTRA_MIME_TYPES)
        uris.forEachIndexed { index, uri ->
            try {
                if (uri.scheme in listOf("http", "https") && intent.action == Intent.ACTION_VIEW) {
                    media.add(json(uri.toString(), "url", intent.type))
                } else {
                    val resolvedType = try { applicationContext.contentResolver.getType(uri) } catch (_: Exception) { null }
                    val mime = resolvedType ?: mimeTypes?.getOrNull(index) ?: intent.type
                    val path = FileDirectory.cacheUri(applicationContext, uri, mime)
                    val actualType = mime ?: URLConnection.guessContentTypeFromName(path)
                    val type = when {
                        actualType?.startsWith("image/") == true -> "image"
                        actualType?.startsWith("video/") == true -> "video"
                        else -> "file" // A text/* URI is a file; only EXTRA_TEXT is literal text.
                    }
                    media.add(json(path, type, actualType))
                }
            } catch (error: Exception) {
                errors.add("第 ${index + 1} 个文件：${error.message ?: "无法导入，请重新分享"}")
            }
        }
        return Loaded(media, errors)
    }

    private fun json(path: String, type: String, mime: String?): JSONObject = JSONObject()
        .put("path", path).put("type", type).put("mimeType", mime)

    private fun acknowledge(call: MethodCall, result: Result) {
        val paths = call.argument<List<String>>("paths") ?: emptyList()
        val texts = call.argument<List<String>>("texts") ?: emptyList()
        acknowledgementWaiters.add(result)
        worker.execute {
            val deleted = mutableSetOf<String>()
            val errors = mutableListOf<String>()
            paths.forEach { path ->
                try { FileDirectory.acknowledge(applicationContext, path); deleted.add(path) }
                catch (error: Exception) { errors.add(error.message ?: "分享缓存清理失败") }
            }
            main.post {
                if (!acknowledgementWaiters.remove(result)) return@post
                if (attached) {
                    pendingMedia.removeAll { value ->
                        val path = value.optString("path")
                        path in deleted || (value.optString("type") in listOf("text", "url") && path in texts)
                    }
                    if (pendingMedia.isEmpty()) latestError = null
                    if (errors.isEmpty()) result.success(null)
                    else result.error("SHARE_CACHE_CLEANUP_FAILED", errors.joinToString("；"), null)
                } else result.error("SHARE_ENGINE_DETACHED", "分享缓存未清理，下次启动可重试", null)
            }
        }
    }

    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        this.binding = binding
        binding.addOnNewIntentListener(this)
        handleIntent(binding.activity.intent, true)
    }
    override fun onDetachedFromActivityForConfigChanges() { binding?.removeOnNewIntentListener(this); binding = null }
    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) {
        this.binding = binding
        binding.addOnNewIntentListener(this)
    }
    override fun onDetachedFromActivity() { binding?.removeOnNewIntentListener(this); binding = null }
    override fun onNewIntent(intent: Intent): Boolean = handleIntent(intent, false)

    inline fun <reified T : Parcelable> Intent.parcelable(key: String): T? = when {
        Build.VERSION.SDK_INT >= 33 -> getParcelableExtra(key, T::class.java)
        else -> @Suppress("DEPRECATION") getParcelableExtra<T>(key)
    }
    inline fun <reified T : Parcelable> Intent.parcelableArrayList(key: String): ArrayList<T>? = when {
        Build.VERSION.SDK_INT >= 33 -> getParcelableArrayListExtra(key, T::class.java)
        else -> @Suppress("DEPRECATION") getParcelableArrayListExtra<T>(key)
    }
}
