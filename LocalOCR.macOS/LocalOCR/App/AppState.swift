import Foundation
import Combine
import SwiftUI

/// Global app state. Owns auth status, household identity, server reachability,
/// and derived counters used by Dock badge + menu bar.
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

    @Published private(set) var currentUser: User? = nil
    @Published private(set) var currentHousehold: Household? = nil

    // MARK: - Server reachability

    @Published private(set) var isServerReachable: Bool = false

    // MARK: - Derived counters (drive menu-bar badge + Dock badge)

    @Published private(set) var lowStockCount: Int = 0
    @Published private(set) var pendingWriteCount: Int = 0

    // MARK: - Demo mode (read-only enforcement, §1.7 rule 10)

    @Published private(set) var isDemoMode: Bool = false

    private init() {}

    // MARK: - Mutators (called by AuthState)

    func setAuthStatus(_ status: AuthStatus) {
        authStatus = status
    }

    func setDemoMode(_ enabled: Bool) {
        isDemoMode = enabled
    }

    func applyAuthenticatedUser(_ me: AuthMeResponse) {
        currentUser = me.user
        currentHousehold = me.household
        isServerReachable = true
        authStatus = .authenticated
    }

    func applyLoggedOut() {
        currentUser = nil
        currentHousehold = nil
        authStatus = .unauthenticated
    }

    func setServerReachable(_ reachable: Bool) {
        isServerReachable = reachable
    }

    func setLowStockCount(_ count: Int) {
        lowStockCount = max(0, count)
    }

    func setPendingWriteCount(_ count: Int) {
        pendingWriteCount = max(0, count)
    }
}
