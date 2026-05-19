import SwiftUI

struct PlaidAccountsView: View {
    @StateObject private var state = FinanceState.shared

    var body: some View {
        Group {
            if state.plaidAccounts.isEmpty && state.stagedTransactions.isEmpty {
                emptyStateView
            } else {
                populatedView
            }
        }
        .navigationTitle("Plaid")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { Task { await state.syncPlaid() } } label: {
                    Label("Sync Now", systemImage: "arrow.triangle.2.circlepath")
                }
                .help("Pull latest transactions from Plaid")
                .disabled(state.plaidAccounts.isEmpty)
                Button { Task { await state.loadPlaid() } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Refresh accounts + staged transactions")
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .task { await state.loadPlaid() }
    }

    private var emptyStateView: some View {
        EmptyStateView(
            systemImage: "creditcard",
            title: "No accounts linked",
            subtitle: "Link a bank or card account to import transactions automatically. Plaid Link is started server-side."
        )
    }

    private var populatedView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                accountsSection
                if !state.stagedTransactions.isEmpty {
                    stagedSection
                }
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .background(DesignTokens.background)
    }

    private var accountsSection: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            HStack {
                Text("Accounts").font(.appTitle2)
                Spacer()
                Text("\(state.plaidAccounts.count) linked")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
            ForEach(state.plaidAccounts) { account in
                accountCard(account)
            }
        }
    }

    private func accountCard(_ account: PlaidAccount) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(account.displayName ?? account.accountName).font(.appHeadline)
                    Spacer()
                    Badge(text: account.status.replacingOccurrences(of: "_", with: " ").capitalized,
                          style: statusStyle(account.status))
                }
                HStack(spacing: 8) {
                    if let mask = account.accountMask {
                        Text("•••• \(mask)")
                            .font(.appMonoCaption)
                            .foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    Text(account.accountType.capitalized)
                        .font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    Spacer()
                    if let cents = account.balanceCents {
                        Text(String(format: "$%.2f", Double(cents) / 100.0))
                            .font(.appMonoBody.weight(.semibold))
                    }
                }
                if let synced = account.lastSyncedAt {
                    Text("Last synced \(synced.formatted(date: .abbreviated, time: .shortened))")
                        .font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                }
            }
        }
    }

    private var stagedSection: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            HStack {
                Text("Staged transactions").font(.appTitle2)
                Spacer()
                Text("\(state.stagedTransactions.count) pending")
                    .font(.appCaption1).foregroundStyle(DesignTokens.warning)
            }
            ForEach(state.stagedTransactions) { tx in
                Card {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(tx.merchantName ?? "Unknown merchant").font(.appBody)
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
                }
            }
        }
    }

    private func statusStyle(_ s: String) -> Badge.Style {
        switch s.lowercased() {
        case "active":         return .success
        case "loginrequired", "login_required":  return .warning
        case "disconnected":   return .error
        default:               return .neutral
        }
    }
}

#Preview("Plaid") {
    PlaidAccountsView().frame(width: 800, height: 600)
}
