import Foundation
import Combine

/// UserDefaults wrapper for non-sensitive preferences (§5.6 keys).
/// Credentials and tokens NEVER live here — see KeychainStore.
@MainActor
final class PreferencesStore: ObservableObject {

    static let shared = PreferencesStore()

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    // MARK: - API base URL

    var apiBaseURL: URL {
        get {
            let stored = defaults.string(forKey: AppConstants.Defaults.apiBaseURL) ?? AppConstants.defaultAPIBaseURL
            return URL(string: stored) ?? URL(string: AppConstants.defaultAPIBaseURL)!
        }
        set {
            defaults.set(newValue.absoluteString, forKey: AppConstants.Defaults.apiBaseURL)
            objectWillChange.send()
        }
    }

    // MARK: - Appearance / landing tab

    enum Appearance: String, CaseIterable, Identifiable {
        case system, light, dark
        var id: String { rawValue }
    }

    var appearance: Appearance {
        get { Appearance(rawValue: defaults.string(forKey: AppConstants.Defaults.appearance) ?? "system") ?? .system }
        set {
            defaults.set(newValue.rawValue, forKey: AppConstants.Defaults.appearance)
            objectWillChange.send()
        }
    }

    var defaultLandingTab: String {
        get { defaults.string(forKey: AppConstants.Defaults.defaultLandingTab) ?? "dashboard" }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.defaultLandingTab)
            objectWillChange.send()
        }
    }

    // MARK: - OCR defaults

    var defaultOCRModel: String {
        get { defaults.string(forKey: AppConstants.Defaults.defaultOCRModel) ?? "gemini-2.0-flash" }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.defaultOCRModel)
            objectWillChange.send()
        }
    }

    var defaultReceiptType: String {
        get { defaults.string(forKey: AppConstants.Defaults.defaultReceiptType) ?? "auto" }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.defaultReceiptType)
            objectWillChange.send()
        }
    }

    var autoRotateLandscape: Bool {
        get { defaults.object(forKey: AppConstants.Defaults.autoRotateLandscape) as? Bool ?? true }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.autoRotateLandscape)
            objectWillChange.send()
        }
    }

    var confirmReceiptBeforeSave: Bool {
        get { defaults.object(forKey: AppConstants.Defaults.confirmReceiptBeforeSave) as? Bool ?? true }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.confirmReceiptBeforeSave)
            objectWillChange.send()
        }
    }

    // MARK: - Notifications

    var shoppingNudgeTime: DateComponents {
        get {
            if let data = defaults.data(forKey: AppConstants.Defaults.shoppingNudgeTime),
               let comps = try? JSONDecoder().decode(DateComponents.self, from: data) {
                return comps
            }
            return DateComponents(hour: 9, minute: 30)
        }
        set {
            if let data = try? JSONEncoder().encode(newValue) {
                defaults.set(data, forKey: AppConstants.Defaults.shoppingNudgeTime)
                objectWillChange.send()
            }
        }
    }

    var nudgeMinThreshold: Int {
        get { defaults.integer(forKey: AppConstants.Defaults.nudgeMinThreshold).nonZeroOr(3) }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.nudgeMinThreshold)
            objectWillChange.send()
        }
    }

    /// Whether inventory threshold alerts fire (§5.6 list, R-04 corrected key).
    var inventoryAlertsEnabled: Bool {
        get { defaults.object(forKey: AppConstants.Defaults.inventoryAlertsEnabled) as? Bool ?? true }
        // veto patch §4 fix: write to the correct key, not nudgeMinThreshold
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.inventoryAlertsEnabled)
            objectWillChange.send()
        }
    }

    var weeklySummaryEnabled: Bool {
        get { defaults.bool(forKey: AppConstants.Defaults.weeklySummaryEnabled) }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.weeklySummaryEnabled)
            objectWillChange.send()
        }
    }

    // MARK: - UI prefs

    var menuBarIconEnabled: Bool {
        get { defaults.object(forKey: AppConstants.Defaults.menuBarIconEnabled) as? Bool ?? true }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.menuBarIconEnabled)
            objectWillChange.send()
        }
    }

    var globalShortcutEnabled: Bool {
        get { defaults.object(forKey: AppConstants.Defaults.globalShortcutEnabled) as? Bool ?? true }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.globalShortcutEnabled)
            objectWillChange.send()
        }
    }

    // MARK: - Onboarding / housekeeping

    var hasCompletedOnboarding: Bool {
        get { defaults.bool(forKey: AppConstants.Defaults.hasCompletedOnboarding) }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.hasCompletedOnboarding)
            objectWillChange.send()
        }
    }

    var lastForegroundRefresh: Date? {
        get { defaults.object(forKey: AppConstants.Defaults.lastForegroundRefresh) as? Date }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.lastForegroundRefresh)
        }
    }

    var accessibilityPromptShown: Bool {
        get { defaults.bool(forKey: AppConstants.Defaults.accessibilityPromptShown) }
        set {
            defaults.set(newValue, forKey: AppConstants.Defaults.accessibilityPromptShown)
        }
    }
}

private extension Int {
    func nonZeroOr(_ fallback: Int) -> Int { self == 0 ? fallback : self }
}
