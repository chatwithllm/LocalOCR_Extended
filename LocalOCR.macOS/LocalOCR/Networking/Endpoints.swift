import Foundation

/// Typed endpoint cases — paths verified against the LocalOCR Extended Flask
/// backend in src/backend/. Each enum exposes `path` + `method` + `isMutating`.

// MARK: - Auth

enum AuthEndpoint {
    case me
    case login(email: String, password: String)
    case logout
    case devicePairingStart(deviceName: String, scope: String)
    case devicePairingStatus(token: String)
    case householdMembers
    case householdUsers

    var path: String {
        switch self {
        case .me:                              return "/auth/me"
        case .login:                           return "/auth/login"
        case .logout:                          return "/auth/logout"
        case .devicePairingStart:              return "/auth/device-pairing/start"
        case .devicePairingStatus(let token):  return "/auth/device-pairing/status/\(token)"
        case .householdMembers:                return "/auth/household-members"
        case .householdUsers:                  return "/auth/users"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .me, .devicePairingStatus, .householdMembers, .householdUsers: return .get
        case .login, .logout, .devicePairingStart:                          return .post
        }
    }

    var isMutating: Bool { method != .get }
}

struct LoginRequestBody: Encodable { let email: String; let password: String }
struct DevicePairingStartBody: Encodable { let deviceName: String; let scope: String }
struct DevicePairingStartResponse: Codable, Equatable { let pairingToken: String; let status: String }
struct DevicePairingStatusResponse: Codable, Equatable { let status: String; let token: String? }

// MARK: - Inventory

enum InventoryEndpoint {
    case list(location: String?, lowStockOnly: Bool)
    case addItem
    case consume(itemId: Int)
    case updateItem(itemId: Int)
    case delete(itemId: Int)
    case patchProduct(productId: Int)
    case deleteExpiryOverride(productId: Int)
    case markLow(productId: Int)
    case regularUse(productId: Int)
    case confirmLow(productId: Int)
    case recentlyUsedUp(days: Int)
    case restore(productId: Int)

    var path: String {
        switch self {
        case .list:                                return "/inventory"
        case .addItem:                             return "/inventory/add-item"
        case .consume(let id):                     return "/inventory/\(id)/consume"
        case .updateItem(let id):                  return "/inventory/\(id)/update"
        case .delete(let id):                      return "/inventory/\(id)"
        case .patchProduct(let pid):               return "/inventory/products/\(pid)"
        case .deleteExpiryOverride(let pid):       return "/inventory/products/\(pid)/expiry-override"
        case .markLow(let pid):                    return "/inventory/products/\(pid)/low-status"
        case .regularUse(let pid):                 return "/inventory/products/\(pid)/regular-use"
        case .confirmLow(let pid):                 return "/inventory/products/\(pid)/confirm-low"
        case .recentlyUsedUp:                      return "/inventory/recently-used-up"
        case .restore(let pid):                    return "/inventory/products/\(pid)/restore"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .list, .recentlyUsedUp:                                   return .get
        case .addItem, .confirmLow, .restore:                          return .post
        case .consume, .updateItem, .markLow, .regularUse:             return .put
        case .patchProduct:                                            return .patch
        case .delete, .deleteExpiryOverride:                           return .delete
        }
    }

    var query: [URLQueryItem] {
        switch self {
        case .list(let location, let lowStockOnly):
            var items: [URLQueryItem] = []
            if let location { items.append(.init(name: "location", value: location)) }
            if lowStockOnly { items.append(.init(name: "low_stock", value: "true")) }
            return items
        case .recentlyUsedUp(let days):
            return [.init(name: "days", value: String(days))]
        default:
            return []
        }
    }

    var isMutating: Bool { method != .get }
}

struct InventoryAddBody: Encodable {
    let productName: String
    let quantity: Double
    let location: String
    let threshold: Double?
    let category: String?
    let size: String?
}

struct ConsumeBody: Encodable { let amount: Double }
struct MarkLowBody: Encodable { let manualLow: Bool }
struct RegularUseBody: Encodable { let isRegularUse: Bool }
struct InventoryRestoreBody: Encodable { let quantity: Double? }

