import Foundation

/// Typed endpoint cases — Phase 3 covers auth + me only. Per-domain endpoint
/// groups (Inventory, Receipts, Shopping, Finance, etc.) land in Phase 4 in this
/// same file.
///
/// Each enum exposes `path` (String) and `method` (HTTPMethod). The APIClient
/// is invoked at call sites; this file is the source-of-truth for path strings.
enum AuthEndpoint {
    case me
    case login(email: String, password: String)
    case logout
    case devicePairingStart(deviceName: String, scope: String)
    case devicePairingStatus(token: String)
    case oauthGoogleStart
    case oauthGoogleCallback(state: String, code: String)

    var path: String {
        switch self {
        case .me:                                  return "/auth/me"
        case .login:                               return "/auth/login"
        case .logout:                              return "/auth/logout"
        case .devicePairingStart:                  return "/auth/device-pairing/start"
        case .devicePairingStatus(let token):      return "/auth/device-pairing/status/\(token)"
        case .oauthGoogleStart:                    return "/auth/google/start"
        case .oauthGoogleCallback:                 return "/auth/google/callback"
        }
    }

    var method: HTTPMethod {
        switch self {
        case .me, .devicePairingStatus, .oauthGoogleStart, .oauthGoogleCallback:
            return .get
        case .login, .logout, .devicePairingStart:
            return .post
        }
    }

    /// Whether the endpoint mutates state — used by DemoModeGate enforcement.
    var isMutating: Bool {
        switch self {
        case .me, .devicePairingStatus, .oauthGoogleStart, .oauthGoogleCallback:
            return false
        case .login, .logout, .devicePairingStart:
            return true
        }
    }
}

// MARK: - Request bodies

struct LoginRequestBody: Encodable {
    let email: String
    let password: String
}

struct DevicePairingStartBody: Encodable {
    let deviceName: String
    let scope: String
}

// MARK: - Response shapes

struct DevicePairingStartResponse: Codable, Equatable {
    let pairingToken: String
    let status: String   // "pending" | "approved" | "rejected"
}

struct DevicePairingStatusResponse: Codable, Equatable {
    let status: String   // "pending" | "approved" | "rejected" | "expired"
    let token: String?   // present only when status == "approved"
}
