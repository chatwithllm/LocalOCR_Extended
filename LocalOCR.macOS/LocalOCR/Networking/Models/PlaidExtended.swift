import Foundation

// MARK: - /plaid/status

struct PlaidStatusResponse: Codable, Equatable {
    let configured: Bool
    let env: String?
}

// MARK: - /plaid/link-token

struct PlaidLinkTokenResponse: Codable, Equatable {
    let linkToken: String
    let expiration: String?
    let env: String?
    let updateMode: Bool?
}

// MARK: - /plaid/items

struct PlaidItem: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let institutionId: String?
    let institutionName: String?
    let nickname: String?
    let products: [String]?
    let status: String?
    let lastSyncAt: String?
    let lastSyncStatus: String?
    let lastSyncError: String?
    let sharedWithUserIds: [Int]?
    let ownerUserId: Int?
    let createdAt: String?

    var lastSyncDate: Date? {
        guard let s = lastSyncAt else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: s) ?? ISO8601DateFormatter().date(from: s)
    }
    var isLoginRequired: Bool { status == "login_required" }
    var isActive: Bool { status == "active" }
}

struct PlaidItemsResponse: Codable, Equatable {
    let configured: Bool?
    let env: String?
    let items: [PlaidItem]
    let autoSyncHours: Int?
}

struct PlaidItemPatchResponse: Codable, Equatable {
    let item: PlaidItem?
}

struct PlaidItemDeleteResponse: Codable, Equatable {
    let deletedId: Int?
}

struct PlaidSyncResponse: Codable, Equatable {
    let item: PlaidItem?
    let inserted: Int?
    let updated: Int?
    let conflict: Bool?
}

// MARK: - /plaid/cards-overview

struct CardsOverviewAccount: Codable, Identifiable, Equatable, Hashable {
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
    let spendMtdCents: Int?
    let txnCountMtd: Int?
    let utilizationPct: Double?
    let paidOffCents: Int?
    let categoriesMtd: [CardsOverviewCategorySlice]?

    var displayLabel: String {
        let primary = (displayName?.trimmingCharacters(in: .whitespaces).isEmpty == false
                       ? displayName : nil) ?? name ?? originalName ?? "Account"
        return primary
    }
    var balanceUpdatedDate: Date? {
        guard let s = balanceUpdatedAt else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: s) ?? ISO8601DateFormatter().date(from: s)
    }
}

struct CardsOverviewCategorySlice: Codable, Equatable, Hashable {
    let category: String
    let amountCents: Int
}

struct CardsOverviewGroup: Codable, Equatable, Hashable {
    let type: String
    let label: String
    let accounts: [CardsOverviewAccount]
    var isCredit: Bool { type == "credit_card" }
    var isLoan: Bool { type == "loan" }
}

struct CardsOverviewTotals: Codable, Equatable {
    let creditBalanceCents: Int?
    let creditLimitCents: Int?
    let overallUtilizationPct: Double?
    let creditSpendMtdCents: Int?
    let loanBalanceCents: Int?
}

struct CardsOverviewResponse: Codable, Equatable {
    let asOf: String?
    let monthStart: String?
    let groups: [CardsOverviewGroup]
    let totals: CardsOverviewTotals?
}

// MARK: - /plaid/transactions

struct PlaidConfirmedTransactionRow: Codable, Identifiable, Equatable, Hashable {
    let purchaseId: Int
    let date: String?
    let amount: Double
    let merchant: String?
    let plaidAccountId: String?
    let plaidCategoryPrimary: String?
    let plaidCategoryDetailed: String?
    let budgetCategory: String?
    let spendingDomain: String?
    let transactionType: String?

    var id: Int { purchaseId }
    var dateValue: Date? {
        guard let s = date else { return nil }
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        fmt.timeZone = TimeZone(identifier: "UTC")
        return fmt.date(from: s)
    }
    var isRefund: Bool { amount < 0 }
}

