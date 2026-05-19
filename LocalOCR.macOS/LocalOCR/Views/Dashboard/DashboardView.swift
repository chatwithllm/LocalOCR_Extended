import SwiftUI

/// Rich Dashboard matching the web app:
///   - Household Ranking strip (top 3 + current user)
///   - Untagged receipts banner (when count > 0)
///   - LOW / INV / PROD counter strip
///   - Spending by Category card (bars + % + amounts + grand total)
///   - Low Stock + Top Picks + Shopping List cards (3-column row)
///   - Receipts Processed sparkline over last 30 days
///   - File drop zone (existing — kept)
struct DashboardView: View {
    @StateObject private var dashboard = DashboardState.shared
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

                if let lb = dashboard.leaderboard, !lb.rankings.isEmpty {
                    householdRankingCard(lb)
                }

                if let untagged = dashboard.untagged, untagged.untaggedCount > 0 {
                    untaggedBanner(untagged)
                }

                countersStrip

                spendingByCategoryCard

                threeColumnRow

                if !dashboard.receiptsProcessedDaily.isEmpty {
                    receiptsProcessedCard
                }

                dropZone
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
        .task { await refreshAll() }
    }

    private func refreshAll() async {
        async let _ = dashboard.loadAll()
        async let _ = inventory.loadInventory()
        async let _ = shopping.loadList()
        async let _ = finance.loadBills()
        async let _ = finance.loadSpending()
    }

    // MARK: - Household Ranking

    private func householdRankingCard(_ lb: Leaderboard) -> some View {
        let leaders: [LeaderboardRow] = lb.leaders ?? Array(lb.rankings.prefix(3))
        return Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                rankingHeader(lb)
                rankingRow(leaders: leaders, lb: lb)
            }
        }
    }

    private func rankingHeader(_ lb: Leaderboard) -> some View {
        HStack {
            Text("HOUSEHOLD RANKING")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(DesignTokens.secondaryLabel)
            Spacer()
            if let month = lb.month {
                Text(month).font(.appCaption1.monospaced()).foregroundStyle(DesignTokens.tertiaryLabel)
            }
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

    private func rankingSelfBadge(rank: Int, total: Int) -> some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text("You").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            Text("#\(rank) of \(total)")
                .font(.appBody.weight(.semibold))
                .foregroundStyle(DesignTokens.accent)
        }
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

    // MARK: - Untagged banner

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

    // MARK: - LOW / INV / PROD counters

    private var countersStrip: some View {
        Card {
            HStack(spacing: 0) {
                counter(label: "LOW",  value: inventory.lowStockItems.count, color: DesignTokens.warning)
                Divider().frame(height: 44).padding(.horizontal, 8)
                counter(label: "INV",  value: inventory.items.count, color: DesignTokens.success)
                Divider().frame(height: 44).padding(.horizontal, 8)
                counter(label: "PROD", value: productCount, color: DesignTokens.accent)
            }
        }
    }

    private var productCount: Int {
        Set(inventory.items.map { $0.productId }).count
    }

    private func counter(label: String, value: Int, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.appCaption2.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryLabel)
            Text("\(value)")
                .font(.appTitle1.weight(.bold))
                .foregroundStyle(color)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Spending by Category

    private var spendingByCategoryCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    HStack(spacing: 6) {
                        Image(systemName: "cart")
                            .foregroundStyle(DesignTokens.accent)
                        Text("Spending by Category")
                            .font(.appTitle2)
                    }
                    Spacer()
                    if let s = finance.spending {
                        Text(String(format: "$%.2f", s.categories.reduce(0) { $0 + $1.total }))
                            .font(.appMonoBody.weight(.semibold))
                            .foregroundStyle(DesignTokens.label)
                    }
                }
                if let s = finance.spending, !s.categories.isEmpty {
                    let total = s.categories.reduce(0) { $0 + $1.total }
                    ForEach(Array(s.categories.enumerated()), id: \.element.id) { idx, cat in
                        categoryBar(category: cat, total: total, color: palette[idx % palette.count])
                    }
                } else {
                    Text("No spending yet — confirm a few receipts to populate this card.")
                        .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
    }

    private func categoryBar(category: SpendingCategoryTotal, total: Double, color: Color) -> some View {
        let pct = total > 0 ? category.total / total : 0
        return HStack(spacing: DesignTokens.Spacing.space3) {
            Text(category.category)
                .font(.appBody)
                .frame(width: 120, alignment: .leading)
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 6).fill(DesignTokens.surface2)
                    RoundedRectangle(cornerRadius: 6)
                        .fill(color)
                        .frame(width: proxy.size.width * pct)
                }
            }
            .frame(height: 14)
            Text("\(Int(pct * 100))%")
                .font(.appCaption1.monospaced())
                .foregroundStyle(DesignTokens.tertiaryLabel)
                .frame(width: 36, alignment: .trailing)
            Text(String(format: "$%.2f", category.total))
                .font(.appMonoBody.weight(.medium))
                .foregroundStyle(DesignTokens.label)
                .frame(width: 90, alignment: .trailing)
        }
    }

    private var palette: [Color] {
        [DesignTokens.accent, DesignTokens.warning, DesignTokens.success, DesignTokens.error, DesignTokens.secondaryLabel]
    }

    // MARK: - Three-column row: Low Stock / Top Picks / Shopping List

    private var threeColumnRow: some View {
        LazyVGrid(
            columns: [
                GridItem(.flexible(), spacing: DesignTokens.Spacing.space3),
                GridItem(.flexible(), spacing: DesignTokens.Spacing.space3),
                GridItem(.flexible(), spacing: DesignTokens.Spacing.space3)
            ],
            spacing: DesignTokens.Spacing.space3
        ) {
            tile(
                systemImage: "exclamationmark.triangle",
                tint: DesignTokens.warning,
                title: "Low Stock",
                badge: "\(inventory.lowStockItems.count)"
            ) {
                router.activeTab = .inventory
            }

            tile(
                systemImage: "lightbulb",
                tint: DesignTokens.accent,
                title: "Top Picks",
                badge: "\(dashboard.recommendations.count)"
            ) {
                router.activeTab = .shopping
            }

            tile(
                systemImage: "cart",
                tint: DesignTokens.secondaryLabel,
                title: "Shopping List",
                badge: "\(shopping.pendingCount)",
                trailing: shoppingTotalText
            ) {
                router.activeTab = .shopping
            }
        }
    }

    private var shoppingTotalText: String? {
        guard shopping.estimatedTotal > 0 else { return nil }
        return String(format: "$%.2f", shopping.estimatedTotal)
    }

    private func tile(systemImage: String, tint: Color, title: String, badge: String, trailing: String? = nil, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: systemImage).foregroundStyle(tint)
                Text(title).font(.appHeadline).foregroundStyle(DesignTokens.label)
                Spacer()
                if let trailing {
                    Text(trailing).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                }
                Text(badge)
                    .font(.appMonoCaption.weight(.semibold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(tint.opacity(0.15))
                    .foregroundStyle(tint)
                    .clipShape(Capsule())
            }
            .padding(DesignTokens.Spacing.space3)
            .background(DesignTokens.surface)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                    .stroke(DesignTokens.border, lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Receipts processed sparkline

    private var receiptsProcessedCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                HStack {
                    Text("Receipts Processed")
                        .font(.appTitle2)
                    Spacer()
                    Text(receiptsProcessedRange)
                        .font(.appCaption1.monospaced())
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
                HStack(spacing: DesignTokens.Spacing.space5) {
                    statColumn(title: "TOTAL", value: "\(processedTotalCount)",
                               sub: String(format: "$%.2f", processedTotalAmount))
                    statColumn(title: "AVG / DAY", value: String(format: "%.1f", avgPerDay),
                               sub: String(format: "$%.2f", processedTotalAmount / max(Double(receiptsProcessedDailyCount), 1)))
                    statColumn(title: "PEAK", value: "\(peakDayCount)",
                               sub: peakDayLabel)
                }
                sparkline
                    .frame(height: 90)
                    .padding(.top, 4)
            }
        }
    }

    private var receiptsProcessedRange: String {
        guard let first = dashboard.receiptsProcessedDaily.first?.month,
              let last  = dashboard.receiptsProcessedDaily.last?.month else { return "" }
        return "\(first) → \(last)"
    }

    private var receiptsProcessedDailyCount: Int { dashboard.receiptsProcessedDaily.count }
    private var processedTotalAmount: Double { dashboard.receiptsProcessedDaily.reduce(0) { $0 + $1.total } }
    /// Approximate processed count: server endpoint returns totals, not counts.
    /// Use number of buckets as proxy for "days with receipts".
    private var processedTotalCount: Int { dashboard.receiptsProcessedDaily.filter { $0.total > 0 }.count }
    private var avgPerDay: Double {
        let total = dashboard.receiptsProcessedDaily.reduce(0.0) { $0 + ($1.total > 0 ? 1 : 0) }
        return total / Double(max(receiptsProcessedDailyCount, 1))
    }
    private var peakDayCount: Int { Int(dashboard.receiptsProcessedDaily.map(\.total).max() ?? 0) }
    private var peakDayLabel: String {
        guard let peak = dashboard.receiptsProcessedDaily.max(by: { $0.total < $1.total }) else { return "—" }
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
            let points = dashboard.receiptsProcessedDaily.map(\.total)
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
            // Filled area below the line for visual weight
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

    // MARK: - Drop zone

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
        .frame(width: 1100, height: 1200)
}
