import SwiftUI

/// NavigationSplitView with sidebar + per-tab detail content.
struct MainSplitView: View {
    @EnvironmentObject private var router: Router
    @State private var sidebarVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        NavigationSplitView(columnVisibility: $sidebarVisibility) {
            SidebarView(active: $router.activeTab)
                .navigationSplitViewColumnWidth(min: 200, ideal: 240, max: 340)
        } detail: {
            tabContent
        }
        .navigationSplitViewStyle(.balanced)
        .sheet(item: $router.activeSheet) { sheet in
            sheetView(for: sheet)
        }
    }

    @ViewBuilder
    private var tabContent: some View {
        switch router.activeTab {
        case .dashboard:    DashboardView()
        case .inventory:    InventoryView()
        case .products:     ProductsView()
        case .receipts:     ReceiptListView()
        case .shopping:     ShoppingListView()
        case .kitchen:      KitchenView()
        case .finance:      FinanceTabView()
        case .restaurant:   RestaurantsView()
        case .balances:     BalancesView()
        case .chat:         AIChatView()
        case .medications:  MedicationsView()
        }
    }

    @ViewBuilder
    private func sheetView(for sheet: Router.Sheet) -> some View {
        switch sheet {
        case .ocrUpload:        OCRUploadView()
        case .cashTransaction:  CashTransactionsView()
        case .shareQR:          ShareQRPlaceholderView()
        case .onboarding:       Text("Onboarding lands in Phase 7").padding(40).frame(width: 480, height: 360)
        }
    }
}

extension Router.TabDestination {
    var displayName: String {
        switch self {
        case .dashboard:    return "Dashboard"
        case .inventory:    return "Inventory"
        case .products:     return "Products"
        case .receipts:     return "Receipts"
        case .shopping:     return "Shopping"
        case .kitchen:      return "Kitchen"
        case .finance:      return "Finance"
        case .restaurant:   return "Restaurants"
        case .balances:     return "Balances"
        case .chat:         return "AI Chat"
        case .medications:  return "Medications"
        }
    }
    var systemImage: String {
        switch self {
        case .dashboard:    return "rectangle.grid.2x2"
        case .inventory:    return "tray.2"
        case .products:     return "barcode"
        case .receipts:     return "doc.text"
        case .shopping:     return "cart"
        case .kitchen:      return "refrigerator"
        case .finance:      return "chart.line.uptrend.xyaxis"
        case .restaurant:   return "fork.knife"
        case .balances:     return "dollarsign.arrow.circlepath"
        case .chat:         return "bubble.left.and.bubble.right"
        case .medications:  return "pills"
        }
    }
}

private struct ShareQRPlaceholderView: View {
    var body: some View {
        VStack(spacing: 16) {
            Text("Share").font(.appTitle2)
            QRCodeView(payload: "https://localocr.example/share/placeholder")
            Text("v1.1: server-issued share URL").font(.appCaption1).foregroundStyle(.secondary)
        }
        .padding(40)
        .frame(width: 360, height: 420)
    }
}

#Preview("MainSplitView") {
    MainSplitView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 1200, height: 800)
}
