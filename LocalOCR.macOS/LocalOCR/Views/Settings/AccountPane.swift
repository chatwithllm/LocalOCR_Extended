import SwiftUI

struct AccountPane: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var prefs = PreferencesStore.shared
    @State private var serverURLText = ""

    var body: some View {
        Form {
            Section("Server") {
                TextField("Server URL", text: $serverURLText, onCommit: applyServerURL)
                    .textFieldStyle(.roundedBorder)
                HStack {
                    Circle()
                        .fill(appState.isServerReachable ? DesignTokens.success : DesignTokens.error)
                        .frame(width: 8, height: 8)
                    Text(appState.isServerReachable ? "Reachable" : "Unreachable")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }

            Section("Signed in") {
                if let user = appState.currentUser {
                    LabeledContent("Name",  value: user.name)
                    LabeledContent("Email", value: user.email)
                    LabeledContent("Role",  value: user.role.capitalized)
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
                    Text("Not signed in").foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task {
            serverURLText = prefs.apiBaseURL.absoluteString
        }
    }

    private func applyServerURL() {
        let trimmed = serverURLText.trimmingCharacters(in: .whitespaces)
        guard let url = URL(string: trimmed) else { return }
        prefs.apiBaseURL = url
    }
}
