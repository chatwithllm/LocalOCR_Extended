import SwiftUI

struct ShoppingListView: View {
    @StateObject private var state = ShoppingState.shared
    @State private var newItemName = ""

    var body: some View {
        VStack(spacing: 0) {
            quickAddBar
            Divider()
            content
        }
        .navigationTitle("Shopping List")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await state.populateFromLowStock() }
                } label: {
                    Label("From low stock", systemImage: "exclamationmark.circle")
                }
            }
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await state.loadList() }
                } label: { Label("Refresh", systemImage: "arrow.clockwise") }
            }
        }
        .task { await state.loadList() }
    }

    private var quickAddBar: some View {
        HStack(spacing: 8) {
            TextField("Add item…", text: $newItemName, onCommit: addItem)
                .textFieldStyle(.roundedBorder)
            Button("Add", action: addItem)
                .buttonStyle(PrimaryButtonStyle())
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(newItemName.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(DesignTokens.Spacing.space3)
        .background(DesignTokens.surface2)
    }

    private var content: some View {
        Group {
            if state.isLoading && state.items.isEmpty {
                ProgressView().controlSize(.regular).padding()
            } else if state.items.isEmpty {
                EmptyStateView(
                    systemImage: "cart",
                    title: "Your shopping list is empty",
                    subtitle: "Add items manually, or auto-populate from low-stock inventory.",
                    ctaTitle: "Auto-populate from low stock"
                ) {
                    Task { await state.populateFromLowStock() }
                }
            } else {
                List {
                    ForEach(state.items) { item in
                        ShoppingRow(
                            item: item,
                            onToggle: { Task { await state.togglePurchased(id: item.id) } },
                            onDelete: { Task { await state.remove(id: item.id) } }
                        )
                    }
                }
                .listStyle(.plain)
            }
        }
        .background(DesignTokens.background)
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
            .keyboardShortcut(.space, modifiers: [])

            VStack(alignment: .leading, spacing: 2) {
                Text(item.productName)
                    .font(.appBody)
                    .foregroundStyle(item.isPending ? DesignTokens.label : DesignTokens.tertiaryLabel)
                    .strikethrough(!item.isPending, color: DesignTokens.tertiaryLabel)
                if let source = item.source {
                    Text(sourceLabel(source))
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
            Spacer()
            Text(String(format: "%.0f", item.quantity))
                .font(.appMonoBody)
                .foregroundStyle(DesignTokens.secondaryLabel)
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

    private func sourceLabel(_ source: String) -> String {
        switch source {
        case "low_stock":      return "From low stock"
        case "recommendation": return "Recommended"
        case "manual":         return "Manual"
        default:               return source
        }
    }
}

#Preview("ShoppingList") {
    ShoppingListView().frame(width: 700, height: 600)
}
