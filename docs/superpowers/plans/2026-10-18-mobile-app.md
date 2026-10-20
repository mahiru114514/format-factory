# Mobile Format Factory Implementation Plan

> **For agentic workers:** Use subagent-driven-development for isolated implementation units, with spec review followed by quality review. Stay in this session and execute continuously. There is no Git repository; preserve the desktop deliverable and edit only assigned directories.

**Goal:** Build a genuine Flutter Android/iOS app with offline text editing/copy, local conversions, optional consented conversion jobs and an installable Android test package.

**Architecture:** Flutter UI calls a local conversion service first. Native adapters handle system file/photo sharing and on-device OCR/codecs. A separately runnable Python HTTP service provides bounded, isolated conversion jobs for complex document/recognition routes, reusing existing engines without changing desktop UI.

**Tech Stack:** Flutter stable/Dart, Android SDK + Java 21, Dart image/excel/csv/pdf/archive/xml packages, native mobile OCR/codec plugins, FastAPI, existing Python conversion engines, LibreOffice for portable Word/PDF rendering.

## Files and responsibilities

- `.tools/`: project-local Flutter and Android SDK; excluded from deliverables.
- `mobile/`: generated real Flutter project with Android and iOS platform sources.
- `mobile/lib/core/`: models, local converters, LaTeX text parser, task state, filesystem and consented server client.
- `mobile/lib/ui/`: responsive mobile shell, conversion workspace, editable text workspace, task history and settings.
- `mobile/android/`, `mobile/ios/`: application identity, permissions, share/file integration, on-device OCR dependencies and native codec capabilities.
- `mobile/assets/`: app mark, openly licensed bundled Chinese PDF font and notices.
- `mobile/test/`: actual conversion, lossless copy/edit, cancellation, consent and widget tests.
- `mobile_server/`: independent API, worker processes, isolated storage, cleanup, configuration, deployment instructions and tests.
- `scripts/mobile/`: environment setup, analysis/test/build scripts and verification helpers.
- `deliverables/mobile/`: Android APK, checksums and user installation instructions; iOS source/build instructions, without claiming an unbuilt IPA.

## Task 1 — independent service

- [x] Write `mobile_server/tests/` first: reject absent consent, wrong actual file type, oversized input and unsupported conversions; prevent cross-task access and path traversal; verify task status, result retrieval, explicit acknowledgement deletion and expiry.
- [x] Run `.venv/Scripts/python.exe -m pytest mobile_server/tests -q` to observe absent functionality, then implement a FastAPI factory with configurable storage/limits and process-isolated workers.
- [x] Contract: `GET /v1/capabilities`; `POST /v1/jobs` multipart fields `file`, `category`, `target`, `options` JSON and `consent=true`; return `id` and secret `token`. Authenticated `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/result`, `DELETE /v1/jobs/{id}`. Authorization uses `Bearer <job token>`. All results are ZIP bundles, including UTF-8 TXT inside the bundle for recognition. The client confirms local persistence before DELETE.
- [x] Categories `documents`, `tables`, `images`, `text`; text options `method=ocr|formula`, `page=0` (zero based). File limits 50 MiB, processing timeout 120 seconds, retention 1 hour are reported as actual server capabilities.
- [x] Use portable sandboxed Pandoc/LibreOffice adapters, validate DOCX external resources, never fetch user-specified URLs, isolate output paths and do not use desktop Word COM in the server route. Service availability reflects installed engines, not invented readiness.
- [x] Verify real local conversions and API lifecycle; perform spec review then quality review and fix important findings.

## Task 2 — toolchain and app foundations

- [x] Download official stable Flutter/Android tooling to `.tools`, verify published checksums, set process-local caches and Java/SDK paths, generate the mobile project for Android and iOS. Flutter 3.47.7 / Dart 3.13.5 / Android API 36 / NDK 28.2.13676358 / Java 21.
- [x] Add locked Flutter dependencies and a bundled open-license Chinese font; do not redistribute Windows system fonts.
- [x] Implement tests before converters: exact LaTeX source preservation and unknown-command retention, editable result dirty/selection state, Unicode/GB18030 table handling, long IDs/leading zeros, multiple worksheets, EXIF rotation/transparency and unique filenames.
- [x] Implement local image, table and basic document conversions behind one typed `ConversionRequest` / `ConversionResult` interface. Tests reopen generated files. Unsupported hardware codecs raise explicit local-unavailable results and never silently upload.
- [x] Implement HTTP job client tests proving that denied/missing consent sends no request; require HTTPS except explicit numeric loopback/private-network development addresses, disable unsafe redirects, check deadlines/size and persist results before requesting remote deletion.
- [x] Run `flutter analyze` and `flutter test`; perform spec review then code quality review.

