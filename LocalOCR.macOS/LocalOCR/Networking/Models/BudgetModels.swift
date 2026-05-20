import Foundation

// MARK: - /budget/category-summary

struct BudgetContribution: Codable, Equatable, Hashable {
    let store: String?
    let date: String?
    let transactionType: String?
    let amount: Double
    let purchaseId: Int?

    var dateValue: Date? {
        guard let s = date else { return nil }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = TimeZone(identifier: "UTC")
        return f.date(from: s)
    }
}

struct BudgetCategoryStatus: Codable, Identifiable, Equatable, Hashable {
    let month: String?
    let budgetCategory: String
    let budgetAmount: Double
    let spent: Double
    let remaining: Double
    let percentage: Double
    let updatedAt: String?
    let contributions: [BudgetContribution]?

    var id: String { budgetCategory }

    var isActive: Bool { budgetAmount > 0 || spent > 0 }
    var isOver: Bool { remaining < 0 }
    var pctClamped: Double { min(100, max(0, percentage)) }
    /// Same ok / warn / danger thresholds as the web (70% / 90%).
    var severityColor: BudgetSeverity {
        if percentage >= 90 { return .danger }
        if percentage >= 70 { return .warn }
        return .ok
    }
    var remainingLabel: String {
        let amt = String(format: "$%.2f", abs(remaining))
        return remaining >= 0 ? "\(amt) left" : "\(amt) over"
    }
    var targetLabel: String {
        budgetAmount > 0
            ? "of \(String(format: "$%.2f", budgetAmount))"
            : "No target"
    }
}

enum BudgetSeverity {
    case ok, warn, danger
}

struct BudgetHouseholdObligation: Codable, Equatable, Hashable {
    let domain: String?
    let label: String?
    let spent: Double?
    let targetTotal: Double?
    let remaining: Double?
    let percentage: Double?
    let committedThisMonth: Double?
    let oneOffThisMonth: Double?
    let recurringCount: Int?
    let oneOffCount: Int?
}

struct BudgetCategorySummaryResponse: Codable, Equatable {
    let month: String?
    let categories: [BudgetCategoryStatus]
    let activeCount: Int?
    let householdObligations: BudgetHouseholdObligation?
}

// MARK: - /budget/target-history

struct BudgetTargetRow: Codable, Identifiable, Equatable, Hashable {
    let month: String?
    let budgetCategory: String
    let budgetAmount: Double
    let updatedAt: String?
    var id: String { budgetCategory }
}

struct BudgetHistoryRow: Codable, Identifiable, Equatable, Hashable {
    let month: String?
    let budgetCategory: String?
    let previousAmount: Double?
    let newAmount: Double
    let changedAt: String?

    /// Combine fields to produce a stable identity (backend has no `id`).
    var id: String {
        "\(month ?? "")|\(budgetCategory ?? "")|\(changedAt ?? "")|\(newAmount)"
    }
    var changedAtDate: Date? {
        guard let s = changedAt else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: s) ?? ISO8601DateFormatter().date(from: s)
    }
    var deltaLabel: String {
        if let prev = previousAmount {
            let arrow = newAmount > prev ? "↑" : (newAmount < prev ? "↓" : "→")
            let prevStr = String(format: "$%.2f", prev)
            let newStr = String(format: "$%.2f", newAmount)
            return "\(prevStr) \(arrow) \(newStr)"
        }
        return "Set to \(String(format: "$%.2f", newAmount))"
    }
}

struct BudgetTargetHistoryResponse: Codable, Equatable {
    let month: String?
    let currentTargets: [BudgetTargetRow]
    let history: [BudgetHistoryRow]
}

// MARK: - Canonical category list (mirrors src/backend/budgeting_domains.py)

enum BudgetCategoryCatalog {
    static let all: [String] = [
        "grocery",
        "dining",
        "utilities",
        "housing",
        "insurance",
        "childcare",
        "health",
        "subscriptions",
        "household",
        "retail",
        "events",
        "entertainment",
        "other_recurring",
        "other",
    ]

    static func label(for raw: String) -> String {
        raw.split(separator: "_")
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }
}
