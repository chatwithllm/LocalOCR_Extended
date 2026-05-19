import SwiftUI

/// LocalOCR macOS — @main entry point.
@main
struct LocalOCRApp: App {

    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var appState = AppState.shared
    @StateObject private var router = Router.shared
    @StateObject private var prefs = PreferencesStore.shared

    var body: some Scene {
        WindowGroup("LocalOCR") {
            RootView()
                .environmentObject(appState)
                .environmentObject(router)
                .frame(minWidth: 1100, minHeight: 700)
                .preferredColorScheme(resolvedColorScheme)
                .onReceive(NotificationCenter.default.publisher(for: .globalShortcutReceiptUpload)) { _ in
                    router.openOCRUpload()
                }
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1200, height: 800)
        .commands { AppMenuCommands(router: router) }

        Settings {
            SettingsView()
                .environmentObject(appState)
                .preferredColorScheme(resolvedColorScheme)
        }
    }

    private var resolvedColorScheme: ColorScheme? {
        switch prefs.appearance {
        case .system: return nil
        case .light:  return .light
        case .dark:   return .dark
        }
    }
}
