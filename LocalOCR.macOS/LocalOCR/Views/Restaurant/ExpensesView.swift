import SwiftUI
import os.log

// MARK: - F-1000..F-1050 — Expenses screen
//
// Mirrors web `loadExpenses`, `loadExpenseBudget`, `saveExpenseBudget`,
// `viewExpenseReceiptDetail`. Routes verified by Rule 1 grep:
//   GET  /analytics/expense-summary
//   GET  /analytics/spending?domain=general_expense
//   GET  /budget/status?domain=general_expense
//   POST /budget/set-monthly (admin only)

@MainActor
final class ExpensesState: ObservableObject {

    static let shared = ExpensesState()

    @Published private(set) var summary: ExpenseSummaryResponse?
    @Published private(set) var spending: AnalyticsSpendingResponse?
    @Published private(set) var budget: BudgetStatusResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?

    @Published var months: Int {
        didSet { UserDefaults.standard.set(months, forKey: Defaults.months) }
    }
    @Published var budgetMonth: String {
        didSet { UserDefaults.standard.set(budgetMonth, forKey: Defaults.budgetMonth) }
    }
    @Published var budgetAmountInput: String = ""

    enum Defaults {
        static let months      = "LocalOCR.expense.months"
        static let budgetMonth = "LocalOCR.expense.budgetMonth"
    }

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "expenses")

    init(api: APIClient = .shared) {
        self.api = api
        let m = UserDefaults.standard.integer(forKey: Defaults.months)
        self.months = [3, 6, 12].contains(m) ? m : 6
        if let saved = UserDefaults.standard.string(forKey: Defaults.budgetMonth),
           RestaurantsState.isValidMonth(saved) {
            self.budgetMonth = saved
        } else {
            self.budgetMonth = RestaurantsState.currentYearMonth()
        }
    }

    func setMonths(_ m: Int) {
        months = m
        Task { await refresh() }
    }

    func setBudgetMonth(_ m: String) {
        budgetMonth = m
        Task { await loadBudget() }
    }

    func refresh() async {
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
            let endpoint = ExpenseEndpoint.summary(months: months)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: ExpenseSummaryResponse.self
            )
            summary = response
            logger.info("loaded expense summary: \(response.purchaseCount ?? 0, privacy: .public) purchases, \(response.topMerchants?.count ?? 0, privacy: .public) top merchants")
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
            let endpoint = ExpenseEndpoint.spending(months: months)
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
            let endpoint = BudgetEndpoint.status(month: budgetMonth, domain: "general_expense", category: nil)
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
            budget = nil
            logger.info("loadBudget: no expense budget (\(error.localizedDescription, privacy: .public))")
        }
    }

    func saveBudget() async {
        guard AppState.shared.currentUser?.isAdmin == true else {
            ToastQueue.shared.push(Toast(message: "Only admins can update budgets", severity: .error))
            return
        }
        let trimmed = budgetAmountInput.trimmingCharacters(in: .whitespaces)
        guard let amount = Double(trimmed), !budgetMonth.isEmpty else {
            ToastQueue.shared.push(Toast(message: "Enter a month and expense budget amount", severity: .error))
            return
        }
        do {
            try DemoModeGate.guardMutation()
            let body = BudgetSetMonthlyBody(month: budgetMonth, budgetCategory: nil, domain: "general_expense", budgetAmount: amount)
            try await api.request(
                .post,
                path: BudgetEndpoint.setMonthly.path,
                jsonBody: body
            )
            ToastQueue.shared.push(Toast(message: "Expense budget saved ✅", severity: .success))
            await loadBudget()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Could not save expense budget",
                severity: .error
            ))
        }
    }

    func openReceiptsTab() {
        Router.shared.activeTab = .receipts
        Task { await ReceiptsState.shared.loadList() }
    }
}

// MARK: - View

struct ExpensesView: View {
    @StateObject private var state = ExpensesState.shared
    @EnvironmentObject private var appState: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                header
                StatsGridExpense(state: state)
                ExpenseBudgetCard(state: state)
                RecentExpensesCard(state: state)
                ExpenseAnalyticsGrid(state: state)
                ExpenseCategoriesCard(state: state)
                PageNavStrip()
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Expenses")
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
                Button {
                    Task { await state.refresh() }
                } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                .help("Refresh expense data")
            }
        }
        .onAppear {
            Task.detached(priority: .userInitiated) {
                await ExpensesState.shared.refresh()
            }
        }
    }

    // F-1000 + F-1001
    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Expenses").font(.appTitle2)
            Text("services, gifts, fees, and retail receipts")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }
}

// MARK: - F-1002..F-1007 stats grid

private struct StatsGridExpense: View {
    @ObservedObject var state: ExpensesState

