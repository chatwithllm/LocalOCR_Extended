import SwiftUI

struct CashTransactionsView: View {
    @StateObject private var state = FinanceState.shared

    @State private var amountText = ""
    @State private var description = ""
    @State private var category = ""
    @State private var date = Date()

    var body: some View {
        VStack(spacing: 0) {
            summaryBar
            Divider()
            quickEntry
            Divider()
            content
        }
        .navigationTitle("Cash Transactions")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { Task { await state.loadCash() } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Refresh cash transactions")
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .task { await state.loadCash() }
    }

    private var summaryBar: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            summaryChip(label: "Entries", value: "\(state.cashTransactions.count)", color: DesignTokens.label)
            if let last = state.cashTransactions.first?.transactionDate {
                Text("Most recent: \(last.formatted(date: .abbreviated, time: .omitted))")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
            Spacer()
            Text(String(format: "Total $%.2f", state.cashTransactions.reduce(0) { $0 + $1.amount }))
                .font(.appMonoBody.weight(.semibold))
                .foregroundStyle(DesignTokens.label)
        }
        .padding(.horizontal, DesignTokens.Spacing.space4)
        .padding(.vertical, DesignTokens.Spacing.space2)
        .background(DesignTokens.surface2)
    }

    private var quickEntry: some View {
        HStack(spacing: 8) {
            TextField("Amount", text: $amountText)
                .textFieldStyle(.roundedBorder)
                .frame(width: 96)
            TextField("Description", text: $description)
                .textFieldStyle(.roundedBorder)
            TextField("Category", text: $category)
                .textFieldStyle(.roundedBorder)
                .frame(width: 140)
            DatePicker("", selection: $date, displayedComponents: .date)
                .labelsHidden()
            Button("Add") { Task { await submit() } }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(Double(amountText) == nil || description.isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(DesignTokens.Spacing.space3)
        .background(DesignTokens.background)
    }

    private var content: some View {
        Group {
            if state.cashTransactions.isEmpty {
                EmptyStateView(
                    systemImage: "banknote",
                    title: "No cash transactions yet",
                    subtitle: "Use the form above to log a cash payment — ⌘Return submits."
                )
            } else {
                List {
                    ForEach(groupedByMonth, id: \.0) { month, items in
                        Section {
                            ForEach(items) { tx in
                                CashRow(transaction: tx)
                            }
                        } header: {
                            sectionHeader(month.uppercased())
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
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

    private var groupedByMonth: [(String, [CashTransaction])] {
        let fmt = DateFormatter()
        fmt.dateFormat = "LLLL yyyy"
        let groups = Dictionary(grouping: state.cashTransactions) { fmt.string(from: $0.transactionDate) }
        return groups
            .map { ($0.key, $0.value.sorted { $0.transactionDate > $1.transactionDate }) }
            .sorted { ($0.1.first?.transactionDate ?? .distantPast) > ($1.1.first?.transactionDate ?? .distantPast) }
    }

    private func submit() async {
        guard let amount = Double(amountText) else { return }
        await state.addCash(amount: amount, description: description,
                            category: category.isEmpty ? nil : category, date: date)
        amountText = ""
        description = ""
        category = ""
    }
}

private struct CashRow: View {
    let transaction: CashTransaction

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            VStack(alignment: .leading, spacing: 2) {
                Text(transaction.description).font(.appBody)
                HStack(spacing: 6) {
                    if let c = transaction.category {
                        Text(c).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    Text("• \(transaction.transactionDate.formatted(date: .abbreviated, time: .omitted))")
                        .font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                }
            }
            Spacer()
            Text(String(format: "$%.2f", transaction.amount))
                .font(.appMonoBody.weight(.semibold))
                .foregroundStyle(DesignTokens.label)
        }
        .padding(.vertical, 4)
    }
}

#Preview("CashTransactions") {
    CashTransactionsView().frame(width: 800, height: 600)
}
