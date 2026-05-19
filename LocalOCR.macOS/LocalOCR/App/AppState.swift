import Foundation
import Combine
import SwiftUI

/// Global app state. Owns auth status, household identity, server reachability,
/// and derived counters used by Dock badge + menu bar.
///
/// Phase 1: stubs only — `@Published` fields declared; methods land in Phase 3 (Networking + Auth).
@MainActor
final class AppState: ObservableObject {

    static let shared = AppState()

    // MARK: - Auth

    enum AuthStatus {
        case unauthenticated
        case authenticating
        case authenticated
        case demoMode
    }

    @Published private(set) var authStatus: AuthStatus = .unauthenticated

    // MARK: - Household identity (placeholder — real types in Phase 3)

    @Published private(set) var currentUserId: Int? = nil
    @Published private(set) var currentUserEmail: String? = nil
    @Published private(set) var currentHouseholdId: Int? = nil
    @Published private(set) var currentHouseholdName: String? = nil

    // MARK: - Server reachability

    @Published private(set) var isServerReachable: Bool = false

    // MARK: - Derived counters (drive menu-bar badge + Dock badge)

    @Published private(set) var lowStockCount: Int = 0
    @Published private(set) var pendingWriteCount: Int = 0

    // MARK: - Demo mode (read-only enforcement, §1.7 rule 10)

    @Published private(set) var isDemoMode: Bool = false

    private init() {}
}