    var body: some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 200), spacing: 12)],
            alignment: .leading,
            spacing: 12
        ) {
            statCard(
                tint: DesignTokens.accent,
                title: "Expense Receipts",
                value: "\(state.summary?.purchaseCount ?? 0)",
                sub: receiptSub
            )
            statCard(
                tint: DesignTokens.success,
                title: "Total Spend",
                value: Self.money(state.summary?.totalSpend ?? state.spending?.grandTotal),
                sub: "current window"
            )
            statCard(
                tint: DesignTokens.label,
                title: "Average Ticket",
                value: Self.money(state.summary?.averageTicket),
                sub: "per receipt"
            )
            statCard(
                tint: DesignTokens.warning,
                title: "Top Merchant",
                value: state.summary?.topMerchants?.first?.store ?? "—",
                sub: topMerchantSub
            )
        }
    }

    private var receiptSub: String {
        if let r = state.summary?.refundCount, r > 0 {
            return "\(r) refund\(r == 1 ? "" : "s") in window"
        }
        return "purchase receipts"
    }

    private var topMerchantSub: String {
        guard let top = state.summary?.topMerchants?.first else { return "No expenses yet" }
        let visits = top.visits ?? 0
        let refunds = top.refunds ?? 0
        let total = top.total ?? 0
        let visitText = "\(visits) receipt\(visits == 1 ? "" : "s")"
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

// MARK: - F-1008..F-1015 Expense Budget

private struct ExpenseBudgetCard: View {
    @ObservedObject var state: ExpensesState
    @EnvironmentObject private var appState: AppState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Expense Budget").font(.appHeadline)
                    Spacer()
                    Text(appState.currentUser?.isAdmin == true ? "Admin" : "Read-only")
                        .font(.appCaption2.weight(.semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(DesignTokens.surface2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                        .clipShape(Capsule())
                }
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
                        TextField("e.g. 200", text: $state.budgetAmountInput)
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
                ProgressBar(percent: pct, tint: barColor(for: pct))
                let visitsLabel = "\(b.purchaseCount ?? 0) receipt\((b.purchaseCount ?? 0) == 1 ? "" : "s")"
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
                title: "No general expense budget set for this month yet."
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

// Reuse ProgressBar from RestaurantsView via a small alias — actually
// SwiftUI doesn't allow type aliases across private types from another file.
// Duplicate the lightweight bar.
private struct ProgressBar: View {
    let percent: Double
    let tint: Color

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Rectangle().fill(DesignTokens.surface2)
                Rectangle()
                    .fill(tint)
                    .frame(width: max(0, min(geo.size.width * CGFloat(percent / 100), geo.size.width)))
            }
            .clipShape(RoundedRectangle(cornerRadius: 4))
        }
        .frame(height: 8)
    }
}

// MARK: - F-1025..F-1036 recent expenses + Open All

private struct RecentExpensesCard: View {
    @ObservedObject var state: ExpensesState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Recent General Expenses").font(.appHeadline)
                    Spacer()
                    Button {
                        state.openReceiptsTab()
                    } label: { Text("Open All") }
                    .buttonStyle(GhostButtonStyle())
                }
                if let err = state.lastError, state.summary == nil {
                    EmptyStateView(
                        systemImage: "exclamationmark.triangle",
                        title: "Could not load general expenses.",
                        subtitle: err
                    )
                    .frame(height: 160)
                } else {
                    let receipts = Array((state.summary?.recentReceipts ?? []).prefix(12))
                    if receipts.isEmpty {
                        EmptyStateView(
                            systemImage: "doc.text",
                            title: "No general expense receipts yet.",
                            subtitle: "Upload one with the General Expense intent and it will land here."
                        )
                        .frame(height: 160)
                    } else {
                        VStack(spacing: 6) {
                            ForEach(receipts) { r in
                                ExpenseReceiptRowView(row: r)
                            }
                        }
                    }
                }
            }
        }
    }
}

private struct ExpenseReceiptRowView: View {
    let row: ExpenseReceiptRow

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.store ?? "Unknown")
                    .font(.appCallout.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
                    .lineLimit(1)
                let meta = [
                    row.date,
                    row.transactionType.map(formatType),
                    row.itemCount.map { "\($0) item\($0 == 1 ? "" : "s")" }
                ].compactMap { $0 }
                Text(meta.joined(separator: " · "))
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            Spacer()
            Text(StatsGridExpense.money(row.total))
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

    private func formatType(_ s: String) -> String {
        s.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

// MARK: - F-1037..F-1044 analytics grid (Top Merchants + Top Items)

private struct ExpenseAnalyticsGrid: View {
    @ObservedObject var state: ExpensesState

    var body: some View {
        let merchants = state.summary?.topMerchants ?? []
        let items = state.summary?.topItems ?? []
        if !merchants.isEmpty && !items.isEmpty {
            HStack(alignment: .top, spacing: 12) {
                TopMerchantsCard(items: merchants).frame(maxWidth: 320)
                TopExpenseItemsCard(items: items)
            }
        } else if !merchants.isEmpty {
            TopMerchantsCard(items: merchants)
        } else if !items.isEmpty {
            TopExpenseItemsCard(items: items)
        } else {
            HStack(alignment: .top, spacing: 12) {
                emptyMerchants
                emptyItems
            }
        }
    }

    private var emptyMerchants: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top Merchants").font(.appHeadline)
                EmptyStateView(systemImage: "storefront", title: "No merchant history yet.")
                    .frame(height: 120)
            }
        }
    }
    private var emptyItems: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top Reference Items").font(.appHeadline)
                EmptyStateView(systemImage: "tag", title: "No saved expense line items yet.")
                    .frame(height: 120)
            }
        }
    }
}

