import SwiftUI

/// Color-coded category tag used in receipt rows, inventory cells, and analytics drill-downs.
/// Mirrors the §1.7 receipt-domain palette: Grocery → blue, Restaurant → amber, Expense → green.
struct CategoryChip: View {
    enum Domain: String {
        case grocery
        case restaurant
        case expense
        case unknown

        var tint: Color {
            switch self {
            case .grocery:    return DesignTokens.accent
            case .restaurant: return DesignTokens.warning
            case .expense:    return DesignTokens.success
            case .unknown:    return DesignTokens.secondaryLabel
            }
        }

        var background: Color {
            switch self {
            case .grocery:    return DesignTokens.accentDim
            case .restaurant: return DesignTokens.warningDim
            case .expense:    return DesignTokens.successDim
            case .unknown:    return DesignTokens.surface2
            }
        }

        var label: String {
            switch self {
            case .grocery:    return "Grocery"
            case .restaurant: return "Restaurant"
            case .expense:    return "Expense"
            case .unknown:    return "Other"
            }
        }
    }

    let domain: Domain
    var customLabel: String? = nil

    var body: some View {
        Text(customLabel ?? domain.label)
            .font(.appCaption1.weight(.medium))
            .padding(.horizontal, DesignTokens.Spacing.space2)
            .padding(.vertical, 2)
            .background(domain.background)
            .foregroundStyle(domain.tint)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.pill))
            .accessibilityLabel(customLabel ?? domain.label)
    }
}

#Preview("CategoryChip") {
    HStack(spacing: 8) {
        CategoryChip(domain: .grocery)
        CategoryChip(domain: .restaurant)
        CategoryChip(domain: .expense)
        CategoryChip(domain: .unknown)
        CategoryChip(domain: .grocery, customLabel: "Frozen")
    }
    .padding(40)
}
