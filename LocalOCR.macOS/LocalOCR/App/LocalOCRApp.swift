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
            SettingsPlaceholderView()
        }
    }
}

/// Phase 2 placeholder for the Preferences window. Replaced in Phase 6 by full
/// Settings panes (§3.8, §5.2).
private struct SettingsPlaceholderView: View {
    var body: some View {
        Text("Settings — implemented in Phase 6")
            .padding(DesignTokens.Spacing.space6)
            .frame(width: 480, height: 320)
    }
}
