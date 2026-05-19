import AppKit
import os.log

/// NSApplicationDelegate. Full impl wires Phase 5 native integrations.
final class AppDelegate: NSObject, NSApplicationDelegate {

    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "lifecycle")

    func applicationDidFinishLaunching(_ notification: Notification) {
        Task { @MainActor in
            // Native integrations (§4.6)
            MenuBarController.shared.install()
            GlobalShortcutManager.shared.register()
            DockBadge.shared.start()
            await NotificationManager.shared.requestAuthorizationIfNeeded()
            await NotificationManager.shared.scheduleShoppingNudge()
        }
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        Task { @MainActor in
            BackgroundFetchScheduler.shared.foregroundRefresh()
        }
    }

    /// Files dropped onto the Dock icon arrive here.
    /// Also handles `localocr://` URL invocations.
    func application(_ application: NSApplication, open urls: [URL]) {
        Task { @MainActor in
            var schemeURLs: [URL] = []
            var fileURLs: [URL] = []
            for url in urls {
                if url.scheme == AppConstants.urlScheme {
                    schemeURLs.append(url)
                } else if url.isFileURL {
                    fileURLs.append(url)
                }
            }
            for url in schemeURLs {
                Router.shared.handleURL(url)
            }
            if !fileURLs.isEmpty {
                Router.shared.handleDroppedFiles(fileURLs)
            }
        }
    }

    /// Return false so closing the last window hides the app rather than quitting
    /// (matches §3.2 main window spec + §4.7 window management).
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}
