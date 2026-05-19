import Foundation
import os.log

/// Foreground refresh dispatcher. Triggered by `AppDelegate.applicationDidBecomeActive`.
///
/// Rate-limits to one refresh per 60s (§4.5 offline strategy, AppConstants).
@MainActor
final class BackgroundFetchScheduler {

    static let shared = BackgroundFetchScheduler()

    private let preferences: PreferencesStore
    private let api: APIClient
    private let appState: AppState
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "background")

    init(
        preferences: PreferencesStore = .shared,
        api: APIClient = .shared,
        appState: AppState = .shared
    ) {
        self.preferences = preferences
        self.api = api
        self.appState = appState
    }

    /// Called from AppDelegate.applicationDidBecomeActive.
    /// Returns immediately if last refresh was within 60s.
    func foregroundRefresh() {
        guard appState.authStatus == .authenticated else { return }

        let now = Date()
        if let last = preferences.lastForegroundRefresh,
           now.timeIntervalSince(last) < AppConstants.foregroundRefreshMinIntervalSeconds {
            return
        }
        preferences.lastForegroundRefresh = now

        Task {
            await refreshSession()
            // Phase 4: refresh InventoryState, FinanceState, etc. here.
        }
    }

    private func refreshSession() async {
        do {
            let me = try await api.request(.get, path: AuthEndpoint.me.path, as: AuthMeResponse.self)
            appState.applyAuthenticatedUser(me)
            appState.setServerReachable(true)
        } catch APIError.unauthorized {
            // AuthInterceptor will fire .authSessionExpired → AuthState handles reauth.
        } catch {
            appState.setServerReachable(false)
            logger.warning("foreground refresh failed: \(error.localizedDescription, privacy: .public)")
        }
    }
}
