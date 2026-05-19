import Foundation

struct CashTransaction: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let purchaseId: Int?
    let amount: Double
    let description: String
    let category: String?
    let transactionDate: Date
    let planningMonth: String?
    let paymentMethod: String?       // "cash" | "card" | "bank"
}
