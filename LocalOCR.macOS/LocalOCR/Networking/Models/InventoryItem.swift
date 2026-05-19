import Foundation

/// Inventory item — mirrors the flat shape emitted by GET /inventory
/// (src/backend/manage_inventory.py:175). Backend wraps the list in
/// `{"inventory": [...], "count": N, "window_start": "...", "window_label": "..."}`.
/// Decode via `InventoryListResponse`.
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
    let latestPrice: LatestPrice?
    let latestSnapshot: LatestSnapshot?
    let quantity: Double
    let location: String?
    let threshold: Double?
    let manualLow: Bool?
    let isLow: Bool?
    let isRegularUse: Bool?
    let updatedBy: Int?
    let lastUpdated: String?
    let expiresAt: String?
    let expiresAtSystem: String?
    let expiresSource: String?
    let lastPurchasedAt: String?
    let daysLeft: Int?
    /// `_status_fields` spread on backend → `remaining_pct`, `status`, `shelf_days`, `is_estimated`.
    let remainingPct: Double?
    let status: String?
    let shelfDays: Int?
    let isEstimated: Bool?

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

struct LatestPrice: Codable, Equatable, Hashable {
    let price: Double?
    let date: String?
}

/// Backend `_latest_snapshot_for_product` → `{id, image_url, created_at}`.
/// `imageUrl` is server-relative (e.g. `/product-snapshots/<id>/image`); resolve
/// against the configured API base URL at render time.
struct LatestSnapshot: Codable, Equatable, Hashable {
    let id: Int?
    let imageUrl: String?
    let createdAt: String?
}

struct InventoryListResponse: Codable, Equatable {
    let inventory: [InventoryItem]
    let count: Int?
    let windowStart: String?
    let windowLabel: String?
}

// MARK: - Mutation responses

struct InventoryAddResponse: Codable, Equatable {
    let id: Int
    let productId: Int
    let productName: String?
    let productDisplayName: String?
    let quantity: Double
    let location: String?
    let threshold: Double?
    let manualLow: Bool?
}

struct InventoryConsumeResponse: Codable, Equatable {
    let id: Int
    let productName: String?
    let quantity: Double
    let consumed: Double?
    let manualLow: Bool?
    let isLow: Bool?
}

struct InventoryUpdateResponse: Codable, Equatable {
    let id: Int
    let productName: String?
    let quantity: Double
    let location: String?
    let threshold: Double?
    let manualLow: Bool?
}

struct InventoryLowStatusResponse: Codable, Equatable {
    let productId: Int
    let inventoryId: Int?
    let productName: String?
    let manualLow: Bool
    let isLow: Bool
}

struct InventoryConfirmLowResponse: Codable, Equatable {
    let status: String
    let productId: Int
    let productName: String?
}

struct InventoryRegularUseResponse: Codable, Equatable {
    let productId: Int
    let productName: String?
    let isRegularUse: Bool
}

struct InventoryPatchResponse: Codable, Equatable {
    let productId: Int?
    let quantity: Double?
    let location: String?
    let expiresAt: String?
    let expiresAtSystem: String?
    let expiresSource: String?
    let lastPurchasedAt: String?
    let daysLeft: Int?
    let deleted: Bool?
}

struct InventoryDeleteResponse: Codable, Equatable {
    let message: String?
}

// MARK: - Recently used up (for restore section — F-121, F-139, F-140)

struct RecentlyUsedUpItem: Codable, Identifiable, Equatable, Hashable {
    let productId: Int
    let productName: String?
    let category: String?
    let priorQuantity: Double?
    let usedUpAt: String?
    let imageUrl: String?
    let inShoppingList: Bool?

    var id: Int { productId }
    var displayName: String { productName ?? "Item #\(productId)" }
}

struct RecentlyUsedUpResponse: Codable, Equatable {
    let items: [RecentlyUsedUpItem]
}
