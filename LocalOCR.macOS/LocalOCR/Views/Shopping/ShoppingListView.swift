import SwiftUI
import Kingfisher

// MARK: - ShoppingListView
//
// Web reference: `src/frontend/index.html` lines 3197–3510 (page markup) +
// `renderShoppingListTable`, `loadShoppingList`, `renderShoppingSessionBanner`,
// session/finalize/ready-to-bill/reopen helpers, past-trips, and quick-find.
//
// Out of scope for v1.0 (justified in FEATURE_PARITY_REGISTRY.md):
//   F-209..F-212 — "Identify from Photo" (Gemini round-trip; defer to v1.1)
//   F-245       — per-item photo upload (same as inventory F-131 — 🚫 v1.0)
//   F-246..F-248 — share link / shopping helper mode (no anonymous guest mode on mac)
//   F-257       — helper intro card (helper mode only)

struct ShoppingListView: View {
    @StateObject private var state = ShoppingState.shared
    @State private var renameTarget: ShoppingListItem?
    @State private var renameText: String = ""
    @State private var noteTarget: ShoppingListItem?
    @State private var noteText: String = ""
    @State private var deleteTarget: ShoppingListItem?
    @State private var confirmFinalize = false
    @State private var quickFindDebounceTask: Task<Void, Never>?

    var body: some View {
        ScrollView {
            VStack(spacing: DesignTokens.Spacing.space4) {
                summaryStrip                                                            // F-203..F-206
                if let session = state.session { sessionBanner(session: session) }      // F-203
                if state.manualAddVisible { ManualAddCard(state: state) }               // F-207..F-219
                QuickFindCard(state: state, onDebouncedSearch: scheduleQuickFindSearch)  // F-220..F-225
                RecommendationsCard(state: state)                                       // F-226..F-231
                CurrentListCard(
                    state: state,
                    onRename: { item in renameText = item.name; renameTarget = item },
                    onEditNote: { item in noteText = item.note ?? ""; noteTarget = item },
                    onDelete: { item in deleteTarget = item }
                )                                                                       // F-232..F-244, F-258..F-267
                PastTripsCard(state: state)                                             // F-252..F-256, F-268
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Shopping List")
        .toolbar { toolbarContent }
        .onAppear {
            Task.detached(priority: .userInitiated) {
                await ShoppingState.shared.loadList()
                await ShoppingState.shared.loadRecommendations()
            }
        }
        .alert("Rename Item", isPresented: Binding(
            get: { renameTarget != nil },
            set: { if !$0 { renameTarget = nil } }
        )) {
            TextField("New name", text: $renameText)
            Button("Save") {
                if let target = renameTarget, !renameText.trimmingCharacters(in: .whitespaces).isEmpty {
                    Task { await state.renameItem(id: target.id, newName: renameText.trimmingCharacters(in: .whitespaces)) }
                }
                renameTarget = nil
            }
            Button("Cancel", role: .cancel) { renameTarget = nil }
        }
        .alert("Edit Note", isPresented: Binding(
            get: { noteTarget != nil },
            set: { if !$0 { noteTarget = nil } }
        )) {
            TextField("Note", text: $noteText)
            Button("Save") {
                if let target = noteTarget {
                    let trimmed = noteText.trimmingCharacters(in: .whitespacesAndNewlines)
                    Task { await state.updateNote(id: target.id, note: trimmed.isEmpty ? nil : trimmed) }
                }
                noteTarget = nil
            }
            Button("Clear", role: .destructive) {
                if let target = noteTarget {
                    Task { await state.updateNote(id: target.id, note: nil) }
                }
                noteTarget = nil
            }
            Button("Cancel", role: .cancel) { noteTarget = nil }
        }
        .confirmationDialog(
            "Delete this shopping list item?",
            isPresented: Binding(
                get: { deleteTarget != nil },
                set: { if !$0 { deleteTarget = nil } }
            ),
            presenting: deleteTarget
        ) { item in
            Button("Delete", role: .destructive) {
                Task { await state.remove(id: item.id) }
                deleteTarget = nil
            }
            Button("Cancel", role: .cancel) { deleteTarget = nil }
        }
        .confirmationDialog(
            finalizeConfirmMessage,
            isPresented: $confirmFinalize
        ) {
            Button("Finalize", role: .destructive) { Task { await state.finalizeSession() } }
            Button("Cancel", role: .cancel) {}
        }
    }

    // MARK: - F-200..F-202 page header / toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            // F-201 — toggle Quick Find card.
            Button { state.toggleQuickFind() } label: {
                Label("Quick Find", systemImage: "magnifyingglass")
            }
            .help("Toggle Quick Find")

            // F-202 — toggle Recommendations.
            Button { state.toggleRecommendations() } label: {
                HStack(spacing: 4) {
                    Image(systemName: "sparkles")
                    Text("\(state.recommendations.count)")
                        .font(.appMonoCaption.weight(.semibold))
                }
            }
            .help("Toggle Recommendations")

            // F-219 quick toggle — manual add card.
            Button { state.toggleManualAdd() } label: {
                Label("Add", systemImage: "plus")
            }
            .help("Add item manually")
            .keyboardShortcut("n", modifiers: [.command])

            Button {
                Task.detached(priority: .userInitiated) { await ShoppingState.shared.loadList() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .help("Refresh shopping list")
            .keyboardShortcut("r", modifiers: .command)
        }
    }

    // MARK: - F-203 session banner

    @ViewBuilder
    private func sessionBanner(session: ShoppingSession) -> some View {
        Card {
            HStack(alignment: .firstTextBaseline, spacing: DesignTokens.Spacing.space3) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        Text("🛒 \(session.name ?? "Current list")")
                            .font(.appHeadline.weight(.semibold))
                        sessionStatusBadge(session: session)
                    }
                    Text(sessionHeadline(session: session))
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
                Spacer(minLength: DesignTokens.Spacing.space3)
                sessionActions(session: session)
            }
        }
    }

