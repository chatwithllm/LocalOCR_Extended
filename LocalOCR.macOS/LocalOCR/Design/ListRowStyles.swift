import SwiftUI

/// Standardized list row appearance for sidebars and main lists. Hover highlight
/// + focus ring + selection-aware background.

extension View {
    /// Standard 44pt list row.
    func appListRow44(isSelected: Bool = false) -> some View {
        modifier(AppListRowModifier(height: 44, isSelected: isSelected))
    }

    /// Larger 52pt list row for inventory and receipts.
    func appListRow52(isSelected: Bool = false) -> some View {
        modifier(AppListRowModifier(height: 52, isSelected: isSelected))
    }
}

private struct AppListRowModifier: ViewModifier {
    let height: CGFloat
    let isSelected: Bool

    @State private var hovering = false

    func body(content: Content) -> some View {
        content
            .padding(.horizontal, DesignTokens.Spacing.space3)
            .frame(height: height)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(background)
            .contentShape(Rectangle())
            .onHover { hovering = $0 }
    }

    private var background: some View {
        let color: Color = {
            if isSelected { return DesignTokens.accentDim }
            if hovering   { return DesignTokens.receiptHover }
            return .clear
        }()
        return color
    }
}

#Preview("ListRowStyles") {
    VStack(spacing: 0) {
        HStack { Text("Default row") }.appListRow44()
        HStack { Text("Hovered (simulated)") }.appListRow44()
        HStack { Text("Selected row") }.appListRow44(isSelected: true)
        Divider()
        HStack { Text("Larger 52pt row") }.appListRow52()
        HStack { Text("Larger selected") }.appListRow52(isSelected: true)
    }
    .padding()
    .frame(width: 360)
}
