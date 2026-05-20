import Foundation
import os.log

// F-1300..F-1321 — Analytics (Spending Overview + Deals Captured).

@MainActor
final class AnalyticsState: ObservableObject {

    static let shared = AnalyticsState()

    enum Period: String, CaseIterable, Identifiable {
        case monthly, weekly
        var id: String { rawValue }
        var label: String {
            switch self {
            case .monthly: return "Monthly"
            case .weekly:  return "Weekly"
            }
        }
    }

    enum Domain: String, CaseIterable, Identifiable {
        case grocery, restaurant, generalExpense = "general_expense", all = ""
        var id: String { rawValue }
        var label: String {
            switch self {
            case .grocery:        return "Grocery"
            case .restaurant:     return "Restaurant"
            case .generalExpense: return "General Expense"
            case .all:            return "All Modules"
            }
        }
        var queryValue: String? { self == .all ? nil : rawValue }
    }

    enum Sort: String, CaseIterable, Identifiable {
        case periodDesc = "period_desc"
        case periodAsc  = "period_asc"
        case totalDesc  = "total_desc"
        case countDesc  = "count_desc"
        var id: String { rawValue }
        var label: String {
            switch self {
            case .periodDesc: return "Newest Period"
            case .periodAsc:  return "Oldest Period"
            case .totalDesc:  return "Highest Total"
            case .countDesc:  return "Most Items"
            }
        }
    }

    @Published var period: Period = .monthly {
        didSet {
            UserDefaults.standard.set(period.rawValue, forKey: Defaults.period)
            Task { @MainActor in await self.loadSpending() }
        }
    }
    @Published var domain: Domain = .grocery {
        didSet {
            UserDefaults.standard.set(domain.rawValue, forKey: Defaults.domain)
            Task { @MainActor in
                await self.loadSpending()
                await self.loadDeals()
            }
        }
    }
    @Published var sort: Sort = .periodDesc {
        didSet { UserDefaults.standard.set(sort.rawValue, forKey: Defaults.sort) }
    }
    @Published private(set) var spending: AnalyticsSpendingOverviewResponse?
    @Published private(set) var deals: AnalyticsDealsResponse?
    @Published var isLoadingSpending = false
    @Published var isLoadingDeals = false
    @Published var spendingError: String?
    @Published var dealsError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "analytics")

    enum Defaults {
        static let period = "LocalOCR.analytics.period"
        static let domain = "LocalOCR.analytics.domain"
        static let sort   = "LocalOCR.analytics.sort"
    }

    init(api: APIClient = .shared) {
        self.api = api
        let d = UserDefaults.standard
        if let raw = d.string(forKey: Defaults.period),
           let p = Period(rawValue: raw) { self.period = p }
        if let raw = d.string(forKey: Defaults.domain),
           let dom = Domain(rawValue: raw) { self.domain = dom }
        if let raw = d.string(forKey: Defaults.sort),
           let s = Sort(rawValue: raw) { self.sort = s }
    }

    func refreshAll() async {
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in await self.loadSpending() }
            group.addTask { @MainActor in await self.loadDeals() }
        }
    }

    func loadSpending() async {
        isLoadingSpending = true
        defer { isLoadingSpending = false }
        do {
            let endpoint = AnalyticsEndpoint.spendingOverview(
                period: period.rawValue,
                domain: domain.queryValue,
                months: 6
            )
            let resp = try await api.request(
                .get, path: endpoint.path,
                query: endpoint.query,
                as: AnalyticsSpendingOverviewResponse.self
            )
            spending = resp
            spendingError = nil
            logger.info("loaded analytics spending — \(resp.spendingByPeriod.count, privacy: .public) periods · grand=\(String(format: "%.2f", resp.grandTotal), privacy: .public)")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            spendingError = (error as? APIError)?.errorDescription ?? "Could not load spending."
            logger.error("loadSpending failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadDeals() async {
        // Deals only relevant for grocery domain or "all"; web suppresses the
        // body for restaurant / general_expense (replaced by a domain notice).
        isLoadingDeals = true
        defer { isLoadingDeals = false }
        do {
            let endpoint = AnalyticsEndpoint.dealsCaptured(months: 1)
            let resp = try await api.request(
                .get, path: endpoint.path,
                query: endpoint.query,
                as: AnalyticsDealsResponse.self
            )
            deals = resp
            dealsError = nil
            logger.info("loaded analytics deals — count=\(resp.dealCount, privacy: .public) saved=\(String(format: "%.2f", resp.totalSaved), privacy: .public)")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            dealsError = (error as? APIError)?.errorDescription ?? "Could not load deals."
        }
    }

    // MARK: - Derived

    var sortedRows: [AnalyticsPeriodRow] {
        guard let spending else { return [] }
        let rows: [AnalyticsPeriodRow] = spending.spendingByPeriod.map { (key, agg) in
            AnalyticsPeriodRow(
                id: key,
                net: agg.total,
                purchaseCount: agg.purchaseCount,
                refundCount: agg.refundCount,
                purchaseTotal: agg.purchaseTotal,
                refundTotal: agg.refundTotal,
                receiptCount: agg.count
            )
        }
        switch sort {
        case .periodDesc: return rows.sorted { $0.id > $1.id }
        case .periodAsc:  return rows.sorted { $0.id < $1.id }
        case .totalDesc:  return rows.sorted { $0.net > $1.net }
        case .countDesc:  return rows.sorted { $0.receiptCount > $1.receiptCount }
        }
    }

    var totalRefundCount: Int {
        spending?.spendingByPeriod.values.reduce(0) { $0 + $1.refundCount } ?? 0
    }
    var totalRefundAmount: Double {
        spending?.spendingByPeriod.values.reduce(0) { $0 + $1.refundTotal } ?? 0
    }
    var showsDealsBody: Bool {
        domain == .grocery || domain == .all
    }
}