/// PUT /inventory/<id>/update — backend reads any subset of these keys.
struct InventoryUpdateBody: Encodable {
    let quantity: Double?
    let location: String?
    let threshold: Double?
    let consumedPctOverride: Double?
}

/// PATCH /inventory/products/<id> — product-level edits (rename, unit, size, expiry, defer, used-up).
/// Pass `quantity: 0` to mark used-up; backend deletes the row and returns `{deleted: true, ...}`.
struct InventoryPatchBody: Encodable {
    let displayName: String?
    let unit: String?
    let sizeLabel: String?
    let quantity: Double?
    let location: String?
    let threshold: Double?
    let expiresAt: String?
    let deferDays: Int?
}

// MARK: - Receipts

enum ReceiptEndpoint {
    case list
    case detail(id: Int)
    case approve(id: Int)
    case reprocess(id: Int)

    var path: String {
        switch self {
        case .list:                  return "/receipts"
        case .detail(let id):        return "/receipts/\(id)"
        case .approve(let id):       return "/receipts/\(id)/approve"
        case .reprocess(let id):     return "/receipts/\(id)/reprocess"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .list, .detail:         return .get
        case .approve, .reprocess:   return .post
        }
    }
    var isMutating: Bool { method != .get }
}

struct ReprocessBody: Encodable { let modelId: Int? }

// MARK: - Shopping (backend prefix: /shopping-list)
//
// Routes mirror manage_shopping_list.py — verified by Rule 1 pre-flight grep
// (see SHOPPING-PARITY work in this commit). Bodies mirror request keys read by
// `add_shopping_item` and `update_shopping_item`.

enum ShoppingEndpoint {
    case list(statusFilter: String?)
    case addItem
    case updateItem(id: Int)
    case deleteItem(id: Int)
    case sessionReadyToBill
    case sessionFinalize
    case sessionReopen
    case sessionsList(statusFilter: String?)
    case sessionDetail(id: Int)
    case confirmRecommendation(productId: Int)
    case shareLink
    case identifyPhoto

    var path: String {
        switch self {
        case .list:                              return "/shopping-list"
        case .addItem:                           return "/shopping-list/items"
        case .updateItem(let id):                return "/shopping-list/items/\(id)"
        case .deleteItem(let id):                return "/shopping-list/items/\(id)"
        case .sessionReadyToBill:                return "/shopping-list/session/ready-to-bill"
        case .sessionFinalize:                   return "/shopping-list/session/finalize"
        case .sessionReopen:                     return "/shopping-list/session/reopen"
        case .sessionsList:                      return "/shopping-list/sessions"
        case .sessionDetail(let id):             return "/shopping-list/sessions/\(id)"
        case .confirmRecommendation(let pid):    return "/shopping-list/products/\(pid)/confirm-recommendation"
        case .shareLink:                         return "/shopping-list/share-link"
        case .identifyPhoto:                     return "/shopping-list/identify-product-photo"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .list, .sessionsList, .sessionDetail:                                     return .get
        case .addItem, .sessionReadyToBill, .sessionFinalize, .sessionReopen,
             .confirmRecommendation, .shareLink, .identifyPhoto:                       return .post
        case .updateItem:                                                              return .put
        case .deleteItem:                                                              return .delete
        }
    }

    var query: [URLQueryItem] {
        switch self {
        case .list(let status):
            guard let status, !status.isEmpty else { return [] }
            return [.init(name: "status", value: status)]
        case .sessionsList(let status):
            guard let status, !status.isEmpty else { return [] }
            return [.init(name: "status", value: status)]
        default:
            return []
        }
    }

    var isMutating: Bool { method != .get }
}

/// POST /shopping-list/items — keys read by `add_shopping_item` in
/// src/backend/manage_shopping_list.py.
struct ShoppingAddBody: Encodable {
    let name: String
    let quantity: Double
    let source: String?
    let productId: Int?
    let category: String?
    let unit: String?
    let sizeLabel: String?
    let note: String?
    let preferredStore: String?
    let manualEstimatedPrice: Double?
    let snapshotId: Int?
}

