import SwiftUI

/// LocalOCR macOS — @main entry point.
///
/// Phase 2: RootView wired (LoginView ↔ MainSplitView based on auth state).
@main
struct LocalOCRApp: App {

    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var appState = AppState.shared
    @StateObject private var router = Router.shared

    var body: some Scene {
        WindowGroup("LocalOCR") {
            RootView()
                .environmentObject(appState)
                .environmentObject(router)
                .frame(minWidth: 900, minHeight: 600)
        }
        .windowResizability(.contentMinSize)
        .commands {
            // TODO Phase 5: full AppMenuCommands per §5.4 / §3.3.
        }

        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }
}