    @ViewBuilder
    private func sessionStatusBadge(session: ShoppingSession) -> some View {
        if session.isActive {
            Badge(text: "Active", style: .warning)
        } else if session.isReadyToBill {
            Badge(text: "Ready to Bill", style: .success)
        } else if session.isClosed {
            Badge(text: "Closed", style: .neutral)
        }
    }

    private func sessionHeadline(session: ShoppingSession) -> String {
        let estOpen = formatMoney(state.estimatedTotalCost)
        let bought = formatMoney(state.boughtEstimatedTotal)
        if session.isActive {
            return "Estimated remaining: \(estOpen) · Bought so far: \(bought) (\(state.purchasedCount))"
        }
        if session.isReadyToBill {
            let actual = formatMoney(state.actualTotal)
            let variance = formatMoney(state.variance)
            let priced = "\(state.actualsEnteredCount)/\(state.purchasedCount)"
            let varianceTxt = state.actualsEnteredCount > 0
                ? "Variance: \(state.variance >= 0 ? "+" : "")\(variance)"
                : "Enter actual prices below to compute variance."
            let carry = state.openCount > 0
                ? " · \(state.openCount) item\(state.openCount == 1 ? "" : "s") still open — will carry to next list"
                : ""
            return "Bought: \(bought) · Actual: \(actual) · \(varianceTxt) · Priced: \(priced)\(carry)"
        }
        if session.isClosed {
            let est = formatMoney(session.estimatedTotalSnapshot ?? 0)
            let act = formatMoney(session.actualTotalSnapshot ?? 0)
            return "Estimated: \(est) · Actual: \(act)"
        }
        return ""
    }

    @ViewBuilder
    private func sessionActions(session: ShoppingSession) -> some View {
        HStack(spacing: 8) {
            if session.isActive {
                // F-249 — Ready to Bill (disabled when nothing purchased)
                if state.purchasedCount > 0 {
                    Button("🧾 Ready to Bill (\(state.purchasedCount))") {
                        Task { await state.markReadyToBill() }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                } else {
                    Text("Mark items bought to enable Ready to Bill.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
            } else if session.isReadyToBill {
                // F-250 — Back to Shopping
                Button("↩ Back to Shopping") {
                    Task { await state.reopenSession() }
                }
                .buttonStyle(GhostButtonStyle())
                // F-251 — Finalize
                Button("✅ Finalize & Close") { confirmFinalize = true }
                    .buttonStyle(PrimaryButtonStyle())
            } else if session.isClosed {
                Button("↩ Reopen") { Task { await state.reopenSession() } }
                    .buttonStyle(GhostButtonStyle())
            }
        }
    }

    private var finalizeConfirmMessage: String {
        if state.openCount > 0 {
            return "Finalize this trip? Purchased items will be archived. \(state.openCount) item\(state.openCount == 1 ? "" : "s") still open will carry to your next list."
        }
        return "Finalize this trip? Purchased items will be archived and a fresh list will start."
    }

    // MARK: - F-204 / F-205 / F-206 summary strip

    private var summaryStrip: some View {
        Card(padding: DesignTokens.Spacing.space3) {
            HStack(spacing: DesignTokens.Spacing.space2) {
                summaryPill(
                    label: "Open",
                    value: "\(state.openCount)",
                    accent: DesignTokens.accent,
                    active: state.listFilter == .open
                ) { state.setFilter(.open) }
                summaryPill(
                    label: "Estimate",
                    value: formatMoney(state.estimatedTotalCost),
                    accent: DesignTokens.secondaryLabel,
                    active: false,
                    nonInteractive: true
                ) { /* F-205 display only */ }
                summaryPill(
                    label: "Close",
                    value: "\(state.purchasedCount)",
                    accent: DesignTokens.success,
                    active: state.listFilter == .purchased
                ) { state.setFilter(.purchased) }
            }
        }
    }

    private func summaryPill(
        label: String,
        value: String,
        accent: Color,
        active: Bool,
        nonInteractive: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(label).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                Text(value).font(.appMonoBody.weight(.semibold)).foregroundStyle(accent)
            }
            .padding(.horizontal, DesignTokens.Spacing.space3)
            .padding(.vertical, DesignTokens.Spacing.space2)
            .background(active ? DesignTokens.accent.opacity(0.15) : DesignTokens.surface2)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.pill * 2))
        }
        .buttonStyle(.borderless)
        .disabled(nonInteractive)
    }

    // MARK: - Helpers

    /// F-222 — debounce searchQuickFind by 180 ms (web `_shoppingQuickTimer`).
    private func scheduleQuickFindSearch() {
        quickFindDebounceTask?.cancel()
        quickFindDebounceTask = Task { [state] in
            try? await Task.sleep(nanoseconds: 180_000_000)
            if Task.isCancelled { return }
            await state.runQuickFindSearch()
        }
    }
}

// MARK: - Manual add card (F-207..F-219)

private struct ManualAddCard: View {
    @ObservedObject var state: ShoppingState
    @State private var name: String = ""
    @State private var category: String = "other"
    @State private var preferredStore: String = ""
    @State private var price: String = ""
    @State private var quantity: Double = 1
    @State private var note: String = ""

