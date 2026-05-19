import Foundation

/// Household identity — derived from the `/auth/me` response (no dedicated table).
/// Server returns household_id and household_name on the authenticated user payload.
struct Household: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String
    let memberCount: Int?
}

/// Wrapper for the full `/auth/me` payload. Server returns user fields at the
/// top level plus a nested household shape; this struct stitches both.
struct AuthMeResponse: Codable, Equatable {
    let user: User
    let household: Household?
}
