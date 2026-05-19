import Foundation

// MARK: - Auth (Phase 3)

enum AuthEndpoint {
    case me
    case login(email: String, password: String)
    case logout
    case devicePairingStart(deviceName: String, scope: String)
    case devicePairingStatus(token: String)
    case oauthGoogleStart
    case oauthGoogleCallback(state: String, code: String)

    var path: String {
        switch self {
        case .me:                              return "/auth/me"
        case .login:                           return "/auth/login"
        case .logout:                          return "/auth/logout"
        case .devicePairingStart:              return "/auth/device-pairing/start"
        case .devicePairingStatus(let token):  return "/auth/device-pairing/status/\(token)"
        case .oauthGoogleStart:                return "/auth/google/start"
        case .oauthGoogleCallback:             return "/auth/google/callback"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .me, .devicePairingStatus, .oauthGoogleStart, .oauthGoogleCallback: return .get
        case .login, .logout, .devicePairingStart:                               return .post
        }
    }

    var isMutating: Bool { method != .get }
}

struct LoginRequestBody: Encodable { let email: String; let password: String }
struct DevicePairingStartBody: Encodable { let deviceName: String; let scope: String }
struct DevicePairingStartResponse: Codable, Equatable { let pairingToken: String; let status: String }
struct DevicePairingStatusResponse: Codable, Equatable { let status: String; let token: String? }

// MARK: - Inventory (Phase 4)

enum InventoryEndpoint {
    case list
    case adjustQuantity(id: Int, delta: Double)
    case markLowStock(id: Int)

    var path: String {
        switch self {
        case .list:                            return "/inventory"
        case .adjustQuantity(let id, _):       return "/inventory/\(id)/adjust"
        case .markLowStock(let id):            return "/inventory/\(id)/mark-low"
        }
    }
    var method: HTTPMethod {
        switch self { case .list: return .get; default: return .post }
    }
    var isMutating: Bool { method != .get }
}

struct AdjustQuantityBody: Encodable { let delta: Double }

// MARK: - Receipts (Phase 4)

enum ReceiptEndpoint {
    case list
    case detail(id: Int)
    case confirm(id: Int)
    case rerunOCR(id: Int, modelId: Int?)
    case delete(id: Int)

    var path: String {
        switch self {
        case .list:                  return "/receipts"
        case .detail(let id):        return "/receipts/\(id)"
        case .confirm(let id):       return "/receipts/\(id)/confirm"
        case .rerunOCR(let id, _):   return "/receipts/\(id)/rerun-ocr"
        case .delete(let id):        return "/receipts/\(id)"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .list, .detail:         return .get
        case .confirm, .rerunOCR:    return .post
        case .delete:                return .delete
        }
    }
    var isMutating: Bool { method != .get }
}

struct RerunOCRBody: Encodable { let modelId: Int? }

// MARK: - Shopping (Phase 4)

enum ShoppingEndpoint {
    case list
    case add(productName: String, quantity: Double, source: String, productId: Int?)
    case toggle(id: Int)
    case delete(id: Int)
    case populateFromLowStock

    var path: String {
        switch self {
        case .list:                  return "/shopping"
        case .add:                   return "/shopping"
        case .toggle(let id):        return "/shopping/\(id)/toggle"
        case .delete(let id):        return "/shopping/\(id)"
        case .populateFromLowStock:  return "/shopping/populate-from-low-stock"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .list:                  return .get
        case .add, .populateFromLowStock: return .post
        case .toggle:                return .post
        case .delete:                return .delete
        }
    }
    var isMutating: Bool { method != .get }
}

struct ShoppingAddBody: Encodable {
    let productName: String
    let quantity: Double
    let source: String
    let productId: Int?
}

// MARK: - Finance — Fixed Bills (Phase 4)

enum FixedBillsEndpoint {
    case list
    case rename(id: Int, label: String)
    case markPaid(id: Int, amount: Double, date: Date)

    var path: String {
        switch self {
        case .list:                  return "/floor-obligations"
        case .rename(let id, _):     return "/floor-obligations/\(id)"
        case .markPaid(let id, _, _): return "/floor-obligations/\(id)/mark-paid"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .list:                  return .get
        case .rename:                return .patch
        case .markPaid:              return .post
        }
    }
    var isMutating: Bool { method != .get }
}

struct BillRenameBody: Encodable { let label: String }
struct BillMarkPaidBody: Encodable { let amount: Double; let paidAt: Date }

// MARK: - Finance — Plaid (Phase 4)

enum PlaidEndpoint {
    case accounts
    case stagedTransactions
    case linkStart
    case linkExchange(publicToken: String)
    case syncNow
    case confirmTransaction(id: Int)
    case dismissTransaction(id: Int)

    var path: String {
        switch self {
        case .accounts:                return "/plaid/accounts"
        case .stagedTransactions:      return "/plaid/staged-transactions"
        case .linkStart:               return "/plaid/link/start"
        case .linkExchange:            return "/plaid/link/exchange"
        case .syncNow:                 return "/plaid/sync"
        case .confirmTransaction(let id): return "/plaid/staged-transactions/\(id)/confirm"
        case .dismissTransaction(let id): return "/plaid/staged-transactions/\(id)/dismiss"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .accounts, .stagedTransactions, .linkStart: return .get
        case .linkExchange, .syncNow, .confirmTransaction, .dismissTransaction: return .post
        }
    }
    var isMutating: Bool { method != .get }
}

struct PlaidExchangeBody: Encodable { let publicToken: String }

// MARK: - Finance — Cash (Phase 4)

enum CashEndpoint {
    case list
    case create(amount: Double, description: String, category: String?, transactionDate: Date)
    case delete(id: Int)

    var path: String {
        switch self {
        case .list, .create:         return "/cash-transactions"
        case .delete(let id):        return "/cash-transactions/\(id)"
        }
    }
    var method: HTTPMethod {
        switch self {
        case .list:                  return .get
        case .create:                return .post
        case .delete:                return .delete
        }
    }
    var isMutating: Bool { method != .get }
}

struct CashCreateBody: Encodable {
    let amount: Double
    let description: String
    let category: String?
    let transactionDate: Date
}

// MARK: - Analytics (Phase 4)

enum AnalyticsEndpoint {
    case spendingByCategory(month: String?)
    case spendingByMerchant
    case monthlyTimeline

    var path: String {
        switch self {
        case .spendingByCategory:    return "/analytics/spending-by-category"
        case .spendingByMerchant:    return "/analytics/spending-by-merchant"
        case .monthlyTimeline:       return "/analytics/monthly-timeline"
        }
    }
    var method: HTTPMethod { .get }
    var isMutating: Bool { false }
}

// MARK: - Household / AI Models (Phase 4)

enum HouseholdEndpoint {
    case members
    case users
    case aiModels

    var path: String {
        switch self {
        case .members:     return "/household/members"
        case .users:       return "/household/users"
        case .aiModels:    return "/household/ai-models"
        }
    }
    var method: HTTPMethod { .get }
    var isMutating: Bool { false }
}

// MARK: - Receipt upload (multipart — used by OCRUploadView)

struct ReceiptUploadFields {
    let imageData: Data
    let mimeType: String
    let receiptType: String           // "auto" | "grocery" | "restaurant" | "expense"
    let modelId: Int?
}
