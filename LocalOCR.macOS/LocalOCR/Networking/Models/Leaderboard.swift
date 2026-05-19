import Foundation

/// Household ranking row — matches `serialize_household_leaderboard` in
/// src/backend/manage_authentication.py. Embedded inside `/auth/me`.
struct LeaderboardRow: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String?
    let email: String?
    let avatarEmoji: String?
    let role: String?
    let rank: Int?
    let score: Double?
    let receiptsProcessed: Int?
    let receiptsMonth: Int?
    let receiptsToday: Int?
    let ocrCorrections: Int?
    let ocrCorrectionsMonth: Int?
    let bonusPoints: Double?
    let floatingPoints: Double?

    var displayName: String { name ?? email ?? "User \(id)" }
}

struct Leaderboard: Codable, Equatable {
    let month: String?
    let rankings: [LeaderboardRow]
    let leaders: [LeaderboardRow]?
    let currentUserRank: Int?
    let totalUsers: Int?
}

/// Extends the existing AuthMeResponse with the leaderboard payload.
/// (AuthMeResponse already defined in Household.swift — extending here.)
struct AuthMeWithLeaderboard: Codable, Equatable {
    let user: User
    let household: Household?
    let leaderboard: Leaderboard?
}
