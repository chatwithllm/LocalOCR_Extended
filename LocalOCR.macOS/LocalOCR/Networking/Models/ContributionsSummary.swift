import Foundation

// /contributions/summary response — covers the full Contributions page.

struct ContributionsUser: Codable, Equatable, Hashable {
    let id: Int?
    let name: String?
    let email: String?
    let avatarEmoji: String?
}

struct ContributionsSummary: Codable, Equatable, Hashable {
    let totalScore: Int
    let receiptPoints: Int
    let ocrPoints: Int
    let bonusPoints: Int
    let floatingPoints: Int
    let receiptsProcessed: Int
    let ocrFixes: Int
}

struct ContributionsRule: Codable, Identifiable, Equatable, Hashable {
    let key: String
    let title: String
    let points: Int
    let description: String?
    var id: String { key }
}

struct ContributionsEvent: Codable, Identifiable, Equatable, Hashable {
    let eventType: String?
    let points: Int
    let description: String?
    let createdAt: String?
    let source: String?
    let status: String?

    /// Backend has no `id`; combine fields for stable identity in ForEach.
    var id: String {
        "\(createdAt ?? "")|\(eventType ?? "")|\(description ?? "")|\(points)"
    }
    var createdAtDate: Date? {
        guard let s = createdAt else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: s) ?? ISO8601DateFormatter().date(from: s)
    }
}

struct ContributionsOpportunity: Codable, Identifiable, Equatable, Hashable {
    let title: String
    let count: Int?
    let description: String?
    let page: String?
    let cta: String?

    var id: String { title }
}

struct ContributionsSummaryResponse: Codable, Equatable {
    let summary: ContributionsSummary
    let rules: [ContributionsRule]?
    let recentEvents: [ContributionsEvent]?
    let opportunities: [ContributionsOpportunity]?
    let notes: [String]?
    let user: ContributionsUser?
}

// Status label helper mirroring web's `contributionStatusLabel()`.
enum ContributionStatusLabel {
    static func format(_ raw: String?) -> String {
        switch (raw ?? "").lowercased() {
        case "pending":      return "Pending validation"
        case "validated":    return "Validated"
        case "void":         return "Voided"
        case "floating":     return "Floating"
        case "finalized":    return "Finalized"
        case "":             return "—"
        default:             return raw!.capitalized
        }
    }
}
