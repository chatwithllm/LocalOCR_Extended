import Foundation

/// Spending category total — derived from /analytics/spending response.
struct SpendingCategoryTotal: Codable, Identifiable, Equatable, Hashable {
    var id: String { category }
    let category: String
    let total: Double
    let receiptCount: Int
}

struct MerchantFrequency: Codable, Identifiable, Equatable, Hashable {
    var id: String { name }
    let name: String
    let visitCount: Int
    let avgAmount: Double
}

struct MonthlySpend: Codable, Identifiable, Equatable, Hashable {
    var id: String { month }
    let month: String
    let total: Double
}

/// Local DTO assembled from /analytics/spending — the backend response shape
/// is rich; this captures only the fields the UI consumes.
struct SpendingAnalytics: Codable, Equatable {
    let categories: [SpendingCategoryTotal]
    let topMerchants: [MerchantFrequency]
    let monthlyTimeline: [MonthlySpend]
    let periodLabel: String

    init(
        categories: [SpendingCategoryTotal] = [],
        topMerchants: [MerchantFrequency] = [],
        monthlyTimeline: [MonthlySpend] = [],
        periodLabel: String = ""
    ) {
        self.categories = categories
        self.topMerchants = topMerchants
        self.monthlyTimeline = monthlyTimeline
        self.periodLabel = periodLabel
    }
}
