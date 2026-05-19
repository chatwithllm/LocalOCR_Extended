import AppKit
import os.log

/// Registers ⌃⌘R as a global shortcut that opens OCR Upload from anywhere (§2.3 win #1).
/// Uses NSEvent.addGlobalMonitorForEvents — requires Accessibility permission.
@MainActor
final class GlobalShortcutManager {

    static let shared = GlobalShortcutManager()

    private var globalMonitor: Any?
    private var localMonitor: Any?
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "global-shortcut")

    private let targetKeyCode: UInt16 = 15   // R
    private let targetModifiers: NSEvent.ModifierFlags = [.control, .command]

    private init() {}

    /// Called from AppDelegate.applicationDidFinishLaunching. Registers monitors
    /// if Accessibility permission is granted; otherwise prompts the user (one time).
    func register() {
        guard PreferencesStore.shared.globalShortcutEnabled else { return }

        guard AXIsProcessTrusted() else {
            requestAccessibilityPermissionIfNeeded()
            return
        }

        if globalMonitor == nil {
            globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
                self?.handle(event: event)
            }
        }
        if localMonitor == nil {
            localMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                self?.handle(event: event)
                return event
            }
        }
        logger.info("Global shortcut ⌃⌘R registered.")
    }

    func unregister() {
        if let g = globalMonitor { NSEvent.removeMonitor(g); globalMonitor = nil }
        if let l = localMonitor  { NSEvent.removeMonitor(l); localMonitor  = nil }
    }

    private func handle(event: NSEvent) {
        guard event.keyCode == targetKeyCode else { return }
        let mods = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        guard mods == targetModifiers else { return }
        NotificationCenter.default.post(name: .globalShortcutReceiptUpload, object: nil)
    }

    private func requestAccessibilityPermissionIfNeeded() {
        let prefs = PreferencesStore.shared
        guard !prefs.accessibilityPromptShown else { return }
        prefs.accessibilityPromptShown = true

        let alert = NSAlert()
        alert.messageText = "Accessibility access required"
        alert.informativeText = "LocalOCR needs Accessibility access to register the ⌃⌘R global shortcut for receipt upload from any app. You can grant this in System Settings → Privacy & Security → Accessibility."
        alert.addButton(withTitle: "Open System Settings")
        alert.addButton(withTitle: "Not Now")
        alert.alertStyle = .informational
        if alert.runModal() == .alertFirstButtonReturn {
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
                NSWorkspace.shared.open(url)
            }
        }
    }
}