/// PUT /shopping-list/items/<id> — keys read by `update_shopping_item`.
/// Server only writes a key when it is present in the JSON body, so all fields
/// are optional. Pass `nil` to skip; pass a value to write.
struct ShoppingUpdateBody: Encodable {
    let name: String?
    let category: String?
    let quantity: Double?
    let status: String?
    let note: String?
    let preferredStore: String?
    let manualEstimatedPrice: Double?
    let actualPrice: Double?
    let unit: String?
    let sizeLabel: String?
    let persistLatestPrice: Bool?
    let priceStore: String?
}

/// POST /shopping-list/session/reopen — optional `session_id` reopens a specific
/// closed trip; omit to reopen the latest closed session.
struct ShoppingReopenBody: Encodable {
    let sessionId: Int?
}

// MARK: - Floor obligations (backend prefix: /floor-obligations, trailing slash on list)

enum FixedBillsEndpoint {
    case list
    case rename(id: Int, label: String)

    var path: String {
        switch self {
        case .list:                  return "/floor-obligations/"
        case .rename(let id, _):     return "/floor-obligations/\(id)"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .list:                  return .get
        case .rename:                return .patch
        }
    }
    var isMutating: Bool { method != .get }
}

struct BillRenameBody: Encodable { let label: String }

// MARK: - Plaid

enum PlaidEndpoint {
    case accounts
    case stagedTransactions
    case refreshBalances
    case confirmStaged(id: Int)
    case dismissStaged(id: Int)

    var path: String {
        switch self {
        case .accounts:                   return "/plaid/accounts"
        case .stagedTransactions:         return "/plaid/staged-transactions"
        case .refreshBalances:            return "/plaid/accounts/refresh-balances"
        case .confirmStaged(let id):      return "/plaid/staged-transactions/\(id)/confirm"
        case .dismissStaged(let id):      return "/plaid/staged-transactions/\(id)/dismiss"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .accounts, .stagedTransactions:                  return .get
        case .refreshBalances, .confirmStaged, .dismissStaged: return .post
        }
    }
    var isMutating: Bool { method != .get }
}

// MARK: - Cash transactions

enum CashEndpoint {
    case list
    case delete(id: Int)

    var path: String {
        switch self {
        case .list:                  return "/cash-transactions"
        case .delete(let id):        return "/cash-transactions/\(id)"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .list:    return .get
        case .delete:  return .delete
        }
    }
    var isMutating: Bool { method != .get }
}

// MARK: - Analytics

enum AnalyticsEndpoint {
    case spending(month: String?)

    var path: String {
        switch self {
        case .spending:                    return "/analytics/spending"
        }
    }
    var method: HTTPMethod { .get }
    var isMutating: Bool { false }
}

// MARK: - Dashboard helpers

enum DashboardEndpoint {
    case attributionStats
    case recommendations

    var path: String {
        switch self {
        case .attributionStats:   return "/receipts/attribution-stats"
        case .recommendations:    return "/recommendations"
        }
    }
    var method: HTTPMethod { .get }
    var isMutating: Bool { false }
}

// MARK: - Shared dining (backend prefix: /shared-dining)
//
// Verified by Rule 1 grep against `shared_dining_endpoints.py`:
//   GET  /shared-dining/balances
//   POST /shared-dining/contacts/<id>/settle-all
//   GET  /shared-dining/contacts
//   POST /shared-dining/contacts
//   POST /shared-dining/contacts/merge

enum SharedDiningEndpoint {
    case balances
    case settleAll(contactId: Int)
    case listContacts
    case createContact

    var path: String {
        switch self {
        case .balances:                    return "/shared-dining/balances"
        case .settleAll(let id):           return "/shared-dining/contacts/\(id)/settle-all"
        case .listContacts, .createContact: return "/shared-dining/contacts"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .balances, .listContacts:    return .get
        case .settleAll, .createContact:  return .post
        }
    }
    var isMutating: Bool { method != .get }
}

/// `[BalanceRow]` direct array — no envelope (`get_all_balances` returns a list).
struct BalanceRow: Codable, Equatable, Hashable, Identifiable {
    let contactId: Int
    let name: String
    let netAmount: Double

