import SwiftUI
import AppKit
import os.log

// MARK: - F-700..F-729 — Restaurant Workspace
//
// Stats grid (visits / spend / avg ticket / top restaurant) + dining budget
// card + recent receipts + top restaurants + top items. Mirrors web
// `loadRestaurant`, `loadRestaurantBudget`, `saveRestaurantBudget`,
// `openStoreReceipts`, `openRestaurantReceipts`.
//
// Routes verified against `calculate_spending_analytics.py` +
// `manage_household_budget.py`.

// MARK: - State

@MainActor
final class RestaurantsState: ObservableObject {

    static let shared = RestaurantsState()

    @Published private(set) var summary: RestaurantSummaryResponse?
    @Published private(set) var spending: AnalyticsSpendingResponse?
    @Published private(set) var budget: BudgetStatusResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?

    /// `3` | `6` (default) | `12`.
    @Published var months: Int {
        didSet { UserDefaults.standard.set(months, forKey: Defaults.months) }
    }
    /// YYYY-MM — currently selected budget month.
    @Published var budgetMonth: String {
        didSet { UserDefaults.standard.set(budgetMonth, forKey: Defaults.budgetMonth) }
    }
    /// Editable budget amount string (matches web "e.g. 300" input).
    @Published var budgetAmountInput: String = ""

    enum Defaults {
        static let months      = "LocalOCR.restaurant.months"
        static let budgetMonth = "LocalOCR.restaurant.budgetMonth"
    }

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "restaurant")

    init(api: APIClient = .shared) {
        self.api = api
        let storedMonths = UserDefaults.standard.integer(forKey: Defaults.months)
        self.months = [3, 6, 12].contains(storedMonths) ? storedMonths : 6
        if let m = UserDefaults.standard.string(forKey: Defaults.budgetMonth), Self.isValidMonth(m) {
            self.budgetMonth = m
        } else {
            self.budgetMonth = Self.currentYearMonth()
        }
    }

    static func currentYearMonth() -> String {
        let df = DateFormatter()
        df.dateFormat = "yyyy-MM"
        return df.string(from: Date())
    }
    static func isValidMonth(_ s: String) -> Bool {
        s.range(of: "^\\d{4}-\\d{2}$", options: .regularExpression) != nil
    }

    func setMonths(_ m: Int) {
        months = m
        Task { await loadSummary() }
    }

    func setBudgetMonth(_ m: String) {
        budgetMonth = m
        Task { await loadBudget() }
    }

    // MARK: - F-701..F-729 load

    func refresh() async {
        // RULE 3 — parallel fan-out via withTaskGroup.
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in await self.loadSummary() }
            group.addTask { @MainActor in await self.loadSpending() }
            group.addTask { @MainActor in await self.loadBudget() }
        }
    }

    func loadSummary() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let endpoint = RestaurantEndpoint.summary(months: months)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: RestaurantSummaryResponse.self
            )
            summary = response
            logger.info("loaded restaurant summary: \(response.visitCount ?? 0, privacy: .public) visits, \(response.topRestaurants?.count ?? 0, privacy: .public) top stores")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadSummary failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadSpending() async {
        do {
            let endpoint = RestaurantEndpoint.spending(months: months)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: AnalyticsSpendingResponse.self
            )
            spending = response
        } catch is CancellationError {
            return
        } catch {
            logger.warning("loadSpending non-fatal: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadBudget() async {
        do {
            let endpoint = BudgetEndpoint.status(month: budgetMonth, domain: "restaurant", category: nil)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: BudgetStatusResponse.self
            )
            budget = response
            if let amount = response.budgetAmount, amount > 0 {
                budgetAmountInput = String(format: "%.2f", amount)
            }
        } catch is CancellationError {
            return
        } catch {
            // F-712 — no-budget state surfaces as nil budget; view handles message
            budget = nil
            logger.info("loadBudget: no budget set (\(error.localizedDescription, privacy: .public))")
        }
    }

    // F-709 save budget
    func saveBudget() async {
        guard AppState.shared.currentUser?.isAdmin == true else {
            ToastQueue.shared.push(Toast(message: "Only admins can update budgets", severity: .error))
            return
        }
        let trimmed = budgetAmountInput.trimmingCharacters(in: .whitespaces)
        guard let amount = Double(trimmed), !budgetMonth.isEmpty else {
            ToastQueue.shared.push(Toast(message: "Enter a month and restaurant budget amount", severity: .error))
            return
        }
        do {
            try DemoModeGate.guardMutation()
            let body = BudgetSetMonthlyBody(month: budgetMonth, budgetCategory: nil, domain: "restaurant", budgetAmount: amount)
            try await api.request(
                .post,
                path: BudgetEndpoint.setMonthly.path,
                jsonBody: body
            )
            ToastQueue.shared.push(Toast(message: "Restaurant budget saved ✅", severity: .success))
            await loadBudget()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Could not save restaurant budget",
                severity: .error
            ))
        }
    }

    // F-719 / F-722 deep-link to Receipts page
    func openReceiptsTab() {
        Router.shared.activeTab = .receipts
        // Trigger a re-load so receipts list is fresh.
        Task { await ReceiptsState.shared.loadList() }
    }
}