## Task 3 — mobile interface and platform adapters

- [x] Add widget tests before UI: all four tabs, conversion validation, offline operation, edited copy/save equality, selection-only copy, protecting dirty results, upload consent dialog cancellation and unconfigured service state.
- [x] Build polished touch-first Chinese screens: conversion categories/options, file/photo input, source preview, editable recognition results with fixed copy actions, task history and server/privacy settings. Batch failures are independent, and cancelling stops subsequent jobs.
- [x] Add Android and iOS system file/photo/camera permissions, incoming file/share handling, result export/sharing, on-device Chinese/English OCR and HEIC capability handling. Explain platform differences in product copy without developer implementation jargon.
- [x] Test long text, narrow width, keyboard, dark/large font accessibility and local task recovery. Save preview screenshots by widget rendering.
- [x] Review spec coverage and code quality; fix defects before packaging.

## Task 4 — installable delivery and verification

- [x] Run the full mobile/service test suites, desktop regression tests where shared engines changed, and a live API/client integration test against generated files.
- [x] Build Android APK and inspect package metadata, signing certificate and checksum. Try emulator/device verification only if an actual target is available; report build verification and device verification separately.
- [x] Prepare iOS build/signing instructions and platform source checks. iOS is not marked installable without macOS/Xcode compilation and signing.
- [x] Document starting the local test service, entering its LAN address, upload/deletion behavior, unsupported codec handling and practical limitations. Public service deployment and store publication remain separate authorized actions.
- [x] Deliver concrete artifact paths and an honest verification report, update checklists only for achieved items, keep the existing desktop app intact.

## Acceptance tests (representative contracts)

```python
def test_no_consent_upload(client):
    response = client.post('/v1/jobs', files={'file': ('a.txt', b'hello', 'text/plain')},
                           data={'category': 'documents', 'target': 'docx', 'consent': 'false'})
    assert response.status_code == 403
```

```dart
test('copy reads the current edited result', () {
  final state = EditableResult()..accept(r'\alpha');
  state.edit('校对后 α\n第二行');
  expect(state.copyText(), '校对后 α\n第二行');
  expect(state.dirty, isTrue);
});
```

No credentials, guessed server addresses, mocked success screens or web previews may substitute for a working conversion, an Android build or an iOS build.

## Verified progress (2026-10-18)

- Service: independent spec and quality reviews passed. Root final combined regression: 108 passed / 1 skipped (59 service + 49 desktop; Windows LibreOffice integration unconfigured).
- Linux Docker service is verified: real Flutter client Chinese CSV -> XLSX -> CSV and DOCX -> PDF -> DOCX -> TXT; real PNG -> HEIC -> JPEG; ordinary Chinese/English OCR and formula image -> UTF-8 TXT; remote directories empty after acknowledgement. Windows standalone LibreOffice timeout is bypassed by this tested Linux route.
- Core: final 31 tests, independent spec and quality reviews passed. The result archive/input mismatch is fixed with real 51 MiB download/persist/CRC/ack coverage: separate 224 MiB result ZIP / 200 MiB expanded / 50 MiB input limits. Root final complete mobile suite: 46 passed / 2 intentionally skipped live-service cases, analyzer clean.
- UI: 15 tests passed; spec and quality approved after formula task history, typed text-file shares, same-name updates and deleted-cache duplicate callbacks were fixed. Controlled Apache-2.0 Android sharing plugin patch retains upstream iOS unchanged.
- Android final release APK built (107,697,060 bytes), v2 development signature verified, minimum API24/target36 and checksums inspected. The exact final build was installed and passed real Files-app cold CSV share -> local XLSX task, changed same-name CSV, warm PNG share and literal text/copy; screenshots saved. Earlier native integration passed Chinese/English OCR, WebP width600 and seven-page Chinese PDF preview. Physical phone compatibility remains unverified.
- iOS: native source integrity checks passed; macOS/Xcode compilation, signing and physical-device checks remain explicitly unverified.
- Delivery: APK, portable client source ZIP, installation guide, verification report and evidence in `deliverables/mobile/`; local test service start/stop verified, no public deployment or store publication performed.
