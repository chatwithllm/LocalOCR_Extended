import SwiftUI
import Kingfisher

/// Inventory screen — implements registry rows F-100 → F-144.
///
/// Concurrency: data fetch happens in `.onAppear { Task.detached { ... } }`
/// because `.task { await heavyWork() }` cancels on view-identity change (I-7).
struct InventoryView: View {
    @StateObject private var state = InventoryState.shared
    @StateObject private var shopping = ShoppingState.shared
    @EnvironmentObject private var router: Router

    @State private var selectedItemId: Int? = nil
    @State private var editingItem: InventoryItem? = nil

    var body: some View {
        VStack(spacing: 0) {
            // F-100..F-112 — Add Item card (collapsible)
            AddInventoryCard()
                .padding(.horizontal, DesignTokens.Spacing.space4)
                .padding(.top, DesignTokens.Spacing.space3)
                .environmentObject(state)

            // F-116..F-122 — toolbar
            InventoryToolbar()
                .padding(.horizontal, DesignTokens.Spacing.space4)
                .padding(.vertical, DesignTokens.Spacing.space2)
                .environmentObject(state)

            Divider()

            // F-124..F-130 — bulk action bar (only when items selected)
            if !state.selectedItemIds.isEmpty {
                BulkActionBar()
                    .padding(.horizontal, DesignTokens.Spacing.space4)
                    .padding(.vertical, DesignTokens.Spacing.space2)
                    .environmentObject(state)
                Divider()
            }

            // F-139..F-141 — restore section (recently used up)
            if state.restoreSectionVisible {
                RecentlyUsedUpSection()
                    .padding(.horizontal, DesignTokens.Spacing.space4)
                    .padding(.vertical, DesignTokens.Spacing.space3)
                    .environmentObject(state)
                Divider()
            }

            // F-113..F-115, F-123, F-132 — header + chip row + grouped list
            InventoryListBody(
                selectedItemId: $selectedItemId,
                editingItem: $editingItem
            )
            .environmentObject(state)
        }
        .background(DesignTokens.background)
        .navigationTitle("Inventory")
        .onAppear {
            // RULE 3 — heavy fetch must NOT use `.task`. Detach so view re-renders
            // don't cancel the request.
            Task.detached(priority: .userInitiated) {
                await state.loadInventory()
            }
        }
        .sheet(item: $editingItem) { item in
            InventoryEditSheet(item: item)
                .environmentObject(state)
                .frame(minWidth: 420, idealWidth: 460)
        }
    }
}

// MARK: - Add Item card (F-100 → F-112)

private struct AddInventoryCard: View {
    @EnvironmentObject private var state: InventoryState

    @State private var name: String = ""
    @State private var qty: Double = 1
    @State private var location: String = "Pantry"
    @State private var customLocation: String = ""
    @State private var threshold: Double = 1
    @State private var category: String = "other"
    @State private var unit: String = "each"
    @State private var preferredStore: String = ""
    @State private var alsoAddToShopping: Bool = false

    private let locations = ["Pantry", "Fridge", "Freezer", "Cabinet", "Laundry Room", "Custom…"]
    private let categories = ["other", "produce", "dairy", "meat", "pantry", "frozen", "bakery", "beverages", "snacks", "household", "personal_care"]
    private let unitChips = ["each", "oz", "lb", "g", "kg", "ml", "L", "pack", "box"]

    var body: some View {
        Card(padding: DesignTokens.Spacing.space4) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                // F-100 — collapse toggle row
                Button {
                    state.addCardCollapsed.toggle()
                } label: {
                    HStack {
                        Image(systemName: state.addCardCollapsed ? "chevron.right" : "chevron.down")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(DesignTokens.secondaryLabel)
                        Text("Add to inventory")
                            .font(.appHeadline)
                        Spacer()
                        if state.addCardCollapsed {
                            Text("Tap to expand").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                        }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(state.addCardCollapsed ? "Expand add item form" : "Collapse add item form")

                if !state.addCardCollapsed {
                    formBody
                }
            }
        }
    }

