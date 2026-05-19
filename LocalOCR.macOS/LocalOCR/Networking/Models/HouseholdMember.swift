import Foundation

struct HouseholdMember: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String
    let ageGroup: String?     // "adult" | "child" | "elder"
    let avatarEmoji: String?
}
