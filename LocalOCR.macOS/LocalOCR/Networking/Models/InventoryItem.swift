import Foundation

struct InventoryItem: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let productId: Int
    let product: Product?
    let quantity: Double
    let location: String?
    let threshold: Double?
    let manualLow: Bool?
    let isActiveWindow: Bool?
    let expiresAt: Date?
    let lastPurchasedAt: Date?

    var isLowStock: Bool {
        if manualLow == true { return true }
        guard let threshold else { return false }
        return quantity <= threshold
    }
}
