import SwiftUI

struct InventoryView: View {
    @StateObject private var state = InventoryState.shared
    @StateObject private var shopping = ShoppingState.shared

    @State private var search = ""
    @State private var selectedCategory: String? = nil
    @State private var lowStockOnly = false
    @State private var selectedItemId: Int? = nil

    var body: some View {
        HSplitView {
            categoriesPanel
                .frame(minWidth: 180, idealWidth: 220, maxWidth: 320)
            itemsPanel
                .frame(minWidth: 480)
        }
        .navigationTitle("Inventory")
        .searchable(text: $search, placement: .toolbar, prompt: "Search inventory")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Toggle(isOn: $lowStockOnly) {
                    Label("Low stock", systemImage: "exclamationmark.circle")
                }
                .toggleStyle(.button)
            }
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await state.loadInventory() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
        }
        .task { await state.loadInventory() }
    }

    private var categoriesPanel: some View {
        List(selection: $selectedCategory) {
            Section("Categories") {
                Text("All")
                    .tag(String?.none)
                ForEach(state.categories, id: \.self) { cat in
                    Text(cat).tag(String?.some(cat))
                }
            }
        }
        .listStyle(.sidebar)
    }

    private var itemsPanel: some View {
        Group {
            if state.isLoading && state.items.isEmpty {
                VStack(spacing: DesignTokens.Spacing.space2) {
                    SkeletonView(width: nil, height: 56, cornerRadius: DesignTokens.Radius.card)
                    SkeletonView(width: nil, height: 56, cornerRadius: DesignTokens.Radius.card)
                    SkeletonView(width: nil, height: 56, cornerRadius: DesignTokens.Radius.card)
                }
                .padding(DesignTokens.Spacing.space4)
            } else if filtered.isEmpty {
                EmptyStateView(
                    systemImage: "tray",
                    title: state.items.isEmpty ? "No inventory yet" : "No matches",
                    subtitle: state.items.isEmpty
                        ? "Upload receipts to start tracking inventory."
                        : "Try clearing search or the low-stock filter."
                )
            } else {
                List(filtered, selection: $selectedItemId) { item in
                    InventoryRow(
                        item: item,
                        onAddToShopping: { Task { await addToShopping(item) } },
                        onAdjust: { delta in Task { await state.adjustQuantity(id: item.id, delta: delta) } },
                        onMarkLow: { Task { await state.markLowStock(id: item.id) } }
                    )
                    .tag(item.id as Int?)
                }
                .listStyle(.plain)
            }
        }
        .background(DesignTokens.background)
    }

    private var filtered: [InventoryItem] {
        state.items.filter { item in
            if lowStockOnly && !item.isLowStock { return false }
            if let cat = selectedCategory {
                if item.product?.category != cat { return false }
            }
            if !search.isEmpty {
                let n = item.product?.displayName ?? item.product?.name ?? ""
                if n.localizedCaseInsensitiveContains(search) == false { return false }
            }
            return true
        }
    }

    private func addToShopping(_ item: InventoryItem) async {
        let name = item.product?.displayName ?? item.product?.name ?? "Item #\(item.productId)"
        await shopping.add(productName: name, quantity: 1, source: "manual", productId: item.productId)
    }
}

private struct InventoryRow: View {
    let item: InventoryItem
    let onAddToShopping: () -> Void
    let onAdjust: (Double) -> Void
    let onMarkLow: () -> Void

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(item.product?.displayName ?? item.product?.name ?? "Item #\(item.productId)")
                        .font(.appBody)
                    if item.isLowStock {
                        LowStockPill(severity: item.quantity <= 0 ? .critical : .low)
                    }
                }
                HStack(spacing: 6) {
                    if let cat = item.product?.category {
                        Text(cat).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    if let loc = item.location {
                        Text("• \(loc)").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
            }
            Spacer()
            HStack(spacing: 4) {
                Button { onAdjust(-1) } label: { Image(systemName: "minus") }
                    .keyboardShortcut(.downArrow, modifiers: .option)
                Text(String(format: "%.0f", item.quantity))
                    .font(.appMonoBody)
                    .frame(minWidth: 32)
                Button { onAdjust(+1) } label: { Image(systemName: "plus") }
                    .keyboardShortcut(.upArrow, modifiers: .option)
            }
            .buttonStyle(.borderless)
            .foregroundStyle(DesignTokens.secondaryLabel)
        }
        .padding(.vertical, 4)
        .contextMenu {
            ContextMenuModifiers.inventoryRow(
                onAddToShoppingList: onAddToShopping,
                onAdjustQuantity: { delta in onAdjust(Double(delta)) },
                onMarkLowStock: onMarkLow,
                onEdit: {},
                onDelete: {}
            )
        }
    }
}

#Preview("InventoryView") {
    InventoryView().frame(width: 900, height: 600)
}
