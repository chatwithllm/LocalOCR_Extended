import SwiftUI
import UserNotifications

struct NotificationsPane: View {
    @StateObject private var prefs = PreferencesStore.shared

    @State private var permissionStatus: UNAuthorizationStatus = .notDetermined
    @State private var nudgeTime = Date()
    @State private var nudgeMinThreshold = 3
    @State private var inventoryAlerts = true
    @State private var weeklySummary = false

    var body: some View {
        Form {
            Section("Permission") {
                HStack {
                    Image(systemName: permissionIcon)
                        .foregroundStyle(permissionColor)
                    Text(permissionLabel)
                    Spacer()
                    if permissionStatus == .denied {
                        Button("Open System Settings") {
                            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.notifications") {
                                NSWorkspace.shared.open(url)
                            }
                        }
                        .buttonStyle(GhostButtonStyle())
                    } else if permissionStatus == .notDetermined {
                        Button("Request Permission") {
                            Task {
                                await NotificationManager.shared.requestAuthorizationIfNeeded()
                                await refreshStatus()
                            }
                        }
                        .buttonStyle(SecondaryButtonStyle())
                    }
                }
            }

            Section("Shopping nudge") {
                Toggle("Enable", isOn: $inventoryAlerts)
                    .onChange(of: inventoryAlerts) { enabled in
                        prefs.inventoryAlertsEnabled = enabled
                        Task { await NotificationManager.shared.scheduleShoppingNudge() }
                    }
                DatePicker("Time", selection: $nudgeTime, displayedComponents: .hourAndMinute)
                    .onChange(of: nudgeTime) { newDate in
                        prefs.shoppingNudgeTime = Calendar.current.dateComponents([.hour, .minute], from: newDate)
                        Task { await NotificationManager.shared.scheduleShoppingNudge() }
                    }
                Stepper(value: $nudgeMinThreshold, in: 1...20) {
                    Text("Nudge when ≥ \(nudgeMinThreshold) item\(nudgeMinThreshold == 1 ? "" : "s") low")
                }
                .onChange(of: nudgeMinThreshold) { newValue in
                    prefs.nudgeMinThreshold = newValue
                    Task { await NotificationManager.shared.scheduleShoppingNudge() }
                }
            }

            Section("Other") {
                Toggle("Weekly spending summary", isOn: $weeklySummary)
                    .onChange(of: weeklySummary) { prefs.weeklySummaryEnabled = $0 }
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task {
            await refreshStatus()
            let comps = prefs.shoppingNudgeTime
            nudgeTime = Calendar.current.date(from: comps) ?? Date()
            nudgeMinThreshold = prefs.nudgeMinThreshold
            inventoryAlerts = prefs.inventoryAlertsEnabled
            weeklySummary = prefs.weeklySummaryEnabled
        }
    }

    private func refreshStatus() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        permissionStatus = settings.authorizationStatus
    }

    private var permissionIcon: String {
        switch permissionStatus {
        case .authorized, .provisional, .ephemeral: return "checkmark.circle.fill"
        case .denied:                                return "xmark.octagon.fill"
        default:                                     return "questionmark.circle"
        }
    }

    private var permissionColor: Color {
        switch permissionStatus {
        case .authorized, .provisional, .ephemeral: return DesignTokens.success
        case .denied:                                return DesignTokens.error
        default:                                     return DesignTokens.warning
        }
    }

    private var permissionLabel: String {
        switch permissionStatus {
        case .authorized:    return "Allowed"
        case .provisional:   return "Provisional"
        case .ephemeral:     return "Ephemeral"
        case .denied:        return "Denied — open System Settings to enable"
        case .notDetermined: return "Not requested yet"
        @unknown default:    return "Unknown"
        }
    }
}
