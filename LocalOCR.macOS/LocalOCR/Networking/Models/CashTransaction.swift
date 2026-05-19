import Foundation

/// Cash transaction — matches the list shape from
/// src/backend/manage_cash_transactions.py.
///
/// Backend wraps in `{"transactions": [...]}` (envelope).
struct CashTransaction: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let purchaseId: Int?
    let serviceLineId: Int?
    let providerId: Int?
    let planningMonth: String?
    let transactionDate: String?
    let amount: Double
    let paymentMethod: String?
    let status: String?
    let notes: String?

    var description: String { notes ?? "Cash payment" }
    var category: String? { nil }   // cash transactions are bill-provider-scoped server-side

    var transactionDateValue: Date {
        guard let s = transactionDate else { return Date() }
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        fmt.timeZone = TimeZone(identifier: "UTC")
        return fmt.date(from: s) ?? Date()
    }
}

struct CashTransactionsResponse: Codable, Equatable {
    let transactions: [CashTransaction]
}