    private var formBody: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            HStack(spacing: DesignTokens.Spacing.space3) {
                // F-101 — name input
                VStack(alignment: .leading, spacing: 2) {
                    Text("Product Name").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    TextField("e.g. Milk, Apples…", text: $name)
                        .textFieldStyle(.roundedBorder)
                }
                // F-102 — quantity
                VStack(alignment: .leading, spacing: 2) {
                    Text("Quantity").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    TextField("1", value: $qty, format: .number)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 80)
                }
            }

            HStack(spacing: DesignTokens.Spacing.space3) {
                // F-103 — location dropdown
                VStack(alignment: .leading, spacing: 2) {
                    Text("Location").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    Picker("Location", selection: $location) {
                        ForEach(locations, id: \.self) { Text($0).tag($0) }
                    }
                    .labelsHidden()
                    .frame(width: 180)
                }
                // F-104 — custom location (conditional)
                if location == "Custom…" {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Custom location").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                        TextField("e.g. Garage shelf", text: $customLocation)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 200)
                    }
                }
                // F-105 — threshold
                VStack(alignment: .leading, spacing: 2) {
                    Text("Low-stock threshold").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    TextField("1", value: $threshold, format: .number)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 80)
                }
                Spacer()
            }

            // F-106 — more details toggle
            Button {
                state.addCardDetailsExpanded.toggle()
            } label: {
                Label(
                    state.addCardDetailsExpanded ? "Hide details" : "More details",
                    systemImage: state.addCardDetailsExpanded ? "chevron.up" : "chevron.down"
                )
                .font(.appCaption1)
            }
            .buttonStyle(.plain)
            .foregroundStyle(DesignTokens.accent)

            if state.addCardDetailsExpanded {
                expandedDetails
            }

            HStack {
                Spacer()
                // F-111 — submit
                Button {
                    submit()
                } label: {
                    Label("Add to inventory", systemImage: "plus.circle.fill")
                }
                .buttonStyle(.borderedProminent)
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    private var expandedDetails: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            HStack(spacing: DesignTokens.Spacing.space3) {
                // F-107 — category
                VStack(alignment: .leading, spacing: 2) {
                    Text("Category").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    Picker("Category", selection: $category) {
                        ForEach(categories, id: \.self) { Text($0.capitalized).tag($0) }
                    }
                    .labelsHidden()
                    .frame(width: 180)
                }
                // F-109 — preferred store
                VStack(alignment: .leading, spacing: 2) {
                    Text("Preferred store").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    TextField("optional", text: $preferredStore)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 200)
                }
                Spacer()
            }
            // F-108 — unit chip row
            VStack(alignment: .leading, spacing: 4) {
                Text("Unit").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                HStack(spacing: 6) {
                    ForEach(unitChips, id: \.self) { u in
                        Button {
                            unit = u
                        } label: {
                            Text(u)
                                .font(.appCaption1)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(unit == u ? DesignTokens.accent.opacity(0.18) : DesignTokens.surface2)
                                .foregroundStyle(unit == u ? DesignTokens.accent : DesignTokens.label)
                                .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            // F-110 — also add to shopping
            Toggle("Also add to shopping list", isOn: $alsoAddToShopping)
                .toggleStyle(.checkbox)
                .font(.appCaption1)
        }
    }

    private func submit() {
        let cleanName = name.trimmingCharacters(in: .whitespaces)
        guard !cleanName.isEmpty else { return }
        let finalLocation = location == "Custom…" ? customLocation.trimmingCharacters(in: .whitespaces) : location
        let useLocation = finalLocation.isEmpty ? "Pantry" : finalLocation
        let useCategory = state.addCardDetailsExpanded ? category : nil
        let useSize = state.addCardDetailsExpanded && !preferredStore.isEmpty ? preferredStore : nil
        Task.detached(priority: .userInitiated) {
            await state.addItem(
                productName: cleanName,
                quantity: qty,
                location: useLocation,
                threshold: threshold,
                category: useCategory,
                size: useSize,
                alsoAddToShopping: alsoAddToShopping
            )
            await MainActor.run {
                name = ""
                qty = 1
                threshold = 1
            }
        }
    }
}

// MARK: - Toolbar (F-116 → F-122)

private struct InventoryToolbar: View {
    @EnvironmentObject private var state: InventoryState

    private let locations = ["All", "Fridge", "Freezer", "Pantry", "Cabinet", "Bathroom"]

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            // F-116 — search
            HStack(spacing: 4) {
                Image(systemName: "magnifyingglass").foregroundStyle(DesignTokens.tertiaryLabel)
                TextField("Search inventory", text: $state.searchText)
                    .textFieldStyle(.plain)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(DesignTokens.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .frame(maxWidth: 240)

            // F-117 — location filter
            Picker("Location", selection: Binding(
                get: { state.locationFilter ?? "All" },
                set: { state.locationFilter = $0 == "All" ? nil : $0 }
            )) {
                ForEach(locations, id: \.self) { Text($0).tag($0) }
            }
            .labelsHidden()
            .frame(width: 140)

            // F-118 — group by
            Picker("Group", selection: $state.groupBy) {
                ForEach(InventoryState.GroupBy.allCases) { Text($0.label).tag($0) }
            }
            .labelsHidden()
            .frame(width: 160)

            // F-119 — sort
            Picker("Sort", selection: $state.sortBy) {
                ForEach(InventoryState.SortBy.allCases) { Text($0.label).tag($0) }
            }
            .labelsHidden()
            .frame(width: 160)

            // F-120 — show empty
            Toggle("Show empty", isOn: $state.showEmpty)
                .toggleStyle(.checkbox)
                .font(.appCaption1)

            Spacer()

            // F-121 — open restore section
            Button {
                state.restoreSectionVisible.toggle()
                if state.restoreSectionVisible {
                    Task.detached(priority: .userInitiated) {
                        await state.loadRecentlyUsedUp(days: 30)
                    }
                }
            } label: {
                Label("Recently used up", systemImage: "arrow.uturn.backward")
                    .font(.appCaption1)
            }

            // F-122 — merge duplicates (calls /products/auto-dedup-tokens, no body)
            Button {
                Task.detached(priority: .userInitiated) {
                    await runDedup()
                }
            } label: {
                Label("Merge duplicates", systemImage: "rectangle.stack.badge.minus")
                    .font(.appCaption1)
            }

            // Refresh
            Button {
                Task.detached(priority: .userInitiated) {
                    await state.loadInventory()
                }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .keyboardShortcut("r", modifiers: .command)
            .help("Refresh")
        }
    }

    private func runDedup() async {
        do {
            try DemoModeGate.guardMutation()
            try await APIClient.shared.request(.post, path: "/products/auto-dedup-tokens")
            await state.loadInventory()
            ToastQueue.shared.push(Toast(message: "Merged duplicate products", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? error.localizedDescription
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
        }
    }
}

// MARK: - Bulk action bar (F-124 → F-130)

private struct BulkActionBar: View {
    @EnvironmentObject private var state: InventoryState

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            // F-125 — selection count label
            Text("\(state.selectedItemIds.count) selected")
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(DesignTokens.label)

            Spacer()

            // F-126 — bulk −1 all
            Button("−1 all") {
                Task.detached(priority: .userInitiated) { await state.bulkDecrement() }
            }
            .help("Decrement quantity by 1 on every selected item")

            // F-127 — bulk +3d defer
            Button("+3d all") {
                Task.detached(priority: .userInitiated) { await state.bulkDefer(days: 3) }
            }
            .help("Push expiry 3 days forward for every selected item")

            // F-128 — bulk +7d defer
            Button("+7d all") {
                Task.detached(priority: .userInitiated) { await state.bulkDefer(days: 7) }
            }
            .help("Push expiry 7 days forward for every selected item")

            // F-129 — bulk used up
            Button("Used up all", role: .destructive) {
                Task.detached(priority: .userInitiated) { await state.bulkUsedUp() }
            }

            // F-130 — clear selection
            Button("Clear") {
                state.clearSelection()
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.space3)
        .padding(.vertical, 6)
        .background(DesignTokens.accent.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Recently used up restore section (F-139 → F-141)

private struct RecentlyUsedUpSection: View {
    @EnvironmentObject private var state: InventoryState

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            HStack {
                Text("Recently used up — last 30 days")
                    .font(.appHeadline)
                Spacer()
                // F-141 — hide button
                Button("Hide") { state.restoreSectionVisible = false }
                    .buttonStyle(.plain)
                    .foregroundStyle(DesignTokens.accent)
                    .font(.appCaption1)
            }

            if state.isLoadingRecentlyUsedUp {
                HStack {
                    ProgressView().controlSize(.small)
                    Text("Loading…").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                }
            } else if state.recentlyUsedUp.isEmpty {
                Text("Nothing was consumed in the last 30 days.")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: DesignTokens.Spacing.space2) {
                        ForEach(state.recentlyUsedUp) { row in
                            recentRow(row)
                        }
                    }
                }
            }
        }
        .padding(DesignTokens.Spacing.space3)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
    }

    private func recentRow(_ row: RecentlyUsedUpItem) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(row.displayName).font(.appCallout)
            HStack(spacing: 6) {
                if let cat = row.category {
                    Text(cat).font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                }
                if let when = row.usedUpAt?.prefix(10) {
                    Text(String(when)).font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                }
            }
            // F-140 — restore button
            Button("Restore") {
                Task.detached(priority: .userInitiated) {
                    await state.restore(productId: row.productId, quantity: row.priorQuantity)
                }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(DesignTokens.Spacing.space2)
        .frame(width: 220, alignment: .leading)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - List body (F-113 → F-115, F-123, F-132 → F-138, F-142, F-144)

private struct InventoryListBody: View {
    @EnvironmentObject private var state: InventoryState
    @Binding var selectedItemId: Int?
    @Binding var editingItem: InventoryItem?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // F-113..F-115 — header + window note + low badge
            header
                .padding(.horizontal, DesignTokens.Spacing.space4)
                .padding(.top, DesignTokens.Spacing.space3)

            // F-123 — category chip row
            if !state.categories.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        chip(label: "All", active: state.categoryFilter == nil) {
                            state.categoryFilter = nil
                        }
                        ForEach(state.categories, id: \.self) { cat in
                            chip(label: cat.capitalized, active: state.categoryFilter == cat) {
                                state.categoryFilter = (state.categoryFilter == cat) ? nil : cat
                            }
                        }
                    }
                    .padding(.horizontal, DesignTokens.Spacing.space4)
                    .padding(.vertical, DesignTokens.Spacing.space2)
                }
            }

            // F-132 — grouped list
            if state.isLoading && state.items.isEmpty {
                loadingView
            } else if state.filteredItems.isEmpty {
                emptyView
            } else {
                List(selection: $selectedItemId) {
                    ForEach(state.groupedItems(), id: \.0) { (header, rows) in
                        Section {
                            ForEach(rows) { item in
                                InventoryRow(item: item, editingItem: $editingItem)
                                    .tag(item.id as Int?)
                            }
                        } header: {
                            groupHeader(title: header, rows: rows)
                        }
                    }
                }
                .listStyle(.inset(alternatesRowBackgrounds: false))
            }
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("Current inventory")
                .font(.appTitle3)
            // F-114 — low badge
            if state.lowStockCount > 0 {
                Text("\(state.lowStockCount) low")
                    .font(.appCaption1.weight(.semibold))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(DesignTokens.lowStockPillBackground)
                    .foregroundStyle(DesignTokens.warning)
                    .clipShape(Capsule())
            }
            Spacer()
            // F-115 — window note
            if let label = state.windowLabel {
                Text(label).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
            }
        }
    }

    /// F-147 + F-157 — group header with emoji prefix, item count, and "N expiring soon" tail.
    /// Matches web's `_invGroupLabel`: 🔴 Running Low / ✅ OK / 📦 Domain / 📦 Location.
    private func groupHeader(title: String, rows: [InventoryItem]) -> some View {
        let expSoon = InventoryState.expiringSoonCount(rows)
        let emoji: String = {
            switch title {
            case "Running low":  return "🔴"
            case "Well stocked": return "✅"
            default:             return "📦"
            }
        }()
        return HStack(spacing: 6) {
            Text("\(emoji) \(title)")
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryLabel)
            Text("· \(rows.count) item\(rows.count == 1 ? "" : "s")")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.tertiaryLabel)
            if expSoon > 0 {
                Text("· \(expSoon) expiring soon")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.warning)
            }
            Spacer()
        }
    }

    private func chip(label: String, active: Bool, onTap: @escaping () -> Void) -> some View {
        Button(action: onTap) {
            Text(label)
                .font(.appCaption1)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(active ? DesignTokens.accent.opacity(0.18) : DesignTokens.surface2)
                .foregroundStyle(active ? DesignTokens.accent : DesignTokens.label)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private var loadingView: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            ForEach(0..<6, id: \.self) { _ in
                SkeletonView(width: nil, height: 56, cornerRadius: DesignTokens.Radius.card)
            }
        }
        .padding(DesignTokens.Spacing.space4)
    }

    private var emptyView: some View {
        // F-142 — loading state silent (we already cover loading). Empty state below.
        EmptyStateView(
            systemImage: state.items.isEmpty ? "tray" : "magnifyingglass",
            title: state.items.isEmpty ? "No inventory yet" : "No matches",
            subtitle: state.items.isEmpty
                ? "Upload a receipt — items will be extracted automatically and added here."
                : "Try clearing filters, search, or low-stock toggle."
        )
    }
}

