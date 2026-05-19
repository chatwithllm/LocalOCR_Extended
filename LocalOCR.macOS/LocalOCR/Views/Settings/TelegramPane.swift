import SwiftUI

struct TelegramPane: View {
    var body: some View {
        Form {
            Section("Telegram bot") {
                Text("The Telegram bot is configured server-side. Use the web app's Telegram pane to:")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                Text("• set the bot token (Fernet-encrypted server-side)")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                Text("• view the webhook URL and rotate it")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                Text("• adjust the shopping nudge time (admin)")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
            Section("Local notifications mirror") {
                Text("This Mac receives shopping nudges via macOS Notification Center independently of Telegram. Configure timing in the Notifications pane.")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
    }
}
