import SwiftUI

struct FixedBillsView: View {
    @StateObject private var state = FinanceState.shared

    var body: some View {
        Group {
            if state.bills.isEmpty {
                EmptyStateView(
                    systemImage: "doc.text",
                    title: "No fixed bills",
                    subtitle: "Add recurring bills (rent, utilities, subscriptions) to track them automatically."
                )
            } else {
                List {
                    Section("Active (\(state.bills.filter(\.isActive).count))") {
                        ForEach(state.bills.filter(\.isActive)) { bill in
                            BillRow(bill: bill,
                                    onRename: { newLabel in Task { await state.renameBill(id: bill.id, label: newLabel) } },
                                    onMarkPaid: { Task { await state.markBillPaid(id: bill.id, amount: bill.expectedMonthlyAmount) } })
                        }
                    }
                    Section("Available") {
                        ForEach(state.bills.filter { !$0.isActive }) { bill in
                            BillRow(bill: bill,
                                    onRename: { newLabel in Task { await state.renameBill(id: bill.id, label: newLabel) } },
                                    onMarkPaid: { Task { await state.markBillPaid(id: bill.id, amount: bill.expectedMonthlyAmount) } })
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Fixed Bills")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await state.loadBills() } } label: { Label("Refresh", systemImage: "arrow.clockwise") }
            }
        }
        .task { await state.loadBills() }
    }
}

private struct BillRow: View {
    let bill: FixedBill
    let onRename: (String) -> Void
    let onMarkPaid: () -> Void

    @State private var editingName: String = ""

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            Button(action: onMarkPaid) {
                Image(systemName: bill.paymentStatus == "paid" ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 17))
                    .foregroundStyle(bill.paymentStatus == "paid" ? DesignTokens.success : DesignTokens.tertiaryLabel)
            }
            .buttonStyle(.borderless)
            .keyboardShortcut(.space, modifiers: [])

            VStack(alignment: .leading, spacing: 2) {
                InlineEditableCell(
                    text: Binding(get: { editingName.isEmpty ? bill.label : editingName }, set: { editingName = $0 }),
                    onCommit: { newValue in onRename(newValue) }
                )
                HStack(spacing: 6) {
                    Badge(text: bill.paymentStatus.capitalized, style: paymentStyle(bill.paymentStatus))
                    Text(bill.billingCycle.capitalized).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    if let d = bill.nextDueDate {
                        Text("• Due \(d.formatted(date: .abbreviated, time: .omitted))")
                            .font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
            }
            Spacer()
            Text(String(format: "$%.2f", bill.expectedMonthlyAmount))
                .font(.appMonoBody.weight(.semibold))
                .foregroundStyle(DesignTokens.label)
        }
        .padding(.vertical, 4)
    }

    private func paymentStyle(_ status: String) -> Badge.Style {
        switch status {
        case "paid":    return .success
        case "overdue": return .error
        default:        return .warning
        }
    }
}

#Preview("FixedBills") {
    FixedBillsView().frame(width: 700, height: 500)
}