    private let categories: [String] = ["other", "produce", "dairy", "meat", "pantry", "frozen", "beverages",
                                        "snacks", "household", "personal", "bakery", "deli"]

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Add Item Manually").font(.appHeadline.weight(.semibold))
                    Spacer()
                    Button("Hide") { state.manualAddVisible = false }
                        .buttonStyle(GhostButtonStyle())
                }

                // F-209..F-212 — Identify from Photo (deferred v1.1).
                HStack(spacing: 8) {
                    Button {
                        ToastQueue.shared.push(Toast(
                            message: "Photo identify available in v1.1 — type the name for now.",
                            severity: .info
                        ))
                    } label: {
                        Label("Identify from Photo", systemImage: "camera")
                    }
                    .disabled(true)
                    .help("Coming in v1.1 — Gemini-powered photo identification")
                    Spacer()
                }

                // F-213 name
                LabeledField(label: "Item Name") {
                    TextField("e.g. Milk", text: $name)
                        .textFieldStyle(.roundedBorder)
                }

                HStack(spacing: DesignTokens.Spacing.space3) {
                    // F-214 category
                    LabeledField(label: "Category") {
                        Picker("", selection: $category) {
                            ForEach(categories, id: \.self) { Text($0.capitalized).tag($0) }
                        }
                        .labelsHidden()
                    }
                    // F-215 preferred store
                    LabeledField(label: "Preferred Store") {
                        Picker("", selection: $preferredStore) {
                            Text("Any").tag("")
                            ForEach(allStoreOptions(), id: \.self) { Text($0).tag($0) }
                        }
                        .labelsHidden()
                    }
                }

                HStack(spacing: DesignTokens.Spacing.space3) {
                    // F-216 estimate price
                    LabeledField(label: "Estimate Price") {
                        TextField("0.00", text: $price)
                            .textFieldStyle(.roundedBorder)
                    }
                    // F-217 quantity
                    LabeledField(label: "Quantity") {
                        TextField("1", value: $quantity, format: .number)
                            .textFieldStyle(.roundedBorder)
                    }
                }

                // F-218 note
                LabeledField(label: "Note") {
                    TextField("optional note", text: $note)
                        .textFieldStyle(.roundedBorder)
                }

                // F-219 submit
                HStack {
                    Spacer()
                    Button("Add to Shopping List") { submit() }
                        .buttonStyle(PrimaryButtonStyle())
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }

    private func allStoreOptions() -> [String] {
        var combined = state.storeBuckets.frequent ?? []
        combined.append(contentsOf: state.storeBuckets.lowFreq ?? [])
        // Fall back to availableStores if buckets empty.
        if combined.isEmpty { combined = state.availableStores }
        return Array(Set(combined)).sorted()
    }

    private func submit() {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let priceVal = Double(price.trimmingCharacters(in: .whitespaces))
        Task {
            let ok = await state.addItem(
                name: trimmed,
                quantity: max(quantity, 1),
                category: category,
                note: note.trimmingCharacters(in: .whitespaces).isEmpty ? nil : note,
                preferredStore: preferredStore.isEmpty ? nil : preferredStore,
                manualEstimatedPrice: priceVal,
                source: "manual"
            )
            if ok {
                name = ""
                price = ""
                quantity = 1
                note = ""
                state.manualAddVisible = false
            }
        }
    }
}

// MARK: - Quick Find card (F-220..F-225)

private struct QuickFindCard: View {
    @ObservedObject var state: ShoppingState
    let onDebouncedSearch: () -> Void

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Quick Find").font(.appHeadline.weight(.semibold))
                    Spacer()
                    // F-221 collapse
                    Button { state.toggleQuickFind() } label: {
                        Image(systemName: state.quickFindCollapsed ? "chevron.down" : "chevron.up")
                    }
                    .buttonStyle(.borderless)
                    .help(state.quickFindCollapsed ? "Expand" : "Collapse")
                }
                if !state.quickFindCollapsed {
                    HStack(spacing: DesignTokens.Spacing.space2) {
                        // F-222 search input
                        TextField("Search products…", text: $state.quickFindQuery)
                            .textFieldStyle(.roundedBorder)
                            .onChange(of: state.quickFindQuery) { _ in onDebouncedSearch() }
                            .onSubmit { Task { await state.runQuickFindSearch() } }
                        // F-223 preferred store filter
                        Picker("", selection: $state.quickFindStoreFilter) {
                            Text("Any store").tag("")
                            ForEach(allStoreOptions(), id: \.self) { Text($0).tag($0) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 180)
                        // F-224 add manually
                        Button("Add Manually") {
                            state.manualAddVisible = true
                        }
                        .buttonStyle(GhostButtonStyle())
                    }
                    // F-225 results
                    QuickFindResults(state: state)
                }
            }
        }
    }

    private func allStoreOptions() -> [String] {
        var combined = state.storeBuckets.frequent ?? []
        combined.append(contentsOf: state.storeBuckets.lowFreq ?? [])
        if combined.isEmpty { combined = state.availableStores }
        return Array(Set(combined)).sorted()
    }
}

private struct QuickFindResults: View {
    @ObservedObject var state: ShoppingState

