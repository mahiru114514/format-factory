"""Package portable Flutter sources without this computer's caches or settings."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile"
OUT = ROOT / "deliverables" / "mobile"
SKIP_DIRS = {"build", ".dart_tool", ".gradle", ".idea", "Pods", ".symlinks", "ephemeral", "xcuserdata"}
SKIP_NAMES = {"local.properties", "key.properties", "Generated.xcconfig", "flutter_export_environment.sh", ".flutter-plugins-dependencies", "GeneratedPluginRegistrant.h", "GeneratedPluginRegistrant.m", "GeneratedPluginRegistrant.java"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / "格式转换工厂-手机工程源码.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(MOBILE.rglob("*")):
            relative = file.relative_to(MOBILE)
            if not file.is_file() or any(part in SKIP_DIRS for part in relative.parts):
                continue
            if file.name in SKIP_NAMES or file.suffix in {".iml", ".jks", ".keystore", ".pyc"}:
                continue
            archive.write(file, "mobile/" + relative.as_posix())
        for relative in ["THIRD_PARTY.md", "mobile_server/README.md", "docs/superpowers/specs/2026-10-18-mobile-app-design.md"]:
            archive.write(ROOT / relative, relative)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        for required in ["mobile/pubspec.lock", "mobile/lib/main.dart", "mobile/ios/Runner.xcodeproj/project.pbxproj", "mobile/ios/ShareExtension/ShareViewController.swift", "mobile/android/gradle/wrapper/gradle-wrapper.jar"]:
            assert required in names, required
        assert not any("local.properties" in n or "/.dart_tool/" in n or "/build/" in n for n in names)
    with destination.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {"file": destination.name, "bytes": destination.stat().st_size, "files": len(names), "sha256": checksum}
    (OUT / "source-package-info.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    sums = OUT / "SHA256SUMS.txt"
    previous = sums.read_text(encoding="utf-8-sig").splitlines() if sums.exists() else []
    lines = [line for line in previous if not line.endswith(destination.name)]
    sums.write_text("\n".join([*lines, f"{checksum}  {destination.name}"]) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