struct PlaidTransactionsResponse: Codable, Equatable {
    let transactions: [PlaidConfirmedTransactionRow]
    let total: Int
    let limit: Int
    let offset: Int
}

// MARK: - /plaid/spending-trends

struct PlaidSpendingTrendRow: Codable, Equatable, Hashable {
    let month: String
    let category: String
    let total: Double
    let count: Int
}

struct PlaidSpendingTrendsResponse: Codable, Equatable {
    let months: Int
    let series: [PlaidSpendingTrendRow]
}

// MARK: - /plaid/transaction-breakdown

struct PlaidBreakdownCounts: Codable, Equatable, Hashable {
    let purchase: Int
    let autopay: Int
    let interest: Int
    let refund: Int
}

struct PlaidBreakdownAccount: Codable, Identifiable, Equatable, Hashable {
    let plaidAccountId: String
    let nickname: String?
    let name: String?
    let mask: String?
    let counts: PlaidBreakdownCounts
    let total: Int
    var id: String { plaidAccountId }
}

struct PlaidBreakdownResponse: Codable, Equatable {
    let accounts: [PlaidBreakdownAccount]
}

// MARK: - /analytics/spend-by-person

struct SpendByPersonRow: Codable, Equatable, Hashable {
    let userId: Int?
    let name: String
    let total: Double
    let receiptCount: Int?
    let isSelf: Bool?
}

struct SpendByPersonResponse: Codable, Equatable {
    let month: String?
    let perPerson: [SpendByPersonRow]?
    let householdTotal: Double?
    let unsetTotal: Double?
    let totalReceipts: Int?
}

// MARK: - /plaid/staged-transactions/<id>/match-candidates

struct StagedMatchCandidate: Codable, Identifiable, Equatable, Hashable {
    let purchaseId: Int
    let date: String?
    let store: String?
    let totalAmount: Double
    let merchantMatch: Bool?
    let amountDelta: Double?
    let dateDeltaDays: Int?
    var id: Int { purchaseId }
    var dateValue: Date? {
        guard let s = date else { return nil }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = TimeZone(identifier: "UTC")
        return f.date(from: s)
    }
}

struct StagedMatchCandidatesResponse: Codable, Equatable {
    let candidates: [StagedMatchCandidate]
    let staged: StagedMatchStagedShort?
}

struct StagedMatchStagedShort: Codable, Equatable {
    let id: Int?
    let merchant: String?
    let amount: Double?
    let date: String?
}

// MARK: - /plaid/staged-transactions (richer payload)

struct PlaidStagedCounts: Codable, Equatable {
    let readyToImport: Int?
    let duplicateFlagged: Int?
    let skippedPending: Int?
    let confirmed: Int?
    let dismissed: Int?
}

struct PlaidStagedListResponse: Codable, Equatable {
    let stagedTransactions: [PlaidTransaction]
    let counts: PlaidStagedCounts?
    let statusFilter: String?
}

// MARK: - /plaid/staged-transactions/<id>/{confirm,dismiss,flag-duplicate}

struct PlaidStagedActionResponse: Codable, Equatable {
    let staged: PlaidTransaction?
    let purchaseId: Int?
    let receiptRecordId: Int?
    let matchedExisting: Bool?
}

struct PlaidBulkConfirmResponse: Codable, Equatable {
    let confirmedIds: [Int]?
    let skipped: [PlaidBulkSkipReason]?
    let summary: PlaidBulkSummary?
}

struct PlaidBulkSkipReason: Codable, Equatable {
    let id: Int?
    let reason: String?
    let error: String?
}

struct PlaidBulkSummary: Codable, Equatable {
    let confirmed: Int?
    let skipped: Int?
    let total: Int?
}

// MARK: - /plaid/staged-transactions/<id>/attach-upload

struct PlaidAttachUploadResponse: Codable, Equatable {
    let purchaseId: Int?
    let receiptRecordId: Int?
    let staged: PlaidTransaction?
    let message: String?
}
