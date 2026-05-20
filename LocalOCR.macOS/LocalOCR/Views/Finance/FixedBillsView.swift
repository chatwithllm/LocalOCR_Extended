import SwiftUI
import os.log

// MARK: - F-1100..F-1191 — Fixed Bills / Household Bills
//
// Top-level page combines:
//   - Floor obligations widget (Selected / Available)
//   - Sticky month picker + 3 tabs (Overview / Providers / History)
//   - Overview: hero stats, alerts, due-soon spotlight, obligation cards
//   - Providers: 12-month provider list
//   - History: month-over-month bars + recent bills
//
// Routes verified by Rule 1 grep against handle_floor_obligations.py,
// calculate_spending_analytics.py, handle_receipt_upload.py.

enum BillsTab: String, CaseIterable, Identifiable {
    case overview, providers, history
    var id: String { rawValue }
    var label: String {
        switch self {
        case .overview:  return "Overview"
        case .providers: return "Providers"
        case .history:   return "History"
        }
    }
}

@MainActor
final class BillsState: ObservableObject {

    static let shared = BillsState()

    @Published var month: String {
        didSet { UserDefaults.standard.set(month, forKey: Defaults.month) }
    }
    @Published var tab: BillsTab = .overview

    @Published private(set) var floorActive: [FloorObligation] = []
    @Published private(set) var floorAvailable: [AvailableProvider] = []
    @Published private(set) var recurring: [RecurringObligation] = []
    @Published private(set) var recurringSummary: RecurringObligationSummary?
    @Published private(set) var utility: UtilitySummaryResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?

    enum Defaults {
        static let month = "LocalOCR.bills.month"
    }

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "bills")

    init(api: APIClient = .shared) {
        self.api = api
        if let m = UserDefaults.standard.string(forKey: Defaults.month),
           RestaurantsState.isValidMonth(m) {
            self.month = m
        } else {
            self.month = RestaurantsState.currentYearMonth()
        }
    }

    func setMonth(_ m: String) {
        guard RestaurantsState.isValidMonth(m) else {
            month = m
            return
        }
        month = m
        Task { await refresh() }
    }

    func stepMonth(_ delta: Int) {
        let parts = month.split(separator: "-").map { String($0) }
        guard parts.count == 2,
              var y = Int(parts[0]),
              var mo = Int(parts[1]) else { return }
        mo += delta
        while mo < 1  { mo += 12; y -= 1 }
        while mo > 12 { mo -= 12; y += 1 }
        setMonth(String(format: "%04d-%02d", y, mo))
    }

    func refresh() async {
        Task.detached { [weak self] in
            await self?.syncAutopay()
        }
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in await self.loadFloor() }
            group.addTask { @MainActor in await self.loadAvailable() }
            group.addTask { @MainActor in await self.loadRecurring() }
            group.addTask { @MainActor in await self.loadUtility() }
        }
    }

    func loadFloor() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await api.request(
                .get,
                path: FloorObligationEndpoint.list.path,
                as: FloorObligationsResponse.self
            )
            floorActive = response.obligations
            logger.info("loaded \(response.obligations.count, privacy: .public) floor obligations")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadFloor failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadAvailable() async {
        do {
            let response = try await api.request(
                .get,
                path: FloorObligationEndpoint.available.path,
                as: AvailableProvidersResponse.self
            )
            floorAvailable = response.available
        } catch {
            logger.warning("loadAvailable failed: \(error.localizedDescription, privacy: .public)")
            floorAvailable = []
        }
    }

    func loadRecurring() async {
        do {
            let endpoint = BillsAnalyticsEndpoint.recurring(month: month)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: RecurringObligationsResponse.self
            )
            recurring = response.obligations
            recurringSummary = response.summary
            logger.info("loaded \(response.obligations.count, privacy: .public) recurring obligations for \(self.month, privacy: .public)")
        } catch is CancellationError {
            return
        } catch {
            logger.error("loadRecurring failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadUtility() async {
        do {
            let endpoint = BillsAnalyticsEndpoint.utility(months: 12)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: UtilitySummaryResponse.self
            )
            utility = response
        } catch {
            logger.warning("loadUtility failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // F-1190 autopay sweep — best-effort, surfaces toast when count > 0
    func syncAutopay() async {
        do {
            let response = try await api.request(
                .post,
                path: BillsAnalyticsEndpoint.syncAutopay.path,
                jsonBody: EmptyBillsBody(),
                as: SyncAutopayResponse.self
            )
            if let n = response.sweptCount, n > 0 {
                await MainActor.run {
                    ToastQueue.shared.push(Toast(
                        message: "Auto-paid \(n) bill\(n == 1 ? "" : "s") on their due date",
                        severity: .success
                    ))
                }
            }
        } catch {
            // Sweep is best-effort; swallow errors silently
        }
    }

    func removeFromFloor(_ ob: FloorObligation) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .patch,
                path: FloorObligationEndpoint.update(id: ob.id).path,
                jsonBody: FloorObligationPatchBody(label: nil, expectedMonthlyAmount: nil, isActive: false)
            )
            ToastQueue.shared.push(Toast(message: "Removed from floor", severity: .success))
            await loadFloor()
            await loadAvailable()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(message: (error as? APIError)?.errorDescription ?? "Could not remove", severity: .error))
        }
    }

    func deleteFromFloor(_ ob: FloorObligation) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.delete, path: FloorObligationEndpoint.delete(id: ob.id).path)
            ToastQueue.shared.push(Toast(message: "Deleted", severity: .success))
            await loadFloor()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(message: (error as? APIError)?.errorDescription ?? "Could not delete", severity: .error))
        }
    }

    func addManualObligation(label: String, amount: Double) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .post,
                path: FloorObligationEndpoint.create.path,
                jsonBody: FloorObligationCreateBody(
                    label: label, expectedMonthlyAmount: amount, billProviderId: nil
                )
            )
            ToastQueue.shared.push(Toast(message: "Added '\(label)'", severity: .success))
            await loadFloor()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(message: (error as? APIError)?.errorDescription ?? "Could not add", severity: .error))
        }
    }
}

