import Foundation
import os.log

/// Aggregates everything the Dashboard renders. Each fetch is independent so
/// partial failures degrade gracefully (one card empty, others still render).
@MainActor
final class DashboardState: ObservableObject {

    static let shared = DashboardState()

    enum ActivityGrain: String, CaseIterable, Identifiable {
        case day, week, month
        var id: String { rawValue }
        var label: String {
            switch self { case .day: return "Day"; case .week: return "Week"; case .month: return "Month" }
        }
    }

    @Published private(set) var leaderboard: Leaderboard?
    @Published private(set) var untagged: AttributionStats?
    @Published private(set) var recommendations: [Recommendation] = []
    @Published private(set) var receiptsActivity: [MonthlySpend] = []
    @Published private(set) var productsCount: Int = 0
    @Published var activityGrain: ActivityGrain = .day
    @Published private(set) var leaderboardCollapsed: Bool = false
    @Published private(set) var spendingCardCollapsed: Bool = false
    @Published private(set) var spendingShowAll: Bool = false
    @Published private(set) var isSpendingLoading: Bool = false
    @Published private(set) var spendingError: String?
    @Published private(set) var isActivityLoading: Bool = false
    @Published private(set) var activityError: String?
    @Published var lastError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "dashboard")

    // UserDefaults persistence keys (mirrors web localStorage keys).
    private let kLeaderboardCollapsed = "LocalOCR.dashboard_leaderboard_collapsed"
    private let kSpendingCardCollapsed = "LocalOCR.dashboard_spending_card_collapsed"
    private let kSpendingShowAll = "LocalOCR.dashboard_spending_show_all"
    private let kActivityGrain = "LocalOCR.dashboard_activity_grain"

    init(api: APIClient = .shared) {
        self.api = api
        leaderboardCollapsed = UserDefaults.standard.bool(forKey: kLeaderboardCollapsed)
        spendingCardCollapsed = UserDefaults.standard.bool(forKey: kSpendingCardCollapsed)
        spendingShowAll = UserDefaults.standard.bool(forKey: kSpendingShowAll)
        if let grainStr = UserDefaults.standard.string(forKey: kActivityGrain),
           let grain = ActivityGrain(rawValue: grainStr) {
            activityGrain = grain
        }
    }

    // MARK: - Toggle persistence

    func toggleLeaderboardCollapsed() {
        leaderboardCollapsed.toggle()
        UserDefaults.standard.set(leaderboardCollapsed, forKey: kLeaderboardCollapsed)
    }

    func toggleSpendingCardCollapsed() {
        spendingCardCollapsed.toggle()
        UserDefaults.standard.set(spendingCardCollapsed, forKey: kSpendingCardCollapsed)
    }

    func toggleSpendingShowAll() {
        spendingShowAll.toggle()
        UserDefaults.standard.set(spendingShowAll, forKey: kSpendingShowAll)
    }

    func setActivityGrain(_ grain: ActivityGrain) {
        activityGrain = grain
        UserDefaults.standard.set(grain.rawValue, forKey: kActivityGrain)
        Task { await loadReceiptsActivity() }
    }

    // MARK: - Loads

    func loadAll() async {
        async let _ = loadLeaderboard()
        async let _ = loadUntagged()
        async let _ = loadRecommendations()
        async let _ = loadReceiptsActivity()
        async let _ = loadProductsCount()
        async let _ = loadSpendingByCategory()
    }

    func loadLeaderboard() async {
        do {
            let me = try await api.request(.get, path: AuthEndpoint.me.path, as: AuthMeWithLeaderboard.self)
            leaderboard = me.leaderboard
        } catch {
            logger.warning("leaderboard: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadUntagged() async {
        do {
            untagged = try await api.request(
                .get,
                path: DashboardEndpoint.attributionStats.path,
                as: AttributionStats.self
            )
        } catch {
            logger.warning("attribution stats: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadRecommendations() async {
        do {
            let resp = try await api.request(
                .get,
                path: DashboardEndpoint.recommendations.path,
                as: RecommendationsResponse.self
            )
            recommendations = resp.recommendations
        } catch {
            logger.warning("recommendations: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Pulls /analytics/spending with the current ActivityGrain to fuel the
    /// "Receipts Processed" sparkline.
    func loadReceiptsActivity() async {
        isActivityLoading = true
        activityError = nil
        defer { isActivityLoading = false }
        do {
            let serverPeriod: String
            switch activityGrain {
            case .day:    serverPeriod = "daily"
            case .week:   serverPeriod = "weekly"
            case .month:  serverPeriod = "monthly"
            }
            let monthsBack: String = (activityGrain == .month) ? "6" : "1"
            let data = try await api.rawRequest(
                .get,
                path: "/analytics/spending",
                query: [
                    URLQueryItem(name: "period", value: serverPeriod),
                    URLQueryItem(name: "months", value: monthsBack)
                ]
            )
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let dict = json["spending_by_period"] as? [String: [String: Any]] else {
                receiptsActivity = []
                return
            }
            receiptsActivity = dict
                .map { key, payload -> MonthlySpend in
                    let total = (payload["total"] as? Double) ?? Double(payload["total"] as? Int ?? 0)
                    return MonthlySpend(month: key, total: total)
                }
                .sorted { $0.month < $1.month }
        } catch is CancellationError {
            // Race condition during view refresh — silently ignore.
        } catch {
            // Don't surface URLSession cancellation as an error either.
            let nsError = error as NSError
            if nsError.domain == NSURLErrorDomain, nsError.code == NSURLErrorCancelled {
                return
            }
            activityError = (error as? APIError)?.errorDescription ?? error.localizedDescription
            logger.warning("activity: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Loads spending-by-category data — proper /analytics/spending-by-category
    /// endpoint (not /analytics/spending — that's a different rollup).
    /// Decodes into FinanceState.spending so the Dashboard card renders.
    func loadSpendingByCategory(month: String? = nil) async {
        isSpendingLoading = true
        spendingError = nil
        defer { isSpendingLoading = false }

        let ym: String
        if let month {
            ym = month
        } else {
            let fmt = DateFormatter()
            fmt.dateFormat = "yyyy-MM"
            fmt.timeZone = TimeZone(identifier: "UTC")
            ym = fmt.string(from: Date())
        }

        do {
            let data = try await api.rawRequest(
                .get,
                path: "/analytics/spending-by-category",
                query: [
                    URLQueryItem(name: "month", value: ym),
                    URLQueryItem(name: "limit", value: "50")
                ]
            )
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                return
            }
            let rawCategories = (json["categories"] as? [[String: Any]]) ?? []
            let categories: [SpendingCategoryTotal] = rawCategories.compactMap { row in
                guard let cat = row["category"] as? String else { return nil }
                let amount = (row["amount"] as? Double) ?? Double(row["amount"] as? Int ?? 0)
                // backend doesn't emit receipt_count for this rollup; pass 0
                return SpendingCategoryTotal(category: cat.capitalized, total: amount, receiptCount: 0)
            }
            let total = (json["total"] as? Double) ?? categories.reduce(0) { $0 + $1.total }
            await MainActor.run {
                FinanceState.shared.injectSpending(
                    SpendingAnalytics(
                        categories: categories,
                        topMerchants: [],
                        monthlyTimeline: [],
                        periodLabel: (json["month"] as? String) ?? ym
                    ),
                    grandTotal: total
                )
            }
        } catch is CancellationError {
            // ignore
        } catch {
            let nsError = error as NSError
            if nsError.domain == NSURLErrorDomain, nsError.code == NSURLErrorCancelled {
                return
            }
            spendingError = (error as? APIError)?.errorDescription ?? error.localizedDescription
            logger.warning("spendingByCategory: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// Loads product catalog count for the LOW / INV / PROD strip.
    /// Endpoint returns `{products: [...], total: N, page, per_page}` — use `total`.
    func loadProductsCount() async {
        do {
            let data = try await api.rawRequest(.get, path: "/products")
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                if let total = json["total"] as? Int {
                    productsCount = total
                } else if let arr = json["products"] as? [Any] {
                    productsCount = arr.count
                } else if let count = json["count"] as? Int {
                    productsCount = count
                }
            } else if let arr = try? JSONSerialization.jsonObject(with: data) as? [Any] {
                productsCount = arr.count
            }
        } catch is CancellationError {
        } catch {
            logger.warning("productsCount: \(error.localizedDescription, privacy: .public)")
        }
    }
}
