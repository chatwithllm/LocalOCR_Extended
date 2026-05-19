import SwiftUI

struct PlaidAccountsView: View {
    @StateObject private var state = FinanceState.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                Text("Plaid Accounts").font(.appTitle1)
                if state.plaidAccounts.isEmpty {
                    EmptyStateView(systemImage: "creditcard", title: "No accounts linked",
                                   subtitle: "Link a bank or card account to import transactions automatically.")
                        .frame(height: 240)
                } else {
                    ForEach(state.plaidAccounts) { account in
                        Card {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(account.displayName ?? account.accountName).font(.appHeadline)
                                    Spacer()
                                    Badge(text: account.status.capitalized, style: statusStyle(account.status))
                                }
                                if let mask = account.accountMask {
                                    Text("•••• \(mask)").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                                }
                                if let cents = account.balanceCents {
                                    Text(String(format: "$%.2f", Double(cents) / 100.0)).font(.appMonoBody)
                                }
                            }
                        }
                    }
                }

                Divider()
                Text("Staged Transactions (\(state.stagedTransactions.count))").font(.appTitle2)
                if state.stagedTransactions.isEmpty {
                    Text("No pending transactions").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                } else {
                    ForEach(state.stagedTransactions) { tx in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(tx.merchantName ?? "Unknown").font(.appBody)
                                Text(tx.transactionDate.formatted(date: .abbreviated, time: .omitted))
                                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                            }
                            Spacer()
                            Text(String(format: "$%.2f", tx.amount)).font(.appMonoBody)
                            Button("Confirm") { Task { await state.confirmStagedTransaction(id: tx.id) } }
                                .buttonStyle(SecondaryButtonStyle())
                            Button("Dismiss") { Task { await state.dismissStagedTransaction(id: tx.id) } }
                                .buttonStyle(GhostButtonStyle())
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .navigationTitle("Plaid")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await state.syncPlaid() } } label: { Label("Sync Now", systemImage: "arrow.triangle.2.circlepath") }
            }
        }
        .task { await state.loadPlaid() }
    }

    private func statusStyle(_ s: String) -> Badge.Style {
        switch s.lowercased() {
        case "active":         return .success
        case "loginrequired":  return .warning
        case "disconnected":   return .error
        default:               return .neutral
        }
    }
}

#Preview("Plaid") {
    PlaidAccountsView().frame(width: 800, height: 600)
}
