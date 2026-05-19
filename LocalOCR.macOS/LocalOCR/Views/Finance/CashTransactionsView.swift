import SwiftUI

struct CashTransactionsView: View {
    @StateObject private var state = FinanceState.shared

    @State private var amountText = ""
    @State private var description = ""
    @State private var category = ""
    @State private var date = Date()

    var body: some View {
        VStack(spacing: 0) {
            quickEntry
            Divider()
            list
        }
        .navigationTitle("Cash Transactions")
        .task { await state.loadCash() }
    }

    private var quickEntry: some View {
        Card {
            HStack(spacing: 8) {
                TextField("Amount", text: $amountText)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 100)
                TextField("Description", text: $description)
                    .textFieldStyle(.roundedBorder)
                TextField("Category", text: $category)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 140)
                DatePicker("", selection: $date, displayedComponents: .date).labelsHidden()
                Button("Add") { Task { await submit() } }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(Double(amountText) == nil || description.isEmpty)
                    .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(DesignTokens.Spacing.space3)
    }

    private var list: some View {
        Group {
            if state.cashTransactions.isEmpty {
                EmptyStateView(systemImage: "banknote", title: "No cash transactions yet",
                               subtitle: "Use the form above to log a cash payment.")
            } else {
                List(state.cashTransactions) { tx in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(tx.description).font(.appBody)
                            HStack(spacing: 6) {
                                if let c = tx.category {
                                    Text(c).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                                }
                                Text("• \(tx.transactionDate.formatted(date: .abbreviated, time: .omitted))")
                                    .font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                            }
                        }
                        Spacer()
                        Text(String(format: "$%.2f", tx.amount)).font(.appMonoBody)
                    }
                }
                .listStyle(.plain)
            }
        }
    }

    private func submit() async {
        guard let amount = Double(amountText) else { return }
        await state.addCash(amount: amount, description: description, category: category.isEmpty ? nil : category, date: date)
        amountText = ""
        description = ""
        category = ""
    }
}

#Preview("CashTransactions") {
    CashTransactionsView().frame(width: 800, height: 600)
}