    var body: some View {
        Group {
            if state.quickFindQuery.trimmingCharacters(in: .whitespaces).count < 2 {
                EmptyStateView(
                    systemImage: "magnifyingglass",
                    title: "Search the catalog",
                    subtitle: "Type 2+ characters to find products to add, mark low, or mark bought."
                )
                .padding(.vertical, DesignTokens.Spacing.space3)
            } else if state.quickFindResults.isEmpty {
                EmptyStateView(
                    systemImage: "tray",
                    title: "No matching products found",
                    subtitle: "Try a different search, or add it manually.",
                    ctaTitle: "Add \"\(state.quickFindQuery)\" manually"
                ) {
                    state.manualAddVisible = true
                }
            } else {
                VStack(spacing: DesignTokens.Spacing.space2) {
                    ForEach(state.quickFindResults.prefix(5)) { product in
                        QuickFindRow(state: state, product: product)
                    }
                }
            }
        }
    }
}

private struct QuickFindRow: View {
    @ObservedObject var state: ShoppingState
    let product: Product

    var body: some View {
        let existing = state.matchingShoppingEntry(productId: product.id, name: product.name)
        HStack(alignment: .firstTextBaseline, spacing: DesignTokens.Spacing.space2) {
            VStack(alignment: .leading, spacing: 2) {
                Text(product.displayName ?? product.name).font(.appBody)
                Text(meta).font(.appCaption2).foregroundStyle(DesignTokens.secondaryLabel)
                if let existing {
                    Text("In list · Qty \(formatQty(existing.quantity))")
                        .font(.appCaption2).foregroundStyle(DesignTokens.success)
                }
            }
            Spacer(minLength: 8)
            if let existing {
                Button("+1") {
                    Task { await state.increaseQuantity(id: existing.id) }
                }
                .buttonStyle(GhostButtonStyle())
                Button("Bought") {
                    Task { await state.toggleStatus(id: existing.id, nextStatus: "purchased") }
                }
                .buttonStyle(GhostButtonStyle())
            } else {
                Button("Add to Shopping") {
                    Task {
                        await state.addItem(
                            name: product.name,
                            quantity: 1,
                            category: product.category ?? "other",
                            preferredStore: state.quickFindStoreFilter.isEmpty ? nil : state.quickFindStoreFilter,
                            productId: product.id,
                            source: "shopping_quick_find"
                        )
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
            }
            Button("Low") {
                Task { await InventoryState.shared.markLow(productId: product.id, manualLow: true) }
            }
            .buttonStyle(GhostButtonStyle())
        }
        .padding(.vertical, 4)
        .padding(.horizontal, DesignTokens.Spacing.space2)
        .background(DesignTokens.surface2.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.control))
    }

    private var meta: String {
        var parts: [String] = []
        if let category = product.category { parts.append(category.capitalized) }
        if let brand = product.brand, !brand.isEmpty { parts.append(brand) }
        return parts.isEmpty ? "Catalog item" : parts.joined(separator: " · ")
    }
}

// MARK: - Recommendations card (F-226..F-231)

private struct RecommendationsCard: View {
    @ObservedObject var state: ShoppingState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Button { state.toggleRecommendations() } label: {
                        HStack(spacing: 6) {
                            Text("Recommendations").font(.appHeadline.weight(.semibold))
                            Text("\(state.recommendations.count)")
                                .font(.appCaption1.weight(.semibold))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(DesignTokens.accent.opacity(0.18))
                                .clipShape(Capsule())
                        }
                    }
                    .buttonStyle(.borderless)
                    Spacer()
                    // F-229 refresh
                    Button {
                        Task { await state.loadRecommendations() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.borderless)
                    .help("Refresh recommendations")
                }

                if !state.recommendationsCollapsed {
                    // F-230 body
                    if state.recommendations.isEmpty {
                        EmptyStateView(
                            systemImage: "lightbulb",
                            title: "No recommendations yet",
                            subtitle: "Add more purchase history to see ideas here."
                        )
                    } else {
                        VStack(spacing: DesignTokens.Spacing.space2) {
                            ForEach(state.recommendations) { rec in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(rec.label).font(.appBody)
                                        Badge(text: rec.badgeLabel, style: rec.badgeStyle)
                                    }
                                    Spacer()
                                    // F-231 confirm
                                    if let pid = rec.productId {
                                        Button("Confirm") {
                                            Task { await state.confirmRecommendation(productId: pid) }
                                        }
                                        .buttonStyle(PrimaryButtonStyle())
                                    }
                                }
                                .padding(.vertical, 4)
                                .padding(.horizontal, DesignTokens.Spacing.space2)
                                .background(DesignTokens.surface2.opacity(0.5))
                                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.control))
                            }
                        }
                    }
                }
            }
        }
    }
}

// MARK: - Current List card (F-232..F-244, F-258..F-267, F-263..F-264)