private struct EmptyBillsBody: Encodable {}

// MARK: - View

struct FixedBillsView: View {
    @StateObject private var state = BillsState.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                header
                FloorObligationsWidget(state: state)
                StickyBar(state: state)
                tabBody
                PageNavStrip()
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Household Bills")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await state.refresh() }
                } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                .help("Reload bills")
            }
        }
        .onAppear {
            Task.detached(priority: .userInitiated) {
                await BillsState.shared.refresh()
            }
        }
    }

    @ViewBuilder
    private var tabBody: some View {
        switch state.tab {
        case .overview:  OverviewPanel(state: state)
        case .providers: ProvidersPanel(state: state)
        case .history:   HistoryPanel(state: state)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Household Bills").font(.appTitle2)
            Text("\(monthLabel) · recurring obligations & payment projections")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }
    private var monthLabel: String {
        let parts = state.month.split(separator: "-")
        guard parts.count == 2,
              let y = Int(parts[0]),
              let m = Int(parts[1]) else { return state.month }
        let df = DateFormatter()
        df.dateFormat = "LLLL yyyy"
        let comps = DateComponents(year: y, month: m)
        if let d = Calendar.current.date(from: comps) {
            return df.string(from: d)
        }
        return state.month
    }
}

// MARK: - F-1102..F-1118 Floor Obligations Widget

private struct FloorObligationsWidget: View {
    @ObservedObject var state: BillsState
    @State private var tab: FloorWidgetTab = .selected
    @State private var addLabel: String = ""
    @State private var addAmount: String = ""