// MARK: - Row (F-133 → F-138, F-144 selection toggle)

private struct InventoryRow: View {
    @EnvironmentObject private var state: InventoryState
    let item: InventoryItem
    @Binding var editingItem: InventoryItem?

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            // F-124 — bulk selection checkbox (one per row)
            Toggle("", isOn: Binding(
                get: { state.selectedItemIds.contains(item.id) },
                set: { _ in state.toggleSelection(item.id) }
            ))
            .toggleStyle(.checkbox)
            .labelsHidden()

            // F-145 — product snapshot thumbnail (web: latest_snapshot.image_url)
            ProductSnapshotThumb(snapshot: item.latestSnapshot, fallbackInitials: item.displayName)
                .frame(width: 44, height: 44)

            VStack(alignment: .leading, spacing: 3) {
                // F-156 / F-159 — draggable remaining-% slider with tap-to-cycle on the
                // name area. The whole row body is the slider; the visible handle sits
                // at the right edge of the fill. Tap (no drag) on the title area cycles
                // status (fresh → low → out → fresh, buckets 80/40/10).
                RemainingSlider(
                    remainingPct: item.remainingPct,
                    status: item.status,
                    onCommit: { newPct in
                        let id = item.id
                        Task.detached(priority: .userInitiated) {
                            await state.setRemainingOverride(itemId: id, remainingPct: newPct)
                        }
                    },
                    onTapCycle: {
                        let id = item.id
                        let status = item.status
                        Task.detached(priority: .userInitiated) {
                            await state.cycleStatus(itemId: id, currentStatus: status)
                        }
                    }
                ) {
                    HStack(spacing: 6) {
                        Text(item.displayName).font(.appBody)
                        if item.isLowStock {
                            LowStockPill(severity: item.quantity <= 0 ? .critical : .low)
                        }
                        if item.isRegularUse == true {
                            Image(systemName: "star.fill")
                                .font(.system(size: 10))
                                .foregroundStyle(DesignTokens.warning)
                                .help("Regular use item")
                        }
                        Spacer()
                        // F-150 — days-left / EXPIRED wording (matches web)
                        Text(daysLabel).font(.appCaption1.monospaced())
                            .foregroundStyle(daysLabelColor)
                    }
                    .padding(.horizontal, 4)
                    .padding(.vertical, 2)
                }

                HStack(spacing: 6) {
                    if let cat = item.category {
                        Text(cat).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    if let loc = item.location {
                        Text("• \(loc)").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                    if let unit = item.unit, unit != "each" {
                        Text("• \(unit)").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }

                // F-148 — Bought line
                if let bought = item.lastPurchasedAt?.prefix(10), !bought.isEmpty {
                    Text("📅 Bought \(String(bought))")
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }

                // F-149 — Expires line with strike when expired; F-151/F-152 source chips
                if let exp = item.expiresAt?.prefix(10), !exp.isEmpty {
                    HStack(spacing: 4) {
                        Text("🍂 Expires")
                            .font(.appCaption2)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                        Text(String(exp))
                            .font(.appCaption2)
                            .foregroundStyle(isExpired ? DesignTokens.error : DesignTokens.tertiaryLabel)
                            .strikethrough(isExpired, color: DesignTokens.error)
                        if item.expiresSource == "defer" {
                            ExpirySourceChip(label: "defer", tint: .deferTint)
                        } else if item.expiresSource == "user" {
                            ExpirySourceChip(label: "user", tint: .userTint)
                        }
                    }
                }
            }

            Spacer()

            // Action button row — order matches web verbatim: ✎ | +3d | 🛒 | −1 | ✓
            // (See `_invBuildTile` in src/frontend/index.html line 24094-24124.)
            //
            // The mac-only −/qty/+ stepper that lived here in v0 was removed:
            // web's quantity stepper has no inline equivalent. Quantity edits
            // happen via the edit sheet (pencil) or via −1 (which patches
            // quantity directly), matching web behavior 1:1.

            // F-153 — inline edit (web ✎)
            Button {
                editingItem = item
            } label: { Image(systemName: "pencil") }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Edit qty / location / threshold")

            // F-146 — +3d defer (⌥-click → +7d, mirrors web's hold-press)
            Button {
                let days = NSEvent.modifierFlags.contains(.option) ? 7 : 3
                let pid = item.productId
                Task.detached(priority: .userInitiated) {
                    await state.deferExpiry(productId: pid, days: days)
                }
            } label: {
                Text("+3d").font(.appCaption1.weight(.medium))
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Push expiry forward 3 days (hold ⌥ for +7d)")

            // F-154 — add-to-shopping (web 🛒)
            Button {
                let pid = item.productId
                let name = item.displayName
                Task.detached(priority: .userInitiated) {
                    await ShoppingState.shared.add(
                        productName: name, quantity: 1,
                        source: "manual", productId: pid
                    )
                }
            } label: { Image(systemName: "cart") }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Add to shopping list")

            // F-160 — −1 single-tap decrement. Matches web's `invDecrement`:
            // PATCH /inventory/products/<pid> { quantity: max(0, q-1) }.
            // Hitting 0 deletes the inventory row server-side (used-up path).
            Button {
                let pid = item.productId
                Task.detached(priority: .userInitiated) {
                    await state.decrementOne(productId: pid)
                }
            } label: {
                Text("−1").font(.appCaption1.weight(.medium).monospacedDigit())
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .keyboardShortcut(.downArrow, modifiers: .option)
            .help("Subtract 1 from quantity")

            // F-155 — ✓ dual-mode (clear-low when low, else used-up). ⌥-click adds
            // to shopping + marks used-up (mirrors web's long-press "✓ + 🛒").
            Button {
                let isLow = item.isLowStock
                let useShortcut = NSEvent.modifierFlags.contains(.option)
                let captured = item
                Task.detached(priority: .userInitiated) {
                    if isLow {
                        await state.clearLow(item: captured)
                    } else {
                        await state.markUsedUp(productId: captured.productId)
                    }
                    if useShortcut {
                        await ShoppingState.shared.add(
                            productName: captured.displayName, quantity: 1,
                            source: "auto_used_up", productId: captured.productId
                        )
                    }
                }
            } label: {
                Image(systemName: "checkmark")
                    .foregroundStyle(item.isLowStock ? DesignTokens.warning : DesignTokens.success)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help(item.isLowStock ? "Clear low flag (⌥ also adds to shopping)" : "Used up (⌥ also adds to shopping)")
        }
        .padding(.vertical, 4)
        // F-138 — swipe delete
        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
            Button(role: .destructive) {
                Task.detached(priority: .userInitiated) {
                    await state.deleteItem(itemId: item.id)
                }
            } label: {
                Label("Delete", systemImage: "trash")
            }
            // F-135 — set/clear low status via swipe
            Button {
                Task.detached(priority: .userInitiated) {
                    await state.markLow(productId: item.productId, manualLow: !(item.manualLow ?? false))
                }
            } label: {
                Label(item.manualLow == true ? "Clear low" : "Mark low",
                      systemImage: "exclamationmark.circle")
            }
            .tint(DesignTokens.warning)
        }
        .contextMenu {
            // F-134 — open inline edit
            Button("Edit…") { editingItem = item }
            Divider()
            // F-135 — toggle low
            Button(item.manualLow == true ? "Clear low-stock flag" : "Mark as low stock") {
                Task.detached(priority: .userInitiated) {
                    await state.markLow(productId: item.productId, manualLow: !(item.manualLow ?? false))
                }
            }
            // F-136 — confirm low
            Button("Confirm low (peer)") {
                Task.detached(priority: .userInitiated) {
                    await state.confirmLow(productId: item.productId)
                }
            }
            .disabled(item.manualLow != true)
            // F-144 — toggle regular use
            Button(item.isRegularUse == true ? "Remove from regulars" : "Mark as regular use") {
                Task.detached(priority: .userInitiated) {
                    await state.toggleRegularUse(productId: item.productId, isRegular: !(item.isRegularUse ?? false))
                }
            }
            Divider()
            // F-143 — clear expiry override
            Button("Reset expiry to system default") {
                Task.detached(priority: .userInitiated) {
                    await state.clearExpiryOverride(productId: item.productId)
                }
            }
            .disabled(item.expiresSource == "system" || item.expiresSource == nil)
            // Add to shopping
            Button("Add to shopping list") {
                Task.detached(priority: .userInitiated) {
                    await ShoppingState.shared.add(
                        productName: item.displayName,
                        quantity: 1,
                        source: "manual",
                        productId: item.productId
                    )
                }
            }
            Divider()
            Button("Delete from inventory", role: .destructive) {
                Task.detached(priority: .userInitiated) {
                    await state.deleteItem(itemId: item.id)
                }
            }
        }
    }
}

// MARK: - Per-row helpers (F-150 days label, F-156 status fill bar, F-151/152 chips)

private extension InventoryRow {
    /// "EXPIRED Nd ago" / "Nd left" / "no expiry" — matches web `_invBuildTile` lines 23961-23963.
    var daysLabel: String {
        guard let days = item.daysLeft else { return "no expiry" }
        if days <= 0 { return "EXPIRED \(abs(days))d ago" }
        return "\(days)d left"
    }

    var daysLabelColor: Color {
        guard let days = item.daysLeft else { return DesignTokens.tertiaryLabel }
        if days <= 0 { return DesignTokens.error }
        if days <= 3 { return DesignTokens.warning }
        return DesignTokens.tertiaryLabel
    }

    var isExpired: Bool {
        guard let days = item.daysLeft else { return false }
        return days <= 0
    }
}

/// Small tag chip used for `expires_source` overrides (defer / user).
private struct ExpirySourceChip: View {
    let label: String
    let tint: Color

    var body: some View {
        Text(label)
            .font(.system(size: 9, weight: .semibold))
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .background(tint.opacity(0.25))
            .foregroundStyle(tint)
            .clipShape(RoundedRectangle(cornerRadius: 3))
    }
}

private extension Color {
    static var deferTint: Color { Color(red: 0.86, green: 0.78, blue: 0.40) }
    static var userTint: Color  { Color(red: 0.42, green: 0.62, blue: 0.85) }
}

/// Draggable remaining-quantity slider used as the name-row background
/// (F-156 + F-159). Mirrors web's `inv-tile-title-row`: a horizontal fill
/// whose width is `remaining_pct` and whose color buckets per `status`,
/// with a thin handle at the fill edge the user can drag to set
/// `consumed_pct_override`. Tapping the title area (no drag) cycles status.
///
/// Color thresholds match web's `_invStatusForPct` (≥60 fresh / ≥20 low / out)
/// AND web's `_invStatusFill` opacities (0.18 / 0.20 / 0.22).
private struct RemainingSlider<Title: View>: View {
    let remainingPct: Double?
    let status: String?
    let onCommit: (Double) -> Void
    let onTapCycle: () -> Void
    @ViewBuilder let title: () -> Title

    @State private var dragPct: Double? = nil
    @State private var isDragging = false

    private var displayPct: Double {
        max(0, min(100, dragPct ?? remainingPct ?? 100))
    }

    private var fillColor: Color {
        switch statusForPct(displayPct) {
        case "fresh": return DesignTokens.success
        case "low":   return DesignTokens.warning
        default:      return DesignTokens.error
        }
    }

    var body: some View {
        GeometryReader { geo in
            let width = max(1, geo.size.width)
            let fillW = width * (displayPct / 100.0)

            ZStack(alignment: .leading) {
                // Background track (subtle so the fill reads as the value).
                RoundedRectangle(cornerRadius: 4)
                    .fill(DesignTokens.surface2.opacity(0.4))
                // Filled portion (status-tinted).
                RoundedRectangle(cornerRadius: 4)
                    .fill(fillColor.opacity(statusFillOpacity()))
                    .frame(width: fillW)
                // Title content (name + days label etc).
                title()
                    .contentShape(Rectangle())
                    .onTapGesture {
                        // Only fire cycle if we didn't just finish a drag.
                        guard !isDragging else { return }
                        onTapCycle()
                    }
                // Drag handle at right edge of fill — slim vertical capsule with
                // a live-% bubble above while dragging. The handle hosts the
                // DragGesture; the title's tap gesture is separate so a click on
                // the name area cycles status without engaging the slider.
                handle(at: fillW)
            }
            .frame(height: 22)
            .gesture(
                DragGesture(minimumDistance: 2)
                    .onChanged { value in
                        isDragging = true
                        let ratio = value.location.x / width
                        let snapped = (max(0, min(100, ratio * 100)) / 5).rounded() * 5
                        dragPct = snapped
                    }
                    .onEnded { _ in
                        if let final = dragPct {
                            onCommit(final)
                        }
                        // Hold isDragging true for a beat so the synthetic tap
                        // that follows a drag end doesn't trigger cycleStatus
                        // (matches web's __invLastDragAt suppression window).
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                            isDragging = false
                            dragPct = nil
                        }
                    }
            )
        }
        .frame(height: 22)
    }

    @ViewBuilder
    private func handle(at x: CGFloat) -> some View {
        ZStack(alignment: .bottom) {
            if isDragging {
                Text("\(Int(displayPct))%")
                    .font(.system(size: 9, weight: .semibold).monospacedDigit())
                    .padding(.horizontal, 5).padding(.vertical, 2)
                    .background(
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.black.opacity(0.7))
                    )
                    .foregroundStyle(.white)
                    .offset(y: -18)
                    .transition(.opacity)
            }
            Capsule()
                .fill(fillColor.opacity(0.9))
                .frame(width: 4, height: 18)
                .overlay(Capsule().stroke(Color.white.opacity(0.6), lineWidth: 0.5))
                .help("Drag to set remaining quantity (\(Int(displayPct))%)")
        }
        .frame(width: 14, height: 22)
        .offset(x: max(0, x - 7))
    }

    private func statusForPct(_ pct: Double) -> String {
        if pct >= 60 { return "fresh" }
        if pct >= 20 { return "low" }
        return "out"
    }

    private func statusFillOpacity() -> Double {
        switch statusForPct(displayPct) {
        case "fresh": return 0.18
        case "low":   return 0.20
        default:      return 0.22
        }
    }
}

// MARK: - Edit sheet (F-137 — edit item fields)

private struct InventoryEditSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var state: InventoryState
    let item: InventoryItem

