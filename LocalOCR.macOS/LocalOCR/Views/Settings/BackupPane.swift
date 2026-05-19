import SwiftUI

struct BackupPane: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        Form {
            if appState.currentUser?.isAdmin == true {
                Section("Server backup") {
                    Text("Backup management runs server-side via the web app. This pane links out to the relevant page.")
                        .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    Button("Open backup page") {
                        let base = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL) ?? AppConstants.defaultAPIBaseURL
                        if let url = URL(string: "\(base)/backups") {
                            NSWorkspace.shared.open(url)
                        }
                    }
                    .buttonStyle(SecondaryButtonStyle())
                }
            } else {
                Section("Backup") {
                    Label("Admin only", systemImage: "lock.fill")
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    Text("Database and volume backups are managed by household admins.")
                        .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
    }
}
