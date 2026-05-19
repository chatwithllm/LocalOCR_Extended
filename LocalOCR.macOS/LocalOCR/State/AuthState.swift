import Foundation
import Combine
import os.log

/// Owns the auth lifecycle per VETO_RESOLUTION_PATCH §2:
///   1. POST /auth/login → cookie session + persist credentials in Keychain
///   2. POST /auth/device-pairing/start → poll status → store device token
///   3. All subsequent requests send X-Trusted-Device-Token (via APIClient)
///   4. On 401 → silent re-login from Keychain → re-pair if needed
///   5. Demo mode is a parallel `.demoMode` status that gates writes via APIClient/DemoModeGate
@MainActor
final class AuthState: ObservableObject {

    static let shared = AuthState()

    private let api: APIClient
    private let keychain: KeychainStore
    private let appState: AppState
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "auth")

    @Published private(set) var lastError: String?
    @Published private(set) var isBusy = false

    private var sessionExpiryObserver: NSObjectProtocol?
    private var devicePairingPollTask: Task<Void, Never>?

    init(api: APIClient = .shared, keychain: KeychainStore = KeychainStore(), appState: AppState = .shared) {
        self.api = api
        self.keychain = keychain
        self.appState = appState
        observeSessionExpiry()
    }

    deinit {
        if let token = sessionExpiryObserver {
            NotificationCenter.default.removeObserver(token)
        }
    }

    // MARK: - Session restore (called on app launch)

    func checkSession() async {
        appState.setAuthStatus(.authenticating)
        do {
            let me = try await api.request(.get, path: AuthEndpoint.me.path, as: AuthMeResponse.self)
            appState.applyAuthenticatedUser(me)
        } catch APIError.unauthorized {
            // Try silent re-login if we have Keychain credentials.
            if await tryReauthFromKeychain() == false {
                appState.setAuthStatus(.unauthenticated)
            }
        } catch {
            // Server unreachable or other failure — surface in LoginView later.
            logger.error("checkSession failed: \(error.localizedDescription, privacy: .public)")
            appState.setAuthStatus(.unauthenticated)
        }
    }

    // MARK: - Email + password login (Phase A — VETO_RESOLUTION_PATCH §2)

    func login(email: String, password: String) async {
        isBusy = true
        defer { isBusy = false }
        lastError = nil

        do {
            // 1. Cookie session
            let body = LoginRequestBody(email: email, password: password)
            try await api.request(.post, path: "/auth/login", jsonBody: body)

            // 2. Persist credentials in Keychain for silent re-auth
            try keychain.saveCredentials(.init(email: email, password: password))

            // 3. Validate session
            let me = try await api.request(.get, path: AuthEndpoint.me.path, as: AuthMeResponse.self)
            appState.applyAuthenticatedUser(me)

            // 4. Kick off Phase B (trusted device pairing) only if we don't already have a token.
            if keychain.loadDeviceToken() == nil {
                Task { await self.pairDeviceIfNeeded() }
            }
        } catch APIError.unauthorized, APIError.validation {
            lastError = "Email or password incorrect."
        } catch let error as APIError {
            lastError = error.errorDescription
        } catch {
            lastError = "Couldn't reach server. Check the server URL and try again."
        }
    }

    // MARK: - Demo mode

    func setDemoMode() {
        appState.setDemoMode(true)
        appState.setAuthStatus(.demoMode)
    }

    // MARK: - Logout

    func logout() async {
        // Best-effort server logout — ignore errors so client always clears state.
        try? await api.request(.post, path: AuthEndpoint.logout.path)

        // Wipe local state
        keychain.wipeAll()
        HTTPCookieStorage.shared.cookies?.forEach { HTTPCookieStorage.shared.deleteCookie($0) }

        appState.applyLoggedOut()
        appState.setAuthStatus(.unauthenticated)
        appState.setDemoMode(false)
    }

    // MARK: - Google OAuth (Phase 3 stub — full flow wired in GoogleOAuthSheet)

    func loginWithGoogle() async {
        // Sheet presentation is handled by LoginView using ASWebAuthenticationSession.
        // On callback, the sheet's onCompletion handler will call back here with the
        // Google `code` + `state` query params, which we exchange via /auth/google/callback.
    }

    func completeGoogleOAuth(state: String, code: String) async {
        isBusy = true
        defer { isBusy = false }
        do {
            let q = [
                URLQueryItem(name: "state", value: state),
                URLQueryItem(name: "code", value: code)
            ]
            // Backend OAuth callback path — inline string since it's not a frequent client invocation.
            try await api.request(.get, path: "/auth/google/callback", query: q)
            let me = try await api.request(.get, path: AuthEndpoint.me.path, as: AuthMeResponse.self)
            appState.applyAuthenticatedUser(me)
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? "Google sign-in failed."
        }
    }

    // MARK: - Phase B — trusted device pairing

    private func pairDeviceIfNeeded() async {
        guard keychain.loadDeviceToken() == nil else { return }
        do {
            let body = DevicePairingStartBody(deviceName: Host.current().localizedName ?? "Mac", scope: "shared_household")
            let response = try await api.request(
                .post,
                path: "/auth/device-pairing/start",
                jsonBody: body,
                as: DevicePairingStartResponse.self
            )

            // Admin users typically auto-approve their own device.
            if response.status == "approved" {
                try keychain.saveDeviceToken(response.pairingToken)
                return
            }

            // Otherwise, poll for up to 5 minutes (manual approval from another admin).
            devicePairingPollTask = Task { [pairingToken = response.pairingToken] in
                await pollDevicePairing(token: pairingToken)
            }
        } catch {
            logger.warning("device pairing start failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func pollDevicePairing(token: String) async {
        let pollInterval: UInt64 = 5_000_000_000  // 5s
        let maxAttempts = 60  // 5 minutes
        for _ in 0..<maxAttempts {
            try? await Task.sleep(nanoseconds: pollInterval)
            guard !Task.isCancelled else { return }
            do {
                let status = try await api.request(
                    .get,
                    path: AuthEndpoint.devicePairingStatus(token: token).path,
                    as: DevicePairingStatusResponse.self
                )
                if status.status == "approved", let issued = status.token {
                    try keychain.saveDeviceToken(issued)
                    logger.info("device paired successfully")
                    return
                }
                if status.status == "rejected" || status.status == "expired" {
                    return
                }
            } catch {
                continue
            }
        }
    }

    // MARK: - 401 handler

    private func observeSessionExpiry() {
        sessionExpiryObserver = NotificationCenter.default.addObserver(
            forName: .authSessionExpired,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                if await self.tryReauthFromKeychain() == false {
                    await self.logout()
                }
            }
        }
    }

    /// Returns true if silent re-auth restored the session.
    private func tryReauthFromKeychain() async -> Bool {
        guard let creds = keychain.loadCredentials() else { return false }
        do {
            let body = LoginRequestBody(email: creds.email, password: creds.password)
            try await api.request(.post, path: "/auth/login", jsonBody: body)
            let me = try await api.request(.get, path: AuthEndpoint.me.path, as: AuthMeResponse.self)
            appState.applyAuthenticatedUser(me)
            return true
        } catch {
            logger.warning("silent reauth failed: \(error.localizedDescription, privacy: .public)")
            return false
        }
    }
}