private struct CurrentListCard: View {
    @ObservedObject var state: ShoppingState
    let onRename: (ShoppingListItem) -> Void
    let onEditNote: (ShoppingListItem) -> Void
    let onDelete: (ShoppingListItem) -> Void

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    // F-233 collapse toggle
                    Button { state.toggleCurrentList() } label: {
                        HStack {
                            Text("Current List").font(.appHeadline.weight(.semibold))
                            Image(systemName: state.currentListCollapsed ? "chevron.down" : "chevron.up")
                                .foregroundStyle(DesignTokens.tertiaryLabel)
                        }
                    }
                    .buttonStyle(.borderless)
                    Spacer()
                    if state.estimatedTotalCost > 0 {
                        // F-234 total
                        Text("\(totalLabel) \(formatMoney(state.estimatedTotalCost))")
                            .font(.appMonoBody.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    // F-235/F-236/F-237 sort chips
                    sortChips
                }

                if !state.currentListCollapsed {
                    // F-238 table body
                    if state.filteredItems.isEmpty {
                        EmptyStateView(
                            systemImage: "cart",
                            title: emptyTitle,
                            subtitle: state.searchQuery.isEmpty
                                ? "Add items manually or via Quick Find."
                                : "No shopping items match your search."
                        )
                    } else {
                        // F-264 store-grouped sections
                        ForEach(state.groupedFilteredItems(), id: \.store) { group in
                            StoreGroupSection(
                                state: state,
                                storeName: group.store,
                                items: group.items,
                                onRename: onRename,
                                onEditNote: onEditNote,
                                onDelete: onDelete
                            )
                        }
                    }
                    // F-263 skipped group <details>
                    if !state.skippedItems.isEmpty {
                        SkippedSection(state: state)
                    }
                }
            }
        }
    }

    private var totalLabel: String {
        switch state.listFilter {
        case .open:      return "Open total"
        case .purchased: return "Closed total"
        case .all:       return "List total"
        }
    }

    private var emptyTitle: String {
        switch state.listFilter {
        case .open:      return "No open shopping items right now."
        case .purchased: return "No closed shopping items right now."
        case .all:       return "Your shopping list is empty."
        }
    }

    @ViewBuilder
    private var sortChips: some View {
        HStack(spacing: 4) {
            // F-235 A-Z
            sortChip(label: "A↓", active: state.sortMode == .nameAsc) { state.setSort(.nameAsc) }
            // F-236 Z-A
            sortChip(label: "Z↑", active: state.sortMode == .nameDesc) { state.setSort(.nameDesc) }
            // F-237 price toggle
            sortChip(
                label: state.sortMode == .priceAsc ? "$↑" : "$",
                active: state.sortMode == .priceAsc || state.sortMode == .priceDesc
            ) { state.togglePriceSort() }
        }
    }

    private func sortChip(label: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.appCaption1.weight(.semibold))
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(active ? DesignTokens.accent.opacity(0.18) : DesignTokens.surface2)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.pill))
        }
        .buttonStyle(.borderless)
    }
}

// MARK: - Store group section (F-264)

private struct StoreGroupSection: View {
    @ObservedObject var state: ShoppingState
    let storeName: String
    let items: [ShoppingListItem]
    let onRename: (ShoppingListItem) -> Void
    let onEditNote: (ShoppingListItem) -> Void
    let onDelete: (ShoppingListItem) -> Void

    var body: some View {
        let collapsed = state.isStoreGroupCollapsed(storeName)
        VStack(alignment: .leading, spacing: 6) {
            Button { state.toggleStoreGroup(storeName) } label: {
                HStack {
                    Image(systemName: collapsed ? "chevron.right" : "chevron.down")
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                    Text(storeName).font(.appBody.weight(.semibold))
                    Spacer()
                    Text(formatMoney(storeTotal)).font(.appMonoCaption).foregroundStyle(DesignTokens.secondaryLabel)
                    Text("\(items.count)")
                        .font(.appMonoCaption.weight(.semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(DesignTokens.surface2)
                        .clipShape(Capsule())
                }
                .padding(.horizontal, DesignTokens.Spacing.space2)
                .padding(.vertical, 6)
                .background(DesignTokens.surface2.opacity(0.4))
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.control))
            }
            .buttonStyle(.borderless)

            if !collapsed {
                VStack(spacing: DesignTokens.Spacing.space2) {
                    ForEach(items) { item in
                        ShoppingItemRow(
                            state: state,
                            item: item,
                            onRename: { onRename(item) },
                            onEditNote: { onEditNote(item) },
                            onDelete: { onDelete(item) }
                        )
                    }
                }
                .padding(.leading, DesignTokens.Spacing.space2)
            }
        }
    }

    private var storeTotal: Double {
        items.reduce(0) { $0 + ($1.estimateLineTotal ?? 0) }
    }
}

// MARK: - Item row (F-239..F-244, F-258..F-262, F-265..F-267)

private struct ShoppingItemRow: View {
    @ObservedObject var state: ShoppingState
    let item: ShoppingListItem
    let onRename: () -> Void
    let onEditNote: () -> Void
    let onDelete: () -> Void

    /// Backend unit set — kept in sync with src/frontend/index.html `UNIT_OPTIONS`.
    static let unitOptions: [String] = [
        "each", "bottle", "can", "bag", "box", "pack", "roll",
        "gal", "oz", "lb", "count", "dozen", "bunch",
    ]