private struct TopMerchantsCard: View {
    let items: [ExpenseMerchant]
    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top Merchants").font(.appHeadline)
                VStack(spacing: 4) {
                    ForEach(items) { item in TopMerchantRow(item: item) }
                }
            }
        }
    }
}

private struct TopMerchantRow: View {
    let item: ExpenseMerchant
    var body: some View {
        Button {
            Router.shared.activeTab = .receipts
            Task { await ReceiptsState.shared.loadList() }
            ToastQueue.shared.push(Toast(
                message: "Showing receipts — filter by \(item.store) in Receipts page",
                severity: .info
            ))
        } label: {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.store).font(.appCallout.weight(.semibold)).lineLimit(1)
                    Text(meta).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel).lineLimit(1)
                }
                Spacer()
                Text(StatsGridExpense.money(item.total)).font(.appCallout.weight(.semibold))
                Image(systemName: "chevron.right").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
            }
            .padding(8)
            .background(DesignTokens.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Open receipts for \(item.store)")
    }
    private var meta: String {
        let visits = item.visits ?? 0
        let refunds = item.refunds ?? 0
        let avg = item.averageTicket ?? 0
        let visitText = "\(visits) receipt\(visits == 1 ? "" : "s")"
        let refundText = refunds > 0 ? " · \(refunds) refund\(refunds == 1 ? "" : "s")" : ""
        let avgText = visits > 0 ? " · Avg \(StatsGridExpense.money(avg))" : ""
        return "\(visitText)\(refundText)\(avgText)"
    }
}

private struct TopExpenseItemsCard: View {
    let items: [ExpenseTopItem]
    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top Reference Items").font(.appHeadline)
                HStack {
                    Text("Item").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(maxWidth: .infinity, alignment: .leading)
                    Text("Qty").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 60, alignment: .trailing)
                    Text("Total").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 90, alignment: .trailing)
                    Text("Avg").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 80, alignment: .trailing)
                }
                .padding(.horizontal, 8)
                Divider()
                VStack(spacing: 2) {
                    ForEach(items) { item in
                        HStack {
                            Text(item.name).font(.appCaption1).lineLimit(1).truncationMode(.tail).frame(maxWidth: .infinity, alignment: .leading)
                            Text(qty(item.quantity)).font(.appCaption1.monospacedDigit()).frame(width: 60, alignment: .trailing)
                            Text(StatsGridExpense.money(item.total)).font(.appCaption1.weight(.semibold)).frame(width: 90, alignment: .trailing)
                            Text(StatsGridExpense.money(item.averagePrice)).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 80, alignment: .trailing)
                        }
                        .padding(.horizontal, 8).padding(.vertical, 4)
                    }
                }
            }
        }
    }
    private func qty(_ q: Double?) -> String {
        guard let q else { return "0" }
        if q.truncatingRemainder(dividingBy: 1) == 0 { return String(Int(q)) }
        return String(format: "%.2f", q)
    }
}

// MARK: - F-1045..F-1048 Expense Categories

private struct ExpenseCategoriesCard: View {
    @ObservedObject var state: ExpensesState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Expense Categories").font(.appHeadline)
                let cats = state.summary?.categoryBreakdown ?? []
                if cats.isEmpty {
                    EmptyStateView(systemImage: "square.grid.2x2", title: "No expense categories yet.")
                        .frame(height: 120)
                } else {
                    HStack {
                        Text("Category").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(maxWidth: .infinity, alignment: .leading)
                        Text("Total").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 100, alignment: .trailing)
                        Text("Lines").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 80, alignment: .trailing)
                    }
                    .padding(.horizontal, 8)
                    Divider()
                    VStack(spacing: 2) {
                        ForEach(cats) { c in
                            HStack {
                                Text(c.category.capitalized).font(.appCaption1).frame(maxWidth: .infinity, alignment: .leading)
                                Text(StatsGridExpense.money(c.total)).font(.appCaption1.weight(.semibold)).frame(width: 100, alignment: .trailing)
                                Text("\(c.count ?? 0)").font(.appCaption1.monospacedDigit()).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 80, alignment: .trailing)
                            }
                            .padding(.horizontal, 8).padding(.vertical, 4)
                        }
                    }
                }
            }
        }
    }
}

#Preview("ExpensesView") {
    ExpensesView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 1000, height: 800)
}
