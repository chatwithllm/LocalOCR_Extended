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
                .frame(minWidth: 1100, minHeight: 700)
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1200, height: 800)
        .commands {
            // TODO Phase 5: full AppMenuCommands per §5.4 / §3.3.
        }

        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }
}
