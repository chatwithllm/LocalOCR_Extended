import Foundation

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
    let month: String   // YYYY-MM
    let total: Double
}

struct SpendingAnalytics: Codable, Equatable {
    let categories: [SpendingCategoryTotal]
    let topMerchants: [MerchantFrequency]
    let monthlyTimeline: [MonthlySpend]
    let periodLabel: String
}