    enum FloorWidgetTab: String, CaseIterable, Identifiable {
        case selected, available
        var id: String { rawValue }
    }

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Fixed Monthly Obligations").font(.appHeadline)
                    Spacer()
                    Picker("", selection: $tab) {
                        Text("Selected (\(state.floorActive.filter { $0.isActive == true }.count))").tag(FloorWidgetTab.selected)
                        Text("Available (\(state.floorAvailable.count))").tag(FloorWidgetTab.available)
                    }
                    .pickerStyle(.segmented)
                    .frame(maxWidth: 280)
                }
                Group {
                    if tab == .selected { selectedBody } else { availableBody }
                }
            }
        }
    }

    @ViewBuilder
    private var selectedBody: some View {
        let rows = state.floorActive.filter { $0.isActive == true }
        if rows.isEmpty {
            EmptyStateView(
                systemImage: "tray",
                title: "No obligations on floor yet.",
                subtitle: "Add one below or pick from Available."
            )
            .frame(height: 140)
        } else {
            VStack(spacing: 4) {
                HStack {
                    Text("Name").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(maxWidth: .infinity, alignment: .leading)
                    Text("Expected/mo").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 110, alignment: .trailing)
                    Text("Avg (6mo)").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 90, alignment: .trailing)
                    Text("Source").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 70, alignment: .leading)
                    Spacer().frame(width: 100)
                }
                .padding(.horizontal, 8)
                Divider()
                ForEach(rows) { row in
                    FloorRow(ob: row, state: state)
                }
            }
        }
        HStack(spacing: 8) {
            TextField("Label", text: $addLabel).textFieldStyle(.roundedBorder).frame(maxWidth: 200)
            TextField("Amount", text: $addAmount).textFieldStyle(.roundedBorder).frame(maxWidth: 110)
            Button {
                let trimmed = addLabel.trimmingCharacters(in: .whitespaces)
                let amount = Double(addAmount.trimmingCharacters(in: .whitespaces)) ?? 0
                guard !trimmed.isEmpty, amount >= 0 else {
                    ToastQueue.shared.push(Toast(message: "Enter a label and amount", severity: .error))
                    return
                }
                Task {
                    await state.addManualObligation(label: trimmed, amount: amount)
                    addLabel = ""
                    addAmount = ""
                }
            } label: { Label("Add", systemImage: "plus") }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(addLabel.trimmingCharacters(in: .whitespaces).isEmpty)
            Spacer()
        }
    }

    @ViewBuilder
    private var availableBody: some View {
        if state.floorAvailable.isEmpty {
            EmptyStateView(
                systemImage: "checkmark.seal",
                title: "All bill providers are already on your floor."
            )
            .frame(height: 140)
        } else {
            VStack(spacing: 4) {
                HStack {
                    Text("Name").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(maxWidth: .infinity, alignment: .leading)
                    Text("Avg (6mo)").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 90, alignment: .trailing)
                    Text("Latest").font(.appCaption2.weight(.semibold)).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 90, alignment: .trailing)
                    Spacer().frame(width: 80)
                }
                .padding(.horizontal, 8)
                Divider()
                ForEach(state.floorAvailable) { ob in
                    HStack {
                        Text(ob.label).font(.appCaption1).frame(maxWidth: .infinity, alignment: .leading).lineLimit(1)
                        Text(money(ob.avg6mo)).font(.appCaption1.monospacedDigit()).foregroundStyle(DesignTokens.secondaryLabel).frame(width: 90, alignment: .trailing)
                        Text(money(ob.latestActual)).font(.appCaption1.monospacedDigit()).foregroundStyle(DesignTokens.tertiaryLabel).frame(width: 90, alignment: .trailing)
                        Button {
                            ToastQueue.shared.push(Toast(message: "Inline add coming v1.1 — use 'Add' row in Selected tab", severity: .info))
                        } label: { Label("Add", systemImage: "plus") }
                        .buttonStyle(.borderless)
                        .help("Add to floor (v1.1)")
                        .frame(width: 80)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    Divider()
                }
            }
        }
    }
}

private struct FloorRow: View {
    let ob: FloorObligation
    @ObservedObject var state: BillsState

    var body: some View {
        HStack {
            Text(ob.label).font(.appCaption1.weight(.medium)).frame(maxWidth: .infinity, alignment: .leading).lineLimit(1)
            Text(money(ob.expectedMonthlyAmount)).font(.appCaption1.monospacedDigit().weight(.semibold)).frame(width: 110, alignment: .trailing)
            Text(money(ob.avg6mo)).font(.appCaption1.monospacedDigit()).foregroundStyle(DesignTokens.secondaryLabel).frame(width: 90, alignment: .trailing)
            sourceBadge.frame(width: 70, alignment: .leading)
            actionButtons.frame(width: 100, alignment: .trailing)
        }
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(DesignTokens.surface2.opacity(0.4))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    @ViewBuilder
    private var sourceBadge: some View {
        let isProvider = (ob.source ?? "manual") == "bill_provider"
        Text(isProvider ? "Bills" : "Manual")
            .font(.appCaption2.weight(.semibold))
            .padding(.horizontal, 5).padding(.vertical, 1)
            .background(isProvider ? DesignTokens.surface2 : DesignTokens.accentDim)
            .foregroundStyle(isProvider ? DesignTokens.tertiaryLabel : DesignTokens.accent)
            .clipShape(Capsule())
    }

    @ViewBuilder
    private var actionButtons: some View {
        HStack(spacing: 4) {
            if ob.source == "bill_provider" {
                Button("Remove") { Task { await state.removeFromFloor(ob) } }
                    .buttonStyle(.borderless)
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.warning)
            } else {
                Button {
                    Task { await state.deleteFromFloor(ob) }
                } label: { Image(systemName: "xmark.circle.fill") }
                .buttonStyle(.borderless)
                .foregroundStyle(DesignTokens.error)
                .help("Delete manual obligation")
            }
        }
    }
}

