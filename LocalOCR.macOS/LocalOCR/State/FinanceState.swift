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

    /// `/analytics/spending` shape (from calculate_spending_analytics.py):
    /// {
    ///   "period": "monthly",
    ///   "domain": "all",
    ///   "months_back": 6,
    ///   "grand_total": 12345.67,
    ///   "spending_by_period": { "2026-05": {total, count, purchase_count, refund_count, purchase_total, refund_total}, ... },
    ///   "category_breakdown": { "Grocery": {total, count}, "Other": {total, count}, ... }
    /// }
    private func parseSpending(_ data: Data) -> SpendingAnalytics? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }

        // Categories — sort by total desc.
        let categoryDict = (json["category_breakdown"] as? [String: [String: Any]]) ?? [:]
        let categories: [SpendingCategoryTotal] = categoryDict
            .map { name, payload in
                let total = (payload["total"] as? Double) ?? Double(payload["total"] as? Int ?? 0)
                let count = (payload["count"] as? Int) ?? 0
                return SpendingCategoryTotal(category: name.capitalized, total: total, receiptCount: count)
            }
            .sorted { $0.total > $1.total }

        // Monthly timeline — keys are "YYYY-MM" strings.
        let periodDict = (json["spending_by_period"] as? [String: [String: Any]]) ?? [:]
        let monthly: [MonthlySpend] = periodDict
            .map { key, payload in
                let total = (payload["total"] as? Double) ?? Double(payload["total"] as? Int ?? 0)
                return MonthlySpend(month: key, total: total)
            }
            .sorted { $0.month < $1.month }

        // Build period label. Prefer months-back range.
        let periodKey = (json["period"] as? String) ?? "monthly"
        let monthsBack = (json["months_back"] as? Int) ?? 6
        let label = "Last \(monthsBack) \(periodKey == "monthly" ? "months" : periodKey)"

        return SpendingAnalytics(
            categories: categories,
            topMerchants: [],       // `/analytics/spending` doesn't expose merchants
            monthlyTimeline: monthly,
            periodLabel: label
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
