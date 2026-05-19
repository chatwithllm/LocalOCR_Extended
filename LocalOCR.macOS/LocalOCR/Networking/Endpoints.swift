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

enum ShoppingEndpoint {
    case list
    case addItem(name: String, quantity: Double, source: String, productId: Int?)
    case updateItem(id: Int, status: String?)
    case deleteItem(id: Int)

    var path: String {
        switch self {
        case .list:                  return "/shopping-list"
        case .addItem:               return "/shopping-list/items"
        case .updateItem(let id, _): return "/shopping-list/items/\(id)"
        case .deleteItem(let id):    return "/shopping-list/items/\(id)"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .list:                  return .get
        case .addItem:               return .post
        case .updateItem:            return .put
        case .deleteItem:            return .delete
        }
    }
    var isMutating: Bool { method != .get }
}

struct ShoppingAddBody: Encodable {
    let name: String
    let quantity: Double
    let source: String?
    let productId: Int?
}

struct ShoppingUpdateBody: Encodable {
    let status: String?
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

// MARK: - Receipt upload (multipart)

struct ReceiptUploadFields {
    let imageData: Data
    let mimeType: String
    let receiptType: String
    let modelId: Int?
}
