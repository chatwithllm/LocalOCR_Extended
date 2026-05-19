import Foundation

/// User model — mirrors the `users` table (§1.3) and the `/auth/me` response shape.
///
/// JSON convention: server emits snake_case, client decodes to camelCase via
/// `JSONDecoder.keyDecodingStrategy = .convertFromSnakeCase`.
struct User: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String
    let email: String
    let role: String                   // "admin" | "member" | "service" | "kid"
    let isActive: Bool
    let googleSub: String?
    let allowedPages: [String]?
    let allowWrite: Bool
    let avatarEmoji: String?
    let activeAiModelConfigId: Int?
    let hasApiToken: Bool?             // present in /auth/me; never the raw token

    /// Lowercase convenience for permission checks.
    var isAdmin: Bool { role.lowercased() == "admin" }
}