// MARK: - F-1120..F-1127 sticky bar

private struct StickyBar: View {
    @ObservedObject var state: BillsState

    var body: some View {
        HStack(spacing: 8) {
            Button { state.stepMonth(-1) } label: {
                Image(systemName: "chevron.left.circle.fill")
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.leftArrow, modifiers: [])

            TextField("YYYY-MM", text: Binding(
                get: { state.month },
                set: { state.setMonth($0) }
            ))
            .textFieldStyle(.roundedBorder)
            .frame(width: 110)

            Button { state.stepMonth(1) } label: {
                Image(systemName: "chevron.right.circle.fill")
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.rightArrow, modifiers: [])

            Picker("Tab", selection: $state.tab) {
                ForEach(BillsTab.allCases) { tab in
                    Text(tab.label).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .frame(maxWidth: 360)

            Spacer()

            Button {
                Router.shared.activeSheet = .ocrUpload
            } label: { Label("New Bill", systemImage: "plus") }
            .buttonStyle(PrimaryButtonStyle())
            .help("Upload a new bill receipt")

            Button {
                Router.shared.activeSheet = .cashTransaction
            } label: { Label("Log Cash", systemImage: "banknote") }
            .buttonStyle(GhostButtonStyle())
            .help("Log a cash payment")
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Overview panel

private struct OverviewPanel: View {
    @ObservedObject var state: BillsState

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
            HeroStatsBar(state: state)
            AlertsContainer(state: state)
            DueSoonStrip(state: state)
            ObligationsList(state: state)
        }
    }
}

// F-1133..F-1138
private struct HeroStatsBar: View {
    @ObservedObject var state: BillsState

    var body: some View {
        let summary = state.recurringSummary
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 180), spacing: 10)],
            alignment: .leading,
            spacing: 10
        ) {
            statCard(title: "Tracked", value: "\(summary?.count ?? 0)",
                     sub: "\(summary?.fixedCount ?? 0) fixed · \(summary?.variableCount ?? 0) variable",
                     tint: DesignTokens.accent)
            statCard(title: "Entered",
                     value: "\(summary?.enteredCount ?? 0)",
                     sub: "Outstanding \(summary?.outstandingCount ?? 0)",
                     tint: DesignTokens.success)
            statCard(title: "Expected",
                     value: money(summary?.expectedTotal),
                     sub: "Actual \(money(summary?.actualTotal))",
                     tint: DesignTokens.label)
            statCard(title: "Variance",
                     value: money(summary?.varianceTotal),
                     sub: (summary?.varianceTotal ?? 0) >= 0 ? "over expected" : "under expected",
                     tint: (summary?.varianceTotal ?? 0) >= 0 ? DesignTokens.warning : DesignTokens.success)
            statCard(title: "Due Soon",
                     value: "\(state.utility?.dueSoon?.count ?? 0)",
                     sub: "this window",
                     tint: DesignTokens.warning)
        }
    }

    private func statCard(title: String, value: String, sub: String, tint: Color) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.appCaption2.weight(.semibold)).foregroundStyle(tint)
                Text(value).font(.appTitle3.weight(.semibold)).foregroundStyle(DesignTokens.label).lineLimit(1).minimumScaleFactor(0.7)
                Text(sub).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel).lineLimit(2)
            }
        }
    }
}

private struct AlertsContainer: View {
    @ObservedObject var state: BillsState

