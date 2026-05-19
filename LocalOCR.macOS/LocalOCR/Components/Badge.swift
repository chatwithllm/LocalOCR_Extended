import SwiftUI

/// Capsule pill with text and a tint color. Used for status labels across receipts,
/// shopping items, and Plaid account states.
struct Badge: View {
    enum Style {
        case success
        case warning
        case error
        case neutral
        case info

        var background: Color {
            switch self {
            case .success: return DesignTokens.successDim
            case .warning: return DesignTokens.warningDim
            case .error:   return DesignTokens.errorDim
            case .info:    return DesignTokens.accentDim
            case .neutral: return DesignTokens.surface2
            }
        }

        var foreground: Color {
            switch self {
            case .success: return DesignTokens.success
            case .warning: return DesignTokens.warning
            case .error:   return DesignTokens.error
            case .info:    return DesignTokens.accent
            case .neutral: return DesignTokens.secondaryLabel
            }
        }
    }

    let text: String
    var style: Style = .neutral

    var body: some View {
        Text(text)
            .font(.appCaption1)
            .padding(.horizontal, DesignTokens.Spacing.space2)
            .padding(.vertical, DesignTokens.Spacing.space1)
            .background(style.background)
            .foregroundStyle(style.foreground)
            .clipShape(Capsule())
            .accessibilityLabel(text)
    }
}

#Preview("Badge / All styles") {
    HStack(spacing: 8) {
        Badge(text: "Active", style: .success)
        Badge(text: "Pending", style: .warning)
        Badge(text: "Failed", style: .error)
        Badge(text: "Auto", style: .info)
        Badge(text: "Draft", style: .neutral)
    }
    .padding(40)
}

#Preview("Badge / Dark") {
    HStack(spacing: 8) {
        Badge(text: "Active", style: .success)
        Badge(text: "Pending", style: .warning)
        Badge(text: "Failed", style: .error)
    }
    .padding(40)
    .preferredColorScheme(.dark)
}
