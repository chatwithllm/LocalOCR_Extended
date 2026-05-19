import SwiftUI

/// Branded button styles per §3.6. Each respects the system focus ring,
/// hover state, and pressed state.

struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.appBody.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, DesignTokens.Spacing.space4)
            .padding(.vertical, DesignTokens.Spacing.space2)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.control)
                    .fill(isEnabled ? DesignTokens.accent : DesignTokens.accent.opacity(0.4))
            )
            .opacity(configuration.isPressed ? 0.85 : 1.0)
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeInOut(duration: 0.12), value: configuration.isPressed)
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.appBody.weight(.medium))
            .foregroundStyle(isEnabled ? DesignTokens.label : DesignTokens.tertiaryLabel)
            .padding(.horizontal, DesignTokens.Spacing.space4)
            .padding(.vertical, DesignTokens.Spacing.space2)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.control)
                    .fill(DesignTokens.surface2)
            )
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.control)
                    .stroke(DesignTokens.border, lineWidth: 0.5)
            )
            .opacity(configuration.isPressed ? 0.85 : 1.0)
    }
}

struct DestructiveButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.appBody.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, DesignTokens.Spacing.space4)
            .padding(.vertical, DesignTokens.Spacing.space2)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.control)
                    .fill(isEnabled ? DesignTokens.error : DesignTokens.error.opacity(0.4))
            )
            .opacity(configuration.isPressed ? 0.85 : 1.0)
    }
}

struct GhostButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.appBody.weight(.medium))
            .foregroundStyle(isEnabled ? DesignTokens.accent : DesignTokens.tertiaryLabel)
            .padding(.horizontal, DesignTokens.Spacing.space3)
            .padding(.vertical, DesignTokens.Spacing.space1)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.control)
                    .fill(configuration.isPressed ? DesignTokens.accentDim : .clear)
            )
    }
}

#Preview("Button styles / All") {
    VStack(alignment: .leading, spacing: 12) {
        Button("Primary action") {}.buttonStyle(PrimaryButtonStyle())
        Button("Secondary") {}.buttonStyle(SecondaryButtonStyle())
        Button("Delete") {}.buttonStyle(DestructiveButtonStyle())
        Button("Cancel") {}.buttonStyle(GhostButtonStyle())
        Button("Disabled primary") {}.buttonStyle(PrimaryButtonStyle()).disabled(true)
    }
    .padding(40)
}
