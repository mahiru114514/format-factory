import Flutter
import UIKit
import receive_sharing_intent

class SceneDelegate: FlutterSceneDelegate {
  private var lastDeliveredShare: Data?
  override func sceneDidBecomeActive(_ scene: UIScene) {
    super.sceneDidBecomeActive(scene)
    // Share extensions save locally and ask the user to open the app. Avoid
    // unsupported extension-to-UIApplication launch tricks.
    guard let group = Bundle.main.object(forInfoDictionaryKey: "AppGroupId") as? String,
          let defaults = UserDefaults(suiteName: group),
          defaults.bool(forKey: "FactoryPendingShare"),
          let payload = defaults.data(forKey: "ShareKey"), payload != lastDeliveredShare,
          let identifier = Bundle.main.bundleIdentifier,
          let url = URL(string: "ShareMedia-\(identifier):share") else { return }
    _ = SwiftReceiveSharingIntentPlugin.instance.application(
      UIApplication.shared,
      didFinishLaunchingWithOptions: [UIApplication.LaunchOptionsKey.url: url])
    // Only the import acknowledgement clears pending records. A process kill
    // before the Dart-side durable copy can then safely retry next launch.
    lastDeliveredShare = payload
  }
}
