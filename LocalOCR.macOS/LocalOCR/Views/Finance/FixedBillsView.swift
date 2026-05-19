import SwiftUI

struct FixedBillsView: View {
    @StateObject private var state = FinanceState.shared

    var body: some View {
        Group {
            if state.bills.isEmpty {
                emptyStateView
            } else {
                populatedView
            }
        }
        .navigationTitle("Fixed Bills")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { Task { await state.loadBills() } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Refresh bills")
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .task { await state.loadBills() }
    }

    private var emptyStateView: some View {
        EmptyStateView(
            systemImage: "doc.text",
            title: "No fixed bills",
            subtitle: "Recurring bills (rent, utilities, subscriptions) show up here once they're configured server-side."
        )
    }

    private var populatedView: some View {
        VStack(spacing: 0) {
            summaryBar
            Divider()
            List {
                if !activeBills.isEmpty {
                    Section {
                        ForEach(activeBills) { bill in
                            BillRow(
                                bill: bill,
                                onRename: { newLabel in Task { await state.renameBill(id: bill.id, label: newLabel) } },
                                onMarkPaid: { Task { await state.markBillPaid(id: bill.id, amount: bill.expectedMonthlyAmount) } }
                            )
                        }
                    } header: {
                        sectionHeader("ACTIVE (\(activeBills.count))")
                    }
                }
                if !availableBills.isEmpty {
                    Section {
                        ForEach(availableBills) { bill in
                            BillRow(
                                bill: bill,
                                onRename: { newLabel in Task { await state.renameBill(id: bill.id, label: newLabel) } },
                                onMarkPaid: { Task { await state.markBillPaid(id: bill.id, amount: bill.expectedMonthlyAmount) } }
                            )
                        }
                    } header: {
                        sectionHeader("AVAILABLE (\(availableBills.count))")
                    }
                }
            }
            .listStyle(.plain)
        }
        .background(DesignTokens.background)
    }

    private var summaryBar: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            summaryChip(label: "Paid", value: "\(paidCount)", color: DesignTokens.success)
            summaryChip(label: "Unpaid", value: "\(unpaidCount)", color: DesignTokens.warning)
            summaryChip(label: "Overdue", value: "\(overdueCount)", color: DesignTokens.error)
            Spacer()
            VStack(alignment: .trailing, spacing: 0) {
                Text(String(format: "$%.2f", expectedTotal))
                    .font(.appMonoBody.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
                Text("expected this month")
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.space4)
        .padding(.vertical, DesignTokens.Spacing.space2)
        .background(DesignTokens.surface2)
    }

    private func summaryChip(label: String, value: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Text(value).font(.appMonoCaption.weight(.semibold)).foregroundStyle(color)
            Text(label).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(DesignTokens.secondaryLabel)
            .padding(.leading, 4)
            .padding(.top, DesignTokens.Spacing.space1)
    }

    private var activeBills: [FixedBill] { state.bills.filter(\.isActive) }
    private var availableBills: [FixedBill] { state.bills.filter { !$0.isActive } }
    private var paidCount: Int { activeBills.filter { $0.paymentStatus == "paid" }.count }
    private var unpaidCount: Int { activeBills.filter { $0.paymentStatus == "unpaid" }.count }
    private var overdueCount: Int { activeBills.filter { $0.paymentStatus == "overdue" }.count }
    private var expectedTotal: Double { activeBills.reduce(0) { $0 + $1.expectedMonthlyAmount } }
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
            .accessibilityLabel(bill.paymentStatus == "paid" ? "Mark unpaid" : "Mark paid")

            VStack(alignment: .leading, spacing: 2) {
                InlineEditableCell(
                    text: Binding(get: { editingName.isEmpty ? bill.label : editingName }, set: { editingName = $0 }),
                    onCommit: { newValue in onRename(newValue) }
                )
                HStack(spacing: 6) {
                    Badge(text: bill.paymentStatus.capitalized, style: paymentStyle(bill.paymentStatus))
                    if let cat = bill.providerCategory {
                        Text(cat.capitalized).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    if let avg = bill.avg6mo {
                        Text("• avg $\(String(format: "%.0f", avg))/mo")
                            .font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                    if let latest = bill.latestActual {
                        Text("• last $\(String(format: "%.0f", latest))")
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
    FixedBillsView().frame(width: 800, height: 500)
}
