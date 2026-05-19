import SwiftUI

/// SF Symbol + title + subtitle + optional CTA. Used across every list view's
/// no-data case (§3.7 empty state spec).
struct EmptyStateView: View {
    let systemImage: String
    let title: String
    var subtitle: String? = nil
    var ctaTitle: String? = nil
    var ctaAction: (() -> Void)? = nil

    var body: some View {
        VStack(spacing: DesignTokens.Spacing.space3) {
            Image(systemName: systemImage)
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(DesignTokens.tertiaryLabel)
                .accessibilityHidden(true)

            VStack(spacing: DesignTokens.Spacing.space1) {
                Text(title)
                    .font(.appTitle3)
                    .foregroundStyle(DesignTokens.label)
                if let subtitle {
                    Text(subtitle)
                        .font(.appSubheadline)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 320)
                }
            }

            if let ctaTitle, let ctaAction {
                Button(ctaTitle, action: ctaAction)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.regular)
                    .padding(.top, DesignTokens.Spacing.space2)
            }
        }
        .padding(DesignTokens.Spacing.space6)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(subtitle.map { "\(title). \($0)" } ?? title)
    }
}

#Preview("EmptyState / No CTA") {
    EmptyStateView(
        systemImage: "doc.text.magnifyingglass",
        title: "No receipts yet",
        subtitle: "Drop a receipt photo on the upload zone, or press ⌘N to start."
    )
    .frame(width: 480, height: 320)
}

#Preview("EmptyState / With CTA") {
    EmptyStateView(
        systemImage: "cart",
        title: "Your shopping list is empty",
        subtitle: "Add items manually, or auto-populate from low-stock inventory.",
        ctaTitle: "Auto-populate from low stock"
    ) {
        // preview action
    }
    .frame(width: 520, height: 360)
}
