import Foundation

/// Shopping list item — mirrors `_serialize_item` in
/// src/backend/manage_shopping_list.py.
///
/// Backend status enum: `open` | `purchased` | `skipped` | `out_of_stock`.
/// Backend list endpoint wraps in `_build_shopping_list_payload` (envelope keys
/// in `ShoppingListResponse`).
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
    let status: String
    let source: String?
    let note: String?
    let preferredStore: String?
    let manualEstimatedPrice: Double?
    let actualPrice: Double?
    let effectiveStore: String?
    let latestPrice: LatestPrice?
    let latestSnapshot: ShoppingLatestSnapshot?
    let createdAt: String?
    let updatedAt: String?

    var productName: String { productDisplayName ?? name }
    var isPending: Bool { status == "open" }
    var isPurchased: Bool { status == "purchased" }
    var isSkipped: Bool { status == "skipped" }
    var isOutOfStock: Bool { status == "out_of_stock" }
    var displayUnit: String { unit ?? "each" }

    /// Per-line estimate using latest_price first, then manual_estimated_price.
    var estimateLineTotal: Double? {
        let unitPrice = latestPrice?.price ?? manualEstimatedPrice
        guard let unitPrice else { return nil }
        return unitPrice * quantity
    }

    /// Group key — matches `renderShoppingListTable()`: preferred_store first,
    /// then effective_store (price-derived), then "Unassigned".
    var groupKey: String {
        if let preferredStore, !preferredStore.isEmpty { return preferredStore }
        if let effectiveStore, !effectiveStore.isEmpty { return effectiveStore }
        return "Unassigned"
    }
}

/// Shopping-specific snapshot envelope — differs from inventory's `LatestSnapshot`
/// (adds status, source_context, notes, captured_at, count).
struct ShoppingLatestSnapshot: Codable, Equatable, Hashable {
    let id: Int?
    let imageUrl: String?
    let status: String?
    let sourceContext: String?
    let notes: String?
    let capturedAt: String?
    let count: Int?
}

/// Session row — `_serialize_session`.
/// status: "active" | "ready_to_bill" | "closed".
struct ShoppingSession: Codable, Equatable, Hashable, Identifiable {
    let id: Int
    let name: String?
    let status: String
    let storeHint: String?
    let estimatedTotalSnapshot: Double?
    let actualTotalSnapshot: Double?
    let createdAt: String?
    let closedAt: String?

    var isActive: Bool { status == "active" }
    var isReadyToBill: Bool { status == "ready_to_bill" }
    var isClosed: Bool { status == "closed" }
}

struct AvailableStoreBuckets: Codable, Equatable, Hashable {
    let frequent: [String]?
    let lowFreq: [String]?
}

struct SuggestedStore: Codable, Equatable, Hashable {
    let store: String
    let estimatedTotal: Double?
    let itemCount: Int?
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
    let actualsEnteredCount: Int?
    let suggestedStores: [SuggestedStore]?
    let availableStores: [String]?
    let availableStoreBuckets: AvailableStoreBuckets?
    let helperMode: Bool?
    let session: ShoppingSession?
}

struct ShoppingItemWrapper: Codable, Equatable {
    let item: ShoppingListItem
    let merged: Bool?
}

struct ShoppingSessionWrapper: Codable, Equatable {
    let session: ShoppingSession?
    let unchanged: Bool?
}

struct ShoppingSessionFinalizeResponse: Codable, Equatable {
    let closedSession: ShoppingSession?
    let activeSession: ShoppingSession?
    let carriedOverCount: Int?
}

/// Past trip row — `_serialize_session` + `item_count`, `purchased_count`, `variance`.
struct ShoppingPastTrip: Codable, Equatable, Hashable, Identifiable {
    let id: Int
    let name: String?
    let status: String
    let storeHint: String?
    let estimatedTotalSnapshot: Double?
    let actualTotalSnapshot: Double?
    let createdAt: String?
    let closedAt: String?
    let itemCount: Int?
    let purchasedCount: Int?
    let variance: Double?
}

struct ShoppingPastTripsResponse: Codable, Equatable {
    let sessions: [ShoppingPastTrip]
    let count: Int?
}

struct ShoppingSessionDetailResponse: Codable, Equatable {
    let session: ShoppingSession?
    let items: [ShoppingListItem]
    let count: Int?
}

struct ShoppingShareLinkResponse: Codable, Equatable {
    let url: String?
    let qrImageUrl: String?
    let expiresAt: String?
}

/// Sort modes mirror `renderShoppingListTable()` sort branches.
enum ShoppingSort: String, CaseIterable {
    case nameAsc      = "name_asc"
    case nameDesc     = "name_desc"
    case priceDesc    = "price_desc"
    case priceAsc     = "price_asc"
}

/// View filter — backend uses query `?status=`, but the web UI filters client-side
/// across the cached `items` array.
enum ShoppingListFilter: String {
    case open      = "open"
    case purchased = "purchased"
    case all       = "all"
}
