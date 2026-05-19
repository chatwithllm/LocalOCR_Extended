import SwiftUI

/// Horizontal label-value row used throughout detail inspectors and receipt review.
/// Left: secondary-label key. Right: primary-label value, right-aligned, monospaced
/// for numeric/identifier values when `mono` is true.
struct KeyValueRow: View {
    let key: String
    let value: String
    var mono: Bool = false
    var valueColor: Color? = nil

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: DesignTokens.Spacing.space3) {
            Text(key)
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
                .accessibilityHidden(true)
            Spacer(minLength: 0)
            Text(value)
                .font(mono ? .appMonoBody : .appBody)
                .foregroundStyle(valueColor ?? DesignTokens.label)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(key): \(value)")
    }
}

#Preview("KeyValueRow") {
    Card {
        VStack(spacing: DesignTokens.Spacing.space2) {
            KeyValueRow(key: "Store", value: "Whole Foods Market")
            KeyValueRow(key: "Date", value: "May 19, 2026")
            KeyValueRow(key: "Total", value: "$47.23", mono: true, valueColor: DesignTokens.success)
            KeyValueRow(key: "Receipt #", value: "TX-2026-05-19-XXXX-7F2A", mono: true)
        }
    }
    .padding(40)
    .frame(width: 380)
}
