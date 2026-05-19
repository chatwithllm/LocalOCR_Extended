import Foundation

struct PlaidAccount: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let plaidItemId: Int
    let accountName: String
    let accountMask: String?
    let accountType: String
    let balanceCents: Int?
    let creditLimitCents: Int?
    let displayName: String?
    let status: String                // "active" | "loginRequired" | "disconnected"
    let lastSyncedAt: Date?
}

struct PlaidTransaction: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let merchantName: String?
    let amount: Double
    let transactionDate: Date
    let suggestedReceiptType: String?
    let status: String                // "pending" | "confirmed" | "dismissed" | "matched"
    let duplicatePurchaseId: Int?
}
