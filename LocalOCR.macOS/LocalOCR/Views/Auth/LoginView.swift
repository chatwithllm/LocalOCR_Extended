import SwiftUI

/// Login form wired to AuthState (Phase 3).
struct LoginView: View {
    @StateObject private var auth = AuthState.shared
    @StateObject private var prefs = PreferencesStore.shared

    @State private var email = ""
    @State private var password = ""
    @State private var serverURLText = ""
    @State private var showServerURL = false

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            container
            Spacer()
            footer
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DesignTokens.background.ignoresSafeArea())
        .onAppear {
            serverURLText = prefs.apiBaseURL.absoluteString
        }
    }

    private var container: some View {
        VStack(spacing: DesignTokens.Spacing.space6) {
            header

            Card {
                VStack(spacing: DesignTokens.Spacing.space3) {
                    if showServerURL {
                        labeledField(
                            label: "Server URL",
                            placeholder: AppConstants.defaultAPIBaseURL,
                            text: $serverURLText,
                            isSecure: false,
                            commit: applyServerURL
                        )
                    }
                    labeledField(
                        label: "Email",
                        placeholder: "you@example.com",
                        text: $email,
                        isSecure: false
                    )
                    labeledField(
                        label: "Password",
                        placeholder: "••••••••",
                        text: $password,
                        isSecure: true
                    )

                    if let errorMessage = auth.lastError {
                        HStack(spacing: 6) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(DesignTokens.error)
                            Text(errorMessage)
                                .font(.appCaption1)
                                .foregroundStyle(DesignTokens.error)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    VStack(spacing: DesignTokens.Spacing.space2) {
                        Button {
                            Task { await signIn() }
                        } label: {
                            HStack {
                                if auth.isBusy {
                                    ProgressView().controlSize(.small)
                                } else {
                                    Text("Sign In")
                                }
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(PrimaryButtonStyle())
                        .keyboardShortcut(.defaultAction)
                        .disabled(email.isEmpty || password.isEmpty || auth.isBusy)

                        Button("Sign in with Google") {
                            // Phase 3: GoogleOAuthSheet driven by AuthState.loginWithGoogle()
                            // — sheet host wires the completion to AuthState.completeGoogleOAuth.
                        }
                        .buttonStyle(SecondaryButtonStyle())
                        .frame(maxWidth: .infinity)
                        .disabled(auth.isBusy)
                    }
                    .padding(.top, DesignTokens.Spacing.space2)
                }
            }
            .frame(maxWidth: 380)
        }
        .padding(DesignTokens.Spacing.space5)
    }

    private var header: some View {
        VStack(spacing: DesignTokens.Spacing.space2) {
            Image(systemName: "doc.text.viewfinder")
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(DesignTokens.accent)
            Text("LocalOCR")
                .font(.appLargeTitle)
                .foregroundStyle(DesignTokens.label)
            Text("Receipts, inventory, finance — at home.")
                .font(.appBody)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private var footer: some View {
        HStack {
            Button("Try Demo Mode") {
                auth.setDemoMode()
            }
            .buttonStyle(GhostButtonStyle())

            Spacer()

            Button {
                showServerURL.toggle()
            } label: {
                Label(showServerURL ? "Hide server URL" : "Change server URL", systemImage: "network")
            }
            .buttonStyle(GhostButtonStyle())
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(maxWidth: 460)
    }

    // MARK: - Actions

    private func signIn() async {
        applyServerURL()
        await auth.login(email: email, password: password)
    }

    private func applyServerURL() {
        let trimmed = serverURLText.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty, let url = URL(string: trimmed) else { return }
        prefs.apiBaseURL = url
    }

    private func labeledField(
        label: String,
        placeholder: String,
        text: Binding<String>,
        isSecure: Bool,
        commit: (() -> Void)? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space1) {
            Text(label)
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryLabel)
            Group {
                if isSecure {
                    SecureField(placeholder, text: text)
                } else {
                    TextField(placeholder, text: text, onCommit: { commit?() })
                }
            }
            .textFieldStyle(.roundedBorder)
            .font(.appBody)
        }
    }
}

#Preview("LoginView / Light") {
    LoginView().frame(width: 900, height: 640)
}

#Preview("LoginView / Dark") {
    LoginView().frame(width: 900, height: 640).preferredColorScheme(.dark)
}
