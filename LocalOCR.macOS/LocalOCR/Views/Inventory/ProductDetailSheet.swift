import SwiftUI

struct ProductDetailSheet: View {
    let item: InventoryItem
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
            HStack {
                Text(item.displayName)
                    .font(.appTitle2)
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }

            Card {
                VStack(alignment: .leading, spacing: 8) {
                    KeyValueRow(key: "Category", value: item.category ?? "—")
                    KeyValueRow(key: "Location", value: item.location ?? "—")
                    KeyValueRow(key: "Quantity", value: String(format: "%.0f", item.quantity), mono: true)
                    if let t = item.threshold {
                        KeyValueRow(key: "Threshold", value: String(format: "%.0f", t), mono: true)
                    }
                    if let exp = item.expiresAt {
                        KeyValueRow(key: "Expires", value: exp)
                    }
                    if let brand = item.brand {
                        KeyValueRow(key: "Brand", value: brand)
                    }
                    if let size = item.size {
                        KeyValueRow(key: "Size", value: size)
                    }
                }
            }
        }
        .padding(DesignTokens.Spacing.space5)
        .frame(width: 480)
    }
}
