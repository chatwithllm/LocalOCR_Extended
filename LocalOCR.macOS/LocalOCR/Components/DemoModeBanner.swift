import SwiftUI

/// Persistent yellow banner shown when `AppState.isDemoMode == true` (§1.7 rule 10).
/// Renders a "Sign In to Save" CTA. Tapping triggers an optional `onSignIn` closure.
///
/// Per VETO_RESOLUTION_PATCH §3 UC-027: banner visibility tracks AppState.isDemoMode;
/// write-action taps should present a sign-in prompt — handled at the call-site by `DemoModeGate`.
struct DemoModeBanner: View {
    var onSignIn: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            Image(systemName: "eye")
                .font(.system(size: 13, weight: .semibold))
            Text("Demo mode — changes will not be saved.")
                .font(.appCaption1.weight(.medium))
            Spacer(minLength: 0)
            if let onSignIn {
                Button("Sign In to Save", action: onSignIn)
                    .buttonStyle(.borderless)
                    .foregroundStyle(DesignTokens.warning)
                    .font(.appCaption1.weight(.semibold))
            }
        }
        .foregroundStyle(DesignTokens.warning)
        .padding(.horizontal, DesignTokens.Spacing.space4)
        .padding(.vertical, DesignTokens.Spacing.space2)
        .frame(maxWidth: .infinity)
        .background(DesignTokens.warningDim)
        .overlay(alignment: .bottom) {
            Rectangle().fill(DesignTokens.warning.opacity(0.3)).frame(height: 0.5)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Demo mode banner. Changes will not be saved.")
    }
}

#Preview("DemoModeBanner") {
    VStack(spacing: 0) {
        DemoModeBanner(onSignIn: {})
        DesignTokens.background.frame(height: 200)
    }
    .frame(width: 600)
}
