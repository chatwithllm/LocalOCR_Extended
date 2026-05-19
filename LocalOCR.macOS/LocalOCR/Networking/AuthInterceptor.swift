import Foundation

/// 401 handler bridge between APIClient and AuthState.
///
/// APIClient posts `Notification.authSessionExpired` when any request returns 401.
/// AuthState (Phase 3) observes the notification and attempts silent re-login via
/// Keychain credentials. If re-login fails, AuthState transitions to
/// `.unauthenticated` and the LoginView is presented.
enum AuthInterceptor {
    /// Sentinel — no logic here. The wiring is split across APIClient (poster) and
    /// AuthState (observer). This file documents the contract.
}
