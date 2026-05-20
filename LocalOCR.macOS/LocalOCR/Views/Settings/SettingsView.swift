import SwiftUI

/// Settings scene root — 8 panes per §3.8.
/// Each pane lives in its own file (GeneralPane.swift, AccountPane.swift, etc.).
struct SettingsView: View {
    var body: some View {
        TabView {
            GeneralPane()
                .tabItem { Label("General", systemImage: "gear") }
            AccountPane()
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
            AIModelsPane()
                .tabItem { Label("AI Models", systemImage: "cpu") }
            TrustedDevicesPane()
                .tabItem { Label("Devices", systemImage: "laptopcomputer.and.iphone") }
            TelegramPane()
                .tabItem { Label("Telegram", systemImage: "paperplane") }
            NotificationsPane()
                .tabItem { Label("Notifications", systemImage: "bell") }
            BackupPane()
                .tabItem { Label("Backup", systemImage: "arrow.clockwise.icloud") }
            AdminToolsPane()
                .tabItem { Label("Admin Tools", systemImage: "wrench.adjustable") }
            AdvancedPane()
                .tabItem { Label("Advanced", systemImage: "wrench.and.screwdriver") }
        }
        .frame(width: 680, height: 540)
    }
}
