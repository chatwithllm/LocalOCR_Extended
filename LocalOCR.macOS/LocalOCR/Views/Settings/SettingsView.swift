import SwiftUI

struct SettingsView: View {
    var body: some View {
        TabView {
            GeneralPane()
                .tabItem { Label("General", systemImage: "gear") }
            AccountPane()
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
            NotificationsPane()
                .tabItem { Label("Notifications", systemImage: "bell") }
            AdvancedPane()
                .tabItem { Label("Advanced", systemImage: "wrench.and.screwdriver") }
        }
        .frame(width: 560, height: 440)
    }
}

struct GeneralPane: View {
    @StateObject private var prefs = PreferencesStore.shared
    @State private var appearance: PreferencesStore.Appearance = .system
    @State private var menuBarEnabled = true
    @State private var globalShortcutEnabled = true

    var body: some View {
        Form {
            Picker("Appearance", selection: $appearance) {
                Text("System").tag(PreferencesStore.Appearance.system)
                Text("Light").tag(PreferencesStore.Appearance.light)
                Text("Dark").tag(PreferencesStore.Appearance.dark)
            }
            .onChange(of: appearance) { prefs.appearance = $0 }

            Toggle("Show menu bar icon", isOn: $menuBarEnabled)
                .onChange(of: menuBarEnabled) { prefs.menuBarIconEnabled = $0 }

            Toggle("Enable global shortcut (⌃⌘R)", isOn: $globalShortcutEnabled)
                .onChange(of: globalShortcutEnabled) { prefs.globalShortcutEnabled = $0 }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task {
            appearance = prefs.appearance
            menuBarEnabled = prefs.menuBarIconEnabled
            globalShortcutEnabled = prefs.globalShortcutEnabled
        }
    }
}

struct AccountPane: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var prefs = PreferencesStore.shared
    @State private var serverURL = ""

    var body: some View {
        Form {
            Section("Server") {
                TextField("Server URL", text: $serverURL, onCommit: applyServerURL)
                    .textFieldStyle(.roundedBorder)
                Text("Default: \(AppConstants.defaultAPIBaseURL)")
                    .font(.appCaption1).foregroundStyle(.secondary)
            }
            Section("Session") {
                if let user = appState.currentUser {
                    LabeledContent("Signed in", value: "\(user.name) (\(user.email))")
                    if let h = appState.currentHousehold {
                        LabeledContent("Household", value: h.name)
                    }
                    Button("Sign Out") { Task { await AuthState.shared.logout() } }
                        .buttonStyle(DestructiveButtonStyle())
                } else if appState.isDemoMode {
                    LabeledContent("Status", value: "Demo Mode")
                    Button("Exit Demo") { Task { await AuthState.shared.logout() } }
                        .buttonStyle(SecondaryButtonStyle())
                } else {
                    Text("Not signed in").foregroundStyle(.secondary)
                }
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task {
            serverURL = prefs.apiBaseURL.absoluteString
        }
    }

    private func applyServerURL() {
        let trimmed = serverURL.trimmingCharacters(in: .whitespaces)
        guard let url = URL(string: trimmed) else { return }
        prefs.apiBaseURL = url
    }
}

struct NotificationsPane: View {
    @StateObject private var prefs = PreferencesStore.shared
    @State private var nudgeTime = Date()
    @State private var nudgeMinThreshold = 3
    @State private var inventoryAlerts = true
    @State private var weeklySummary = false

    var body: some View {
        Form {
            DatePicker("Shopping nudge time", selection: $nudgeTime, displayedComponents: .hourAndMinute)
                .onChange(of: nudgeTime) { newDate in
                    let comps = Calendar.current.dateComponents([.hour, .minute], from: newDate)
                    prefs.shoppingNudgeTime = comps
                }
            Stepper(value: $nudgeMinThreshold, in: 1...20) {
                Text("Nudge when ≥ \(nudgeMinThreshold) items low")
            }
            .onChange(of: nudgeMinThreshold) { prefs.nudgeMinThreshold = $0 }
            Toggle("Inventory threshold alerts", isOn: $inventoryAlerts)
                .onChange(of: inventoryAlerts) { prefs.inventoryAlertsEnabled = $0 }   // veto §4 — correct key
            Toggle("Weekly spending summary", isOn: $weeklySummary)
                .onChange(of: weeklySummary) { prefs.weeklySummaryEnabled = $0 }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task {
            let comps = prefs.shoppingNudgeTime
            nudgeTime = Calendar.current.date(from: comps) ?? Date()
            nudgeMinThreshold = prefs.nudgeMinThreshold
            inventoryAlerts = prefs.inventoryAlertsEnabled
            weeklySummary = prefs.weeklySummaryEnabled
        }
    }
}

struct AdvancedPane: View {
    var body: some View {
        Form {
            Text("Phase 6: cache purge, debug logging, diagnostics export")
                .font(.appCaption1)
                .foregroundStyle(.secondary)
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
    }
}
