import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    guard let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "FactorySharedFiles") else { return }
    let channel = FlutterMethodChannel(name: "factory/shared_files", binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      guard call.method == "acknowledge", let imported = call.arguments as? [String: Any],
            let paths = imported["paths"] as? [String], let texts = imported["texts"] as? [String],
            let group = Bundle.main.object(forInfoDictionaryKey: "AppGroupId") as? String,
            let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group) else {
        result(FlutterMethodNotImplemented)
        return
      }
      let inbox = container.appendingPathComponent("Inbox", isDirectory: true).resolvingSymlinksInPath().path + "/"
      if let defaults = UserDefaults(suiteName: group), let payload = defaults.data(forKey: "ShareKey"),
         let pending = try? JSONSerialization.jsonObject(with: payload) as? [[String: String]] {
        let remaining = pending.filter { record in
          guard let path = record["path"] else { return true }
          if record["type"] == "text" { return !texts.contains(path) }
          return !paths.contains(path) && !paths.contains(path.replacingOccurrences(of: "file://", with: ""))
        }
        if let data = try? JSONSerialization.data(withJSONObject: remaining) {
          defaults.set(data, forKey: "ShareKey")
          defaults.set(!remaining.isEmpty, forKey: "FactoryPendingShare")
        }
      }
      for path in paths {
        let url = URL(fileURLWithPath: path).resolvingSymlinksInPath()
        if url.path.hasPrefix(inbox) { try? FileManager.default.removeItem(at: url) }
      }
      result(nil)
    }
  }
}