    var id: Int { contactId }
    var owesYou: Bool { netAmount > 0 }
}

struct SettleAllResponse: Codable, Equatable {
    let settled: Int?
}

struct DiningContactRow: Codable, Equatable, Hashable, Identifiable {
    let id: Int
    let name: String
    let phone: String?
    let email: String?
}

struct CreateContactBody: Encodable {
    let name: String
    let phone: String?
    let email: String?
}

// MARK: - Restaurant analytics + Budget (backend prefixes /analytics, /budget)
//
// Verified by Rule 1 grep:
//   GET  /analytics/restaurant-summary
//   GET  /analytics/spending
//   GET  /budget/status
//   POST /budget/set-monthly

enum RestaurantEndpoint {
    case summary(months: Int)
    case spending(months: Int)

    var path: String {
        switch self {
        case .summary:  return "/analytics/restaurant-summary"
        case .spending: return "/analytics/spending"
        }
    }
    var method: HTTPMethod { .get }
    var query: [URLQueryItem] {
        switch self {
        case .summary(let m):
            return [.init(name: "months", value: String(m))]
        case .spending(let m):
            return [
                .init(name: "period", value: "monthly"),
                .init(name: "domain", value: "restaurant"),
                .init(name: "months", value: String(m)),
            ]
        }
    }
    var isMutating: Bool { false }
}

enum BudgetEndpoint {
    case status(month: String, domain: String)
    case setMonthly

    var path: String {
        switch self {
        case .status:     return "/budget/status"
        case .setMonthly: return "/budget/set-monthly"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .status:     return .get
        case .setMonthly: return .post
        }
    }
    var query: [URLQueryItem] {
        switch self {
        case .status(let month, let domain):
            return [
                .init(name: "month",  value: month),
                .init(name: "domain", value: domain),
            ]
        case .setMonthly: return []
        }
    }
    var isMutating: Bool { method != .get }
}

struct BudgetSetMonthlyBody: Encodable {
    let month: String
    let domain: String
    let budgetAmount: Double
}

struct RestaurantSummaryResponse: Codable, Equatable {
    let monthsBack: Int?
    let visitCount: Int?
    let receiptCount: Int?
    let refundCount: Int?
    let totalSpend: Double?
    let purchaseTotal: Double?
    let refundTotal: Double?
    let averageTicket: Double?
    let topRestaurants: [TopRestaurant]?
    let topItems: [TopRestaurantItem]?
    let recentReceipts: [RestaurantReceiptRow]?
}

struct TopRestaurant: Codable, Equatable, Hashable, Identifiable {
    let store: String
    let visits: Int?
    let refunds: Int?
    let total: Double?
    let purchaseTotal: Double?
    let refundTotal: Double?
    let averageTicket: Double?
    let latestDate: String?
    var id: String { store }
}

struct TopRestaurantItem: Codable, Equatable, Hashable, Identifiable {
    let name: String
    let quantity: Double?
    let total: Double?
    let averagePrice: Double?
    let category: String?
    var id: String { name }
}

struct RestaurantReceiptRow: Codable, Equatable, Hashable, Identifiable {
    let purchaseId: Int
    let store: String?
    let date: String?
    let total: Double?
    let transactionType: String?
    var id: Int { purchaseId }
}

struct AnalyticsSpendingResponse: Codable, Equatable {
    /// Backend `spending_by_period` is `{key: {total, count, purchase_count, ...}}`.
    /// Mac only uses `grand_total` for now — leave the period map opaque.
    let grandTotal: Double?
}

struct BudgetStatusResponse: Codable, Equatable {
    let month: String?
    let domain: String?
    let budgetCategory: String?
    let budgetAmount: Double?
    let spent: Double?
    let remaining: Double?
    let percentage: Double?
    let alertTriggered: Bool?
    let purchaseCount: Int?
    let refundCount: Int?
    let receiptCount: Int?
}

// MARK: - Medications (backend prefix: /medications)
//
// Verified by Rule 1 grep against src/backend/manage_medications.py.
// Household roster comes from AuthEndpoint.householdMembers (/auth/household-members)
// — the web's POST/DELETE /household-members endpoints don't exist server-side.