    @State private var expanded: Bool = false
    @State private var unitInput: String = ""
    @State private var sizeInput: String = ""
    @State private var priceInput: String = ""
    @State private var preferredStoreInput: String = ""
    @State private var actualPriceInput: String = ""

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: DesignTokens.Spacing.space3) {
                // F-259 thumbnail (F-145 mirror)
                ShoppingSnapshotThumb(snapshot: item.latestSnapshot, fallbackInitials: item.productName)

                // Explicit Button so SwiftUI hit-testing reliably fires the
                // expand toggle even with sibling Buttons later in the HStack.
                // `.onTapGesture` on the parent was unreliable when nested
                // Buttons consumed the tap pipeline. The actual-price field is
                // kept OUTSIDE the Button so its TextField stays focusable.
                VStack(alignment: .leading, spacing: 4) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.18)) { expanded.toggle() }
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 6) {
                                Text(item.productName)
                                    .font(.appBody.weight(.semibold))
                                    .strikethrough(item.isPurchased, color: DesignTokens.tertiaryLabel)
                                    .foregroundStyle(item.isPurchased ? DesignTokens.secondaryLabel : DesignTokens.label)
                                Image(systemName: expanded ? "chevron.down" : "chevron.right")
                                    .font(.appCaption2)
                                    .foregroundStyle(DesignTokens.tertiaryLabel)
                            }
                            metaLine
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .help(expanded ? "Hide details" : "Edit unit, size, price")

                    if item.isReadyToBillEditable(session: state.session) {
                        actualPriceField
                    }
                }

                rowTrailing
            }
            .padding(.vertical, 4)
            .contextMenu { rowContextMenu }

            if expanded {
                expandedEditor
                    .transition(.opacity)
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.space2)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.control))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.control)
                .stroke(DesignTokens.border, lineWidth: 0.5)
        )
        .onAppear { syncInputs() }
        .onChange(of: item) { _ in syncInputs() }
    }

    private func syncInputs() {
        let rawUnit = (item.unit ?? "each").lowercased()
        unitInput = Self.unitOptions.contains(rawUnit) ? rawUnit : "each"
        sizeInput = item.sizeLabel ?? ""
        if let p = item.latestPrice?.price {
            priceInput = String(format: "%g", p)
        } else if let mp = item.manualEstimatedPrice {
            priceInput = String(format: "%g", mp)
        } else {
            priceInput = ""
        }
        preferredStoreInput = item.preferredStore ?? item.effectiveStore ?? ""
        if let actual = item.actualPrice {
            actualPriceInput = String(format: "%g", actual)
        } else {
            actualPriceInput = ""
        }
    }

    private var metaLine: some View {
        HStack(spacing: 8) {
            Text(String(format: "Qty %@", formatQty(item.quantity)))
                .font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
            if let total = item.estimateLineTotal {
                Text("· est. \(formatMoney(total))")
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
                if let unitPrice = item.latestPrice?.price {
                    Text("(\(formatMoney(unitPrice)) each)")
                        .font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                }
            }
            if let note = item.note, !note.isEmpty {
                Text("· \(note)").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
            }
            statusBadge
        }
    }

    @ViewBuilder
    private var statusBadge: some View {
        if item.isPurchased {
            Badge(text: "Bought", style: .success)
        } else if item.isOutOfStock {
            Badge(text: "Out of Stock", style: .warning)
        }
    }

    private var rowTrailing: some View {
        HStack(spacing: 6) {
            // F-265 −1
            Button("−1") { Task { await state.decreaseQuantity(id: item.id) } }
                .buttonStyle(GhostButtonStyle())
                .help("Decrease quantity")
            // F-266 Bought / Reopen
            if item.isPurchased {
                Button("Reopen") { Task { await state.togglePurchased(id: item.id) } }
                    .buttonStyle(GhostButtonStyle())
            } else {
                Button("Bought") { Task { await state.togglePurchased(id: item.id) } }
                    .buttonStyle(PrimaryButtonStyle())
            }
        }
    }

    /// F-243 / F-267 actual-price field (ready_to_bill + purchased only).
    private var actualPriceField: some View {
        HStack(spacing: 6) {
            Text("Actual $").font(.appCaption2).foregroundStyle(DesignTokens.secondaryLabel)
            TextField("0.00", text: $actualPriceInput)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 90)
                .onSubmit { submitActualPrice() }
            if item.actualPrice != nil {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(DesignTokens.success)
                    .font(.appCaption1)
            }
        }
    }

    private func submitActualPrice() {
        let trimmed = actualPriceInput.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty {
            Task { await state.updateActualPrice(id: item.id, value: nil) }
            return
        }
        guard let val = Double(trimmed), val.isFinite, val >= 0 else {
            ToastQueue.shared.push(Toast(message: "Enter a valid price", severity: .error))
            return
        }
        Task { await state.updateActualPrice(id: item.id, value: val) }
    }

    /// F-258 inline editor.
    private var expandedEditor: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            Divider()
            HStack(spacing: DesignTokens.Spacing.space3) {
                LabeledField(label: "Store") {
                    Picker("", selection: $preferredStoreInput) {
                        Text("Any").tag("")
                        ForEach(allStoreOptions(), id: \.self) { Text($0).tag($0) }
                    }
                    .labelsHidden()
                }
                LabeledField(label: "Unit") {
                    // Web UNIT_OPTIONS (index.html line 8252) — must match the
                    // backend's accepted unit set used by `update_shopping_item`.
                    Picker("", selection: $unitInput) {
                        ForEach(ShoppingItemRow.unitOptions, id: \.self) { Text($0).tag($0) }
                    }
                    .labelsHidden()
                }
                LabeledField(label: "Size") {
                    TextField("e.g. 1 gal", text: $sizeInput)
                        .textFieldStyle(.roundedBorder)
                }
                LabeledField(label: "Unit Price") {
                    TextField("0.00", text: $priceInput)
                        .textFieldStyle(.roundedBorder)
                }
            }
            HStack {
                // F-258 Update — persist all four + latest_price
                Button("Update") { submitDetails() }
                    .buttonStyle(PrimaryButtonStyle())
                // F-262 Rename
                Button("Rename") { onRename() }
                    .buttonStyle(GhostButtonStyle())
                // F-260 Low / Clear Low
                if let pid = item.productId {
                    Button("Mark Low") {
                        Task { await InventoryState.shared.markLow(productId: pid, manualLow: true) }
                    }
                    .buttonStyle(GhostButtonStyle())
                }
                // F-261 Out of Stock / Reopen
                Button(item.isOutOfStock ? "Reopen" : "Out of Stock") {
                    Task { await state.markOutOfStock(id: item.id, currentStatus: item.status) }
                }
                .buttonStyle(GhostButtonStyle())
                Spacer()
                // F-242 edit note
                Button("Edit Note…") { onEditNote() }
                    .buttonStyle(GhostButtonStyle())
                // F-244 delete
                Button("Delete") { onDelete() }
                    .buttonStyle(DestructiveButtonStyle())
            }
        }
        .padding(.vertical, DesignTokens.Spacing.space2)
    }

    private func submitDetails() {
        let unit = unitInput.trimmingCharacters(in: .whitespaces).lowercased()
        let size = sizeInput.trimmingCharacters(in: .whitespaces)
        let priceTrimmed = priceInput.trimmingCharacters(in: .whitespaces)
        let unitPrice = priceTrimmed.isEmpty ? nil : Double(priceTrimmed)
        if !priceTrimmed.isEmpty, unitPrice == nil {
            ToastQueue.shared.push(Toast(message: "Enter a valid unit price", severity: .error))
            return
        }
        let store = preferredStoreInput.isEmpty ? nil : preferredStoreInput

        Task {
            // Persist store first (if changed) — same endpoint, same body field.
            if (store ?? "") != (item.preferredStore ?? "") {
                await state.updatePreferredStore(id: item.id, store: store)
            }
            await state.updateUnitSizePrice(
                id: item.id,
                unit: unit.isEmpty ? nil : unit,
                sizeLabel: size.isEmpty ? nil : size,
                unitPrice: unitPrice,
                priceStore: store
            )
        }
    }

    @ViewBuilder
    private var rowContextMenu: some View {
        Button(item.isPurchased ? "Reopen" : "Mark Bought") {
            Task { await state.togglePurchased(id: item.id) }
        }
        Button(item.isOutOfStock ? "Reopen" : "Mark Out of Stock") {
            Task { await state.markOutOfStock(id: item.id, currentStatus: item.status) }
        }
        Divider()
        Button("Edit Note…", action: onEditNote)
        Button("Rename…", action: onRename)
        if let pid = item.productId {
            Button("Mark Low Stock") {
                Task { await InventoryState.shared.markLow(productId: pid, manualLow: true) }
            }
        }
        Divider()
        Button("Delete", role: .destructive, action: onDelete)
    }

    private func allStoreOptions() -> [String] {
        var combined = state.storeBuckets.frequent ?? []
        combined.append(contentsOf: state.storeBuckets.lowFreq ?? [])
        if combined.isEmpty { combined = state.availableStores }
        return Array(Set(combined)).sorted()
    }
}

