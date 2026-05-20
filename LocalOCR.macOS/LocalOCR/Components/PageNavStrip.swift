import SwiftUI

/// Bottom prev/next navigation strip used at the foot of every workspace page.
/// Mirrors the web's "START / NEXT" footer.
struct PageNavStrip: View {
    @EnvironmentObject private var router: Router

    private let order: [Router.TabDestination] = [
        .dashboard, .inventory, .products, .receipts, .shopping, .kitchen, .finance, .restaurant, .chat, .medications
    ]

    var body: some View {
        let prev = previousTab
        let next = nextTab
        return HStack(spacing: 0) {
            navCell(label: "START",
                    title: prev?.displayName ?? "No earlier page",
                    systemImage: "arrow.left",
                    alignment: .leading,
                    isActive: prev != nil) {
                if let prev { router.activeTab = prev }
            }
            Divider().frame(width: 1, height: 36)
            navCell(label: "NEXT",
                    title: next?.displayName ?? "No next page",
                    systemImage: "arrow.right",
                    alignment: .trailing,
                    isActive: next != nil,
                    iconTrailing: true) {
                if let next { router.activeTab = next }
            }
        }
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .stroke(DesignTokens.border, lineWidth: 0.5)
        )
    }

    private var previousTab: Router.TabDestination? {
        guard let idx = order.firstIndex(of: router.activeTab), idx > 0 else { return nil }
        return order[idx - 1]
    }

    private var nextTab: Router.TabDestination? {
        guard let idx = order.firstIndex(of: router.activeTab), idx < order.count - 1 else { return nil }
        return order[idx + 1]
    }

    private func navCell(
        label: String,
        title: String,
        systemImage: String,
        alignment: HorizontalAlignment,
        isActive: Bool,
        iconTrailing: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: DesignTokens.Spacing.space3) {
                if !iconTrailing {
                    Image(systemName: systemImage)
                        .foregroundStyle(isActive ? DesignTokens.accent : DesignTokens.tertiaryLabel)
                }
                VStack(alignment: alignment == .leading ? .leading : .trailing, spacing: 2) {
                    Text(label)
                        .font(.appCaption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                    Text(title)
                        .font(.appBody.weight(.medium))
                        .foregroundStyle(isActive ? DesignTokens.label : DesignTokens.secondaryLabel)
                }
                .frame(maxWidth: .infinity, alignment: alignment == .leading ? .leading : .trailing)
                if iconTrailing {
                    Image(systemName: systemImage)
                        .foregroundStyle(isActive ? DesignTokens.accent : DesignTokens.tertiaryLabel)
                }
            }
            .padding(.horizontal, DesignTokens.Spacing.space4)
            .padding(.vertical, DesignTokens.Spacing.space2)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!isActive)
    }
}

#Preview("PageNavStrip") {
    PageNavStrip()
        .environmentObject(Router.shared)
        .padding(20)
        .frame(width: 800)
}
