package com.kasem.receive_sharing_intent

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.nio.file.Files

class ShareCacheIoTest {
    @Test fun copiesExactBytesAndRejectsUntrustedLengthBeyondBound() {
        val bytes = byteArrayOf(0, 1, -1, 25, 10)
        val output = ByteArrayOutputStream()
        assertEquals(5L, ShareCacheIo.copyBounded(ByteArrayInputStream(bytes), output, 5))
        assertArrayEquals(bytes, output.toByteArray())
        val rejected = ByteArrayOutputStream()
        try {
            ShareCacheIo.copyBounded(ByteArrayInputStream(bytes), rejected, 4)
            fail("The streamed bound must be checked without provider metadata")
        } catch (_: IOException) { assertTrue(rejected.size() <= 4) }
        assertEquals(50L * 1024 * 1024, ShareCacheIo.MAX_BYTES)
        assertEquals(20, ShareCacheIo.MAX_ITEMS)
    }
    @Test fun sameNamedFilesUseIndependentDirectories() {
        val parent = Files.createTempDirectory("share-unit-").toFile()
        val a = ShareCacheIo.uniqueDirectory(parent)
        val b = ShareCacheIo.uniqueDirectory(parent)
        try {
            File(a, "报告.csv").writeText("A,100")
            File(b, "报告.csv").writeText("B,200")
            assertNotEquals(a, b)
            assertEquals("A,100", File(a, "报告.csv").readText())
            assertEquals("B,200", File(b, "报告.csv").readText())
        } finally { File(a,"报告.csv").delete(); File(b,"报告.csv").delete(); a.delete(); b.delete(); parent.delete() }
    }
    @Test fun namesPreserveChineseAndExtensionWithoutTraversalOrUtf8Overflow() {
        assertEquals("中文报告.csv", ShareCacheIo.safeName("../../ignored\\中文报告.csv", "分享文件"))
        val name = ShareCacheIo.safeName("中".repeat(200) + ".tiff", "分享文件")
        assertTrue(name.endsWith(".tiff"))
        assertTrue(name.toByteArray(Charsets.UTF_8).size <= 240)
        assertFalse(name.contains('/'))
        assertEquals("分享文件", ShareCacheIo.safeName("..", "分享文件"))
    }
}