// MARK: - View

struct RestaurantsView: View {
    @StateObject private var state = RestaurantsState.shared
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var router: Router

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                pageHeader
                StatsGrid(state: state)
                DiningBudgetCard(state: state)
                ReceiptReviewCard(state: state)
                AnalyticsGrid(state: state)
                PageNavStrip()
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Restaurant")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Picker("Period", selection: Binding(
                    get: { state.months },
                    set: { state.setMonths($0) }
                )) {
                    Text("3 mo").tag(3)
                    Text("6 mo").tag(6)
                    Text("12 mo").tag(12)
                }
                .pickerStyle(.segmented)
                .help("Restaurant data window")

                Button {
                    Task { await state.refresh() }
                } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                .help("Refresh restaurant data")
            }
        }
        .onAppear {
            Task.detached(priority: .userInitiated) {
                await RestaurantsState.shared.refresh()
            }
        }
    }

    // F-700
    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Restaurant").font(.appTitle2)
            Text("Track dining-out receipts, repeat orders, and restaurant spend without touching grocery inventory.")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }
}

// MARK: - F-701..F-705 stats grid

private struct StatsGrid: View {
    @ObservedObject var state: RestaurantsState

    var body: some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 200), spacing: 12)],
            alignment: .leading,
            spacing: 12
        ) {
            statCard(
                tint: DesignTokens.accent,
                title: "Visits",
                value: "\(state.summary?.visitCount ?? 0)",
                sub: visitSub
            )
            statCard(
                tint: DesignTokens.success,
                title: "Dining Spend",
                value: Self.money(state.summary?.totalSpend ?? state.spending?.grandTotal),
                sub: "current window"
            )
            statCard(
                tint: DesignTokens.label,
                title: "Average Ticket",
                value: Self.money(state.summary?.averageTicket),
                sub: "per visit"
            )
            statCard(
                tint: DesignTokens.warning,
                title: "Top Restaurant",
                value: state.summary?.topRestaurants?.first?.store ?? "—",
                sub: topStoreSub
            )
        }
    }

    private var visitSub: String {
        if let r = state.summary?.refundCount, r > 0 {
            return "\(r) refund\(r == 1 ? "" : "s") in window"
        }
        return "restaurant purchases"
    }

    private var topStoreSub: String {
        guard let top = state.summary?.topRestaurants?.first else { return "No visits yet" }
        let visits = top.visits ?? 0
        let refunds = top.refunds ?? 0
        let total = top.total ?? 0
        let visitText = "\(visits) visit\(visits == 1 ? "" : "s")"
        let refundText = refunds > 0 ? " · \(refunds) refund\(refunds == 1 ? "" : "s")" : ""
        return "\(visitText)\(refundText) · Net \(Self.money(total))"
    }

    private func statCard(tint: Color, title: String, value: String, sub: String) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(tint)
                Text(value)
                    .font(.appTitle3.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text(sub)
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                    .lineLimit(2)
            }
        }
    }

    static func money(_ v: Double?) -> String {
        guard let v else { return "$0.00" }
        return String(format: "$%.2f", v)
    }
}

// MARK: - F-706..F-712 dining budget card

