import SwiftUI

struct ShoppingListView: View {
    @StateObject private var state = ShoppingState.shared
    @State private var newItemName = ""

    var body: some View {
        Group {
            if state.isLoading && state.items.isEmpty {
                loadingView
            } else if state.items.isEmpty {
                emptyStateView
            } else {
                listView
            }
        }
        .navigationTitle("Shopping List")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    Task { await state.populateFromLowStock() }
                } label: {
                    Label("From low stock", systemImage: "tray.and.arrow.down")
                }
                .help("Populate list from low-stock inventory")

                Button {
                    Task { await state.loadList() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Refresh shopping list")
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .task { await state.loadList() }
    }

    // MARK: - State subviews

    private var loadingView: some View {
        VStack(spacing: DesignTokens.Spacing.space2) {
            ForEach(0..<5, id: \.self) { _ in
                SkeletonView(width: nil, height: 44, cornerRadius: DesignTokens.Radius.card)
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }

    private var emptyStateView: some View {
        EmptyStateView(
            systemImage: "cart",
            title: "Your shopping list is empty",
            subtitle: "Add items manually below — or auto-populate from low-stock inventory.",
            ctaTitle: "Auto-populate from low stock"
        ) {
            Task { await state.populateFromLowStock() }
        }
    }

    private var listView: some View {
        VStack(spacing: 0) {
            summaryBar
            Divider()
            quickAddBar
            Divider()
            List {
                if !pendingItems.isEmpty {
                    Section {
                        ForEach(pendingItems) { item in
                            ShoppingRow(
                                item: item,
                                onToggle: { Task { await state.togglePurchased(id: item.id) } },
                                onDelete: { Task { await state.remove(id: item.id) } }
                            )
                        }
                    } header: {
                        sectionHeader("PENDING (\(pendingItems.count))")
                    }
                }
                if !purchasedItems.isEmpty {
                    Section {
                        ForEach(purchasedItems) { item in
                            ShoppingRow(
                                item: item,
                                onToggle: { Task { await state.togglePurchased(id: item.id) } },
                                onDelete: { Task { await state.remove(id: item.id) } }
                            )
                        }
                    } header: {
                        sectionHeader("PURCHASED (\(purchasedItems.count))")
                    }
                }
            }
            .listStyle(.plain)
        }
        .background(DesignTokens.background)
    }

    private var summaryBar: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            summaryChip(label: "Pending", value: "\(pendingItems.count)", color: DesignTokens.accent)
            summaryChip(label: "Purchased", value: "\(purchasedItems.count)", color: DesignTokens.success)
            Spacer()
            if let estTotal = estimatedTotal {
                Text(String(format: "Est. $%.2f", estTotal))
                    .font(.appMonoBody.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.space4)
        .padding(.vertical, DesignTokens.Spacing.space2)
        .background(DesignTokens.surface2)
    }

    private var quickAddBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "plus.circle")
                .foregroundStyle(DesignTokens.secondaryLabel)
            TextField("Add item…", text: $newItemName, onCommit: addItem)
                .textFieldStyle(.plain)
                .font(.appBody)
            if !newItemName.isEmpty {
                Button("Add", action: addItem)
                    .buttonStyle(PrimaryButtonStyle())
                    .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.space4)
        .padding(.vertical, DesignTokens.Spacing.space2)
        .background(DesignTokens.background)
    }

    private func summaryChip(label: String, value: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Text(value).font(.appMonoCaption.weight(.semibold)).foregroundStyle(color)
            Text(label).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(DesignTokens.secondaryLabel)
            .padding(.leading, 4)
            .padding(.top, DesignTokens.Spacing.space1)
    }

    private var pendingItems: [ShoppingListItem]   { state.items.filter(\.isPending) }
    private var purchasedItems: [ShoppingListItem] { state.items.filter { !$0.isPending } }

    private var estimatedTotal: Double? {
        let estimates = state.items.compactMap(\.manualEstimatedPrice)
        guard !estimates.isEmpty else { return nil }
        return estimates.reduce(0, +)
    }

    private func addItem() {
        let trimmed = newItemName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let snapshot = trimmed
        newItemName = ""
        Task { await state.add(productName: snapshot, quantity: 1) }
    }
}

private struct ShoppingRow: View {
    let item: ShoppingListItem
    let onToggle: () -> Void
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            Button(action: onToggle) {
                Image(systemName: item.isPending ? "circle" : "checkmark.circle.fill")
                    .foregroundStyle(item.isPending ? DesignTokens.tertiaryLabel : DesignTokens.success)
                    .font(.system(size: 17))
            }
            .buttonStyle(.borderless)
            .accessibilityLabel(item.isPending ? "Mark purchased" : "Mark pending")

            VStack(alignment: .leading, spacing: 2) {
                Text(item.productName)
                    .font(.appBody)
                    .foregroundStyle(item.isPending ? DesignTokens.label : DesignTokens.tertiaryLabel)
                    .strikethrough(!item.isPending, color: DesignTokens.tertiaryLabel)
                HStack(spacing: 6) {
                    if let source = item.source {
                        sourceBadge(source)
                    }
                    if let note = item.note, !note.isEmpty {
                        Text("• \(note)").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
            }
            Spacer()
            if item.quantity > 1 {
                Text("× \(String(format: "%.0f", item.quantity))")
                    .font(.appMonoBody)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
        .padding(.vertical, 4)
        .contextMenu {
            ContextMenuModifiers.shoppingListRow(
                onTogglePurchased: onToggle,
                onEditNote: {},
                onMove: {},
                onDelete: onDelete
            )
        }
    }

    @ViewBuilder
    private func sourceBadge(_ source: String) -> some View {
        switch source {
        case "low_stock":
            Badge(text: "Low stock", style: .warning)
        case "recommendation":
            Badge(text: "Recommended", style: .info)
        default:
            EmptyView()
        }
    }
}

#Preview("ShoppingList / Empty") {
    ShoppingListView().frame(width: 700, height: 600)
}