enum MedicationEndpoint {
    case list(status: String?, userId: Int?, memberId: String?)
    case create
    case detail(id: Int)
    case update(id: Int)
    case delete(id: Int)
    case barcodeLookup
    case uploadPhoto(id: Int)

    var path: String {
        switch self {
        case .list:                  return "/medications"
        case .create:                return "/medications"
        case .detail(let id):        return "/medications/\(id)"
        case .update(let id):        return "/medications/\(id)"
        case .delete(let id):        return "/medications/\(id)"
        case .barcodeLookup:         return "/medications/barcode-lookup"
        case .uploadPhoto(let id):   return "/medications/\(id)/photo"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .list, .detail:                       return .get
        case .create, .barcodeLookup, .uploadPhoto: return .post
        case .update:                              return .put
        case .delete:                              return .delete
        }
    }

    var query: [URLQueryItem] {
        switch self {
        case .list(let status, let userId, let memberId):
            var items: [URLQueryItem] = []
            if let status, !status.isEmpty { items.append(.init(name: "status", value: status)) }
            if let userId { items.append(.init(name: "user_id", value: String(userId))) }
            if let memberId, !memberId.isEmpty { items.append(.init(name: "member_id", value: memberId)) }
            return items
        default:
            return []
        }
    }

    var isMutating: Bool { method != .get }
}

/// POST /medications + PUT /medications/<id> body — every field optional.
/// Backend `_MUTABLE_FIELDS` accepts every key here when present.
struct MedicationBody: Encodable {
    let name: String?
    let brand: String?
    let strength: String?
    let activeIngredient: String?
    let dosageForm: String?
    let ageGroup: String?
    let belongsTo: String?
    let memberId: Int?
    let userId: Int?
    let quantity: Double?
    let unit: String?
    let lowThreshold: Double?
    let expiryDate: String?
    let manufactureDate: String?
    let barcode: String?
    let notes: String?
    let status: String?
}

struct BarcodeLookupBody: Encodable {
    let barcode: String?
    let name: String?
}

struct BarcodeLookupResponse: Codable, Equatable {
    let found: Bool
    let fields: MedicationLookupFields?
}

/// Subset of medication fields returned by /medications/barcode-lookup.
struct MedicationLookupFields: Codable, Equatable {
    let name: String?
    let brand: String?
    let strength: String?
    let activeIngredient: String?
    let dosageForm: String?
    let ageGroup: String?
    let barcode: String?
}

// MARK: - Products (backend prefix: /products)
//
// Verified by Rule 1 grep against src/backend/manage_product_catalog.py.

enum ProductsEndpoint {
    case list(page: Int?, perPage: Int?, category: String?)
    case search(query: String)
    case create
    case update(id: Int)
    case delete(id: Int)
    case detail(id: Int)
    case priceHistory(id: Int)
    case reviewQueue(status: String)
    case bulkEnhance
    case enhance(id: Int)
    case reviewStatus(id: Int)
    case autoDedupTokens

    var path: String {
        switch self {
        case .list:                     return "/products"
        case .search:                   return "/products/search"
        case .create:                   return "/products/create"
        case .update(let id):           return "/products/\(id)/update"
        case .delete(let id):           return "/products/\(id)"
        case .detail(let id):           return "/products/\(id)"
        case .priceHistory(let id):     return "/products/\(id)/price-history"
        case .reviewQueue:              return "/products/review-queue"
        case .bulkEnhance:              return "/products/review-queue/enhance"
        case .enhance(let id):          return "/products/\(id)/enhance"
        case .reviewStatus(let id):     return "/products/\(id)/review-status"
        case .autoDedupTokens:          return "/products/auto-dedup-tokens"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .list, .search, .detail, .priceHistory, .reviewQueue: return .get
        case .create, .bulkEnhance, .enhance, .autoDedupTokens:    return .post
        case .update, .reviewStatus:                               return .put
        case .delete:                                              return .delete
        }
    }

