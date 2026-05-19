import Foundation

struct ShoppingListItem: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let productId: Int?
    let productName: String
    let quantity: Double
    let status: String                  // "pending" | "purchased" | "skipped"
    let source: String?                 // "manual" | "recommendation" | "low_stock"
    let note: String?
    let manualEstimatedPrice: Double?
    let actualPrice: Double?
    let createdAt: Date?

    var isPending: Bool { status == "pending" }
}
