import SwiftUI

/// AI model selector. Used on OCR Upload and AI Chat views.
/// Lightweight DTO here; real `AIModelConfig` Codable model lands in Phase 3.
struct ModelPicker: View {
    struct ModelOption: Identifiable, Hashable {
        let id: Int
        let name: String
        let provider: String
        let priceTier: String     // "free" | "paid" | "premium"
        let supportsVision: Bool
        let supportsPdf: Bool
    }

    let options: [ModelOption]
    @Binding var selectedId: Int?
    var requiresVision: Bool = false
    var requiresPdf: Bool = false
    var label: String = "AI Model"

    private var filtered: [ModelOption] {
        options.filter { opt in
            (!requiresVision || opt.supportsVision) &&
            (!requiresPdf || opt.supportsPdf)
        }
    }

    var body: some View {
        Picker(label, selection: $selectedId) {
            ForEach(filtered) { m in
                HStack(spacing: 4) {
                    Text(m.name)
                    Spacer(minLength: 0)
                    Badge(text: m.priceTier.capitalized, style: tierStyle(m.priceTier))
                }
                .tag(Int?.some(m.id))
            }
        }
        .pickerStyle(.menu)
        .accessibilityLabel(label)
        .accessibilityHint(filtered.isEmpty ? "No compatible models" : "Select an AI model")
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

#Preview("ModelPicker") {
    struct Wrapper: View {
        @State var selected: Int? = 2
        var body: some View {
            Card {
                ModelPicker(
                    options: [
                        .init(id: 1, name: "gemini-2.0-flash",  provider: "google", priceTier: "free",    supportsVision: true,  supportsPdf: true),
                        .init(id: 2, name: "gpt-4o-mini",       provider: "openai", priceTier: "paid",    supportsVision: true,  supportsPdf: true),
                        .init(id: 3, name: "claude-haiku-4.5",  provider: "anthropic", priceTier: "paid", supportsVision: true,  supportsPdf: true),
                        .init(id: 4, name: "ollama-llava",      provider: "ollama", priceTier: "free",    supportsVision: true,  supportsPdf: false)
                    ],
                    selectedId: $selected,
                    requiresVision: true
                )
            }
            .padding(40)
            .frame(width: 360)
        }
    }
    return Wrapper()
}
