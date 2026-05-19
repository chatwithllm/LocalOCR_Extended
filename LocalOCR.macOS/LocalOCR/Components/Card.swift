import SwiftUI

/// Surface container used across detail panes, dashboard tiles, and inspector regions.
/// Wraps content in DesignTokens.surface with a 10pt corner radius (§3.1).
struct Card<Content: View>: View {
    var padding: CGFloat = DesignTokens.Spacing.space4
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DesignTokens.surface)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                    .stroke(DesignTokens.border, lineWidth: 0.5)
            )
    }
}

#Preview("Card / Light") {
    Card {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            Text("Spending this month").font(.appHeadline)
            Text("$1,247.83").font(.appTitle1).foregroundStyle(DesignTokens.label)
            Text("12% under budget").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        }
    }
    .padding(40)
    .frame(width: 360)
}

#Preview("Card / Dark") {
    Card {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            Text("Low stock items").font(.appHeadline)
            Text("7").font(.appTitle1).foregroundStyle(DesignTokens.warning)
        }
    }
    .padding(40)
    .frame(width: 360)
    .preferredColorScheme(.dark)
}
