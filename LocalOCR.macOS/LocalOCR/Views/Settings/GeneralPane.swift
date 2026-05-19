import SwiftUI

struct GeneralPane: View {
    @StateObject private var prefs = PreferencesStore.shared
    @StateObject private var household = HouseholdState.shared

    @State private var appearance: PreferencesStore.Appearance = .system
    @State private var landingTab = "dashboard"
    @State private var defaultOCRModel = ""
    @State private var menuBarEnabled = true
    @State private var globalShortcutEnabled = true
    @State private var launchAtLogin = false

    private let landingTabs: [(String, String)] = [
        ("dashboard", "Dashboard"), ("inventory", "Inventory"),
        ("receipts", "Receipts"), ("shopping", "Shopping"), ("finance", "Finance")
    ]

    var body: some View {
        Form {
            Section("Appearance") {
                Picker("Theme", selection: $appearance) {
                    Text("System").tag(PreferencesStore.Appearance.system)
                    Text("Light").tag(PreferencesStore.Appearance.light)
                    Text("Dark").tag(PreferencesStore.Appearance.dark)
                }
                .onChange(of: appearance) { prefs.appearance = $0 }
            }

            Section("Defaults") {
                Picker("Landing tab", selection: $landingTab) {
                    ForEach(landingTabs, id: \.0) { code, label in
                        Text(label).tag(code)
                    }
                }
                .onChange(of: landingTab) { prefs.defaultLandingTab = $0 }

                Picker("Default OCR model", selection: $defaultOCRModel) {
                    ForEach(household.aiModels.filter(\.supportsVision)) { model in
                        Text(model.name).tag(model.name)
                    }
                }
                .onChange(of: defaultOCRModel) { prefs.defaultOCRModel = $0 }
            }

            Section("System") {
                Toggle("Show menu bar icon", isOn: $menuBarEnabled)
                    .onChange(of: menuBarEnabled) { enabled in
                        prefs.menuBarIconEnabled = enabled
                        enabled ? MenuBarController.shared.install() : MenuBarController.shared.uninstall()
                    }

                Toggle("Enable global shortcut (⌃⌘R)", isOn: $globalShortcutEnabled)
                    .onChange(of: globalShortcutEnabled) { enabled in
                        prefs.globalShortcutEnabled = enabled
                        enabled ? GlobalShortcutManager.shared.register() : GlobalShortcutManager.shared.unregister()
                    }

                Toggle("Launch at login", isOn: $launchAtLogin)
                    .onChange(of: launchAtLogin) { enabled in
                        if #available(macOS 13.0, *) {
                            LoginItemController.shared.set(enabled: enabled)
                        }
                    }
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task {
            appearance = prefs.appearance
            landingTab = prefs.defaultLandingTab
            defaultOCRModel = prefs.defaultOCRModel
            menuBarEnabled = prefs.menuBarIconEnabled
            globalShortcutEnabled = prefs.globalShortcutEnabled
            if #available(macOS 13.0, *) {
                launchAtLogin = LoginItemController.shared.isRegistered
            }
            await household.loadAIModels()
        }
    }
}
