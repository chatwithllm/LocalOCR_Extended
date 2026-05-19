import Foundation
import ServiceManagement
import os.log

/// Auto-launch-at-login toggle via SMAppService (macOS 13+) per veto §3 R-01.
/// Replaces the deprecated SMLoginItemSetEnabled API.
@available(macOS 13.0, *)
@MainActor
final class LoginItemController {

    static let shared = LoginItemController()

    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "login-item")

    private init() {}

    var isRegistered: Bool {
        SMAppService.mainApp.status == .enabled
    }

    func register() {
        do {
            try SMAppService.mainApp.register()
            logger.info("Registered for auto-launch at login")
        } catch {
            logger.error("Register failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func unregister() {
        do {
            try SMAppService.mainApp.unregister()
            logger.info("Unregistered from auto-launch")
        } catch {
            logger.error("Unregister failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func set(enabled: Bool) {
        enabled ? register() : unregister()
    }
}