private struct DiningBudgetCard: View {
    @ObservedObject var state: RestaurantsState
    @EnvironmentObject private var appState: AppState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Dining Budget").font(.appHeadline)
                    Spacer()
                    Text(appState.currentUser?.isAdmin == true ? "Admin" : "Read-only")
                        .font(.appCaption2.weight(.semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(DesignTokens.surface2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                        .clipShape(Capsule())
                }

                // F-707 + F-708 + F-709 controls row
                HStack(spacing: 8) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Month").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                        TextField("YYYY-MM", text: Binding(
                            get: { state.budgetMonth },
                            set: {
                                if RestaurantsState.isValidMonth($0) {
                                    state.setBudgetMonth($0)
                                } else {
                                    state.budgetMonth = $0
                                }
                            }
                        ))
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 110)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Monthly Target").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                        TextField("e.g. 300", text: $state.budgetAmountInput)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 120)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text("").font(.appCaption2)
                        Button {
                            Task { await state.saveBudget() }
                        } label: { Text("Save") }
                        .buttonStyle(PrimaryButtonStyle())
                        .disabled(appState.currentUser?.isAdmin != true)
                    }
                    Spacer()
                }

                statusBody
            }
        }
    }

    // F-710 + F-711 progress + F-712 no-budget state
    @ViewBuilder
    private var statusBody: some View {
        if let b = state.budget, (b.budgetAmount ?? 0) > 0 {
            let pct = b.percentage ?? 0
            let spent = b.spent ?? 0
            let cap = b.budgetAmount ?? 0
            let remaining = b.remaining ?? 0
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline) {
                    Text(String(format: "$%.2f", spent))
                        .font(.appTitle3.weight(.semibold))
                    Text("of \(String(format: "$%.2f", cap))")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                    Spacer()
                }
                // F-711
                ProgressBar(percent: pct, tint: barColor(for: pct))
                let visitsLabel = "\(b.purchaseCount ?? 0) visit\((b.purchaseCount ?? 0) == 1 ? "" : "s")"
                let refundsLabel = (b.refundCount ?? 0) > 0
                    ? " · \(b.refundCount ?? 0) refund\((b.refundCount ?? 0) == 1 ? "" : "s")"
                    : ""
                let remainingLabel = remaining >= 0
                    ? "\(String(format: "$%.2f", remaining)) left"
                    : "\(String(format: "$%.2f", abs(remaining))) over"
                HStack {
                    Text("\(Int(pct))% used · \(visitsLabel)\(refundsLabel)")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                    Spacer()
                    Text(remainingLabel)
                        .font(.appCaption1.weight(.semibold))
                        .foregroundStyle(remaining >= 0 ? DesignTokens.success : DesignTokens.error)
                }
            }
        } else {
            EmptyStateView(
                systemImage: "creditcard",
                title: "No restaurant budget set for this month yet."
            )
            .frame(height: 120)
        }
    }

    private func barColor(for pct: Double) -> Color {
        if pct >= 90 { return DesignTokens.error }
        if pct >= 70 { return DesignTokens.warning }
        return DesignTokens.success
    }
}

private struct ProgressBar: View {
    let percent: Double
    let tint: Color

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(DesignTokens.surface2)
                Rectangle()
                    .fill(tint)
                    .frame(width: max(0, min(geo.size.width * CGFloat(percent / 100), geo.size.width)))
            }
            .clipShape(RoundedRectangle(cornerRadius: 4))
        }
        .frame(height: 8)
    }
}

// MARK: - F-713..F-719 receipt review card

private struct ReceiptReviewCard: View {
    @ObservedObject var state: RestaurantsState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Restaurant Receipts").font(.appHeadline)
                    Spacer()
                    Button {
                        state.openReceiptsTab()
                    } label: { Text("Open All") }
                    .buttonStyle(GhostButtonStyle())
                }
                if let err = state.lastError, state.summary == nil {
                    EmptyStateView(
                        systemImage: "exclamationmark.triangle",
                        title: "Could not load restaurant receipts.",
                        subtitle: err
                    )
                    .frame(height: 160)
                } else {
                    let receipts = Array((state.summary?.recentReceipts ?? []).prefix(8))
                    if receipts.isEmpty {
                        EmptyStateView(
                            systemImage: "fork.knife",
                            title: "No restaurant receipts yet.",
                            subtitle: "Upload one and it will land here."
                        )
                        .frame(height: 160)
                    } else {
                        VStack(spacing: 6) {
                            ForEach(receipts) { r in
                                ReceiptRow(row: r)
                            }
                        }
                    }
                }
            }
        }
    }
}

