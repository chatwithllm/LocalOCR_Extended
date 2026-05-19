import SwiftUI
import UserNotifications

struct OnboardingSheet: View {
    enum Step: Int, CaseIterable { case welcome, server, notifications, done }

    @Environment(\.dismiss) private var dismiss
    @StateObject private var prefs = PreferencesStore.shared

    @State private var step: Step = .welcome
    @State private var serverURLText = ""

    var body: some View {
        VStack(spacing: DesignTokens.Spacing.space5) {
            content
            Spacer()
            footer
        }
        .padding(DesignTokens.Spacing.space5)
        .frame(width: 520, height: 420)
        .background(DesignTokens.background)
        .task {
            serverURLText = prefs.apiBaseURL.absoluteString
        }
    }

    @ViewBuilder
    private var content: some View {
        switch step {
        case .welcome:
            VStack(spacing: DesignTokens.Spacing.space3) {
                Image(systemName: "doc.text.viewfinder")
                    .font(.system(size: 56, weight: .light))
                    .foregroundStyle(DesignTokens.accent)
                Text("Welcome to LocalOCR")
                    .font(.appTitle1)
                Text("This native client connects to your LocalOCR Extended backend. We'll get you set up in three quick steps.")
                    .font(.appBody)
                    .foregroundStyle(DesignTokens.secondaryLabel)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 380)
            }
            .frame(maxWidth: .infinity)

        case .server:
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                stepHeader("Server URL", "Where does your LocalOCR backend live? Defaults to localhost if you're running Docker on this Mac.")
                TextField("Server URL", text: $serverURLText)
                    .textFieldStyle(.roundedBorder)
                Text("You can change this anytime in Settings → Account.")
                    .font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
            }

        case .notifications:
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                stepHeader("Notifications", "Get a daily shopping nudge when your inventory drops below a threshold you choose. You can change timing in Settings → Notifications.")
                Button("Request Notification Permission") {
                    Task { await NotificationManager.shared.requestAuthorizationIfNeeded() }
                }
                .buttonStyle(SecondaryButtonStyle())
                Text("If you skip this, you can request permission later from Settings.")
                    .font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
            }

        case .done:
            VStack(spacing: DesignTokens.Spacing.space3) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 56))
                    .foregroundStyle(DesignTokens.success)
                Text("You're set up")
                    .font(.appTitle1)
                Text("Sign in to start tracking receipts. Try Demo Mode first if you want to explore.")
                    .font(.appBody)
                    .foregroundStyle(DesignTokens.secondaryLabel)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 380)
            }
            .frame(maxWidth: .infinity)
        }
    }

    private func stepHeader(_ title: String, _ subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space1) {
            Text(title).font(.appTitle2)
            Text(subtitle).font(.appBody).foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private var footer: some View {
        HStack {
            // Progress dots
            HStack(spacing: 6) {
                ForEach(Step.allCases, id: \.rawValue) { s in
                    Circle()
                        .fill(s.rawValue <= step.rawValue ? DesignTokens.accent : DesignTokens.surface2)
                        .frame(width: 7, height: 7)
                }
            }
            Spacer()
            if step != .welcome {
                Button("Back") { back() }
                    .buttonStyle(GhostButtonStyle())
            }
            Button(step == .done ? "Get Started" : "Continue") { next() }
                .buttonStyle(PrimaryButtonStyle())
                .keyboardShortcut(.defaultAction)
        }
    }

    private func back() {
        if let prev = Step(rawValue: step.rawValue - 1) { step = prev }
    }

    private func next() {
        switch step {
        case .welcome:
            step = .server
        case .server:
            if let url = URL(string: serverURLText.trimmingCharacters(in: .whitespaces)), !serverURLText.isEmpty {
                prefs.apiBaseURL = url
            }
            step = .notifications
        case .notifications:
            step = .done
        case .done:
            prefs.hasCompletedOnboarding = true
            dismiss()
        }
    }
}

#Preview("Onboarding") {
    OnboardingSheet().frame(width: 520, height: 420)
}