// MARK: - Skipped section (F-263)

private struct SkippedSection: View {
    @ObservedObject var state: ShoppingState
    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(spacing: 4) {
                ForEach(state.skippedItems) { item in
                    HStack(spacing: 8) {
                        Text(item.productName).font(.appBody)
                        if item.quantity > 1 {
                            Text("×\(formatQty(item.quantity))")
                                .font(.appCaption2)
                                .foregroundStyle(DesignTokens.tertiaryLabel)
                        }
                        if let note = item.note, !note.isEmpty {
                            Text("· \(note)").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                        }
                        Spacer()
                        Button("↩ Open") {
                            Task { await state.toggleStatus(id: item.id, nextStatus: "open") }
                        }
                        .buttonStyle(GhostButtonStyle())
                        Button("🗑") {
                            Task { await state.remove(id: item.id) }
                        }
                        .buttonStyle(GhostButtonStyle())
                    }
                    .padding(.vertical, 4)
                    .opacity(0.85)
                }
            }
        } label: {
            Text("Skipped (\(state.skippedItems.count))")
                .font(.appBody.weight(.semibold))
        }
        .padding(.top, DesignTokens.Spacing.space3)
    }
}

// MARK: - Past Trips card (F-252..F-256, F-268)

private struct PastTripsCard: View {
    @ObservedObject var state: ShoppingState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Button { state.togglePastTrips() } label: {
                    HStack {
                        Text("Past Trips").font(.appHeadline.weight(.semibold))
                        Text("\(state.pastTrips.count)")
                            .font(.appCaption1.weight(.semibold))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(DesignTokens.surface2)
                            .clipShape(Capsule())
                        Spacer()
                        Image(systemName: state.pastTripsCollapsed ? "chevron.right" : "chevron.down")
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
                .buttonStyle(.borderless)

                if !state.pastTripsCollapsed {
                    if state.isLoadingPastTrips && state.pastTrips.isEmpty {
                        ForEach(0..<3, id: \.self) { _ in
                            SkeletonView(width: nil, height: 56, cornerRadius: DesignTokens.Radius.control)
                        }
                    } else if state.pastTrips.isEmpty {
                        EmptyStateView(
                            systemImage: "tray",
                            title: "No past trips yet",
                            subtitle: "Finalize a shopping session to see it here."
                        )
                    } else {
                        ForEach(state.pastTrips) { trip in
                            PastTripRow(state: state, trip: trip)
                        }
                    }
                }
            }
        }
    }
}

private struct PastTripRow: View {
    @ObservedObject var state: ShoppingState
    let trip: ShoppingPastTrip

