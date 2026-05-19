import Foundation

struct FixedBill: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let label: String
    let expectedMonthlyAmount: Double
    let isActive: Bool
    let paymentStatus: String          // "paid" | "unpaid" | "overdue"
    let billingCycle: String           // "monthly" | "quarterly" | "yearly"
    let nextDueDate: Date?
    let lastPaidAt: Date?
    let providerName: String?
}
