import Foundation

/// Plaid account — matches `_serialize_plaid_account` in plaid_integration.py.
/// Backend wraps in `{"accounts": [...]}`.
struct PlaidAccount: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let plaidItemId: Int
    let plaidAccountId: String?
    let name: String?
    let originalName: String?
    let displayName: String?
    let ownerLabel: String?
    let mask: String?
    let type: String?
    let subtype: String?
    let balanceCents: Int?
    let creditLimitCents: Int?
    let availableCreditCents: Int?
    let originalLoanAmountCents: Int?
    let aprBps: Int?
    let monthlyPaymentCents: Int?
    let monthlyPaymentDueDay: Int?
    let balanceCurrency: String?
    let balanceUpdatedAt: String?

    var accountName: String { name ?? originalName ?? "Account" }
    var accountMask: String? { mask }
    var accountType: String { type ?? "unknown" }
    var status: String { "active" }   // backend doesn't expose login-required flag here
    var lastSyncedAtDate: Date? {
        guard let s = balanceUpdatedAt else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: s) ?? ISO8601DateFormatter().date(from: s)
    }
}

/// Staged Plaid transaction — matches `_serialize_staged`.
struct PlaidTransaction: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let plaidItemId: Int?
    let institutionName: String?
    let plaidTransactionId: String?
    let plaidAccountId: String?
    let amount: Double
    let isoCurrencyCode: String?
    let transactionDate: String?
    let authorizedDate: String?
    let name: String?
    let merchantName: String?
    let plaidCategoryPrimary: String?
    let plaidCategoryDetailed: String?
    let pending: Bool?
    let status: String?
    let suggestedReceiptType: String?
    let duplicatePurchaseId: Int?
    let confirmedPurchaseId: Int?
    let createdAt: String?

    var transactionDateValue: Date {
        guard let s = transactionDate else { return Date.distantPast }
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        fmt.timeZone = TimeZone(identifier: "UTC")
        return fmt.date(from: s) ?? Date.distantPast
    }
}

struct PlaidAccountsResponse: Codable, Equatable {
    let accounts: [PlaidAccount]
}

struct PlaidStagedResponse: Codable, Equatable {
    let stagedTransactions: [PlaidTransaction]?
    let transactions: [PlaidTransaction]?

    /// Backend key is `staged_transactions` per the serializer wrapper —
    /// fall back to `transactions` if a future shape uses that.
    var rows: [PlaidTransaction] { stagedTransactions ?? transactions ?? [] }
}
