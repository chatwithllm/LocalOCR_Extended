import SwiftUI

/// Static login form. Wires to AuthState in Phase 3 (Networking + Auth).
///
/// Form:
///   - Server URL (shown only when no URL persisted in UserDefaults)
///   - Email
///   - Password
///   - Sign In (PrimaryButtonStyle)
///   - Sign in with Google (SecondaryButtonStyle, triggers GoogleOAuthSheet in Phase 3)
///   - Try Demo Mode (GhostButtonStyle)
struct LoginView: View {
    @State private var email = ""
    @State private var password = ""
    @State private var serverURL = ""
    @State private var showServerURL = true   // Phase 3 reads from PreferencesStore

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            container
            Spacer()
            footer
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DesignTokens.background.ignoresSafeArea())
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
                            text: $serverURL,
                            isSecure: false
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

                    VStack(spacing: DesignTokens.Spacing.space2) {
                        Button("Sign In") {
                            // Phase 3: AuthState.shared.login(email:password:)
                        }
                        .buttonStyle(PrimaryButtonStyle())
                        .frame(maxWidth: .infinity)
                        .keyboardShortcut(.defaultAction)
                        .disabled(email.isEmpty || password.isEmpty)

                        Button("Sign in with Google") {
                            // Phase 3: AuthState.shared.loginWithGoogle()
                        }
                        .buttonStyle(SecondaryButtonStyle())
                        .frame(maxWidth: .infinity)
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
                // Phase 3: AuthState.shared.setDemoMode()
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

    private func labeledField(label: String, placeholder: String, text: Binding<String>, isSecure: Bool) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space1) {
            Text(label)
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryLabel)
            Group {
                if isSecure {
                    SecureField(placeholder, text: text)
                } else {
                    TextField(placeholder, text: text)
                }
            }
            .textFieldStyle(.roundedBorder)
            .font(.appBody)
        }
    }
}

#Preview("LoginView / Light") {
    LoginView()
        .frame(width: 900, height: 640)
}

#Preview("LoginView / Dark") {
    LoginView()
        .frame(width: 900, height: 640)
        .preferredColorScheme(.dark)
}
