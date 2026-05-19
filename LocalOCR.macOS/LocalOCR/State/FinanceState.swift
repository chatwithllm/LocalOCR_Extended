import Foundation
import os.log

@MainActor
final class FinanceState: ObservableObject {

    static let shared = FinanceState()

    @Published private(set) var bills: [FixedBill] = []
    @Published private(set) var cashTransactions: [CashTransaction] = []
    @Published private(set) var plaidAccounts: [PlaidAccount] = []
    @Published private(set) var stagedTransactions: [PlaidTransaction] = []
    @Published private(set) var spending: SpendingAnalytics?
    @Published private(set) var isLoading = false
    @Published var lastError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "finance")

    init(api: APIClient = .shared) {
        self.api = api
    }

    // MARK: - Loads

    func loadBills() async {
        do {
            let response = try await api.request(
                .get,
                path: FixedBillsEndpoint.list.path,
                as: ObligationsListResponse.self
            )
            bills = response.obligations
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadBills: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadCash() async {
        do {
            let response = try await api.request(
                .get,
                path: CashEndpoint.list.path,
                as: CashTransactionsResponse.self
            )
            cashTransactions = response.transactions
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func loadPlaid() async {
        do {
            async let accountsResponse = api.request(.get, path: PlaidEndpoint.accounts.path, as: PlaidAccountsResponse.self)
            async let stagedResponse = api.request(.get, path: PlaidEndpoint.stagedTransactions.path, as: PlaidStagedResponse.self)
            plaidAccounts = try await accountsResponse.accounts
            stagedTransactions = try await stagedResponse.rows
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadPlaid: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Loads analytics — backend `/analytics/spending` returns a rich envelope.
    /// Phase 4 polish: decode loosely with JSON, extract the slice we use.
    func loadSpending(month: String? = nil) async {
        do {
            var query: [URLQueryItem] = []
            if let month { query.append(URLQueryItem(name: "month", value: month)) }

            // Use raw JSON to be forgiving of the rich/changing analytics shape.
            let data = try await api.rawRequest(
                .get,
                path: AnalyticsEndpoint.spending(month: month).path,
                query: query
            )
            spending = parseSpending(data)
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    private func parseSpending(_ data: Data) -> SpendingAnalytics? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        let categoriesRaw = (json["categories"] as? [[String: Any]]) ?? []
        let categories: [SpendingCategoryTotal] = categoriesRaw.compactMap { row in
            guard let cat = row["category"] as? String else { return nil }
            let total = (row["total"] as? Double) ?? Double(row["total"] as? Int ?? 0)
            let count = (row["receipt_count"] as? Int) ?? (row["count"] as? Int) ?? 0
            return SpendingCategoryTotal(category: cat, total: total, receiptCount: count)
        }

        let merchantsRaw = (json["top_merchants"] as? [[String: Any]]) ?? []
        let merchants: [MerchantFrequency] = merchantsRaw.compactMap { row in
            guard let name = row["name"] as? String else { return nil }
            let visits = (row["visit_count"] as? Int) ?? (row["count"] as? Int) ?? 0
            let avg = (row["avg_amount"] as? Double) ?? 0
            return MerchantFrequency(name: name, visitCount: visits, avgAmount: avg)
        }

        let monthlyRaw = (json["monthly_timeline"] as? [[String: Any]]) ?? []
        let monthly: [MonthlySpend] = monthlyRaw.compactMap { row in
            guard let month = row["month"] as? String else { return nil }
            let total = (row["total"] as? Double) ?? Double(row["total"] as? Int ?? 0)
            return MonthlySpend(month: month, total: total)
        }

        let period = (json["period_label"] as? String) ?? (json["period"] as? String) ?? ""
        return SpendingAnalytics(
            categories: categories,
            topMerchants: merchants,
            monthlyTimeline: monthly,
            periodLabel: period
        )
    }

    // MARK: - Mutations

    func renameBill(id: Int, label: String) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .patch,
                path: FixedBillsEndpoint.rename(id: id, label: label).path,
                jsonBody: BillRenameBody(label: label)
            )
            await loadBills()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    /// Bill mark-paid isn't a single backend endpoint — it routes through a cash
    /// transaction tied to the bill provider. Phase 4 surfaces an info toast
    /// rather than a broken POST.
    func markBillPaid(id: Int, amount: Double, date: Date = Date()) async {
        ToastQueue.shared.push(Toast(
            message: "Mark Paid is handled through cash transactions on the web app.",
            severity: .info
        ))
    }

    // Cash + Plaid mutations preserved as no-ops until matching backend
    // endpoints are wired. (Web app handles linking flow + transaction confirm.)

    func syncPlaid() async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: PlaidEndpoint.refreshBalances.path)
            await loadPlaid()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func confirmStagedTransaction(id: Int) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: PlaidEndpoint.confirmStaged(id: id).path)
            stagedTransactions.removeAll { $0.id == id }
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func dismissStagedTransaction(id: Int) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: PlaidEndpoint.dismissStaged(id: id).path)
            stagedTransactions.removeAll { $0.id == id }
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func addCash(amount: Double, description: String, category: String?, date: Date) async {
        ToastQueue.shared.push(Toast(
            message: "Cash entries are managed under bill providers on the web app.",
            severity: .info
        ))
    }
}
