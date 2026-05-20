import SwiftUI

// F-1701..F-1719 — Session card (avatar bubble + name + sub + Sign Out + avatar
// editor + activity stats) + server URL config.

struct AccountPane: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var prefs = PreferencesStore.shared
    @State private var serverURLText = ""
    @State private var avatarDraft = ""
    @State private var avatarSaving = false
    @State private var showAvatarEditor = false
    @State private var showSessionDetails = false

    var body: some View {
        Form {
            sessionSection
            if appState.currentUser != nil && showSessionDetails {
                sessionDetailsSection
            }
            serverSection
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task {
            serverURLText = prefs.apiBaseURL.absoluteString
            avatarDraft = appState.currentUser?.avatarEmoji ?? ""
        }
        .onChange(of: appState.currentUser?.id) { _ in
            avatarDraft = appState.currentUser?.avatarEmoji ?? ""
        }
    }

    // F-1701..F-1706, F-1715..F-1719
    private var sessionSection: some View {
        Section("Session") {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.space3) {
                avatarBubble
                VStack(alignment: .leading, spacing: 2) {
                    Text(appState.currentUser?.name ?? "Not signed in")
                        .font(.appHeadline)
                    Text(sessionSubLine)
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    if let stats = activityStats {
                        Text(stats)
                            .font(.appCaption2)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                            .padding(.top, 2)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    if appState.currentUser != nil {
                        Button(showAvatarEditor ? "Hide" : "Change Avatar") {
                            showAvatarEditor.toggle()
                        }
                        .buttonStyle(GhostButtonStyle())
                        .controlSize(.small)
                        Button(showSessionDetails ? "▲ Hide details" : "▼ Details") {
                            showSessionDetails.toggle()
                        }
                        .buttonStyle(GhostButtonStyle())
                        .controlSize(.small)
                        Button("Sign Out") {
                            Task { await AuthState.shared.logout() }
                        }
                        .buttonStyle(DestructiveButtonStyle())
                        .controlSize(.small)
                    } else if appState.isDemoMode {
                        Text("Demo Mode")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.warning)
                        Button("Exit Demo") {
                            Task { await AuthState.shared.logout() }
                        }
                        .buttonStyle(SecondaryButtonStyle())
                        .controlSize(.small)
                    }
                }
            }
            if showAvatarEditor && appState.currentUser != nil {
                avatarEditor
            }
        }
    }

    private var avatarBubble: some View {
        Text(appState.currentUser?.avatarEmoji ?? "🦊")
            .font(.system(size: 40))
            .frame(width: 56, height: 56)
            .background(DesignTokens.surface2)
            .clipShape(Circle())
            .overlay(Circle().stroke(DesignTokens.border, lineWidth: 0.5))
    }

    // F-1707..F-1709
    private var avatarEditor: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Profile avatar (1–4 chars; emoji recommended)")
                .font(.appCaption2)
                .foregroundStyle(DesignTokens.secondaryLabel)
            HStack {
                TextField("😀", text: $avatarDraft)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 80)
                    .onChange(of: avatarDraft) { new in
                        if new.count > 4 { avatarDraft = String(new.prefix(4)) }
                    }
                Button("Save Avatar") {
                    Task { await saveAvatar() }
                }
                .buttonStyle(PrimaryButtonStyle())
                .controlSize(.small)
                .disabled(avatarSaving || avatarDraft.trimmingCharacters(in: .whitespaces).isEmpty)
                Button("Cancel") {
                    avatarDraft = appState.currentUser?.avatarEmoji ?? ""
                    showAvatarEditor = false
                }
                .buttonStyle(GhostButtonStyle())
                .controlSize(.small)
                if avatarSaving {
                    ProgressView().controlSize(.small)
                }
            }
        }
    }

    private func saveAvatar() async {
        guard let userId = appState.currentUser?.id else { return }
        let trimmed = avatarDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        avatarSaving = true
        defer { avatarSaving = false }
        do {
            try await APIClient.shared.request(
                .patch,
                path: AuthEndpoint.patchUser(id: userId).path,
                jsonBody: UserPatchBody(avatarEmoji: trimmed)
            )
            await AuthState.shared.checkSession()
            ToastQueue.shared.push(Toast(message: "Avatar updated", severity: .success))
            showAvatarEditor = false
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Could not update avatar"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
        }
    }

    private var sessionSubLine: String {
        guard let user = appState.currentUser else { return "Sign in to track contributions and sync devices." }
        let role = user.role.capitalized
        return "\(role) · \(user.email)"
    }

    private var activityStats: String? {
        guard appState.currentUser != nil else { return nil }
        if let h = appState.currentHousehold {
            return "Household: \(h.name)"
        }
        return nil
    }

    // F-1710..F-1714
    private var sessionDetailsSection: some View {
        Section("Session details") {
            LabeledContent("Current login") {
                Text(appState.currentUser?.email ?? "—")
                    .font(.appMonoCaption)
                    .textSelection(.enabled)
            }
            LabeledContent("Auth source") {
                Text(authSource)
                    .font(.appMonoCaption)
            }
            LabeledContent("Trusted device") {
                Text(KeychainStore().loadDeviceToken() != nil ? "Paired" : "Not paired")
                    .font(.appMonoCaption)
            }
            LabeledContent("Server") {
                Text(prefs.apiBaseURL.absoluteString)
                    .font(.appMonoCaption)
                    .textSelection(.enabled)
            }
        }
    }

    private var authSource: String {
        guard let user = appState.currentUser else { return "Signed out" }
        if user.googleSub != nil { return "google" }
        return "password"
    }

    // F-1865..F-1869 (server URL only — API tokens are issued + revoked server-side)
    private var serverSection: some View {
        Section("Server") {
            TextField("Server URL", text: $serverURLText, onCommit: applyServerURL)
                .textFieldStyle(.roundedBorder)
                .help("API base URL — change to point at a different server")
            HStack {
                Circle()
                    .fill(appState.isServerReachable ? DesignTokens.success : DesignTokens.error)
                    .frame(width: 8, height: 8)
                Text(appState.isServerReachable ? "Reachable" : "Unreachable")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
                Spacer()
                Button("Apply") { applyServerURL() }
                    .buttonStyle(SecondaryButtonStyle())
                    .controlSize(.small)
                    .disabled(serverURLText.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }

    private func applyServerURL() {
        let trimmed = serverURLText.trimmingCharacters(in: .whitespaces)
        guard let url = URL(string: trimmed) else { return }
        prefs.apiBaseURL = url
        ToastQueue.shared.push(Toast(message: "Server URL set to \(trimmed)", severity: .success))
    }
}
