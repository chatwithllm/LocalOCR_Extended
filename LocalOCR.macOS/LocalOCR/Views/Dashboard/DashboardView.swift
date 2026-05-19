import SwiftUI

struct DashboardView: View {
    @StateObject private var inventory = InventoryState.shared
    @StateObject private var shopping = ShoppingState.shared
    @StateObject private var finance = FinanceState.shared
    @EnvironmentObject private var router: Router

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space5) {
                Text("Dashboard")
                    .font(.appLargeTitle)
                    .foregroundStyle(DesignTokens.label)

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: DesignTokens.Spacing.space4)], alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                    lowStockTile
                    pendingShoppingTile
                    unpaidBillsTile
                    monthlySpendTile
                }

                DropZone(
                    title: "Drop a receipt to upload",
                    subtitle: "JPEG, PNG, HEIC, or PDF",
                    systemImage: "tray.and.arrow.down"
                ) { urls in
                    if let first = urls.first {
                        router.activeSheet = .ocrUpload
                        Task {
                            await ReceiptsState.shared.uploadReceipt(
                                fileURL: first,
                                receiptType: PreferencesStore.shared.defaultReceiptType,
                                modelId: nil
                            )
                        }
                    }
                }
                .padding(.top, DesignTokens.Spacing.space4)
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .background(DesignTokens.background)
        .navigationTitle("Dashboard")
        .task {
            async let _ = inventory.loadInventory()
            async let _ = shopping.loadList()
            async let _ = finance.loadBills()
        }
    }

    private var lowStockTile: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("Low stock").font(.appHeadline).foregroundStyle(DesignTokens.secondaryLabel)
                Text("\(inventory.lowStockItems.count)")
                    .font(.appLargeTitle)
                    .foregroundStyle(inventory.lowStockItems.isEmpty ? DesignTokens.label : DesignTokens.warning)
                Text(inventory.lowStockItems.isEmpty ? "All stocked" : "items below threshold")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
    }

    private var pendingShoppingTile: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("Shopping list").font(.appHeadline).foregroundStyle(DesignTokens.secondaryLabel)
                Text("\(shopping.pendingCount)")
                    .font(.appLargeTitle)
                    .foregroundStyle(DesignTokens.label)
                Text("pending items").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
    }

    private var unpaidBillsTile: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("Bills due").font(.appHeadline).foregroundStyle(DesignTokens.secondaryLabel)
                Text("\(finance.bills.filter { $0.paymentStatus != "paid" }.count)")
                    .font(.appLargeTitle)
                    .foregroundStyle(DesignTokens.label)
                Text("unpaid this month").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
    }

    private var monthlySpendTile: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("Monthly spend").font(.appHeadline).foregroundStyle(DesignTokens.secondaryLabel)
                Text(formatCurrency(finance.spending?.categories.reduce(0) { $0 + $1.total } ?? 0))
                    .font(.appLargeTitle).foregroundStyle(DesignTokens.label)
                Text(finance.spending?.periodLabel ?? "—").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
    }

    private func formatCurrency(_ amount: Double) -> String {
        let fmt = NumberFormatter()
        fmt.numberStyle = .currency
        fmt.maximumFractionDigits = 0
        return fmt.string(from: NSNumber(value: amount)) ?? "$\(Int(amount))"
    }
}

#Preview("Dashboard") {
    DashboardView()
        .environmentObject(Router.shared)
        .frame(width: 900, height: 700)
}