    @State private var quantity: Double = 0
    @State private var location: String = "Pantry"
    @State private var threshold: Double = 1

    private let locations = ["Pantry", "Fridge", "Freezer", "Cabinet", "Bathroom"]

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            Text("Edit \(item.displayName)").font(.appHeadline)
            HStack {
                Text("Quantity").frame(width: 80, alignment: .leading)
                TextField("", value: $quantity, format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 100)
            }
            HStack {
                Text("Location").frame(width: 80, alignment: .leading)
                Picker("", selection: $location) {
                    ForEach(locations, id: \.self) { Text($0).tag($0) }
                }
                .labelsHidden()
                .frame(width: 180)
            }
            HStack {
                Text("Threshold").frame(width: 80, alignment: .leading)
                TextField("", value: $threshold, format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 100)
            }
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                Button("Save") {
                    Task.detached(priority: .userInitiated) {
                        await state.updateItem(
                            itemId: item.id,
                            quantity: quantity,
                            location: location,
                            threshold: threshold
                        )
                        await MainActor.run { dismiss() }
                    }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(DesignTokens.Spacing.space5)
        .onAppear {
            quantity = item.quantity
            location = item.location ?? "Pantry"
            threshold = item.threshold ?? 1
        }
    }
}

// MARK: - Product snapshot thumbnail (F-145)

