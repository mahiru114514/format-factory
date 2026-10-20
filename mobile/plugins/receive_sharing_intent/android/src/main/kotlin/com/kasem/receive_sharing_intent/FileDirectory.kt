package com.kasem.receive_sharing_intent

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import android.webkit.MimeTypeMap
import java.io.File
import java.io.FileOutputStream
import java.io.IOException

/**
 * Format Factory patch of the Apache-2.0 upstream FileDirectory helper.
 * Original SAF path helper credited @author paulburke by upstream Kasem Jaffer.
 * Never derive a filesystem path from DocumentsContract IDs or `_data`.
 */
object FileDirectory {
    private const val CACHE_ROOT = "factory_shared"

    fun cacheUri(context: Context, uri: Uri, mimeType: String?): String {
        if (uri.scheme != "content" && uri.scheme != "file") {
            throw IOException("不支持的分享文件地址")
        }
        val resolver = context.contentResolver
        var displayName: String? = null
        var declaredSize: Long? = null
        if (uri.scheme == "content") {
            // Provider metadata is advisory. The streamed byte bound is enforced
            // even when SIZE is absent, incorrect, or changes while downloading.
            try { resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val name = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (name >= 0 && !cursor.isNull(name)) displayName = cursor.getString(name)
                    val size = cursor.getColumnIndex(OpenableColumns.SIZE)
                    if (size >= 0 && !cursor.isNull(size)) declaredSize = cursor.getLong(size)
                }
            } } catch (_: Exception) { /* A provider may permit the stream without metadata queries. */ }
        } else {
            displayName = uri.path?.let { File(it).name }
        }
        if ((declaredSize ?: -1) > ShareCacheIo.MAX_BYTES) throw IOException("分享文件超过 50 MiB，未导入")
        val extension = MimeTypeMap.getSingleton().getExtensionFromMimeType(mimeType)
        val fallback = if (extension.isNullOrBlank()) "分享文件" else "分享文件.$extension"
        val directory = ShareCacheIo.uniqueDirectory(File(context.cacheDir, CACHE_ROOT))
        val target = File(directory, ShareCacheIo.safeName(displayName, fallback))
        try {
            val input = resolver.openInputStream(uri) ?: throw IOException("无法读取分享文件")
            input.use { source ->
                FileOutputStream(target).use { output ->
                    ShareCacheIo.copyBounded(source, output)
                    output.fd.sync()
                }
            }
            return target.absolutePath
        } catch (error: Exception) {
            target.delete()
            directory.delete()
            throw error
        }
    }

    /** Only an exact regular file inside our own unique share cache may be removed. */
    fun acknowledge(context: Context, path: String) {
        val root = File(context.cacheDir, CACHE_ROOT).canonicalFile
        val file = File(path).canonicalFile
        if (!file.path.startsWith(root.path + File.separator) || file.parentFile?.parentFile != root) {
            throw IOException("拒绝清理分享缓存以外的文件")
        }
        if (file.exists() && (!file.isFile || !file.delete())) throw IOException("无法清理已导入的分享缓存")
        file.parentFile?.delete() // Non-recursive: another file is never removed.
    }
}
