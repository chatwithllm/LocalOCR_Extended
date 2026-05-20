import Foundation

// MARK: - /analytics/spending (raw shape)

struct AnalyticsPeriodAggregate: Codable, Equatable, Hashable {
    let total: Double
    let count: Int
    let purchaseCount: Int
    let refundCount: Int
    let purchaseTotal: Double
    let refundTotal: Double
}

struct AnalyticsCategoryAggregate: Codable, Equatable, Hashable {
    let total: Double
    let count: Int
}

struct AnalyticsSpendingOverviewResponse: Codable, Equatable {
    let period: String
    let domain: String
    let monthsBack: Int
    let grandTotal: Double
    let spendingByPeriod: [String: AnalyticsPeriodAggregate]
    let categoryBreakdown: [String: AnalyticsCategoryAggregate]
}

/// Convenience row used by the UI table.
struct AnalyticsPeriodRow: Identifiable, Equatable, Hashable {
    let id: String                 // period key (e.g. "2026-05", "2026-W21")
    let net: Double
    let purchaseCount: Int
    let refundCount: Int
    let purchaseTotal: Double
    let refundTotal: Double
    let receiptCount: Int
}

// MARK: - /analytics/deals-captured

struct AnalyticsDealItem: Codable, Identifiable, Equatable, Hashable {
    let productName: String?
    let paid: Double
    let avgPrice: Double
    let quantity: Double?
    let saved: Double
    let date: String?

    var id: String {
        "\(productName ?? "—")|\(date ?? "")|\(paid)|\(saved)"
    }
}

struct AnalyticsDealsResponse: Codable, Equatable {
    let monthsBack: Int
    let totalSaved: Double
    let dealCount: Int
    let deals: [AnalyticsDealItem]
}
