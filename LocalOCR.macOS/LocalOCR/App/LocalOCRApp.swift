import SwiftUI

/// LocalOCR macOS — @main entry point.
///
/// Phase 1: bare WindowGroup + Settings scene stubs so the project builds
/// and launches to an empty window. Real view content lands in Phase 2+.
@main
struct LocalOCRApp: App {

    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var appState = AppState.shared
    @StateObject private var router = Router.shared

    var body: some Scene {
        WindowGroup("LocalOCR") {
            ContentView()
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

/// Phase 1 placeholder. Replaced by RootView (Phase 2) + MainSplitView (Phase 2 + 3).
private struct ContentView: View {
    var body: some View {
        VStack(spacing: DesignTokens.Spacing.space4) {
            Text("LocalOCR")
                .font(.appLargeTitle)
                .foregroundStyle(DesignTokens.label)
            Text("Phase 1 — Foundation")
                .font(.appBody)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DesignTokens.background)
    }
}

/// Phase 1 placeholder. Replaced in Phase 6 by full Settings panes (§3.8, §5.2).
private struct SettingsPlaceholderView: View {
    var body: some View {
        Text("Settings — implemented in Phase 6")
            .padding(DesignTokens.Spacing.space6)
            .frame(width: 480, height: 320)
    }
}
