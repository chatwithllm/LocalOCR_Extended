import SwiftUI

// Phase 1: compile-only stubs. Full implementations land in Phase 2 (§5.8, §5.1).

/// Standard primary action — `.borderedProminent` tinted with DesignTokens.accent.
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
    }
}

/// Standard secondary action — `.bordered` with default tint.
struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
    }
}

/// Destructive action — `.borderedProminent` tinted red.
struct DestructiveButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
    }
}

/// Ghost / link-style action — no border, accent text only.
struct GhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
    }
}