private struct ReceiptRow: View {
    let row: RestaurantReceiptRow

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.store ?? "Unknown")
                    .font(.appCallout.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
                    .lineLimit(1)
                Text([row.date, row.transactionType.map(formatTransactionType)]
                    .compactMap { $0 }
                    .joined(separator: " · "))
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            Spacer()
            Text(StatsGrid.money(row.total))
                .font(.appCallout.weight(.semibold))
                .foregroundStyle(row.transactionType == "refund" ? DesignTokens.warning : DesignTokens.label)
        }
        .padding(8)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .contentShape(Rectangle())
        .onTapGesture {
            Router.shared.activeTab = .receipts
            Router.shared.activeDetailDestination = .receipt(row.purchaseId)
            Task { await ReceiptsState.shared.loadDetail(id: row.purchaseId) }
        }
        .help("Open receipt #\(row.purchaseId)")
    }

    private func formatTransactionType(_ s: String) -> String {
        s.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

// MARK: - F-720..F-728 analytics grid

private struct AnalyticsGrid: View {
    @ObservedObject var state: RestaurantsState

    var body: some View {
        // Web's 1fr / 2fr split — top restaurants narrower, items wider.
        // Use a wrapping LazyVGrid so small widths collapse to single column.
        if let topRestaurants = state.summary?.topRestaurants, !topRestaurants.isEmpty,
           let topItems = state.summary?.topItems, !topItems.isEmpty {
            HStack(alignment: .top, spacing: 12) {
                TopRestaurantsCard(items: topRestaurants).frame(maxWidth: 320)
                TopItemsCard(items: topItems)
            }
        } else if let topRestaurants = state.summary?.topRestaurants, !topRestaurants.isEmpty {
            TopRestaurantsCard(items: topRestaurants)
        } else if let topItems = state.summary?.topItems, !topItems.isEmpty {
            TopItemsCard(items: topItems)
        } else {
            HStack(alignment: .top, spacing: 12) {
                emptyTopRestaurants
                emptyTopItems
            }
        }
    }

    private var emptyTopRestaurants: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top Restaurants").font(.appHeadline)
                EmptyStateView(systemImage: "storefront", title: "No restaurant history yet.")
                    .frame(height: 120)
            }
        }
    }

    private var emptyTopItems: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top Ordered Items").font(.appHeadline)
                EmptyStateView(systemImage: "fork.knife", title: "No restaurant line items yet.")
                    .frame(height: 120)
            }
        }
    }
}

// F-720..F-723
private struct TopRestaurantsCard: View {
    let items: [TopRestaurant]

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top Restaurants").font(.appHeadline)
                VStack(spacing: 4) {
                    ForEach(items) { item in
                        TopRestaurantRow(item: item)
                    }
                }
            }
        }
    }
}

private struct TopRestaurantRow: View {
    let item: TopRestaurant

    var body: some View {
        Button {
            // F-722 deep-link to Receipts filtered by this store
            Router.shared.activeTab = .receipts
            Task { await ReceiptsState.shared.loadList() }
            ToastQueue.shared.push(Toast(
                message: "Showing receipts — filter by \(item.store) in Receipts page",
                severity: .info
            ))
        } label: {
            HStack(alignment: .center, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.store)
                        .font(.appCallout.weight(.semibold))
                        .foregroundStyle(DesignTokens.label)
                        .lineLimit(1)
                    Text(metaText)
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                        .lineLimit(1)
                }
                Spacer()
                Text(StatsGrid.money(item.total))
                    .font(.appCallout.weight(.semibold))
                Image(systemName: "chevron.right")
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            .padding(8)
            .background(DesignTokens.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Open receipts for \(item.store)")
    }

    private var metaText: String {
        let visits = item.visits ?? 0
        let refunds = item.refunds ?? 0
        let avg = item.averageTicket ?? 0
        let visitText = "\(visits) visit\(visits == 1 ? "" : "s")"
        let refundText = refunds > 0 ? " · \(refunds) refund\(refunds == 1 ? "" : "s")" : ""
        let avgText = visits > 0 ? " · Avg \(StatsGrid.money(avg))" : ""
        return "\(visitText)\(refundText)\(avgText)"
    }
}

// F-724..F-727
private struct TopItemsCard: View {
    let items: [TopRestaurantItem]

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top Ordered Items").font(.appHeadline)
                // Header row
                HStack {
                    Text("Item")
                        .font(.appCaption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text("Qty").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 60, alignment: .trailing)
                    Text("Total").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 90, alignment: .trailing)
                    Text("Avg").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 80, alignment: .trailing)
                }
                .padding(.horizontal, 8)
                Divider()
                VStack(spacing: 2) {
                    ForEach(items) { item in
                        HStack {
                            Text(item.name)
                                .font(.appCaption1)
                                .lineLimit(1)
                                .truncationMode(.tail)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text(formatQty(item.quantity))
                                .font(.appCaption1.monospacedDigit())
                                .frame(width: 60, alignment: .trailing)
                            Text(StatsGrid.money(item.total))
                                .font(.appCaption1.weight(.semibold))
                                .frame(width: 90, alignment: .trailing)
                            Text(StatsGrid.money(item.averagePrice))
                                .font(.appCaption1)
                                .foregroundStyle(DesignTokens.tertiaryLabel)
                                .frame(width: 80, alignment: .trailing)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                    }
                }
            }
        }
    }

    private func formatQty(_ q: Double?) -> String {
        guard let q else { return "0" }
        if q.truncatingRemainder(dividingBy: 1) == 0 {
            return String(Int(q))
        }
        return String(format: "%.2f", q)
    }
}

#Preview("RestaurantsView") {
    RestaurantsView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 1000, height: 800)
}
