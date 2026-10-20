import UIKit
import UniformTypeIdentifiers

/// Saves selected attachments into the app group. No file leaves the device.
final class ShareViewController: UIViewController {
  private let label = UILabel()
  private let done = UIButton(type: .system)
  private var started = false

  override func viewDidLoad() {
    super.viewDidLoad()
    view.backgroundColor = .systemBackground
    label.numberOfLines = 0
    label.textAlignment = .center
    label.text = "正在存入格式转换工厂…"
    label.font = .preferredFont(forTextStyle: .body)
    label.adjustsFontForContentSizeCategory = true
    done.setTitle("完成", for: .normal)
    done.isEnabled = false
    done.addTarget(self, action: #selector(finish), for: .touchUpInside)
    let stack = UIStackView(arrangedSubviews: [label, done])
    stack.axis = .vertical
    stack.spacing = 24
    stack.translatesAutoresizingMaskIntoConstraints = false
    view.addSubview(stack)
    NSLayoutConstraint.activate([
      stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
      stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
      stack.centerYAnchor.constraint(equalTo: view.safeAreaLayoutGuide.centerYAnchor),
      done.heightAnchor.constraint(greaterThanOrEqualToConstant: 48)
    ])
  }

  override func viewDidAppear(_ animated: Bool) {
    super.viewDidAppear(animated)
    guard !started else { return }
    started = true
    Task { await importAttachments() }
  }

  @MainActor private func importAttachments() async {
    guard let groupID = Bundle.main.object(forInfoDictionaryKey: "AppGroupId") as? String,
          let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: groupID),
          let defaults = UserDefaults(suiteName: groupID) else {
      label.text = "无法存入文件，请检查 App 的共享权限配置。"
      done.isEnabled = true
      return
    }
    let providers = (extensionContext?.inputItems as? [NSExtensionItem] ?? []).flatMap { $0.attachments ?? [] }
    guard !providers.isEmpty, providers.count <= 20 else {
      label.text = "每次请选择 1 至 20 个文件或一段文字。"
      done.isEnabled = true
      return
    }
    let inbox = container.appendingPathComponent("Inbox", isDirectory: true)
    var records = [[String: String]]()
    var failures = 0
    for provider in providers {
      do {
        let record = try await load(provider, inbox: inbox)
        records.append(record)
      } catch { failures += 1 }
    }
    if !records.isEmpty {
      // Retain a previous unconsumed share instead of silently losing it.
      if defaults.bool(forKey: "FactoryPendingShare"), let old = defaults.data(forKey: "ShareKey"),
         let previous = try? JSONSerialization.jsonObject(with: old) as? [[String: String]] {
        records = previous + records
      }
      if let data = try? JSONSerialization.data(withJSONObject: records) {
        defaults.set(data, forKey: "ShareKey")
        defaults.set(true, forKey: "FactoryPendingShare")
      }
      label.text = "已存入格式转换工厂。\n打开 App 即可继续转换或核对文字。" + (failures > 0 ? "\n有 \(failures) 项未能读取，请重新选择。" : "")
    } else { label.text = "未能读取所选内容，请改用 App 内的选择文件入口。" }
    done.isEnabled = true
  }

  private func load(_ provider: NSItemProvider, inbox: URL) async throws -> [String: String] {
    // Text alone is a literal string. File-backed text documents retain their
    // original encoding and filename through the data representation route.
    let types = provider.registeredTypeIdentifiers
    let type = types.first { identifier in
      guard let value = UTType(identifier) else { return false }
      return value.conforms(to: .image) || value.conforms(to: .pdf) || value.conforms(to: .spreadsheet) || value.conforms(to: .zip)
    } ?? types.first { $0 != UTType.plainText.identifier && $0 != UTType.fileURL.identifier && UTType($0)?.conforms(to: .data) == true }
    func copyFile(_ url: URL, type: String) throws -> [String: String] {
      let scoped = url.startAccessingSecurityScopedResource()
      defer { if scoped { url.stopAccessingSecurityScopedResource() } }
      let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
      guard size > 0 && size <= 50 * 1024 * 1024 else { throw CocoaError(.fileReadTooLarge) }
      try FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
      var name = provider.suggestedName ?? url.lastPathComponent
      name = URL(fileURLWithPath: name).lastPathComponent
      if URL(fileURLWithPath: name).pathExtension.isEmpty {
        let ext = UTType(type)?.preferredFilenameExtension ?? url.pathExtension
        if !ext.isEmpty { name += "." + ext }
      }
      let destination = inbox.appendingPathComponent(UUID().uuidString + "_" + String(name.prefix(150)))
      try FileManager.default.copyItem(at: url, to: destination)
      // receive_sharing_intent 1.8 strips file:// without percent-decoding.
      // Match its native contract, retaining literal %, spaces and Chinese.
      return ["path": "file://" + destination.path, "type": UTType(type)?.conforms(to: .image) == true ? "image" : "file"]
    }
    if let type {
      return try await withCheckedThrowingContinuation { continuation in
        provider.loadFileRepresentation(forTypeIdentifier: type) { url, error in
          guard let url else { continuation.resume(throwing: error ?? CocoaError(.fileReadUnknown)); return }
          do {
            continuation.resume(returning: try copyFile(url, type: type))
          } catch { continuation.resume(throwing: error) }
        }
      }
    }
    if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
      return try await withCheckedThrowingContinuation { continuation in
        provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, error in
          guard let url = item as? URL else { continuation.resume(throwing: error ?? CocoaError(.fileReadUnknown)); return }
          do { continuation.resume(returning: try copyFile(url, type: UTType(filenameExtension: url.pathExtension)?.identifier ?? UTType.data.identifier)) }
          catch { continuation.resume(throwing: error) }
        }
      }
    }
    return try await withCheckedThrowingContinuation { continuation in
      provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { item, error in
        guard let text = item as? String else { continuation.resume(throwing: error ?? CocoaError(.fileReadUnknown)); return }
        guard text.utf8.count <= 2 * 1024 * 1024 else { continuation.resume(throwing: CocoaError(.fileReadTooLarge)); return }
        continuation.resume(returning: ["path": text, "type": "text", "mimeType": "text/plain"])
      }
    }
  }

  @objc private func finish() { extensionContext?.completeRequest(returningItems: nil) }
}