    var body: some View {
        let dueSoon = state.utility?.dueSoon ?? []
        let overdue = dueSoon.filter { ($0.daysUntilDue ?? 0) < 0 }
        if !dueSoon.isEmpty || !overdue.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                if !overdue.isEmpty {
                    alertBanner(
                        icon: "exclamationmark.triangle.fill",
                        title: "\(overdue.count) overdue bill\(overdue.count == 1 ? "" : "s")",
                        message: overdue.prefix(3).compactMap { $0.providerName }.joined(separator: ", "),
                        tint: DesignTokens.error
                    )
                }
                if !dueSoon.isEmpty {
                    alertBanner(
                        icon: "clock.fill",
                        title: "Due Soon",
                        message: dueSoon.prefix(3).compactMap { $0.providerName }.joined(separator: ", "),
                        tint: DesignTokens.warning
                    )
                }
            }
        }
    }

    private func alertBanner(icon: String, title: String, message: String, tint: Color) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon).foregroundStyle(tint).font(.title3)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.appCallout.weight(.semibold)).foregroundStyle(DesignTokens.label)
                Text(message).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel).lineLimit(2)
            }
            Spacer()
        }
        .padding(10)
        .background(tint.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .stroke(tint.opacity(0.4), lineWidth: 0.5)
        )
    }
}

private struct DueSoonStrip: View {
    @ObservedObject var state: BillsState

    var body: some View {
        let items = Array((state.utility?.dueSoon ?? []).prefix(8))
        if !items.isEmpty {
            Card {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Due This Week").font(.appHeadline)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(items) { item in
                                DueSoonChip(item: item)
                            }
                        }
                    }
                }
            }
        }
    }
}

private struct DueSoonChip: View {
    let item: DueSoonItem

    private var tint: Color {
        let d = item.daysUntilDue ?? 0
        if d < 0 { return DesignTokens.error }
        if d <= 3 { return DesignTokens.warning }
        return DesignTokens.accent
    }

    private var daysLabel: String {
        guard let d = item.daysUntilDue else { return "—" }
        if d < 0 { return "\(-d) day\(d == -1 ? "" : "s") overdue" }
        if d == 0 { return "Due today" }
        return "In \(d) day\(d == 1 ? "" : "s")"
    }

    var body: some View {
        Button {
            if let pid = item.purchaseId {
                Router.shared.activeTab = .receipts
                Router.shared.activeDetailDestination = .receipt(pid)
                Task { await ReceiptsState.shared.loadDetail(id: pid) }
            }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Text(item.providerName ?? "Unknown")
                    .font(.appCaption1.weight(.semibold))
                    .lineLimit(1)
                Text(daysLabel)
                    .font(.appCaption2)
                    .foregroundStyle(tint)
                Text(money(item.amount))
                    .font(.appCallout.weight(.semibold).monospacedDigit())
            }
            .padding(10)
            .frame(minWidth: 150)
            .background(tint.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10).stroke(tint.opacity(0.4), lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
        .help(item.purchaseId.map { "Open receipt #\($0)" } ?? "No receipt linked yet")
    }
}

private struct ObligationsList: View {
    @ObservedObject var state: BillsState
    @State private var expanded: Bool = false

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Recurring Obligations").font(.appHeadline)
                    Spacer()
                    Text("\(state.recurring.count)")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
                if state.recurring.isEmpty {
                    EmptyStateView(
                        systemImage: "doc.text",
                        title: "No obligations this month.",
                        subtitle: "Add a household bill via + New Bill."
                    )
                    .frame(height: 160)
                } else {
                    let threshold = 6
                    let visible = expanded ? state.recurring : Array(state.recurring.prefix(threshold))
                    VStack(spacing: 8) {
                        ForEach(visible) { ob in
                            ObligationCard(ob: ob)
                        }
                    }
                    if state.recurring.count > threshold {
                        Button {
                            expanded.toggle()
                        } label: {
                            Text(expanded ? "Show less" : "Show all \(state.recurring.count)")
                                .font(.appCallout.weight(.semibold))
                        }
                        .buttonStyle(GhostButtonStyle())
                    }
                }
            }
        }
    }
}

private struct ObligationCard: View {
    let ob: RecurringObligation

