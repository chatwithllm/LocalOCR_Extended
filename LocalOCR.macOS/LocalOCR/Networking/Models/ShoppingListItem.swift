import Foundation

/// Shopping list item — matches `_serialize_item` in
/// src/backend/manage_shopping_list.py.
///
/// Backend status uses "open" / "purchased" — NOT "pending".
/// Backend wraps in `{"items": [...], "count": N, "open_count": N, "purchased_count": N, ...}`.
struct ShoppingListItem: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let productId: Int?
    let shoppingSessionId: Int?
    let name: String
    let productDisplayName: String?
    let productFullName: String?
    let category: String?
    let quantity: Double
    let unit: String?
    let sizeLabel: String?
    let status: String                  // "open" | "purchased"
    let source: String?                 // "manual" | "recommendation" | "low_stock" | nil
    let note: String?
    let preferredStore: String?
    let manualEstimatedPrice: Double?
    let actualPrice: Double?
    let createdAt: String?
    let updatedAt: String?

    /// Display name fallback chain.
    var productName: String {
        productDisplayName ?? name
    }

    /// Server uses "open" for pending items.
    var isPending: Bool { status == "open" }
}

struct ShoppingListResponse: Codable, Equatable {
    let items: [ShoppingListItem]
    let count: Int?
    let openCount: Int?
    let purchasedCount: Int?
    let estimatedTotalCost: Double?
    let boughtEstimatedTotal: Double?
    let actualTotal: Double?
    let variance: Double?
}
