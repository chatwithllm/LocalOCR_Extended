import Foundation

struct ReceiptItem: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let purchaseId: Int
    let productId: Int?
    let productName: String?
    let quantity: Double
    let unitPrice: Double?
    let totalPrice: Double?
    let sizeLabel: String?
    let spendingDomain: String?
    let budgetCategory: String?
    let kind: String?       // "item" | "tax" | "discount" | "tip"
}
