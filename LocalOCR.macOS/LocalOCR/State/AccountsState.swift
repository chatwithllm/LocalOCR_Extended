import Foundation
import os.log

// F-1200..F-1279 — Accounts (Plaid) state container.
//
// Commit A scope: Card Usage panel + Connected Accounts panel + Plaid Link
// bridge. Transactions, Review queue, Activity Breakdown, Spend by Person,
// and Spending Trends arrive in Commit B/C.

@MainActor
final class AccountsState: ObservableObject {

    static let shared = AccountsState()

    // Status
    @Published private(set) var plaidConfigured: Bool = false
    @Published private(set) var plaidEnv: String?

    // Card Usage (/plaid/cards-overview)
    @Published private(set) var cardsOverview: CardsOverviewResponse?
    @Published private(set) var cardsOverviewLoadedAt: Date?
    @Published var cardUsageCollapsed: Bool {
        didSet { UserDefaults.standard.set(cardUsageCollapsed, forKey: Defaults.cardUsageCollapsed) }
    }
    @Published var cardUsagePieFilter: String = "all"
    @Published var cardUsagePieCollapsed: Bool {
        didSet { UserDefaults.standard.set(cardUsagePieCollapsed, forKey: Defaults.pieCollapsed) }
    }
    @Published var cardUsageLoansCollapsed: Bool {
        didSet { UserDefaults.standard.set(cardUsageLoansCollapsed, forKey: Defaults.loansCollapsed) }
    }
    @Published var cardCollapsedOverrides: [String: Bool] {
        didSet { saveOverrides() }
    }

    // Connected Accounts (/plaid/items + /plaid/accounts)
    @Published private(set) var items: [PlaidItem] = []
    @Published private(set) var accounts: [PlaidAccount] = []
    @Published var connectionsCollapsed: Bool {
        didSet { UserDefaults.standard.set(connectionsCollapsed, forKey: Defaults.connectionsCollapsed) }
    }

    // UX state
    @Published var isLoadingCards = false
    @Published var isLoadingConnections = false
    @Published var isRefreshingBalances = false
    @Published var lastError: String?
    @Published var pendingLinkToken: String?
    @Published var pendingLinkItemId: Int?

