import Foundation

/// Inventory item — matches the flat shape emitted by GET /inventory in the
/// LocalOCR Extended backend (src/backend/manage_inventory.py).
///
/// Backend wraps the list in `{"inventory": [...], "count": N, ...}`. Decode
/// via `InventoryListResponse`.
struct InventoryItem: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let productId: Int
    let productName: String?
    let rawName: String?
    let size: String?
    let brand: String?
    let category: String?
    let unit: String?
    let sizeLabel: String?
    let quantity: Double
    let location: String?
    let threshold: Double?
    let manualLow: Bool?
    let isLow: Bool?
    let isRegularUse: Bool?
    let expiresAt: String?
    let lastPurchasedAt: String?
    let daysLeft: Int?

    /// Display name fallback chain — backend prefers `productName`, then `rawName`.
    var displayName: String {
        productName ?? rawName ?? "Item #\(productId)"
    }

    /// True when backend flags as low OR client computes low from threshold.
    var isLowStock: Bool {
        if isLow == true { return true }
        if manualLow == true { return true }
        guard let threshold else { return false }
        return quantity <= threshold
    }
}

struct InventoryListResponse: Codable, Equatable {
    let inventory: [InventoryItem]
    let count: Int?
}