    private var status: BillCardStatus {
        if ob.isAutopaySettled == true { return .autopaySettled }
        if let entry = ob.currentEntry,
           entry.paymentStatus == "paid" { return .paid }
        if let due = ob.currentEntry?.dueDate ?? ob.lastDueDate,
           let date = BillsDateFormatter.dateOnly.date(from: due) {
            let days = Calendar.current.dateComponents([.day], from: Date(), to: date).day ?? 0
            if days < 0 { return .overdue }
            if days <= 7 { return .dueSoon }
        }
        return .upcoming
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(ob.providerName).font(.appCallout.weight(.semibold)).foregroundStyle(DesignTokens.label)
                    if let label = ob.accountLabel {
                        Text(label).font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
                Spacer()
                statusPill
            }
            HStack(alignment: .firstTextBaseline, spacing: 14) {
                stat(label: "Expected", value: money(ob.expectedAmount))
                stat(label: "Actual", value: money(ob.actualAmount), tint: actualTint)
                if let v = ob.variance, abs(v) > 0.01 {
                    stat(label: "Δ", value: money(v), tint: v >= 0 ? DesignTokens.warning : DesignTokens.success)
                }
                Spacer()
            }
            if ob.isAutopaySettled == true,
               let date = ob.currentEntry?.date ?? ob.lastSeenDate {
                Text("💳 Paid via autopay on \(date)")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.success)
            }
            let footer = [
                ob.lastSeenDate.map { "Last seen \($0)" },
                ob.lastDueDate.map { "Due \($0)" }
            ].compactMap { $0 }
            if !footer.isEmpty {
                Text(footer.joined(separator: " · "))
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            if let pid = ob.currentEntry?.purchaseId {
                HStack {
                    Spacer()
                    Button {
                        Router.shared.activeTab = .receipts
                        Router.shared.activeDetailDestination = .receipt(pid)
                        Task { await ReceiptsState.shared.loadDetail(id: pid) }
                    } label: { Label("Open Receipt", systemImage: "doc.text") }
                    .buttonStyle(GhostButtonStyle())
                }
            }
        }
        .padding(10)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .stroke(status.tint.opacity(0.4), lineWidth: 0.5)
        )
    }

    private var statusPill: some View {
        Text(status.label)
            .font(.appCaption2.weight(.semibold))
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(status.tint.opacity(0.18))
            .foregroundStyle(status.tint)
            .clipShape(Capsule())
    }

    private var actualTint: Color {
        let actual = ob.actualAmount ?? 0
        let expected = ob.expectedAmount ?? 0
        if actual == 0 { return DesignTokens.tertiaryLabel }
        if expected == 0 { return DesignTokens.label }
        let pct = actual / expected
        if pct > 1.1 { return DesignTokens.warning }
        if pct < 0.9 { return DesignTokens.success }
        return DesignTokens.label
    }

    private func stat(label: String, value: String, tint: Color = DesignTokens.label) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
            Text(value).font(.appCallout.weight(.semibold).monospacedDigit()).foregroundStyle(tint)
        }
    }
}

private enum BillCardStatus {
    case paid, autopaySettled, overdue, dueSoon, upcoming

    var label: String {
        switch self {
        case .paid:           return "Paid"
        case .autopaySettled: return "Autopay"
        case .overdue:        return "Overdue"
        case .dueSoon:        return "Due Soon"
        case .upcoming:       return "Upcoming"
        }
    }
    var tint: Color {
        switch self {
        case .paid, .autopaySettled: return DesignTokens.success
        case .overdue:               return DesignTokens.error
        case .dueSoon:               return DesignTokens.warning
        case .upcoming:              return DesignTokens.accent
        }
    }
}

// MARK: - Providers tab

private struct ProvidersPanel: View {
    @ObservedObject var state: BillsState
    @State private var expanded: Bool = false

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Providers (last 12 months)").font(.appHeadline)
                    Spacer()
                    if let count = state.utility?.providers?.count, count > 0 {
                        Text("\(count)").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
                let providers = state.utility?.providers ?? []
                if providers.isEmpty {
                    EmptyStateView(
                        systemImage: "storefront",
                        title: "No provider history yet.",
                        subtitle: "Once you enter a bill it lands here."
                    )
                    .frame(height: 160)
                } else {
                    let threshold = 8
                    let visible = expanded ? providers : Array(providers.prefix(threshold))
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 280), spacing: 10)],
                        alignment: .leading,
                        spacing: 10
                    ) {
                        ForEach(visible) { p in
                            ProviderCard(provider: p)
                        }
                    }
                    if providers.count > threshold {
                        Button { expanded.toggle() } label: {
                            Text(expanded ? "Show less" : "Show all \(providers.count)")
                                .font(.appCallout.weight(.semibold))
                        }
                        .buttonStyle(GhostButtonStyle())
                    }
                }
            }
        }
    }
}

