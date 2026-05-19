import Foundation
import os.log

/// Aggregates everything the Dashboard renders. Each fetch is independent so
/// partial failures degrade gracefully (one card empty, others still render).
@MainActor
final class DashboardState: ObservableObject {

    static let shared = DashboardState()

    @Published private(set) var leaderboard: Leaderboard?
    @Published private(set) var untagged: AttributionStats?
    @Published private(set) var recommendations: [Recommendation] = []
    @Published private(set) var receiptsProcessedDaily: [MonthlySpend] = []   // reused as daily-totals shape
    @Published private(set) var isLoading = false
    @Published var lastError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "dashboard")

    init(api: APIClient = .shared) {
        self.api = api
    }

    func loadAll() async {
        isLoading = true
        defer { isLoading = false }
        async let _ = loadLeaderboard()
        async let _ = loadUntagged()
        async let _ = loadRecommendations()
        async let _ = loadReceiptsProcessed()
    }

    func loadLeaderboard() async {
        do {
            // /auth/me carries the leaderboard envelope.
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

    /// Pulls /analytics/spending?period=daily&months=1 to fuel the
    /// "Receipts Processed" line chart over the last ~30 days.
    func loadReceiptsProcessed() async {
        do {
            let data = try await api.rawRequest(
                .get,
                path: "/analytics/spending",
                query: [
                    URLQueryItem(name: "period", value: "daily"),
                    URLQueryItem(name: "months", value: "1")
                ]
            )
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let dict = json["spending_by_period"] as? [String: [String: Any]] else { return }
            receiptsProcessedDaily = dict
                .map { key, payload -> MonthlySpend in
                    let total = (payload["total"] as? Double) ?? Double(payload["total"] as? Int ?? 0)
                    return MonthlySpend(month: key, total: total)
                }
                .sorted { $0.month < $1.month }
        } catch {
            logger.warning("receiptsProcessed: \(error.localizedDescription, privacy: .public)")
        }
    }
}
