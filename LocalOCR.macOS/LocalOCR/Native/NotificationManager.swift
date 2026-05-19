import Foundation
import AppKit
import UserNotifications
import os.log

/// UNUserNotificationCenter wrapper (§4.6 Integration 2).
@MainActor
final class NotificationManager: NSObject {

    static let shared = NotificationManager()

    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "notifications")

    private override init() {
        super.init()
        UNUserNotificationCenter.current().delegate = self
        registerCategories()
    }

    func requestAuthorizationIfNeeded() async {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        guard settings.authorizationStatus == .notDetermined else { return }

        // Unsigned macOS builds cannot request notification permission — the
        // system rejects the call with UNError code 1 ('notificationsNotAllowed')
        // BEFORE showing the user a prompt, so authorizationStatus stays
        // .notDetermined forever. Without a guard we'd retry on every launch
        // and spam Console.app with red error lines. Track the rejection in
        // UserDefaults and skip subsequent attempts.
        let rejectionKey = "LocalOCR.notificationRequestRejected"
        if UserDefaults.standard.bool(forKey: rejectionKey) {
            logger.info("notification request previously rejected — skipping")
            return
        }

        do {
            _ = try await center.requestAuthorization(options: [.alert, .sound, .badge])
            // Cleared by a successful prompt — clear any stale rejection flag.
            UserDefaults.standard.removeObject(forKey: rejectionKey)
        } catch let error as NSError {
            // UNError.notificationsNotAllowed = 1 — expected for unsigned local
            // builds. Log at .info, latch the rejection so we don't retry, and
            // surface it as a one-time hint instead of a recurring red error.
            if error.domain == "UNErrorDomain", error.code == 1 {
                UserDefaults.standard.set(true, forKey: rejectionKey)
                logger.info("notifications unavailable (unsigned build or system-blocked) — silenced for future launches")
                return
            }
            logger.warning("requestAuthorization failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func scheduleShoppingNudge() async {
        let prefs = PreferencesStore.shared
        let center = UNUserNotificationCenter.current()

        // Always clear any previously-scheduled nudge first.
        let identifier = "shoppingNudge.daily"
        center.removePendingNotificationRequests(withIdentifiers: [identifier])

        guard prefs.inventoryAlertsEnabled else { return }

        // Only schedule when low-stock count meets the threshold.
        let count = AppState.shared.lowStockCount
        guard count >= prefs.nudgeMinThreshold else { return }

        let content = UNMutableNotificationContent()
        content.title = "Shopping nudge"
        content.body = "\(count) item\(count == 1 ? "" : "s") below threshold. Open your shopping list."
        content.sound = .default
        content.categoryIdentifier = AppConstants.NotificationCategory.shoppingNudge

        var dateComps = prefs.shoppingNudgeTime
        dateComps.second = 0
        let trigger = UNCalendarNotificationTrigger(dateMatching: dateComps, repeats: true)
        let request = UNNotificationRequest(identifier: identifier, content: content, trigger: trigger)

        do {
            try await center.add(request)
            logger.info("scheduled shopping nudge at \(dateComps.hour ?? -1):\(dateComps.minute ?? -1)")
        } catch {
            logger.error("schedule failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func cancelAll() {
        UNUserNotificationCenter.current().removeAllPendingNotificationRequests()
        UNUserNotificationCenter.current().removeAllDeliveredNotifications()
    }

    private func registerCategories() {
        let view = UNNotificationAction(
            identifier: AppConstants.NotificationAction.viewList,
            title: "View List",
            options: [.foreground]
        )
        let dismiss = UNNotificationAction(
            identifier: AppConstants.NotificationAction.dismiss,
            title: "Dismiss",
            options: [.destructive]
        )
        let nudge = UNNotificationCategory(
            identifier: AppConstants.NotificationCategory.shoppingNudge,
            actions: [view, dismiss],
            intentIdentifiers: [],
            options: []
        )
        UNUserNotificationCenter.current().setNotificationCategories([nudge])
    }
}

extension NotificationManager: UNUserNotificationCenterDelegate {
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let actionId = response.actionIdentifier
        Task { @MainActor in
            switch actionId {
            case AppConstants.NotificationAction.viewList,
                 UNNotificationDefaultActionIdentifier:
                Router.shared.activeTab = .shopping
                NSApp.activate(ignoringOtherApps: true)
            default:
                break
            }
            completionHandler()
        }
    }
}
