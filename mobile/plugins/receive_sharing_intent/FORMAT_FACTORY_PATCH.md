# Local Android sharing fix for Format Factory

Upstream: receive_sharing_intent 1.8.1 by Kasem Jaffer.
Source: https://github.com/KasemJaffer/receive_sharing_intent
License: Apache-2.0; the original LICENSE, README, CHANGELOG and iOS implementation are retained.

Local modifications (2026-10-18):

- Android content:// and file:// streams are copied through ContentResolver into separate private cache directories. No DocumentsContract/_data/external-storage path is fabricated. Basenames and exact bytes are preserved after filename safety checks.
- Each source is bounded to 50 MiB both from advisory SIZE and the actual stream; at most 20 URI items are accepted per intent. Failed partial copies are removed. Duplicate display names cannot overwrite each other.
- Provider queries and copying run on one background worker. Channel events and state changes run on the main thread. Cold getInitialMedia waits for the initial import, receives errors on failure, and an event listener replays all currently unacknowledged entries.
- EXTRA_TEXT remains literal text, while a text/* URI is emitted as a file.
- The app calls acknowledgeFiles with only paths/text already durably imported. Cleanup checks exact canonical paths inside this plugin's own two-level cache tree, removes only the acknowledged file and its empty directory, and filters only matching pending records. reset never deletes cache files. New or failed imports are retained.
- Video thumbnail extraction was removed because this app does not consume video thumbnails; shared media bytes are unchanged.
- iOS source is unchanged. Dart uses the same API and behavior, with only its part-of directive modernized to a URI; Format Factory's NativeBridge uses the Android acknowledgement extension. iOS keeps its existing app-group acknowledgement and plugin reset behavior.

Native tests: android/src/test/.../ShareCacheIoTest.kt covers streamed byte bounds, distinct same-name copies and safe Unicode names. Final Android APK must additionally be verified with a granted ACTION_SEND/ACTION_VIEW document-provider content URI, cold and warm.

