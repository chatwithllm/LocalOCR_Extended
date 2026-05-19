import SwiftUI

/// Amber pill that conveys "low stock" status. Always includes the word "Low" so
/// information is not conveyed by color alone (§2.6 AC-11, §6.7).
struct LowStockPill: View {
    enum Severity {
        case low      // amber
        case critical // red — out of stock or below 50% of threshold

        var background: Color {
            switch self {
            case .low:      return DesignTokens.lowStockPillBackground
            case .critical: return DesignTokens.errorDim
            }
        }

        var foreground: Color {
            switch self {
            case .low:      return DesignTokens.warning
            case .critical: return DesignTokens.error
            }
        }

        var label: String {
            switch self {
            case .low:      return "Low"
            case .critical: return "Out"
            }
        }
    }

    let severity: Severity

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "exclamationmark.circle.fill")
                .font(.system(size: 8, weight: .bold))
            Text(severity.label)
                .font(.appCaption1.weight(.semibold))
        }
        .padding(.horizontal, DesignTokens.Spacing.space2)
        .padding(.vertical, 2)
        .background(severity.background)
        .foregroundStyle(severity.foreground)
        .clipShape(Capsule())
        .accessibilityLabel(severity == .low ? "Low stock" : "Out of stock")
    }
}

#Preview("LowStockPill / Severities") {
    HStack(spacing: 12) {
        LowStockPill(severity: .low)
        LowStockPill(severity: .critical)
    }
    .padding(40)
}
