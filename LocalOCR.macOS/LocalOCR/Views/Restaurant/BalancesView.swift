import SwiftUI
import AppKit
import os.log

// MARK: - F-800..F-817 — Balances
//
// "Who Owes What" table for shared-dining debts. Mirrors web
// `loadBalances` and `settleAllWithContact`.
// Routes verified against `shared_dining_endpoints.py`.

@MainActor
final class SharedDiningState: ObservableObject {

    static let shared = SharedDiningState()

    @Published private(set) var balances: [BalanceRow] = []
    @Published private(set) var contacts: [DiningContactRow] = []
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?
    @Published var pendingSettle: BalanceRow?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "shared-dining")

    init(api: APIClient = .shared) {
        self.api = api
    }

    func loadBalances() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let rows = try await api.request(
                .get,
                path: SharedDiningEndpoint.balances.path,
                as: [BalanceRow].self
            )
            balances = rows
            logger.info("loaded \(rows.count, privacy: .public) balance rows")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadBalances failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // F-813..F-817
    func settleAll(_ row: BalanceRow) async {
        do {
            try DemoModeGate.guardMutation()
            let response = try await api.request(
                .post,
                path: SharedDiningEndpoint.settleAll(contactId: row.contactId).path,
                jsonBody: EmptyBody(),
                as: SettleAllResponse.self
            )
            let count = response.settled ?? 0
            ToastQueue.shared.push(Toast(
                message: "Settled \(count) debt\(count == 1 ? "" : "s") with \(row.name)",
                severity: .success
            ))
            await loadBalances()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Could not settle debts",
                severity: .error
            ))
        }
    }
}

private struct EmptyBody: Encodable {}

// MARK: - View

struct BalancesView: View {
    @StateObject private var state = SharedDiningState.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                header
                BalancesCard(state: state)
                PageNavStrip()
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Balances")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await state.loadBalances() }
                } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                .help("Reload outstanding balances")
            }
        }
        .onAppear {
            Task.detached(priority: .userInitiated) {
                await SharedDiningState.shared.loadBalances()
            }
        }
        .confirmationDialog(
            "Mark all debts with \(state.pendingSettle?.name ?? "") as settled?",
            isPresented: Binding(
                get: { state.pendingSettle != nil },
                set: { if !$0 { state.pendingSettle = nil } }
            ),
            titleVisibility: .visible,
            presenting: state.pendingSettle
        ) { row in
            Button("Settle all", role: .destructive) {
                let target = row
                state.pendingSettle = nil
                Task { await state.settleAll(target) }
            }
            Button("Cancel", role: .cancel) {
                state.pendingSettle = nil
            }
        } message: { _ in
            Text("This marks every outstanding debt with this contact as settled. The action can't be undone here.")
        }
    }

    // F-800 + F-801
    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Balances").font(.appTitle2)
            Text("Outstanding debts across all shared receipts")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }
}

// MARK: - F-803..F-813 balances card / table

private struct BalancesCard: View {
    @ObservedObject var state: SharedDiningState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Who Owes What").font(.appHeadline)
                    Spacer()
                    if !state.balances.isEmpty {
                        Text("\(state.balances.count) contact\(state.balances.count == 1 ? "" : "s")")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
                content
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if state.isLoading && state.balances.isEmpty {
            EmptyStateView(systemImage: "hourglass", title: "Loading…")
                .frame(height: 160)
        } else if let err = state.lastError, state.balances.isEmpty {
            EmptyStateView(
                systemImage: "exclamationmark.triangle",
                title: "Could not load balances.",
                subtitle: err
            )
            .frame(height: 160)
        } else if state.balances.isEmpty {
            EmptyStateView(
                systemImage: "checkmark.seal",
                title: "No outstanding balances — all settled! 🎉"
            )
            .frame(height: 160)
        } else {
            VStack(spacing: 0) {
                BalanceHeaderRow()
                ForEach(state.balances) { row in
                    BalanceRowView(row: row, state: state)
                    Divider()
                }
            }
        }
    }
}

private struct BalanceHeaderRow: View {
    var body: some View {
        HStack {
            Text("Contact")
                .font(.appCaption2.weight(.semibold))
                .foregroundStyle(DesignTokens.tertiaryLabel)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text("Direction")
                .font(.appCaption2.weight(.semibold))
                .foregroundStyle(DesignTokens.tertiaryLabel)
                .frame(width: 100, alignment: .leading)
            Text("Amount")
                .font(.appCaption2.weight(.semibold))
                .foregroundStyle(DesignTokens.tertiaryLabel)
                .frame(width: 100, alignment: .trailing)
            Spacer().frame(width: 110)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }
}

// F-808 / F-809 / F-810 / F-811 / F-812 / F-813
private struct BalanceRowView: View {
    let row: BalanceRow
    @ObservedObject var state: SharedDiningState

    var body: some View {
        HStack {
            Text(row.name)
                .font(.appCallout.weight(.medium))
                .foregroundStyle(DesignTokens.label)
                .frame(maxWidth: .infinity, alignment: .leading)
                .lineLimit(1)
                .truncationMode(.tail)
            Text(row.owesYou ? "Owes you" : "You owe")
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(row.owesYou ? DesignTokens.success : DesignTokens.error)
                .frame(width: 100, alignment: .leading)
            Text(amountText)
                .font(.appCallout.weight(.semibold).monospacedDigit())
                .foregroundStyle(row.owesYou ? DesignTokens.success : DesignTokens.error)
                .frame(width: 100, alignment: .trailing)
            Button {
                state.pendingSettle = row
            } label: { Text("Settle all") }
            .buttonStyle(DestructiveButtonStyle())
            .help("Mark every debt with \(row.name) as settled")
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
    }

    private var amountText: String {
        String(format: "$%.2f", abs(row.netAmount))
    }
}

#Preview("BalancesView") {
    BalancesView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 800, height: 600)
}
