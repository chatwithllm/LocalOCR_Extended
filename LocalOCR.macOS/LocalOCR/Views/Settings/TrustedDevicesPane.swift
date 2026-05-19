import SwiftUI

struct TrustedDevicesPane: View {
    var body: some View {
        Form {
            Section("This device") {
                if KeychainStore().loadDeviceToken() != nil {
                    Label("Paired", systemImage: "checkmark.shield.fill")
                        .foregroundStyle(DesignTokens.success)
                    Text("This Mac authenticates via a trusted-device token. The token is stored in Keychain and sent as X-Trusted-Device-Token on every request.")
                        .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    Button("Remove this device") {
                        KeychainStore().deleteDeviceToken()
                    }
                    .buttonStyle(DestructiveButtonStyle())
                } else {
                    Label("Not paired", systemImage: "exclamationmark.shield")
                        .foregroundStyle(DesignTokens.warning)
                    Text("Device pairing runs automatically after first login. If the server returns a 401, the app re-authenticates with stored credentials, then re-attempts pairing.")
                        .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                }
            }

            Section("All household devices") {
                Text("Manage other paired devices from the web app's Trusted Devices page — admin-only.")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
    }
}
