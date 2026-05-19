import SwiftUI

/// Dashboard view — covers all 45 rows from FEATURE_PARITY_REGISTRY.md (F-001 … F-045).
/// Section markers in this file map directly to F-IDs so the registry can be
/// updated when individual rows change.
struct DashboardView: View {
    @StateObject private var dashboard = DashboardState.shared
    @StateObject private var inventory = InventoryState.shared
    @StateObject private var shopping = ShoppingState.shared
    @StateObject private var finance = FinanceState.shared
    @EnvironmentObject private var router: Router
    @EnvironmentObject private var appState: AppState

    @State private var shoppingPreviewExpanded = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space5) {
                headerWithSubtitle                                // F-000 — Dashboard title + subtitle

                if appState.isDemoMode {
                    demoHero                                      // F-001 … F-008
                }

                if let lb = dashboard.leaderboard, !lb.rankings.isEmpty {
                    leaderboardCard(lb)                           // F-009 … F-014
                } else if dashboard.leaderboard != nil {
                    leaderboardEmptyState()                       // F-014
                }

                if let untagged = dashboard.untagged, untagged.untaggedCount > 0 {
                    untaggedBanner(untagged)                      // F-015, F-016
                }

                countersStrip                                     // F-017, F-018, F-019

                spendingByCategoryCard                            // F-020 … F-026

                threeTileRow                                      // F-027/028, F-037/038, F-040/041
                                                                  // (combined Low Stock + Top Picks + Shopping)

                receiptsActivityCard                              // F-030 … F-036
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .background(DesignTokens.background)
        .navigationTitle("Dashboard")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await refreshAll() } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Refresh all dashboard data")
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .onAppear { triggerRefresh() }
    }

    /// Fire-and-forget refresh — NOT bound to view lifecycle so SwiftUI can't
    /// cancel the in-flight URLSession requests when the view's identity
    /// changes. (Using `.task { ... }` caused a 200ms cancel-and-retry loop
    /// because the closure was being re-invoked on every body re-evaluation.)
    private func triggerRefresh() {
        Task.detached(priority: .userInitiated) {
            await dashboard.loadAll()
        }
        Task.detached(priority: .userInitiated) {
            await inventory.loadInventory()
        }
        Task.detached(priority: .userInitiated) {
            await shopping.loadList()
        }
        Task.detached(priority: .userInitiated) {
            await finance.loadBills()
        }
    }

    private func refreshAll() async {
        async let _ = dashboard.loadAll()
        async let _ = inventory.loadInventory()
        async let _ = shopping.loadList()
        async let _ = finance.loadBills()
    }

    // MARK: - Header with subtitle (web parity)

    private var headerWithSubtitle: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: DesignTokens.Spacing.space2) {
                Text("Dashboard")
                    .font(.appLargeTitle)
                    .foregroundStyle(DesignTokens.label)
                Text("Track groceries, dining out, and household expenses in one place")
                    .font(.appBody)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
    }

    // MARK: - 3-tile row (Low Stock / Top Picks / Shopping List)

    private var threeTileRow: some View {
        LazyVGrid(
            columns: [
                GridItem(.flexible(), spacing: DesignTokens.Spacing.space3),
                GridItem(.flexible(), spacing: DesignTokens.Spacing.space3),
                GridItem(.flexible(), spacing: DesignTokens.Spacing.space3)
            ],
            alignment: .leading,
            spacing: DesignTokens.Spacing.space3
        ) {
            lowStockTile
            topPicksTile
            shoppingListTile
        }
    }

    // Each tile shows a header (icon + name + count) AND a vertical item list
    // with per-item action buttons. Mirrors the web's expanded-tile layout.
    private var lowStockTile: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                tileHeader(title: "Low Stock",
                           systemImage: "exclamationmark.triangle.fill",
                           tint: DesignTokens.warning,
                           badge: "\(inventory.lowStockItems.count)",
                           onBadgeTap: { dashboard.toggleLowStockTile() })

                if !dashboard.lowStockTileCollapsed {
                    if inventory.lowStockItems.isEmpty {
                        Text("All items well-stocked!")
                            .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    } else {
                        ForEach(inventory.lowStockItems.prefix(6)) { item in
                            lowStockRow(item)
                        }
                        if inventory.lowStockItems.count > 6 {
                            Button("View all (\(inventory.lowStockItems.count))") {
                                router.activeTab = .inventory
                            }
                            .buttonStyle(GhostButtonStyle())
                        }
                    }
                }
            }
        }
    }

    private func lowStockRow(_ item: InventoryItem) -> some View {
        HStack(spacing: 6) {
            LowStockPill(severity: item.quantity <= 0 ? .critical : .low)
            Text(truncate(item.displayName, length: 14))
                .font(.appCaption1).foregroundStyle(DesignTokens.label)
            Spacer()
            actionChip(text: "Confirm", systemImage: "checkmark") {
                Task { await inventory.markLow(productId: item.productId) }
            }
            actionChip(text: "Cart", systemImage: "cart.fill") {
                Task { await shopping.add(productName: item.displayName, quantity: 1, source: "low_stock", productId: item.productId) }
            }
        }
    }

    private var topPicksTile: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                tileHeader(title: "Top Picks",
                           systemImage: "lightbulb.fill",
                           tint: DesignTokens.accent,
                           badge: "\(dashboard.recommendations.count)",
                           onBadgeTap: { dashboard.toggleTopPicksTile() })

                if !dashboard.topPicksTileCollapsed {
                    if dashboard.recommendations.isEmpty {
                        Text("No recommendations yet")
                            .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    } else {
                        ForEach(dashboard.recommendations.prefix(5)) { rec in
                            topPickRow(rec)
                        }
                        if dashboard.recommendations.count > 5 {
                            Button("View all (\(dashboard.recommendations.count))") {
                                router.activeTab = .shopping
                            }
                            .buttonStyle(GhostButtonStyle())
                        }
                    }
                }
            }
        }
    }

    private func topPickRow(_ rec: Recommendation) -> some View {
        HStack(spacing: 6) {
            Text(categoryEmoji(for: rec.category ?? "")).font(.system(size: 12))
            Text(truncate(rec.label, length: 14))
                .font(.appCaption1).foregroundStyle(DesignTokens.label)
            Spacer()
            actionChip(text: "Add", systemImage: "cart.fill") {
                Task { await shopping.add(productName: rec.label, quantity: 1, source: "recommendation", productId: rec.productId) }
            }
            actionChip(text: "Confirm", systemImage: "checkmark") {
                // Phase: mark recommendation applied (server endpoint exists, can wire later)
            }
        }
    }

    private var shoppingListTile: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                tileHeader(
                    title: "Shopping List",
                    systemImage: "cart.fill",
                    tint: DesignTokens.secondaryLabel,
                    badge: "\(shopping.pendingCount)",
                    trailing: shopping.estimatedTotal > 0 ? String(format: "$%.2f", shopping.estimatedTotal) : nil,
                    onBadgeTap: { dashboard.toggleShoppingTile() }
                )

                if !dashboard.shoppingTileCollapsed {
                    if shopping.items.isEmpty {
                        Text("List is empty")
                            .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    } else {
                        ForEach(shopping.items.filter(\.isPending).prefix(5)) { item in
                            shoppingListRowInline(item)
                        }
                        if shopping.pendingCount > 5 {
                            Button("View all (\(shopping.pendingCount))") {
                                router.activeTab = .shopping
                            }
                            .buttonStyle(GhostButtonStyle())
                        }
                    }
                }
            }
        }
    }

    private func shoppingListRowInline(_ item: ShoppingListItem) -> some View {
        HStack(spacing: 6) {
            Text(truncate(item.productName, length: 16))
                .font(.appCaption1).foregroundStyle(DesignTokens.label)
            if item.quantity > 1 {
                Text("×\(Int(item.quantity))")
                    .font(.appCaption2.monospaced())
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            Spacer()
            if let price = item.manualEstimatedPrice ?? item.actualPrice, price > 0 {
                Text(String(format: "$%.2f", price))
                    .font(.appMonoCaption.weight(.medium))
                    .foregroundStyle(DesignTokens.label)
            }
        }
    }

    /// Shared tile header — icon + title + count pill (+ optional trailing $).
    /// The count badge is tappable: passing `onBadgeTap` makes the badge a
    /// Button that toggles tile collapse (matches the web's behavior).
    private func tileHeader(
        title: String,
        systemImage: String,
        tint: Color,
        badge: String,
        trailing: String? = nil,
        onBadgeTap: (() -> Void)? = nil
    ) -> some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage).foregroundStyle(tint)
            Text(title).font(.appHeadline)
            Spacer()
            if let trailing {
                Text(trailing)
                    .font(.appCaption1.monospaced())
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
            if let onBadgeTap {
                Button(action: onBadgeTap) {
                    Text(badge)
                        .font(.appMonoCaption.weight(.semibold))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(tint.opacity(0.15))
                        .foregroundStyle(tint)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
                .help("Click to expand/collapse")
            } else {
                Text(badge)
                    .font(.appMonoCaption.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(tint.opacity(0.15))
                    .foregroundStyle(tint)
                    .clipShape(Capsule())
            }
        }
    }

    /// Compact action chip — icon + tiny label. Used inside Low Stock + Top Picks rows.
    private func actionChip(text: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 3) {
                Image(systemName: systemImage).font(.system(size: 9, weight: .semibold))
                Text(text).font(.appCaption2.weight(.medium))
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(DesignTokens.accentDim)
            .foregroundStyle(DesignTokens.accent)
            .clipShape(RoundedRectangle(cornerRadius: 5))
        }
        .buttonStyle(.plain)
    }

    // MARK: - F-001 … F-008  Demo hero card

    private var demoHero: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                Text("Welcome to the LocalOCR Extended demo")
                    .font(.appTitle2)
                Text("You're browsing in read-only mode. Sign in to track your own household.")
                    .font(.appBody)
                    .foregroundStyle(DesignTokens.secondaryLabel)

                HStack(spacing: DesignTokens.Spacing.space2) {
                    Button("Sign In") { Task { await AuthState.shared.logout() } }
                        .buttonStyle(PrimaryButtonStyle())
                    Button("Shopping Demo") { router.activeTab = .shopping }
                        .buttonStyle(SecondaryButtonStyle())
                    Button("Restaurant Demo") { router.activeTab = .restaurant }
                        .buttonStyle(SecondaryButtonStyle())
                }

                LazyVGrid(
                    columns: [
                        GridItem(.flexible(), spacing: DesignTokens.Spacing.space3),
                        GridItem(.flexible(), spacing: DesignTokens.Spacing.space3),
                        GridItem(.flexible(), spacing: DesignTokens.Spacing.space3)
                    ],
                    spacing: DesignTokens.Spacing.space3
                ) {
                    demoMiniCard(title: "Grocery", subtitle: "Inventory, shopping, low stock")
                    demoMiniCard(title: "Restaurant", subtitle: "Dining receipts and repeat orders")
                    demoMiniCard(title: "Expenses", subtitle: "Services, gifts, fees, and budgets")
                }

                Text("Read-only — no real changes are saved in demo mode.")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
        }
    }

    private func demoMiniCard(title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.appHeadline)
            Text(subtitle).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        }
        .padding(DesignTokens.Spacing.space3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
    }

    // MARK: - F-009 … F-014  Household leaderboard

    private func leaderboardCard(_ lb: Leaderboard) -> some View {
        // Match web: horizontal top-3 cards by default, "Show full ranking"
        // button toggles into vertical full list.
        let collapsed = dashboard.leaderboardCollapsed
        let leaders = lb.leaders ?? Array(lb.rankings.prefix(3))
        return Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                if collapsed {
                    leaderboardCollapsedRow(leaders: leaders, lb: lb)
                } else {
                    rankingHeader(lb)
                    rankingFullList(lb)
                    rankingFooter(lb)
                }
            }
        }
    }

    /// Web-style collapsed row: HOUSEHOLD RANKING label + top 3 cards + Show-full button.
    private func leaderboardCollapsedRow(leaders: [LeaderboardRow], lb: Leaderboard) -> some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            Text("HOUSEHOLD RANKING")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(DesignTokens.secondaryLabel)
                .frame(width: 160, alignment: .leading)
            ForEach(Array(leaders.prefix(3).enumerated()), id: \.element.id) { idx, row in
                leaderTopCard(rank: idx + 1, row: row)
            }
            Spacer()
            Button("Show full ranking") {
                dashboard.toggleLeaderboardCollapsed()
            }
            .buttonStyle(SecondaryButtonStyle())
        }
    }

    /// Top-3 card pill — matches web design.
    private func leaderTopCard(rank: Int, row: LeaderboardRow) -> some View {
        HStack(spacing: 8) {
            Text("\(rank)\(ordinalSuffix(rank))")
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(rank == 1 ? DesignTokens.warning : DesignTokens.secondaryLabel)
            Text(row.avatarEmoji ?? "👤").font(.system(size: 18))
            VStack(alignment: .leading, spacing: 0) {
                Text(truncate(row.displayName, length: 8))
                    .font(.appBody.weight(.medium))
                    .foregroundStyle(DesignTokens.label)
                Text("\(Int(row.score ?? 0))")
                    .font(.appMonoCaption.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(rank == 1 ? DesignTokens.accent.opacity(0.5) : Color.clear, lineWidth: 1)
        )
    }

    private func leaderboardEmptyState() -> some View {
        Card {
            Text("No household rankings yet — start uploading receipts to earn points.")
                .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private func rankingHeader(_ lb: Leaderboard) -> some View {
        HStack {
            Text("HOUSEHOLD RANKING")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(DesignTokens.secondaryLabel)
            if let month = lb.month {
                Text(month).font(.appCaption1.monospaced()).foregroundStyle(DesignTokens.tertiaryLabel)
            }
            Spacer()
            Button {
                dashboard.toggleLeaderboardCollapsed()
            } label: {
                Image(systemName: dashboard.leaderboardCollapsed ? "chevron.down" : "chevron.up")
                    .font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.borderless)
            .foregroundStyle(DesignTokens.secondaryLabel)
            .accessibilityLabel(dashboard.leaderboardCollapsed ? "Expand leaderboard" : "Collapse leaderboard")
        }
    }

    private func rankingRow(leaders: [LeaderboardRow], lb: Leaderboard) -> some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            ForEach(Array(leaders.enumerated()), id: \.element.id) { idx, row in
                leaderChip(rank: idx + 1, row: row)
            }
            Spacer()
            if let rank = lb.currentUserRank, let total = lb.totalUsers {
                rankingSelfBadge(rank: rank, total: total)
            }
        }
    }

    private func rankingFullList(_ lb: Leaderboard) -> some View {
        VStack(spacing: 6) {
            ForEach(Array(lb.rankings.enumerated()), id: \.element.id) { idx, row in
                rankingFullRow(idx: idx, row: row)
            }
        }
    }

    private func rankingFullRow(idx: Int, row: LeaderboardRow) -> some View {
        let rank = row.rank ?? (idx + 1)
        return HStack(spacing: 10) {
            Text("\(rank)\(ordinalSuffix(rank))")
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(rank == 1 ? DesignTokens.warning : DesignTokens.secondaryLabel)
                .frame(width: 32, alignment: .leading)
            Text(row.avatarEmoji ?? "👤").font(.system(size: 14))
            Text(row.displayName).font(.appBody)
            Spacer()
            Text("\(Int(row.score ?? 0))")
                .font(.appMonoBody.weight(.semibold))
                .foregroundStyle(DesignTokens.label)
        }
        .padding(.vertical, 2)
    }

    private func rankingFooter(_ lb: Leaderboard) -> some View {
        HStack {
            Spacer()
            if let rank = lb.currentUserRank, let total = lb.totalUsers {
                Text("Your rank: #\(rank) of \(total)")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
        .padding(.top, DesignTokens.Spacing.space1)
    }

    private func leaderChip(rank: Int, row: LeaderboardRow) -> some View {
        HStack(spacing: 6) {
            Text("\(rank)\(ordinalSuffix(rank))")
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(rank == 1 ? DesignTokens.warning : DesignTokens.secondaryLabel)
            Text(row.avatarEmoji ?? "👤").font(.system(size: 14))
            Text(truncate(row.displayName, length: 10)).font(.appCaption1)
            Text("\(Int(row.score ?? 0))")
                .font(.appMonoCaption.weight(.semibold))
                .foregroundStyle(DesignTokens.label)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 4)
        .background(DesignTokens.surface2)
        .clipShape(Capsule())
    }

    private func ordinalSuffix(_ n: Int) -> String {
        switch n { case 1: return "st"; case 2: return "nd"; case 3: return "rd"; default: return "th" }
    }

    private func truncate(_ s: String, length: Int) -> String {
        s.count > length ? "\(s.prefix(length))…" : s
    }

    private func rankingSelfBadge(rank: Int, total: Int) -> some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text("You").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            Text("#\(rank) of \(total)")
                .font(.appBody.weight(.semibold))
                .foregroundStyle(DesignTokens.accent)
        }
    }

    // MARK: - F-015, F-016  Untagged banner

    private func untaggedBanner(_ stats: AttributionStats) -> some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            Image(systemName: "lightbulb.fill")
                .foregroundStyle(DesignTokens.warning)
            Text("\(stats.untaggedCount) receipts untagged")
                .font(.appBody)
                .foregroundStyle(DesignTokens.label)
            Spacer()
            Button("Tag now →") { router.activeTab = .receipts }
                .buttonStyle(GhostButtonStyle())
                .foregroundStyle(DesignTokens.accent)
        }
        .padding(.horizontal, DesignTokens.Spacing.space4)
        .padding(.vertical, DesignTokens.Spacing.space2)
        .background(DesignTokens.warningDim)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
    }

    // MARK: - F-017, F-018, F-019  LOW / INV / PROD counters

    private var countersStrip: some View {
        Card {
            HStack(spacing: 0) {
                Button { router.activeTab = .inventory } label: {
                    counter(label: "LOW", value: inventory.lowStockItems.count, color: DesignTokens.warning)
                }
                .buttonStyle(.plain)
                .help("Low-stock inventory items")

                Divider().frame(height: 44).padding(.horizontal, 8)

                Button { router.activeTab = .inventory } label: {
                    counter(label: "INV", value: inventory.items.count, color: DesignTokens.success)
                }
                .buttonStyle(.plain)
                .help("Total inventory items")

                Divider().frame(height: 44).padding(.horizontal, 8)

                Button { router.activeTab = .inventory } label: {
                    counter(label: "PROD", value: dashboard.productsCount, color: DesignTokens.accent)
                }
                .buttonStyle(.plain)
                .help("Distinct products in catalog")
            }
        }
    }

    private func counter(label: String, value: Int, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(label).font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.secondaryLabel)
            Text("\(value)").font(.appTitle1.weight(.bold)).foregroundStyle(color)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - F-020 … F-025  Spending by Category

    private var spendingByCategoryCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                spendingHeader()
                if dashboard.spendingCardCollapsed { EmptyView() } else {
                    spendingBody()
                }
            }
        }
    }

    private func spendingHeader() -> some View {
        HStack {
            HStack(spacing: 6) {
                Image(systemName: "cart").foregroundStyle(DesignTokens.accent)
                Text("Spending by Category").font(.appTitle2)
            }
            Spacer()
            if let s = finance.spending {
                Text(String(format: "$%.2f", s.categories.reduce(0) { $0 + $1.total }))
                    .font(.appMonoBody.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
            }
            Button {
                dashboard.toggleSpendingCardCollapsed()
            } label: {
                Image(systemName: dashboard.spendingCardCollapsed ? "chevron.down" : "chevron.up")
                    .font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.borderless)
            .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    @ViewBuilder
    private func spendingBody() -> some View {
        if let error = dashboard.spendingError {
            Text(error)
                .font(.appCaption1).foregroundStyle(DesignTokens.error)
        } else if dashboard.isSpendingLoading && finance.spending == nil {
            Text("Loading…").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
        } else if let s = finance.spending, !s.categories.isEmpty {
            let total = s.categories.reduce(0) { $0 + $1.total }
            let displayed = dashboard.spendingShowAll ? s.categories : Array(s.categories.prefix(5))
            ForEach(Array(displayed.enumerated()), id: \.element.id) { idx, cat in
                categoryBar(category: cat, total: total, color: palette[idx % palette.count])
            }
            if dashboard.fixedExpectedTotal > 0 {
                fixedObligationsRow()
            }
            if s.categories.count > 5 {
                Button(dashboard.spendingShowAll ? "Show less" : "Show more (\(s.categories.count - 5))") {
                    dashboard.toggleSpendingShowAll()
                }
                .buttonStyle(GhostButtonStyle())
            }
        } else {
            Text("No spending yet — confirm a few receipts to populate this card.")
                .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private func categoryBar(category: SpendingCategoryTotal, total: Double, color: Color) -> some View {
        // backend's share_pct preferred; fallback to computed.
        let pct: Double = {
            if let s = category.sharePct { return Double(s) / 100.0 }
            return total > 0 ? category.total / total : 0
        }()
        let categoryColor = paletteColor(for: category.category)
        return HStack(spacing: DesignTokens.Spacing.space3) {
            HStack(spacing: 4) {
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                Text(categoryEmoji(for: category.category)).font(.system(size: 14))
                Text(category.category).font(.appBody)
            }
            .frame(width: 160, alignment: .leading)
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 6).fill(DesignTokens.surface2)
                    RoundedRectangle(cornerRadius: 6).fill(categoryColor).frame(width: proxy.size.width * pct)
                }
            }
            .frame(height: 14)
            Text("\(Int(pct * 100))%")
                .font(.appCaption1.monospaced()).foregroundStyle(DesignTokens.tertiaryLabel)
                .frame(width: 36, alignment: .trailing)
            VStack(alignment: .trailing, spacing: 0) {
                Text(String(format: "$%.2f", category.total))
                    .font(.appMonoBody.weight(.medium))
                    .foregroundStyle(DesignTokens.label)
                if let delta = category.deltaPct {
                    deltaLabel(delta)
                }
            }
            .frame(width: 110, alignment: .trailing)
        }
    }

    @ViewBuilder
    private func deltaLabel(_ pct: Int) -> some View {
        let isDown = pct < 0
        let arrow = isDown ? "↓" : "↑"
        let absVal = abs(pct)
        Text("\(arrow) \(absVal)% vs last")
            .font(.appCaption2.monospaced())
            .foregroundStyle(isDown ? DesignTokens.success : DesignTokens.error)
    }

    /// Fixed obligations row — appended below regular categories, with
    /// 'X% paid' badge instead of 'vs last' delta.
    private func fixedObligationsRow() -> some View {
        let pct = Double(dashboard.fixedPaidPct) / 100.0
        let color = paletteColor(for: "fixed")
        return HStack(spacing: DesignTokens.Spacing.space3) {
            HStack(spacing: 4) {
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                Text("📌").font(.system(size: 14))
                Text("Fixed").font(.appBody)
            }
            .frame(width: 160, alignment: .leading)
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 6).fill(DesignTokens.surface2)
                    RoundedRectangle(cornerRadius: 6).fill(color).frame(width: proxy.size.width * pct)
                }
            }
            .frame(height: 14)
            Spacer().frame(width: 36)
            VStack(alignment: .trailing, spacing: 0) {
                Text(String(format: "$%.2f", dashboard.fixedExpectedTotal))
                    .font(.appMonoBody.weight(.medium))
                    .foregroundStyle(DesignTokens.label)
                Text("\(dashboard.fixedPaidPct)% paid")
                    .font(.appCaption2.monospaced())
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
            .frame(width: 110, alignment: .trailing)
        }
    }

    private func paletteColor(for category: String) -> Color {
        switch category.lowercased() {
        case "grocery":       return Color(red: 0.27, green: 0.55, blue: 0.95)
        case "other":         return Color(red: 0.95, green: 0.55, blue: 0.27)
        case "dining":        return Color(red: 0.27, green: 0.78, blue: 0.55)
        case "subscriptions": return Color(red: 0.95, green: 0.78, blue: 0.27)
        case "fixed":         return Color(red: 0.58, green: 0.55, blue: 0.95)
        case "household":     return Color(red: 0.95, green: 0.42, blue: 0.55)
        case "utilities":     return Color(red: 0.27, green: 0.78, blue: 0.78)
        default:              return DesignTokens.secondaryLabel
        }
    }

    private func categoryEmoji(for category: String) -> String {
        switch category.lowercased() {
        case "grocery":       return "🛒"
        case "other":         return "📦"
        case "dining":        return "🍽"
        case "subscriptions": return "🔁"
        case "fixed":         return "📌"
        case "household":     return "🏠"
        case "utilities":     return "💡"
        default:              return "💸"
        }
    }

    private var palette: [Color] {
        [DesignTokens.accent, DesignTokens.warning, DesignTokens.success, DesignTokens.error, DesignTokens.secondaryLabel]
    }

    // MARK: - F-027, F-028, F-029  Low Stock alert card

    private var lowStockCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(DesignTokens.warning)
                    Text("Low Stock").font(.appTitle2)
                    Spacer()
                    if inventory.lowStockItems.count > 0 {
                        Text("\(inventory.lowStockItems.count)")
                            .font(.appMonoCaption.weight(.semibold))
                            .padding(.horizontal, 8).padding(.vertical, 2)
                            .background(DesignTokens.warningDim)
                            .foregroundStyle(DesignTokens.warning)
                            .clipShape(Capsule())
                    }
                }
                if inventory.lowStockItems.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(DesignTokens.success)
                        Text("All items well-stocked!")
                            .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    }
                } else {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(inventory.lowStockItems.prefix(8)) { item in
                            HStack {
                                Text(item.displayName).font(.appBody)
                                Spacer()
                                LowStockPill(severity: item.quantity <= 0 ? .critical : .low)
                            }
                            .padding(.vertical, 2)
                        }
                        if inventory.lowStockItems.count > 8 {
                            Button("View all (\(inventory.lowStockItems.count))") {
                                router.activeTab = .inventory
                            }
                            .buttonStyle(GhostButtonStyle())
                        }
                    }
                }
            }
        }
    }

    // MARK: - F-030 … F-036  Receipts Activity card

    private var receiptsActivityCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                HStack {
                    Text("Receipts Processed").font(.appTitle2)
                    Spacer()
                    grainPicker
                }
                activityBody
            }
        }
    }

    private var grainPicker: some View {
        Picker("Grain", selection: Binding(
            get: { dashboard.activityGrain },
            set: { dashboard.setActivityGrain($0) }
        )) {
            ForEach(DashboardState.ActivityGrain.allCases) { g in
                Text(g.label).tag(g)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .frame(width: 220)
    }

    @ViewBuilder
    private var activityBody: some View {
        if let error = dashboard.activityError {
            Text("Could not load receipt activity. \(error)")
                .font(.appCaption1).foregroundStyle(DesignTokens.error)
        } else if dashboard.isActivityLoading && dashboard.receiptsActivity.isEmpty {
            Text("Loading…").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
        } else if dashboard.receiptsActivity.isEmpty {
            Text("No receipts processed yet.")
                .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        } else {
            HStack(spacing: DesignTokens.Spacing.space5) {
                statColumn(title: "TOTAL", value: "\(processedTotalCount)",
                           sub: String(format: "$%.2f", processedTotalAmount))
                statColumn(title: "AVG / \(dashboard.activityGrain.label.uppercased())",
                           value: String(format: "%.1f", avgPerBucket),
                           sub: String(format: "$%.2f", processedTotalAmount / Double(max(dashboard.receiptsActivity.count, 1))))
                statColumn(title: "PEAK", value: "\(peakDayCount)", sub: peakDayLabel)
            }
            sparkline.frame(height: 90).padding(.top, 4)
        }
    }

    private var processedTotalCount: Int { dashboard.receiptsActivity.filter { $0.total > 0 }.count }
    private var processedTotalAmount: Double { dashboard.receiptsActivity.reduce(0) { $0 + $1.total } }
    private var avgPerBucket: Double {
        let total = dashboard.receiptsActivity.reduce(0.0) { $0 + ($1.total > 0 ? 1 : 0) }
        return total / Double(max(dashboard.receiptsActivity.count, 1))
    }
    private var peakDayCount: Int { Int(dashboard.receiptsActivity.map(\.total).max() ?? 0) }
    private var peakDayLabel: String {
        guard let peak = dashboard.receiptsActivity.max(by: { $0.total < $1.total }) else { return "—" }
        return "\(peak.month) · $\(Int(peak.total))"
    }

    private func statColumn(title: String, value: String, sub: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.secondaryLabel)
            Text(value).font(.appTitle2.weight(.bold)).foregroundStyle(DesignTokens.label)
            Text(sub).font(.appCaption2.monospaced()).foregroundStyle(DesignTokens.tertiaryLabel)
        }
    }

    private var sparkline: some View {
        GeometryReader { proxy in
            let points = dashboard.receiptsActivity.map(\.total)
            let maxVal = max(points.max() ?? 1, 1)
            Path { path in
                guard points.count > 1 else { return }
                let stepX = proxy.size.width / CGFloat(points.count - 1)
                for (idx, val) in points.enumerated() {
                    let x = CGFloat(idx) * stepX
                    let y = proxy.size.height - CGFloat(val / maxVal) * proxy.size.height
                    if idx == 0 { path.move(to: CGPoint(x: x, y: y)) }
                    else { path.addLine(to: CGPoint(x: x, y: y)) }
                }
            }
            .stroke(DesignTokens.accent, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
            Path { path in
                guard points.count > 1 else { return }
                let stepX = proxy.size.width / CGFloat(points.count - 1)
                path.move(to: CGPoint(x: 0, y: proxy.size.height))
                for (idx, val) in points.enumerated() {
                    let x = CGFloat(idx) * stepX
                    let y = proxy.size.height - CGFloat(val / maxVal) * proxy.size.height
                    path.addLine(to: CGPoint(x: x, y: y))
                }
                path.addLine(to: CGPoint(x: proxy.size.width, y: proxy.size.height))
                path.closeSubpath()
            }
            .fill(DesignTokens.accent.opacity(0.12))
        }
    }

    // MARK: - F-037, F-038, F-039  Top Picks card

    private var topPicksCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                HStack {
                    Image(systemName: "lightbulb").foregroundStyle(DesignTokens.accent)
                    Text("Top Picks").font(.appTitle2)
                    Spacer()
                    if !dashboard.recommendations.isEmpty {
                        Text("\(dashboard.recommendations.count)")
                            .font(.appMonoCaption.weight(.semibold))
                            .padding(.horizontal, 8).padding(.vertical, 2)
                            .background(DesignTokens.accentDim)
                            .foregroundStyle(DesignTokens.accent)
                            .clipShape(Capsule())
                    }
                }
                if dashboard.recommendations.isEmpty {
                    Text("No recommendations yet — confirm a few receipts to seed deal/seasonal picks.")
                        .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                } else {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(dashboard.recommendations.prefix(5)) { rec in
                            HStack {
                                Text(rec.label).font(.appBody)
                                Spacer()
                                Badge(text: rec.badgeLabel, style: rec.badgeStyle)
                            }
                            .padding(.vertical, 2)
                        }
                        if dashboard.recommendations.count > 5 {
                            Button("View all (\(dashboard.recommendations.count))") {
                                router.activeTab = .shopping
                            }
                            .buttonStyle(GhostButtonStyle())
                        }
                    }
                }
            }
        }
    }

    // MARK: - F-040 … F-045  Shopping List card

    private var shoppingListCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                shoppingHeader
                if shoppingPreviewExpanded {
                    shoppingExpandedBody
                }
            }
        }
    }

    private var shoppingHeader: some View {
        HStack {
            Image(systemName: "cart").foregroundStyle(DesignTokens.secondaryLabel)
            Text("Shopping List").font(.appTitle2)
            Spacer()
            Text("\(shopping.pendingCount)")
                .font(.appMonoCaption.weight(.semibold))
                .padding(.horizontal, 8).padding(.vertical, 2)
                .background(DesignTokens.surface2)
                .foregroundStyle(DesignTokens.label)
                .clipShape(Capsule())
            if shopping.estimatedTotal > 0 {
                Button {
                    shoppingPreviewExpanded.toggle()
                } label: {
                    Text(String(format: "$%.2f", shopping.estimatedTotal))
                        .font(.appMonoCaption)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
                .buttonStyle(.borderless)
                .help("Toggle preview list")
            }
            Button { router.activeTab = .shopping } label: {
                Image(systemName: "arrow.up.right.square")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(DesignTokens.accent)
            .help("Open Shopping List")
        }
    }

    private var shoppingExpandedBody: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("\(shopping.pendingCount) pending • \(shopping.items.count - shopping.pendingCount) purchased")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                Spacer()
                if shopping.estimatedTotal > 0 {
                    Text("Estimate \(String(format: "$%.2f", shopping.estimatedTotal))")
                        .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
            ForEach(shopping.items.prefix(5)) { item in
                HStack {
                    Image(systemName: item.isPending ? "circle" : "checkmark.circle.fill")
                        .foregroundStyle(item.isPending ? DesignTokens.tertiaryLabel : DesignTokens.success)
                    Text(item.productName)
                        .font(.appBody)
                        .foregroundStyle(item.isPending ? DesignTokens.label : DesignTokens.tertiaryLabel)
                        .strikethrough(!item.isPending)
                    Spacer()
                }
                .padding(.vertical, 2)
            }
        }
    }

    // MARK: - Drop zone (extra — not in registry)

    private var dropZone: some View {
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
    }
}

#Preview("Dashboard") {
    DashboardView()
        .environmentObject(Router.shared)
        .environmentObject(AppState.shared)
        .frame(width: 1100, height: 1400)
}