    var body: some View {
        let expanded = state.expandedTripIds.contains(trip.id)
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            Button { Task { await state.togglePastTrip(trip.id) } } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(formatTripDate(trip.closedAt)).font(.appBody.weight(.semibold))
                        Text(summaryLine).font(.appCaption2).foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    Spacer()
                    if let v = trip.variance {
                        Text((v >= 0 ? "+" : "") + formatMoney(v))
                            .font(.appMonoCaption.weight(.semibold))
                            .foregroundStyle(v > 0.01 ? DesignTokens.warning : (v < -0.01 ? DesignTokens.success : DesignTokens.secondaryLabel))
                    }
                    Image(systemName: expanded ? "chevron.down" : "chevron.right")
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
                .padding(.vertical, 6)
                .padding(.horizontal, DesignTokens.Spacing.space2)
                .background(DesignTokens.surface2.opacity(0.4))
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.control))
            }
            .buttonStyle(.borderless)

            if expanded {
                if let detail = state.pastTripDetails[trip.id] {
                    PastTripDetail(state: state, trip: trip, detail: detail)
                } else {
                    SkeletonView(width: nil, height: 60, cornerRadius: DesignTokens.Radius.control)
                }
            }
        }
    }

    private var summaryLine: String {
        let est = trip.estimatedTotalSnapshot.map(formatMoney) ?? "—"
        let act = trip.actualTotalSnapshot.map(formatMoney) ?? "—"
        let purchased = trip.purchasedCount ?? 0
        return "Est \(est) · Actual \(act) · \(purchased) item\(purchased == 1 ? "" : "s")"
    }
}

private struct PastTripDetail: View {
    @ObservedObject var state: ShoppingState
    let trip: ShoppingPastTrip
    let detail: ShoppingSessionDetailResponse

    var body: some View {
        let purchased = detail.items.filter { $0.isPurchased }
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            if purchased.isEmpty {
                Text("No purchased items recorded for this trip.")
                    .font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    .padding(.horizontal, DesignTokens.Spacing.space2)
            } else {
                VStack(spacing: 4) {
                    ForEach(purchased) { item in
                        HStack {
                            Text(item.productName).font(.appBody)
                            Spacer()
                            Text("× \(formatQty(item.quantity))")
                                .font(.appMonoCaption).foregroundStyle(DesignTokens.tertiaryLabel)
                            Text(item.estimateLineTotal.map(formatMoney) ?? "—")
                                .frame(width: 80, alignment: .trailing)
                                .font(.appMonoCaption).foregroundStyle(DesignTokens.secondaryLabel)
                            if let actual = item.actualPrice {
                                Text(formatMoney(actual * item.quantity))
                                    .frame(width: 80, alignment: .trailing)
                                    .font(.appMonoCaption.weight(.semibold))
                            } else {
                                Text("—")
                                    .frame(width: 80, alignment: .trailing)
                                    .font(.appMonoCaption).foregroundStyle(DesignTokens.tertiaryLabel)
                            }
                        }
                        .padding(.horizontal, DesignTokens.Spacing.space2)
                    }
                }
            }
            HStack {
                Spacer()
                // F-268 reopen past trip
                Button("↩ Reopen trip") {
                    Task { await state.reopenSession(sessionId: trip.id) }
                }
                .buttonStyle(GhostButtonStyle())
            }
            .padding(.horizontal, DesignTokens.Spacing.space2)
        }
        .padding(.vertical, DesignTokens.Spacing.space2)
    }
}

// MARK: - Thumbnail (F-259, parallels F-145/F-158)

private struct ShoppingSnapshotThumb: View {
    let snapshot: ShoppingLatestSnapshot?
    let fallbackInitials: String

    @State private var isHovering = false
    @State private var showPopover = false

    private var resolvedURL: URL? {
        guard let path = snapshot?.imageUrl, !path.isEmpty else { return nil }
        let base = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                ?? AppConstants.defaultAPIBaseURL
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
            RoundedRectangle(cornerRadius: 6).fill(DesignTokens.surface2)
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
        let chars = parts.compactMap { $0.first.map(String.init) }.joined()
        return chars.isEmpty ? "·" : chars.uppercased()
    }
}

// MARK: - Small helpers

private struct LabeledField<Content: View>: View {
    let label: String
    @ViewBuilder var content: () -> Content
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            content()
        }
    }
}

private extension ShoppingListItem {
    func isReadyToBillEditable(session: ShoppingSession?) -> Bool {
        session?.isReadyToBill == true && isPurchased
    }
}

private func formatMoney(_ value: Double) -> String {
    let f = NumberFormatter()
    f.numberStyle = .currency
    f.locale = Locale(identifier: "en_US")
    f.maximumFractionDigits = 2
    return f.string(from: value as NSNumber) ?? "$\(value)"
}

private func formatQty(_ value: Double) -> String {
    if value.rounded() == value { return String(format: "%.0f", value) }
    return String(format: "%g", value)
}

private func formatTripDate(_ iso: String?) -> String {
    guard let iso else { return "—" }
    let parsers: [DateFormatter] = {
        let f1 = DateFormatter()
        f1.locale = Locale(identifier: "en_US_POSIX")
        f1.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        let f2 = DateFormatter()
        f2.locale = Locale(identifier: "en_US_POSIX")
        f2.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return [f1, f2]
    }()
    let date = parsers.lazy.compactMap { $0.date(from: iso) }.first ?? ISO8601DateFormatter().date(from: iso)
    guard let date else { return iso }
    let out = DateFormatter()
    out.dateStyle = .medium
    out.timeStyle = .short
    return out.string(from: date)
}

#Preview("ShoppingList") {
    ShoppingListView().frame(width: 900, height: 720)
}
