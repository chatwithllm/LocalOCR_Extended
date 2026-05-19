import Foundation
import KeychainAccess

/// Wraps KeychainAccess (§4.3 SPM dep). Two services per VETO_RESOLUTION_PATCH §2:
///   1. `com.localocr.extended`        — user credentials (email + password) for silent re-auth
///   2. `com.localocr.extended.device` — trusted device pairing token for long-lived auth
///
/// Never stores items in UserDefaults (§4.5, §7.4 hard gate).
struct KeychainStore {

    // MARK: - Credentials (Phase A — see VETO_RESOLUTION_PATCH §2)

    struct Credentials: Codable, Equatable {
        let email: String
        let password: String
    }

    private static var credentialsKeychain: Keychain {
        Keychain(service: AppConstants.Keychain.credentialsService)
            .accessibility(.afterFirstUnlock)
    }

    func saveCredentials(_ creds: Credentials) throws {
        let data = try JSONEncoder().encode(creds)
        try Self.credentialsKeychain.set(data, key: AppConstants.Keychain.credentialsKey)
    }

    func loadCredentials() -> Credentials? {
        guard let data = try? Self.credentialsKeychain.getData(AppConstants.Keychain.credentialsKey) else {
            return nil
        }
        return try? JSONDecoder().decode(Credentials.self, from: data)
    }

    func deleteCredentials() {
        try? Self.credentialsKeychain.remove(AppConstants.Keychain.credentialsKey)
    }

    // MARK: - Device token (Phase B — see VETO_RESOLUTION_PATCH §2)

    private static var deviceKeychain: Keychain {
        Keychain(service: AppConstants.Keychain.deviceService)
            .accessibility(.afterFirstUnlock)
    }

    func saveDeviceToken(_ token: String) throws {
        try Self.deviceKeychain.set(token, key: AppConstants.Keychain.deviceTokenKey)
    }

    func loadDeviceToken() -> String? {
        try? Self.deviceKeychain.get(AppConstants.Keychain.deviceTokenKey)
    }

    func deleteDeviceToken() {
        try? Self.deviceKeychain.remove(AppConstants.Keychain.deviceTokenKey)
    }

    // MARK: - Bulk wipe (logout)

    func wipeAll() {
        deleteCredentials()
        deleteDeviceToken()
    }
}
