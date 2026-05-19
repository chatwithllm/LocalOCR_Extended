import AppKit

/// NSApplicationDelegate for LocalOCR macOS.
///
/// Phase 1: empty method stubs that compile. Concrete wiring:
///   - Phase 3 (auth): foreground session refresh
///   - Phase 5 (native): global shortcut registration, Dock drop handling,
///                       menu bar item, hide-instead-of-quit behaviour
final class AppDelegate: NSObject, NSApplicationDelegate {

    func applicationDidFinishLaunching(_ notification: Notification) {
        // TODO Phase 5: register GlobalShortcutManager, MenuBarController.
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        Task { @MainActor in
            BackgroundFetchScheduler.shared.foregroundRefresh()
        }
    }

    /// Files dropped onto the Dock icon arrive here.
    func application(_ application: NSApplication, open urls: [URL]) {
        // TODO Phase 5: forward to Router (file drops → OCR upload sheet; localocr:// → handleURL).
    }

    /// Return false so closing the last window hides the app rather than quitting
    /// (matches §3.2 main window spec + §4.7 window management).
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}
