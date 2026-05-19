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
            bills = try await api.request(.get, path: FixedBillsEndpoint.list.path, as: [FixedBill].self)
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadBills: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadCash() async {
        do {
            cashTransactions = try await api.request(.get, path: CashEndpoint.list.path, as: [CashTransaction].self)
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func loadPlaid() async {
        do {
            async let accounts = api.request(.get, path: PlaidEndpoint.accounts.path, as: [PlaidAccount].self)
            async let staged = api.request(.get, path: PlaidEndpoint.stagedTransactions.path, as: [PlaidTransaction].self)
            plaidAccounts = try await accounts
            stagedTransactions = try await staged
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func loadSpending(month: String? = nil) async {
        do {
            var query: [URLQueryItem] = []
            if let month { query.append(URLQueryItem(name: "month", value: month)) }
            spending = try await api.request(
                .get,
                path: AnalyticsEndpoint.spendingByCategory(month: month).path,
                query: query,
                as: SpendingAnalytics.self
            )
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    // MARK: - Mutations (bills)

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

    func markBillPaid(id: Int, amount: Double, date: Date = Date()) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .post,
                path: FixedBillsEndpoint.markPaid(id: id, amount: amount, date: date).path,
                jsonBody: BillMarkPaidBody(amount: amount, paidAt: date)
            )
            await loadBills()
            ToastQueue.shared.push(Toast(message: "Bill marked paid", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    // MARK: - Mutations (cash)

    func addCash(amount: Double, description: String, category: String?, date: Date) async {
        do {
            try DemoModeGate.guardMutation()
            let body = CashCreateBody(amount: amount, description: description, category: category, transactionDate: date)
            let created: CashTransaction = try await api.request(.post, path: CashEndpoint.list.path, jsonBody: body)
            cashTransactions.insert(created, at: 0)
            ToastQueue.shared.push(Toast(message: "Cash transaction added", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    // MARK: - Plaid

    func syncPlaid() async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: PlaidEndpoint.syncNow.path)
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
            try await api.request(.post, path: PlaidEndpoint.confirmTransaction(id: id).path)
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
            try await api.request(.post, path: PlaidEndpoint.dismissTransaction(id: id).path)
            stagedTransactions.removeAll { $0.id == id }
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }
}
