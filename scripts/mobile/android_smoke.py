"""Exercise the installed release app on this project's disposable Android AVD.

Run from the process-local env.ps1 environment. Uses Android's document provider,
not broad storage permission or a debug-only back door into the app.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SDK = Path(os.environ["ANDROID_HOME"])
ADB = SDK / "platform-tools" / "adb.exe"
SERIAL = "emulator-5554"
APP = "dev.formatfactory.mobile"
ACTIVITY = APP + "/dev.formatfactory.format_factory_mobile.MainActivity"
OUT = ROOT / "deliverables/mobile"
WORK = ROOT / ".work/mobile-smoke"


def adb(*arguments, binary=False):
    result = subprocess.run([str(ADB), "-s", SERIAL, *map(str, arguments)], check=True, capture_output=True, timeout=40)
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace")


def tree():
    adb("shell", "uiautomator", "dump", "/sdcard/factory-smoke.xml")
    data = adb("exec-out", "cat", "/sdcard/factory-smoke.xml")
    return ET.fromstring(data)


def descriptions(root):
    return [node.get("content-desc", "") + node.get("text", "") for node in root.iter("node")]


def wait_text(text, attempts=6):
    for _ in range(attempts):
        root = tree()
        if any(text in value for value in descriptions(root)):
            return root
        time.sleep(0.5)
    raise AssertionError(f"Screen does not contain {text!r}: {descriptions(root)}")


def tap(text, scroll=False):
    for _ in range(6 if scroll else 1):
        root = tree()
        for node in root.iter("node"):
            label = node.get("content-desc", "") or node.get("text", "")
            if (label == text or label.startswith(text + "\n")) and node.get("clickable") == "true":
                x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds", "")))
                adb("shell", "input", "tap", (x1 + x2) // 2, (y1 + y2) // 2)
                return
        if scroll:
            adb("shell", "input", "swipe", "540", "1900", "540", "650", "350")
    raise AssertionError(f"Button not found: {text}")


def screenshot(name):
    data = adb("exec-out", "screencap", "-p", binary=True)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    (OUT / "previews" / name).write_bytes(data)


def tap_any_label(text, long_press=False):
    root = tree()
    for node in root.iter("node"):
        if text in {node.get("content-desc"), node.get("text")}:
            x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds", "")))
            x, y = (x1 + x2) // 2, (y1 + y2) // 2
            if long_press:
                adb("shell", "input", "swipe", x, y, x, y, "900")
            else:
                adb("shell", "input", "tap", x, y)
            return
    raise AssertionError(f"System label not found: {text}")


def share(name, mime, cold=False):
    if cold:
        adb("shell", "am", "force-stop", APP)
    # A shell-created document URI has no grant to transfer. Use the real Files
    # app so Android grants the URI exactly as in a user's share action.
    adb("shell", "am", "start", "-n", "com.google.android.documentsui/com.android.documentsui.files.FilesActivity")
    current = tree()
    if any(node.get("content-desc") == "Cancel" for node in current.iter("node")):
        tap_any_label("Cancel")
    wait_text(name)
    tap_any_label(name, long_press=True)
    tap_any_label("Share")
    wait_text("格式转换工厂")
    tap_any_label("格式转换工厂")


def main():
    assert SERIAL.startswith("emulator-")
    assert adb("shell", "getprop", "ro.kernel.qemu").strip() == "1", "Use only the project AVD"
    assert (ROOT / ".work/mobile-emulator.pid").exists(), "Start the project AVD first"
    assert adb("shell", "pm", "clear", APP).strip() == "Success", "Reset only this app's synthetic AVD data"
    WORK.mkdir(parents=True, exist_ok=True)
    (OUT / "previews").mkdir(parents=True, exist_ok=True)
    csv = WORK / "factory-smoke.csv"
    csv.write_text("姓名,编号\r\n张三,001234567890123456789\r\n", encoding="utf-8")
    adb("push", csv, "/sdcard/Download/factory-smoke.csv")
    share("factory-smoke.csv", "text/csv", cold=True)
    wait_text("factory-smoke.csv")
    tap("表格")
    tap("开始转换", scroll=True)
    wait_text("转换完成")
    tap("任务")
    wait_text("已完成 · XLSX · 本机")
    screenshot("06-android-release-tasks.png")
    tap("转换")
    # A second share uses the same provider URI/name with changed content.
    csv.write_text("姓名,编号\r\n李四,009876543210987654321\r\n", encoding="utf-8")
    adb("push", csv, "/sdcard/Download/factory-smoke.csv")
    share("factory-smoke.csv", "text/csv")
    for _ in range(6):
        root = tree()
        if sum("factory-smoke.csv" in value for value in descriptions(root)) >= 2:
            break
        time.sleep(0.5)
    else:
        raise AssertionError("Updated file with the same name was not imported")
    image = ROOT / ".work/native-share.png"
    adb("push", image, "/sdcard/Download/native-share.png")
    share("native-share.png", "image/png")
    wait_text("native-share.png")
    screenshot("07-android-release-share.png")
    adb("shell", "am", "start", "-a", "android.intent.action.SEND", "-t", "text/plain",
        "--es", "android.intent.extra.TEXT", "Factory_Text_123", "-n", ACTIVITY)
    tap("文本")
    wait_text("Factory_Text_123")
    tap("原文 / LaTeX 原样保留", scroll=True)
    tap("复制全部")
    wait_text("已复制当前全文")
    screenshot("08-android-release-text.png")
    report = {"platform": "Android 15 emulator", "package": APP, "source": "real Android Files app share UI",
              "checks": ["cold content-URI CSV import", "real offline CSV to XLSX through release UI",
                         "changed same-name CSV import", "hot content-URI PNG import",
                         "literal text share and copy action"], "passed": True}
    (OUT / "android-release-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
