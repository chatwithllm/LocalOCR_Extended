import SwiftUI

struct AIModelsPane: View {
    @StateObject private var household = HouseholdState.shared
    @EnvironmentObject private var appState: AppState

    var body: some View {
        Form {
            Section("Available models") {
                if household.aiModels.isEmpty {
                    Text("No models loaded — verify backend AI configuration.")
                        .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                } else {
                    ForEach(household.aiModels) { model in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(model.name).font(.appBody)
                                HStack(spacing: 6) {
                                    Text(model.provider).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                                    Badge(text: model.priceTier.capitalized, style: tierStyle(model.priceTier))
                                    if model.supportsVision { Badge(text: "Vision", style: .info) }
                                    if model.supportsPdf    { Badge(text: "PDF",    style: .info) }
                                }
                            }
                            Spacer()
                            Image(systemName: model.isEnabled ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(model.isEnabled ? DesignTokens.success : DesignTokens.tertiaryLabel)
                        }
                    }
                }
            }
            Section("Cost configuration") {
                Text("API keys live server-side (Fernet-encrypted). This pane is read-only; use the web app to add or revoke keys.")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task { await household.loadAIModels() }
    }

    private func tierStyle(_ tier: String) -> Badge.Style {
        switch tier {
        case "free":     return .success
        case "paid":     return .info
        case "premium":  return .warning
        default:         return .neutral
        }
    }
}
