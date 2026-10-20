package com.kasem.receive_sharing_intent

import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.io.IOException
import java.util.UUID

/** Local Format Factory patch; upstream receive_sharing_intent is Apache-2.0. */
internal object ShareCacheIo {
    const val MAX_BYTES = 50L * 1024 * 1024
    const val MAX_ITEMS = 20

    fun uniqueDirectory(parent: File): File {
        if (!parent.isDirectory && !parent.mkdirs()) throw IOException("无法建立分享缓存目录")
        val directory = File(parent, "share-${UUID.randomUUID()}")
        if (!directory.mkdir()) throw IOException("无法建立独立分享缓存")
        return directory
    }

    fun safeName(value: String?, fallback: String): String {
        val leaf = (value ?: fallback).replace('\\', '/').substringAfterLast('/')
        val cleaned = leaf.map { if (it.code < 32 || it in "<>:\"/\\|?*") '_' else it }
            .joinToString("").trim().trimEnd('.', ' ')
            .takeUnless { it.isEmpty() || it == "." || it == ".." } ?: fallback
        if (cleaned.toByteArray(Charsets.UTF_8).size <= 240) return cleaned
        val extension = cleaned.substringAfterLast('.', "").take(16)
        val suffix = if (extension.isEmpty()) "" else ".$extension"
        val budget = 240 - suffix.toByteArray(Charsets.UTF_8).size
        val result = StringBuilder()
        var used = 0
        for (point in cleaned.substringBeforeLast('.', cleaned).codePoints().toArray()) {
            val piece = String(Character.toChars(point))
            val size = piece.toByteArray(Charsets.UTF_8).size
            if (used + size > budget) break
            result.append(piece)
            used += size
        }
        return result.toString() + suffix
    }

    fun copyBounded(input: InputStream, output: OutputStream, limit: Long = MAX_BYTES): Long {
        val buffer = ByteArray(64 * 1024)
        var count = 0L
        while (true) {
            if (Thread.currentThread().isInterrupted) throw IOException("分享导入已中断")
            val read = input.read(buffer)
            if (read == -1) break
            count += read
            if (count > limit) throw IOException("分享文件超过 50 MiB，未导入")
            output.write(buffer, 0, read)
        }
        output.flush()
        return count
    }
}
