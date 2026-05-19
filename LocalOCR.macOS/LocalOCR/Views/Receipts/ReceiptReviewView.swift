import SwiftUI

struct ReceiptReviewView: View {
    let receiptId: Int

    @StateObject private var state = ReceiptsState.shared
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                if let r = state.detail {
                    Text(r.storeName ?? "Receipt").font(.appTitle2)
                    KeyValueRow(key: "Date",   value: r.date?.formatted(date: .abbreviated, time: .omitted) ?? "—")
                    KeyValueRow(key: "Total",  value: String(format: "$%.2f", r.totalAmount), mono: true, valueColor: DesignTokens.success)
                    KeyValueRow(key: "Domain", value: r.domain ?? "—")
                }
                Spacer()
                HStack {
                    Button("Cancel") { dismiss() }
                        .buttonStyle(SecondaryButtonStyle())
                    Spacer()
                    Button("Confirm") {
                        Task {
                            await state.confirm(id: receiptId)
                            dismiss()
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .keyboardShortcut(.defaultAction)
                }
            }
            .frame(minWidth: 320)
            .padding(DesignTokens.Spacing.space4)

            VStack(alignment: .leading, spacing: 8) {
                Text("Line items").font(.appHeadline)
                List(state.detailItems) { item in
                    HStack {
                        Text(item.productName ?? "Item #\(item.productId ?? 0)").font(.appBody)
                        Spacer()
                        Text(String(format: "$%.2f", item.totalPrice ?? (item.unitPrice ?? 0) * item.quantity))
                            .font(.appMonoBody)
                    }
                }
                .listStyle(.plain)
            }
            .frame(minWidth: 360)
            .padding(DesignTokens.Spacing.space4)
        }
        .frame(minWidth: 720, minHeight: 480)
        .navigationTitle("Review Receipt")
        .task { await state.loadDetail(id: receiptId) }
    }
}