/// Authenticated thumbnail for the row's `latest_snapshot`. Backend serves the
/// image at `/product-snapshots/<id>/image` (auth required); Kingfisher's
/// `tokenModifier` attaches the trusted-device header for us.
private struct ProductSnapshotThumb: View {
    let snapshot: LatestSnapshot?
    let fallbackInitials: String

    @State private var isHovering = false
    @State private var showPopover = false

    private var resolvedURL: URL? {
        guard let path = snapshot?.imageUrl, !path.isEmpty else { return nil }
        let base = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                ?? AppConstants.defaultAPIBaseURL
        // path is server-relative ("/product-snapshots/123/image"); compose.
        return URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                   + (path.hasPrefix("/") ? path : "/" + path))
    }

    var body: some View {
        if let url = resolvedURL {
            KFImage(url)
                .requestModifier(ImageCache.tokenModifier)
                .placeholder { placeholder }
                .resizable()
                .scaledToFill()
                .frame(width: 44, height: 44)
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(DesignTokens.border, lineWidth: 0.5)
                )
                // F-158 — hover preview popup (web `.inv-tile-img:hover` scale 2.6×).
                // Hover delay (~250 ms) keeps a cursor swept past the row from
                // flashing every popover on the way through.
                .onHover { hovering in
                    isHovering = hovering
                    if hovering {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                            if isHovering { showPopover = true }
                        }
                    } else {
                        showPopover = false
                    }
                }
                .popover(isPresented: $showPopover, arrowEdge: .leading) {
                    KFImage(url)
                        .requestModifier(ImageCache.tokenModifier)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 320, height: 320)
                        .padding(8)
                }
        } else {
            placeholder
        }
    }

    private var placeholder: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 6)
                .fill(DesignTokens.surface2)
            Text(initials)
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
        .frame(width: 44, height: 44)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(DesignTokens.border, lineWidth: 0.5)
        )
    }

    private var initials: String {
        let parts = fallbackInitials.split(separator: " ").prefix(2)
        let chars = parts.compactMap { $0.first.map { String($0) } }.joined()
        return chars.isEmpty ? "·" : chars.uppercased()
    }
}

#Preview("InventoryView") {
    InventoryView()
        .environmentObject(Router.shared)
        .frame(width: 1100, height: 720)
}
