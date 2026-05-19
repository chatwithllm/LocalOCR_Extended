import SwiftUI

/// NavigationSplitView with sidebar + content. Per §3.2 main window spec.
///
/// Phase 2: sidebar + placeholder detail content per tab. Real per-tab views
/// land in Phase 4 (Views/Dashboard, Views/Inventory, etc.).
struct MainSplitView: View {
    @EnvironmentObject private var router: Router
    @State private var sidebarVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        NavigationSplitView(columnVisibility: $sidebarVisibility) {
            SidebarView(active: $router.activeTab)
                .frame(minWidth: 180, idealWidth: 220, maxWidth: 340)
                .navigationSplitViewColumnWidth(min: 180, ideal: 220, max: 340)
        } detail: {
            TabPlaceholderView(tab: router.activeTab)
        }
        .navigationSplitViewStyle(.balanced)
    }
}

/// Phase 2 placeholder. Phase 4 wires each tab to its real view.
private struct TabPlaceholderView: View {
    let tab: Router.TabDestination

    var body: some View {
        VStack(spacing: DesignTokens.Spacing.space4) {
            Image(systemName: iconForTab(tab))
                .font(.system(size: 48, weight: .light))
                .foregroundStyle(DesignTokens.tertiaryLabel)
            Text(tab.displayName)
                .font(.appTitle1)
                .foregroundStyle(DesignTokens.label)
            Text("Phase 2 — sidebar wired. Tab content lands in Phase 4.")
                .font(.appBody)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DesignTokens.background)
        .navigationTitle(tab.displayName)
    }

    private func iconForTab(_ tab: Router.TabDestination) -> String {
        switch tab {
        case .dashboard:    return "rectangle.grid.2x2"
        case .inventory:    return "tray.2"
        case .receipts:     return "doc.text"
        case .shopping:     return "cart"
        case .finance:      return "chart.line.uptrend.xyaxis"
        case .restaurant:   return "fork.knife"
        case .chat:         return "bubble.left.and.bubble.right"
        case .medications:  return "pills"
        }
    }
}

extension Router.TabDestination {
    var displayName: String {
        switch self {
        case .dashboard:    return "Dashboard"
        case .inventory:    return "Inventory"
        case .receipts:     return "Receipts"
        case .shopping:     return "Shopping"
        case .finance:      return "Finance"
        case .restaurant:   return "Restaurants"
        case .chat:         return "AI Chat"
        case .medications:  return "Medications"
        }
    }

    var systemImage: String {
        switch self {
        case .dashboard:    return "rectangle.grid.2x2"
        case .inventory:    return "tray.2"
        case .receipts:     return "doc.text"
        case .shopping:     return "cart"
        case .finance:      return "chart.line.uptrend.xyaxis"
        case .restaurant:   return "fork.knife"
        case .chat:         return "bubble.left.and.bubble.right"
        case .medications:  return "pills"
        }
    }
}

#Preview("MainSplitView") {
    MainSplitView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 1200, height: 800)
}
