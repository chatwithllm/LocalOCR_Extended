import Foundation

struct ContributionEvent: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let userId: Int
    let eventType: String
    let subjectType: String?
    let subjectId: Int?
    let status: String
    let points: Int
    let description: String?
    let occurredAt: Date
}

struct ContributionLeaderRow: Codable, Identifiable, Equatable, Hashable {
    var id: Int { userId }
    let userId: Int
    let userName: String
    let avatarEmoji: String?
    let points: Int
    let receiptCount: Int
}
