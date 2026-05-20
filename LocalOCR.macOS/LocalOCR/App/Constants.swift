import Foundation

/// Top-level constants for LocalOCR macOS.
///
/// UserDefaults key strings, URL scheme hosts, notification category IDs,
/// API path constants that are not view-local.
enum AppConstants {

    // MARK: - URL scheme

    /// Custom URL scheme registered in Info.plist (CFBundleURLTypes).
    static let urlScheme = "localocr"

    /// Hosts the Router pattern-matches in `Router.handleURL(_:)`.
    enum URLHost {
        static let receipt = "receipt"
        static let upload = "upload"
        static let shopping = "shopping"
        static let inventory = "inventory"
        static let kitchen = "kitchen"
        static let products = "products"
        static let oauthCallback = "oauth"
        static let plaidCallback = "plaid-callback"
    }

    // MARK: - Keychain services (per VETO_RESOLUTION_PATCH §2)

    enum Keychain {
        /// Service for user credentials (silent re-auth on session expiry).
        static let credentialsService = "com.localocr.extended"
        static let credentialsKey = "localocr.credentials"

        /// Service for trusted device token (long-lived native auth).
        static let deviceService = "com.localocr.extended.device"
        static let deviceTokenKey = "localocr.device_token"
    }

    // MARK: - UserDefaults keys

    enum Defaults {
        static let apiBaseURL = "LocalOCR.apiBaseURL"
        static let appearance = "LocalOCR.appearance"
        static let defaultLandingTab = "LocalOCR.defaultLandingTab"
        static let defaultOCRModel = "LocalOCR.defaultOCRModel"
        static let autoRotateLandscape = "LocalOCR.autoRotateLandscape"
        static let defaultReceiptType = "LocalOCR.defaultReceiptType"
        static let confirmReceiptBeforeSave = "LocalOCR.confirmReceiptBeforeSave"
        static let shoppingNudgeTime = "LocalOCR.shoppingNudgeTime"
        static let nudgeMinThreshold = "LocalOCR.nudgeMinThreshold"
        static let inventoryAlertsEnabled = "LocalOCR.inventoryAlertsEnabled"
        static let weeklySummaryEnabled = "LocalOCR.weeklySummaryEnabled"
        static let menuBarIconEnabled = "LocalOCR.menuBarIconEnabled"
        static let globalShortcutEnabled = "LocalOCR.globalShortcutEnabled"
        static let openReceiptInspectors = "LocalOCR.openReceiptInspectors"
        static let spotlightLastIndexed = "LocalOCR.spotlightLastIndexed"
        static let accessibilityPromptShown = "LocalOCR.accessibilityPromptShown"
        static let lastForegroundRefresh = "LocalOCR.lastForegroundRefresh"
        static let hasCompletedOnboarding = "LocalOCR.hasCompletedOnboarding"
    }

    // MARK: - Notification categories / names

    enum NotificationCategory {
        static let shoppingNudge = "SHOPPING_NUDGE"
        static let plaidLoginRequired = "PLAID_LOGIN_REQUIRED"
    }

    enum NotificationAction {
        static let viewList = "VIEW_LIST"
        static let dismiss = "DISMISS"
    }

    // MARK: - Defaults

    static let defaultAPIBaseURL = "http://localhost:8090"
    static let foregroundRefreshMinIntervalSeconds: TimeInterval = 60
}

extension Notification.Name {
    /// Posted by `GlobalShortcutManager` when ⌃⌘R fires.
    static let globalShortcutReceiptUpload = Notification.Name("LocalOCR.globalShortcut.receiptUpload")

    /// Posted by `AuthInterceptor` when a 401 is observed.
    static let authSessionExpired = Notification.Name("LocalOCR.auth.sessionExpired")
}