    enum Defaults {
        static let cardUsageCollapsed = "LocalOCR.accounts.cardUsage.collapsed"
        static let pieCollapsed       = "LocalOCR.accounts.pie.collapsed"
        static let loansCollapsed     = "LocalOCR.accounts.loans.collapsed"
        static let connectionsCollapsed = "LocalOCR.accounts.connections.collapsed"
        static let cardCollapseOverrides = "LocalOCR.accounts.cardCollapseOverrides"
        static let pieFilter          = "LocalOCR.accounts.pieFilter"
    }

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "accounts")

    init(api: APIClient = .shared) {
        self.api = api
        let d = UserDefaults.standard
        self.cardUsageCollapsed   = d.bool(forKey: Defaults.cardUsageCollapsed)
        self.cardUsagePieCollapsed = d.bool(forKey: Defaults.pieCollapsed)
        self.cardUsageLoansCollapsed = d.bool(forKey: Defaults.loansCollapsed)
        self.connectionsCollapsed = d.bool(forKey: Defaults.connectionsCollapsed)
        self.cardUsagePieFilter   = d.string(forKey: Defaults.pieFilter) ?? "all"
        if let raw = d.data(forKey: Defaults.cardCollapseOverrides),
           let map = try? JSONDecoder().decode([String: Bool].self, from: raw) {
            self.cardCollapsedOverrides = map
        } else {
            self.cardCollapsedOverrides = [:]
        }
    }

    private func saveOverrides() {
        guard let data = try? JSONEncoder().encode(cardCollapsedOverrides) else { return }
        UserDefaults.standard.set(data, forKey: Defaults.cardCollapseOverrides)
    }

    // MARK: - Top-level refresh

    func refreshAll() async {
        await loadStatus()
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in await self.loadCardsOverview() }
            group.addTask { @MainActor in await self.loadConnections() }
        }
    }

    // MARK: - Status (F-1214 gating)

    func loadStatus() async {
        do {
            let resp = try await api.request(
                .get, path: PlaidEndpoint.status.path,
                as: PlaidStatusResponse.self
            )
            plaidConfigured = resp.configured
            plaidEnv = resp.env
            logger.info("plaid status configured=\(resp.configured, privacy: .public) env=\(resp.env ?? "-", privacy: .public)")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            logger.warning("loadStatus failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - Card Usage (F-1202..F-1212)

    func loadCardsOverview() async {
        isLoadingCards = true
        defer { isLoadingCards = false }
        do {
            let resp = try await api.request(
                .get, path: PlaidEndpoint.cardsOverview.path,
                as: CardsOverviewResponse.self
            )
            cardsOverview = resp
            cardsOverviewLoadedAt = Date()
            let total = resp.groups.reduce(0) { $0 + $1.accounts.count }
            logger.info("loaded \(total, privacy: .public) cards overview accounts in \(resp.groups.count, privacy: .public) groups")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadCardsOverview failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func refreshCardUsage() async {
        await refreshBalancesQuiet()
        await loadCardsOverview()
    }

    func setPieFilter(_ value: String) {
        cardUsagePieFilter = value
        UserDefaults.standard.set(value, forKey: Defaults.pieFilter)
    }

    func setCardCollapsed(_ plaidAccountId: String, collapsed: Bool) {
        cardCollapsedOverrides[plaidAccountId] = collapsed
    }

    func isCardCollapsed(_ account: CardsOverviewAccount) -> Bool {
        if let override = cardCollapsedOverrides[account.plaidAccountId ?? ""] {
            return override
        }
        return (account.balanceCents ?? 0) == 0
    }

    // MARK: - Connections (F-1215..F-1229)

    func loadConnections() async {
        isLoadingConnections = true
        defer { isLoadingConnections = false }
        do {
            async let itemsResp = api.request(
                .get, path: PlaidEndpoint.items.path,
                as: PlaidItemsResponse.self
            )
            async let acctResp = api.request(
                .get, path: PlaidEndpoint.accounts.path,
                as: PlaidAccountsResponse.self
            )
            let it = try await itemsResp
            let ac = try await acctResp
            items = it.items
            accounts = ac.accounts
            plaidConfigured = it.configured ?? plaidConfigured
            plaidEnv = it.env ?? plaidEnv
            logger.info("loaded \(it.items.count, privacy: .public) plaid items, \(ac.accounts.count, privacy: .public) sub-accounts")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadConnections failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func refreshBalances() async {
        isRefreshingBalances = true
        defer { isRefreshingBalances = false }
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: PlaidEndpoint.refreshBalances.path)
            ToastQueue.shared.push(Toast(message: "Balances refreshed", severity: .success))
            await loadConnections()
            await loadCardsOverview()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Refresh failed"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
            logger.warning("refreshBalances failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func refreshBalancesQuiet() async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: PlaidEndpoint.refreshBalances.path)
        } catch {
            // Quiet refresh — swallow errors; loadCardsOverview will surface staleness.
        }
    }

    func syncItem(_ item: PlaidItem) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: PlaidEndpoint.syncItem(id: item.id).path)
            ToastQueue.shared.push(Toast(message: "Sync started for \(item.institutionName ?? "bank")", severity: .success))
            await loadConnections()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Sync failed"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
        }
    }

    func renameItem(_ item: PlaidItem, nickname: String?) async {
        do {
            try DemoModeGate.guardMutation()
            let trimmed = (nickname ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let body = PlaidItemPatchBody(nickname: String(trimmed.prefix(64)), sharedWithUserIds: nil)
            try await api.request(.patch, path: PlaidEndpoint.patchItem(id: item.id).path, jsonBody: body)
            ToastQueue.shared.push(Toast(message: "Nickname saved", severity: .success))
            await loadConnections()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Could not rename"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
        }
    }

    func disconnectItem(_ item: PlaidItem) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.delete, path: PlaidEndpoint.deleteItem(id: item.id).path)
            ToastQueue.shared.push(Toast(
                message: "Disconnected \(item.institutionName ?? "bank")",
                severity: .success
            ))
            await loadConnections()
            await loadCardsOverview()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Could not disconnect"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
        }
    }

    func updateAccountIdentity(
        accountId: Int,
        displayName: String? = nil,
        ownerLabel: String? = nil
    ) async {
        do {
            try DemoModeGate.guardMutation()
            let body = PlaidIdentityBody(displayName: displayName, ownerLabel: ownerLabel)
            try await api.request(.patch, path: PlaidEndpoint.identityUpdate(id: accountId).path, jsonBody: body)
            await loadCardsOverview()
            await loadConnections()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Could not update card"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
        }
    }

    // MARK: - Plaid Link flow (F-1214 + F-1225 + F-1278 + F-1279)

    /// Begin the Connect Bank flow. Fetches a `link_token` and stores it for
    /// the `PlaidLinkSheet` to consume. `existingItemId` triggers update-mode
    /// (Re-authenticate an existing connection).
    func beginPlaidLink(itemId: Int? = nil) async -> String? {
        do {
            try DemoModeGate.guardMutation()
            let body = PlaidLinkTokenBody(itemId: itemId)
            let resp = try await api.request(
                .post, path: PlaidEndpoint.linkToken.path,
                jsonBody: body,
                as: PlaidLinkTokenResponse.self
            )
            pendingLinkToken = resp.linkToken
            pendingLinkItemId = itemId
            return resp.linkToken
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
            return nil
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Could not start Plaid Link"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
            return nil
        }
    }

    /// Plaid Link onSuccess callback — exchange the public token for an item.
    func completePlaidLink(publicToken: String, metadata: PlaidLinkMetadata?) async {
        do {
            try DemoModeGate.guardMutation()
            let body = PlaidExchangeBody(publicToken: publicToken, metadata: metadata)
            try await api.request(
                .post, path: PlaidEndpoint.exchangePublicToken.path,
                jsonBody: body
            )
            let name = metadata?.institution?.name ?? "bank"
            ToastQueue.shared.push(Toast(message: "Connected \(name)", severity: .success))
            pendingLinkToken = nil
            pendingLinkItemId = nil
            await loadConnections()
            await loadCardsOverview()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Could not save Plaid connection"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
        }
    }

    func cancelPlaidLink() {
        pendingLinkToken = nil
        pendingLinkItemId = nil
    }

    // MARK: - Derived

    func subAccounts(forItem itemId: Int) -> [PlaidAccount] {
        accounts.filter { $0.plaidItemId == itemId }
    }

    var hasNonUsdAccounts: Bool {
        cardsOverview?.groups
            .flatMap { $0.accounts }
            .contains(where: { ($0.balanceCurrency ?? "USD") != "USD" })
        ?? false
    }

    var creditGroup: CardsOverviewGroup? {
        cardsOverview?.groups.first(where: { $0.isCredit })
    }

    var loanGroup: CardsOverviewGroup? {
        cardsOverview?.groups.first(where: { $0.isLoan })
    }
}
