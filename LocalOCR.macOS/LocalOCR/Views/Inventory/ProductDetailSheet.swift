import SwiftUI

struct ProductDetailSheet: View {
    let item: InventoryItem
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
            HStack {
                Text(item.product?.displayName ?? item.product?.name ?? "Item")
                    .font(.appTitle2)
                Spacer()
                Button("Done") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }

            Card {
                VStack(alignment: .leading, spacing: 8) {
                    KeyValueRow(key: "Category", value: item.product?.category ?? "—")
                    KeyValueRow(key: "Location", value: item.location ?? "—")
                    KeyValueRow(key: "Quantity", value: String(format: "%.0f", item.quantity), mono: true)
                    if let t = item.threshold {
                        KeyValueRow(key: "Threshold", value: String(format: "%.0f", t), mono: true)
                    }
                    if let exp = item.expiresAt {
                        KeyValueRow(key: "Expires", value: exp.formatted(date: .abbreviated, time: .omitted))
                    }
                }
            }
        }
        .padding(DesignTokens.Spacing.space5)
        .frame(width: 480)
    }
}