    var query: [URLQueryItem] {
        switch self {
        case .list(let page, let perPage, let category):
            var items: [URLQueryItem] = []
            if let page { items.append(.init(name: "page", value: String(page))) }
            if let perPage { items.append(.init(name: "per_page", value: String(perPage))) }
            if let category, !category.isEmpty { items.append(.init(name: "category", value: category)) }
            return items
        case .search(let q):
            return [.init(name: "q", value: q)]
        case .reviewQueue(let status):
            return [.init(name: "status", value: status)]
        default:
            return []
        }
    }

    var isMutating: Bool { method != .get }
}

struct ProductCreateBody: Encodable {
    let name: String
    let category: String?
    let barcode: String?
}

struct ProductUpdateBody: Encodable {
    let name: String?
    let category: String?
    let barcode: String?
    let defaultUnit: String?
    let defaultSizeLabel: String?
}

struct ProductReviewStatusBody: Encodable {
    let reviewState: String
}

struct ProductBulkEnhanceBody: Encodable {
    let limit: Int?
    let provider: String?
}

// MARK: - Product snapshots (backend prefix: /product-snapshots)

enum ProductSnapshotEndpoint {
    case upload
    case list(productId: Int?)
    case detail(id: Int)
    case image(id: Int)
    case reviewQueue(status: String)
    case review(id: Int)
    case promote(id: Int)
    case delete(id: Int)

    var path: String {
        switch self {
        case .upload:                   return "/product-snapshots/upload"
        case .list:                     return "/product-snapshots"
        case .detail(let id):           return "/product-snapshots/\(id)"
        case .image(let id):            return "/product-snapshots/\(id)/image"
        case .reviewQueue:              return "/product-snapshots/review-queue"
        case .review(let id):           return "/product-snapshots/\(id)/review"
        case .promote(let id):          return "/product-snapshots/\(id)/promote"
        case .delete(let id):           return "/product-snapshots/\(id)"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .upload, .promote:                    return .post
        case .list, .detail, .image, .reviewQueue: return .get
        case .review:                              return .put
        case .delete:                              return .delete
        }
    }

    var query: [URLQueryItem] {
        switch self {
        case .list(let pid):
            guard let pid else { return [] }
            return [.init(name: "product_id", value: String(pid))]
        case .reviewQueue(let status):
            return [.init(name: "status", value: status)]
        default:
            return []
        }
    }

    var isMutating: Bool { method != .get }
}

struct SnapshotReviewBody: Encodable {
    let productName: String?
    let category: String?
    let status: String
    let productId: Int?
    let notes: String?
}

// MARK: - Kitchen (backend prefix: /api/kitchen)
//
// Single route: GET /api/kitchen/catalog. All mutations reuse /shopping-list and
// /inventory endpoints — kitchen blueprint is read-only by design (verified by
// Rule 1 grep in src/backend/manage_kitchen_endpoint.py).

enum KitchenEndpoint {
    case catalog

    var path: String {
        switch self {
        case .catalog: return "/api/kitchen/catalog"
        }
    }
    var method: HTTPMethod { .get }
    var isMutating: Bool { false }
}

/// Response shape for GET /api/kitchen/catalog — see
/// `get_kitchen_catalog()` in src/backend/manage_kitchen.py.
///
/// Backend JSON:
///   { frequent: [ProductTile, ...],
///     categories: { Produce: [...], Meat: [...], Dairy: [...],
///                   Bakery: [...], Pantry: [...], Other: [...] },
///     on_list_product_ids: [Int, ...] }
struct KitchenCatalogResponse: Codable, Equatable {
    let frequent: [KitchenTile]
    let categories: [String: [KitchenTile]]
    let onListProductIds: [Int]
}

/// `ProductTile` from `get_kitchen_catalog()` — fields named exactly as the
/// backend serializes them (snake → camel via APIClient's decoder).
struct KitchenTile: Codable, Equatable, Hashable, Identifiable {
    let productId: Int
    let name: String
    let category: String?
    let imageUrl: String?
    let fallbackEmoji: String?
    let purchaseCount: Int?
    let latestUnitPrice: Double?
    let stores: [String]?

    var id: Int { productId }
}

// MARK: - Receipt upload (multipart)

struct ReceiptUploadFields {
    let imageData: Data
    let mimeType: String
    let receiptType: String
    let modelId: Int?
}
