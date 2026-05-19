import SwiftUI

/// Shared ContextMenu builders for the most common right-click surfaces (§3.5).
///
/// Phase 2: structurally complete. Each handler is a closure that the host view
/// wires to its state (Phase 3+). Empty closures here just no-op.
enum ContextMenuModifiers {

    @ViewBuilder
    static func receiptRow(
        onOpen: @escaping () -> Void,
        onRerunOCR: @escaping () -> Void,
        onMarkReviewed: @escaping () -> Void,
        onCopyTotal: @escaping () -> Void,
        onDelete: @escaping () -> Void
    ) -> some View {
        Button("Open", action: onOpen)
        Button("Re-run OCR…", action: onRerunOCR)
        Button("Mark Reviewed", action: onMarkReviewed)
        Divider()
        Button("Copy Total", action: onCopyTotal)
        Divider()
        Button("Delete…", role: .destructive, action: onDelete)
    }

    @ViewBuilder
    static func inventoryRow(
        onAddToShoppingList: @escaping () -> Void,
        onAdjustQuantity: @escaping (Int) -> Void,
        onMarkLowStock: @escaping () -> Void,
        onEdit: @escaping () -> Void,
        onDelete: @escaping () -> Void
    ) -> some View {
        Button("Add to Shopping List", action: onAddToShoppingList)
        Divider()
        Button("Increment Quantity")  { onAdjustQuantity(+1) }
        Button("Decrement Quantity")  { onAdjustQuantity(-1) }
        Button("Mark Low Stock", action: onMarkLowStock)
        Divider()
        Button("Edit…", action: onEdit)
        Button("Delete…", role: .destructive, action: onDelete)
    }

    @ViewBuilder
    static func shoppingListRow(
        onTogglePurchased: @escaping () -> Void,
        onEditNote: @escaping () -> Void,
        onMove: @escaping () -> Void,
        onDelete: @escaping () -> Void
    ) -> some View {
        Button("Toggle Purchased", action: onTogglePurchased)
        Button("Edit Note…", action: onEditNote)
        Divider()
        Button("Move…", action: onMove)
        Divider()
        Button("Delete", role: .destructive, action: onDelete)
    }

    @ViewBuilder
    static func transactionRow(
        onMatchReceipt: @escaping () -> Void,
        onDismiss: @escaping () -> Void,
        onCategorize: @escaping () -> Void
    ) -> some View {
        Button("Match to Receipt…", action: onMatchReceipt)
        Button("Categorize…", action: onCategorize)
        Divider()
        Button("Dismiss", role: .destructive, action: onDismiss)
    }
}

#Preview("Context Menus / Inventory row") {
    Card {
        Text("Right-click anywhere on this card to see the inventory context menu.")
            .padding()
    }
    .contextMenu {
        ContextMenuModifiers.inventoryRow(
            onAddToShoppingList: {},
            onAdjustQuantity: { _ in },
            onMarkLowStock: {},
            onEdit: {},
            onDelete: {}
        )
    }
    .padding(40)
    .frame(width: 400)
}