private struct ProviderCard: View {
    let provider: UtilityProvider
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(provider.providerName).font(.appCallout.weight(.semibold)).lineLimit(1)
            HStack {
                stat(label: "12 mo total", value: money(provider.total))
                stat(label: "Avg/mo", value: money(provider.averageMonthly))
            }
            HStack(spacing: 8) {
                if let p = provider.purchaseCount, p > 0 {
                    Text("\(p) payment\(p == 1 ? "" : "s")").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                }
                if let r = provider.refundCount, r > 0 {
                    Text("· \(r) refund\(r == 1 ? "" : "s")").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                }
            }
        }
        .padding(10)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .stroke(DesignTokens.border, lineWidth: 0.5)
        )
    }
    private func stat(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label).font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
            Text(value).font(.appCaption1.weight(.semibold).monospacedDigit())
        }
    }
}

// MARK: - History tab

private struct HistoryPanel: View {
    @ObservedObject var state: BillsState

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
            MoMCard(state: state)
            RecentBillsCard(state: state)
        }
    }
}

private struct MoMCard: View {
    @ObservedObject var state: BillsState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                Text("Month-over-Month").font(.appHeadline)
                let totals = state.utility?.monthlyTotals ?? [:]
                let sorted = totals.sorted { $0.key < $1.key }.suffix(6)
                if sorted.isEmpty {
                    EmptyStateView(systemImage: "chart.bar", title: "No month-over-month totals yet.")
                        .frame(height: 140)
                } else {
                    let maxValue = sorted.map(\.value).max() ?? 1
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(sorted), id: \.key) { entry in
                            HStack(spacing: 8) {
                                Text(entry.key).font(.appCaption1.monospaced()).frame(width: 70, alignment: .leading).foregroundStyle(DesignTokens.tertiaryLabel)
                                GeometryReader { geo in
                                    let pct = max(0.06, entry.value / max(maxValue, 0.01))
                                    Rectangle()
                                        .fill(DesignTokens.accent)
                                        .frame(width: geo.size.width * CGFloat(pct), height: 16)
                                        .clipShape(RoundedRectangle(cornerRadius: 4))
                                }
                                .frame(height: 16)
                                Text(money(entry.value)).font(.appCaption1.weight(.semibold).monospacedDigit()).frame(width: 90, alignment: .trailing)
                            }
                        }
                    }
                }
            }
        }
    }
}

private struct RecentBillsCard: View {
    @ObservedObject var state: BillsState
    @State private var expanded: Bool = false

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Recent Bills").font(.appHeadline)
                    Spacer()
                    if let count = state.utility?.recentBills?.count, count > 0 {
                        Text("\(count)").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
                let rows = state.utility?.recentBills ?? []
                if rows.isEmpty {
                    EmptyStateView(
                        systemImage: "doc.text",
                        title: "No recent bills.",
                        subtitle: "Uploaded receipts and logged cash payments appear here."
                    )
                    .frame(height: 140)
                } else {
                    let threshold = 8
                    let visible = expanded ? rows : Array(rows.prefix(threshold))
                    VStack(spacing: 4) {
                        ForEach(visible) { row in
                            RecentBillRowView(row: row)
                            Divider()
                        }
                    }
                    if rows.count > threshold {
                        Button { expanded.toggle() } label: {
                            Text(expanded ? "Show less" : "Show all \(rows.count)")
                                .font(.appCallout.weight(.semibold))
                        }
                        .buttonStyle(GhostButtonStyle())
                    }
                }
            }
        }
    }
}

private struct RecentBillRowView: View {
    let row: RecentBillRow
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.providerName ?? "Unknown")
                    .font(.appCallout.weight(.semibold))
                    .lineLimit(1)
                let meta = [row.date, row.sourceType.map { $0 == "cash_transaction" ? "Cash" : "Receipt" }, row.budgetCategory]
                    .compactMap { $0 }
                Text(meta.joined(separator: " · ")).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
            }
            Spacer()
            Text(money(row.amount))
                .font(.appCallout.weight(.semibold).monospacedDigit())
            if let pid = row.purchaseId {
                Button { Router.shared.activeTab = .receipts; Router.shared.activeDetailDestination = .receipt(pid); Task { await ReceiptsState.shared.loadDetail(id: pid) } } label: {
                    Image(systemName: "arrow.up.right.square")
                }
                .buttonStyle(.borderless)
                .help("Open receipt #\(pid)")
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }
}

// MARK: - shared helpers

private func money(_ v: Double?) -> String {
    guard let v else { return "$0.00" }
    return String(format: "$%.2f", v)
}

private enum BillsDateFormatter {
    static let dateOnly: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()
}

#Preview("FixedBillsView") {
    FixedBillsView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 1100, height: 800)
}
