import SwiftUI
import AppKit
import os.log

// F-1200..F-1279 — Accounts (Plaid).
//
// Commit A: Card Usage panel + Connected Accounts panel + Plaid Link.
// Commit B (next): Transactions tabs + Pending Review + Link/Attach modals.
// Commit C: Spend by Person + Spending Trends.

struct AccountsView: View {
    @StateObject private var state = AccountsState.shared
    @State private var renameTarget: PlaidItem?
    @State private var renameDraft: String = ""
    @State private var disconnectTarget: PlaidItem?
    @State private var renameCardTarget: CardsOverviewAccount?
    @State private var renameCardDraft: String = ""
    @State private var tagCardTarget: CardsOverviewAccount?
    @State private var tagCardDraft: String = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                pageHeader                          // F-1200
                CardUsageSection(                   // F-1201..F-1212 + sub-rows
                    state: state,
                    onRenameCard: { acct in
                        renameCardTarget = acct
                        renameCardDraft = acct.displayName ?? acct.name ?? ""
                    },
                    onTagCard: { acct in
                        tagCardTarget = acct
                        tagCardDraft = acct.ownerLabel ?? ""
                    }
                )
                ConnectionsSection(                 // F-1213..F-1229
                    state: state,
                    onRename: { item in
                        renameTarget = item
                        renameDraft = item.nickname ?? item.institutionName ?? ""
                    },
                    onDisconnect: { item in
                        disconnectTarget = item
                    }
                )
                placeholderRemainingSections        // Commit B/C placeholders
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .background(DesignTokens.background)
        .navigationTitle("Accounts")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    Task { await state.refreshAll() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Reload Card Usage + Connected Accounts")
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .task { await state.refreshAll() }
        .sheet(item: $renameTarget) { item in
            renameItemSheet(item)
        }
        .sheet(item: $disconnectTarget) { item in
            disconnectSheet(item)
        }
        .sheet(item: $renameCardTarget) { acct in
            renameCardSheet(acct)
        }
        .sheet(item: $tagCardTarget) { acct in
            tagCardSheet(acct)
        }
        .sheet(isPresented: linkSheetBinding) {
            if let token = state.pendingLinkToken {
                PlaidLinkSheet(
                    linkToken: token,
                    onSuccess: { publicToken, metadata in
                        Task {
                            await state.completePlaidLink(
                                publicToken: publicToken,
                                metadata: metadata
                            )
                        }
                    },
                    onExit: { state.cancelPlaidLink() }
                )
            }
        }
    }

    // F-1200 — page header
    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space1) {
            Text("Accounts").font(.appTitle1)
            Text("Connected banks, recent transactions, and spending trends.")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private var placeholderRemainingSections: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("Activity by Account · Spend by Person · Transactions · Spending Trends")
                    .font(.appHeadline)
                Text("Arriving in the next two builds. Existing data is already loaded into the macOS state — UI surfaces are in Commit B (Transactions + Review queue) and Commit C (Spend by Person + Spending Trends).")
                    .font(.appSubheadline)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
    }

    // MARK: - Sheets

    private var linkSheetBinding: Binding<Bool> {
        Binding(
            get: { state.pendingLinkToken != nil },
            set: { open in if !open { state.cancelPlaidLink() } }
        )
    }

    @ViewBuilder
    private func renameItemSheet(_ item: PlaidItem) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            Text("Nickname for \(item.institutionName ?? "this bank")")
                .font(.appHeadline)
            TextField("e.g. Joint chase card", text: $renameDraft)
                .textFieldStyle(.roundedBorder)
            HStack {
                Spacer()
                Button("Cancel") { renameTarget = nil }
                    .keyboardShortcut(.cancelAction)
                Button("Save") {
                    let target = item
                    let draft = renameDraft
                    renameTarget = nil
                    Task { await state.renameItem(target, nickname: draft) }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(PrimaryButtonStyle())
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 360)
    }

    @ViewBuilder
    private func disconnectSheet(_ item: PlaidItem) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            Text("Disconnect \(item.institutionName ?? "bank")?")
                .font(.appHeadline)
            Text("Disconnecting removes the Plaid token. Imported transactions stay; future syncs stop until you reconnect.")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
            HStack {
                Spacer()
                Button("Cancel") { disconnectTarget = nil }
                    .keyboardShortcut(.cancelAction)
                Button("Disconnect", role: .destructive) {
                    let target = item
                    disconnectTarget = nil
                    Task { await state.disconnectItem(target) }
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 420)
    }

    @ViewBuilder
    private func renameCardSheet(_ acct: CardsOverviewAccount) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            Text("Rename card").font(.appHeadline)
            Text("Plaid name: \(acct.originalName ?? acct.name ?? "—")")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
            TextField("Display name (blank to clear)", text: $renameCardDraft)
                .textFieldStyle(.roundedBorder)
            HStack {
                Spacer()
                Button("Cancel") { renameCardTarget = nil }
                    .keyboardShortcut(.cancelAction)
                Button("Save") {
                    let target = acct
                    let value = renameCardDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                    renameCardTarget = nil
                    Task {
                        await state.updateAccountIdentity(
                            accountId: target.id,
                            displayName: value.isEmpty ? "" : value,
                            ownerLabel: nil
                        )
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(PrimaryButtonStyle())
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 380)
    }

    @ViewBuilder
    private func tagCardSheet(_ acct: CardsOverviewAccount) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            Text("Tag person").font(.appHeadline)
            Text("Used to group Card Usage tiles by owner. Free-text — e.g. \"Nik\" or \"Joint\".")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
            TextField("Owner label (blank to clear)", text: $tagCardDraft)
                .textFieldStyle(.roundedBorder)
            HStack {
                Spacer()
                Button("Cancel") { tagCardTarget = nil }
                    .keyboardShortcut(.cancelAction)
                Button("Save") {
                    let target = acct
                    let value = tagCardDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                    tagCardTarget = nil
                    Task {
                        await state.updateAccountIdentity(
                            accountId: target.id,
                            displayName: nil,
                            ownerLabel: value.isEmpty ? "" : value
                        )
                    }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(PrimaryButtonStyle())
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 380)
    }
}

// Back-compat alias for FinanceTabView wiring.
typealias PlaidAccountsView = AccountsView

// MARK: - Card Usage section (F-1201..F-1212 + decomposed sub-rows)

private struct CardUsageSection: View {
    @ObservedObject var state: AccountsState
    let onRenameCard: (CardsOverviewAccount) -> Void
    let onTagCard: (CardsOverviewAccount) -> Void

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                header                       // F-1201 + F-1202
                if !state.cardUsageCollapsed {
                    if state.isLoadingCards && state.cardsOverview == nil {
                        loadingState
                    } else if let overview = state.cardsOverview {
                        if overview.groups.isEmpty {
                            emptyState
                        } else {
                            summaryStrip(overview)
                            if state.hasNonUsdAccounts { currencyBanner }
                            pieSubpanel(overview)
                            loansSubpanel(overview)
                            mainBody(overview)
                        }
                    } else {
                        emptyState
                    }
                }
            }
        }
    }

    // F-1201 collapse header + F-1202 refresh
    private var header: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            Button {
                state.cardUsageCollapsed.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: state.cardUsageCollapsed ? "chevron.right" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    Text("📊 Card Usage").font(.appHeadline)
                }
            }
            .buttonStyle(.plain)
            .help("Click to collapse / expand")
            Spacer()
            Button {
                Task { await state.refreshCardUsage() }
            } label: {
                if state.isRefreshingBalances {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text("Refreshing…")
                    }
                } else {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
            .buttonStyle(GhostButtonStyle())
            .disabled(state.isRefreshingBalances)
            .help("Refresh balances and reload")
        }
    }

    private var loadingState: some View {
        HStack {
            ProgressView().controlSize(.small)
            Text("Loading card usage…")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            Text("No linked credit cards or loans yet.")
                .font(.appBody)
            Button {
                Task {
                    if await state.beginPlaidLink() == nil { return }
                }
            } label: {
                Label("Link via Plaid below.", systemImage: "creditcard")
            }
            .buttonStyle(.link)
            .disabled(!state.plaidConfigured)
            .help(state.plaidConfigured ? "Open Plaid Link" : "Plaid not configured on this server")
        }
    }

    // F-1203 — 4-stat summary strip
    private func summaryStrip(_ overview: CardsOverviewResponse) -> some View {
        let totals = overview.totals
        return HStack(alignment: .top, spacing: DesignTokens.Spacing.space4) {
            statCell(label: "Total credit balance",
                     value: formatMoneyCents(totals?.creditBalanceCents ?? 0))
            statCell(label: "Total credit limit",
                     value: formatMoneyCents(totals?.creditLimitCents ?? 0))
            statCell(label: "Overall utilization",
                     value: totals?.overallUtilizationPct.map { String(format: "%.1f%%", $0) } ?? "—",
                     valueColor: utilizationColor(totals?.overallUtilizationPct))
            statCell(label: "Credit spend (this month)",
                     value: formatMoneyCents(totals?.creditSpendMtdCents ?? 0))
        }
        .padding(.vertical, DesignTokens.Spacing.space1)
    }

    private func statCell(label: String, value: String, valueColor: Color? = nil) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(.appCaption2)
                .foregroundStyle(DesignTokens.tertiaryLabel)
            Text(value)
                .font(.appTitle3.monospacedDigit())
                .foregroundStyle(valueColor ?? DesignTokens.label)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // F-1204 cross-currency banner
    private var currencyBanner: some View {
        Text("Some accounts use a non-USD currency and are excluded from totals.")
            .font(.appCaption1)
            .foregroundStyle(DesignTokens.warning)
            .padding(.horizontal, DesignTokens.Spacing.space2)
            .padding(.vertical, DesignTokens.Spacing.space1)
            .background(DesignTokens.warningDim)
            .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // F-1205..F-1208 Pie subpanel
    @ViewBuilder
    private func pieSubpanel(_ overview: CardsOverviewResponse) -> some View {
        if let credit = state.creditGroup, !credit.accounts.isEmpty {
            pieSubpanelBody(overview: overview, credit: credit)
        }
    }

    private func pieSubpanelBody(overview: CardsOverviewResponse,
                                 credit: CardsOverviewGroup) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            HStack(spacing: DesignTokens.Spacing.space2) {
                Button {
                    state.cardUsagePieCollapsed.toggle()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: state.cardUsagePieCollapsed ? "chevron.right" : "chevron.down")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryLabel)
                        Text("Spend by Category (this month)")
                            .font(.appSubheadline.weight(.semibold))
                    }
                }
                .buttonStyle(.plain)
                Spacer()
                Picker("", selection: Binding(
                    get: { state.cardUsagePieFilter },
                    set: { state.setPieFilter($0) }
                )) {
                    Text("All Cards").tag("all")
                    ForEach(credit.accounts, id: \.id) { a in
                        Text("💳 \(a.displayLabel) ····\(a.mask ?? "")")
                            .tag(a.plaidAccountId ?? "")
                    }
                }
                .labelsHidden()
                .frame(maxWidth: 240)
            }
            if !state.cardUsagePieCollapsed {
                let slices = aggregatedPieSlices(scope: state.cardUsagePieFilter, overview: overview)
                if slices.total > 0 {
                    PieDonutView(slices: slices.slices, total: slices.total)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text("No spend \(state.cardUsagePieFilter == "all" ? "this month" : "on the selected card").")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
        .padding(DesignTokens.Spacing.space3)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // F-1209/F-1210 Loan subpanel
    @ViewBuilder
    private func loansSubpanel(_ overview: CardsOverviewResponse) -> some View {
        if let loans = state.loanGroup, !loans.accounts.isEmpty {
            loansSubpanelBody(loans: loans)
        }
    }

    private func loansSubpanelBody(loans: CardsOverviewGroup) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            Button {
                state.cardUsageLoansCollapsed.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: state.cardUsageLoansCollapsed ? "chevron.right" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    Text("Loan Progress")
                        .font(.appSubheadline.weight(.semibold))
                }
            }
            .buttonStyle(.plain)
            if !state.cardUsageLoansCollapsed {
                VStack(spacing: DesignTokens.Spacing.space2) {
                    ForEach(loans.accounts, id: \.id) { acct in
                        LoanRow(account: acct)
                    }
                }
            }
        }
        .padding(DesignTokens.Spacing.space3)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // F-1211 main body — groups + owner sub-groups + chip strip + tile grid
    private func mainBody(_ overview: CardsOverviewResponse) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            if let credit = state.creditGroup, !credit.accounts.isEmpty {
                CardGroupView(
                    group: credit,
                    state: state,
                    onRename: onRenameCard,
                    onTag: onTagCard
                )
            }
        }
    }
}

// MARK: - Pie aggregation

private struct PieSlice: Identifiable, Hashable {
    let category: String
    let label: String
    let amountCents: Int
    let color: Color
    var id: String { category }
}

private struct PieAggregation {
    let slices: [PieSlice]
    let total: Int
}

private let cardUsagePalette: [Color] = [
    Color(red: 0.18, green: 0.49, blue: 0.42),
    Color(red: 0.04, green: 0.52, blue: 1.0),
    Color(red: 1.0,  green: 0.62, blue: 0.04),
    Color(red: 0.75, green: 0.36, blue: 0.95),
    Color(red: 1.0,  green: 0.27, blue: 0.23),
    Color(red: 0.20, green: 0.78, blue: 0.35),
]
private let cardUsageOtherColor = Color(red: 0.56, green: 0.56, blue: 0.58)

private func categoryLabel(_ raw: String) -> String {
    if raw == "UNCATEGORIZED" || raw.isEmpty { return "Uncategorized" }
    return raw
        .split(separator: "_")
        .map { word -> String in
            let w = String(word)
            return w.prefix(1) + w.dropFirst().lowercased()
        }
        .joined(separator: " ")
        .replacingOccurrences(of: " And ", with: " & ")
}

private func aggregatedPieSlices(scope: String, overview: CardsOverviewResponse) -> PieAggregation {
    guard let credit = overview.groups.first(where: { $0.isCredit }) else {
        return PieAggregation(slices: [], total: 0)
    }
    let pool: [CardsOverviewAccount] = scope == "all"
        ? credit.accounts
        : credit.accounts.filter { $0.plaidAccountId == scope }

    var byCat: [String: Int] = [:]
    for acct in pool {
        guard (acct.balanceCurrency ?? "USD") == "USD" else { continue }
        for c in acct.categoriesMtd ?? [] {
            byCat[c.category, default: 0] += c.amountCents
        }
    }
    var entries = byCat
        .map { ($0.key, $0.value) }
        .sorted { $0.1 > $1.1 }
    let total = entries.reduce(0) { $0 + $1.1 }
    var slices: [PieSlice] = []
    if entries.count > 6 {
        let top = Array(entries.prefix(6))
        let restTotal = entries.dropFirst(6).reduce(0) { $0 + $1.1 }
        slices = top.enumerated().map { i, e in
            PieSlice(
                category: e.0,
                label: categoryLabel(e.0),
                amountCents: e.1,
                color: cardUsagePalette[i % cardUsagePalette.count]
            )
        }
        if restTotal > 0 {
            slices.append(PieSlice(
                category: "OTHER",
                label: "Other",
                amountCents: restTotal,
                color: cardUsageOtherColor
            ))
        }
    } else {
        slices = entries.enumerated().map { i, e in
            PieSlice(
                category: e.0,
                label: categoryLabel(e.0),
                amountCents: e.1,
                color: cardUsagePalette[i % cardUsagePalette.count]
            )
        }
    }
    return PieAggregation(slices: slices, total: total)
}

// MARK: - Donut + Legend

private struct PieDonutView: View {
    let slices: [PieSlice]
    let total: Int

    var body: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.space4) {
            DonutShape(slices: slices, total: total)
                .frame(width: 160, height: 160)
            VStack(alignment: .leading, spacing: 4) {
                ForEach(slices) { slice in
                    HStack(spacing: 8) {
                        RoundedRectangle(cornerRadius: 3)
                            .fill(slice.color)
                            .frame(width: 12, height: 12)
                        Text(slice.label).font(.appCaption1)
                        Spacer(minLength: 8)
                        Text(formatMoneyCents(slice.amountCents))
                            .font(.appMonoCaption)
                        Text("\(Int((Double(slice.amountCents) / Double(max(1, total))) * 100))%")
                            .font(.appCaption2)
                            .foregroundStyle(DesignTokens.secondaryLabel)
                            .frame(width: 36, alignment: .trailing)
                    }
                }
                Divider().padding(.vertical, 2)
                HStack {
                    Text("Gross spend").font(.appCaption1.weight(.semibold))
                    Spacer()
                    Text(formatMoneyCents(total)).font(.appMonoCaption.weight(.semibold))
                }
            }
            .frame(maxWidth: 280)
        }
    }
}

private struct DonutShape: View {
    let slices: [PieSlice]
    let total: Int

    var body: some View {
        Canvas { ctx, size in
            let cx = size.width / 2
            let cy = size.height / 2
            let outer = min(cx, cy) - 4
            let inner = outer * 0.6
            var start = -Double.pi / 2
            for slice in slices {
                let fraction = Double(slice.amountCents) / Double(max(1, total))
                let end = start + fraction * 2 * .pi
                var path = Path()
                path.move(to: CGPoint(x: cx + cos(start) * outer, y: cy + sin(start) * outer))
                path.addArc(
                    center: CGPoint(x: cx, y: cy),
                    radius: outer,
                    startAngle: .radians(start),
                    endAngle: .radians(end),
                    clockwise: false
                )
                path.addLine(to: CGPoint(x: cx + cos(end) * inner, y: cy + sin(end) * inner))
                path.addArc(
                    center: CGPoint(x: cx, y: cy),
                    radius: inner,
                    startAngle: .radians(end),
                    endAngle: .radians(start),
                    clockwise: true
                )
                path.closeSubpath()
                ctx.fill(path, with: .color(slice.color))
                start = end
            }
        }
    }
}

// MARK: - Loan row

private struct LoanRow: View {
    let account: CardsOverviewAccount

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("🏦 \(account.displayLabel)").font(.appBody)
                if let mask = account.mask, !mask.isEmpty {
                    Text("····\(mask)").font(.appMonoCaption).foregroundStyle(DesignTokens.tertiaryLabel)
                }
                Spacer()
                Text(formatMoneyCents(account.balanceCents ?? 0))
                    .font(.appMonoBody.weight(.semibold))
            }
            ProgressBar(value: paidProgress)
                .frame(height: 6)
            HStack(spacing: 12) {
                metaItem("Paid", formatMoneyCents(account.paidOffCents ?? 0))
                if let orig = account.originalLoanAmountCents, orig > 0 {
                    metaItem("Original", formatMoneyCents(orig))
                }
                if let apr = account.aprBps {
                    metaItem("APR", String(format: "%.2f%%", Double(apr) / 100.0))
                }
                if let pmt = account.monthlyPaymentCents {
                    metaItem("Monthly", formatMoneyCents(pmt))
                }
                Spacer()
            }
        }
        .padding(DesignTokens.Spacing.space2)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private var paidProgress: Double {
        guard let orig = account.originalLoanAmountCents, orig > 0,
              let paid = account.paidOffCents else { return 0 }
        return min(1.0, Double(paid) / Double(orig))
    }

    private func metaItem(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(label.uppercased())
                .font(.appCaption2)
                .foregroundStyle(DesignTokens.tertiaryLabel)
            Text(value).font(.appMonoCaption)
        }
    }
}

private struct ProgressBar: View {
    let value: Double
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 3).fill(DesignTokens.surface2)
                RoundedRectangle(cornerRadius: 3)
                    .fill(DesignTokens.success)
                    .frame(width: geo.size.width * min(1.0, max(0, value)))
            }
        }
    }
}

// MARK: - Card group + owner sub-groups + chip strip + tiles

private struct CardGroupView: View {
    let group: CardsOverviewGroup
    @ObservedObject var state: AccountsState
    let onRename: (CardsOverviewAccount) -> Void
    let onTag: (CardsOverviewAccount) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            Text(group.label).font(.appHeadline)
            let anyOwner = group.accounts.contains { !($0.ownerLabel ?? "").isEmpty }
            if anyOwner {
                ForEach(ownerSubgroups(), id: \.0) { (owner, accounts) in
                    OwnerSubgroup(
                        owner: owner,
                        accounts: accounts,
                        state: state,
                        onRename: onRename,
                        onTag: onTag
                    )
                }
            } else {
                cardsBody(group.accounts)
            }
        }
    }

    private func ownerSubgroups() -> [(String?, [CardsOverviewAccount])] {
        var buckets: [String: [CardsOverviewAccount]] = [:]
        var unassigned: [CardsOverviewAccount] = []
        for acct in group.accounts {
            let label = (acct.ownerLabel ?? "").trimmingCharacters(in: .whitespaces)
            if label.isEmpty {
                unassigned.append(acct)
            } else {
                buckets[label, default: []].append(acct)
            }
        }
        var out: [(String?, [CardsOverviewAccount])] = buckets
            .sorted { $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending }
            .map { (Optional($0.key), $0.value) }
        if !unassigned.isEmpty { out.append((nil, unassigned)) }
        return out
    }

    @ViewBuilder
    private func cardsBody(_ accounts: [CardsOverviewAccount]) -> some View {
        let collapsed = accounts.filter { state.isCardCollapsed($0) }
        let expanded = accounts.filter { !state.isCardCollapsed($0) }
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            if !collapsed.isEmpty {
                CreditCardStrip(
                    accounts: collapsed,
                    hasExpanded: !expanded.isEmpty,
                    state: state
                )
            }
            if !expanded.isEmpty {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 260), spacing: 12)],
                    spacing: 12
                ) {
                    ForEach(expanded, id: \.id) { acct in
                        CreditCardTile(
                            account: acct,
                            state: state,
                            onRename: onRename,
                            onTag: onTag
                        )
                    }
                }
            }
        }
    }
}

private struct OwnerSubgroup: View {
    let owner: String?
    let accounts: [CardsOverviewAccount]
    @ObservedObject var state: AccountsState
    let onRename: (CardsOverviewAccount) -> Void
    let onTag: (CardsOverviewAccount) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            head
            // Render directly — never re-enter CardGroupView (it would
            // re-detect anyOwner==true on the sub-group and recurse
            // forever, blowing the stack).
            let collapsed = accounts.filter { state.isCardCollapsed($0) }
            let expanded = accounts.filter { !state.isCardCollapsed($0) }
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                if !collapsed.isEmpty {
                    CreditCardStrip(
                        accounts: collapsed,
                        hasExpanded: !expanded.isEmpty,
                        state: state
                    )
                }
                if !expanded.isEmpty {
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 260), spacing: 12)],
                        spacing: 12
                    ) {
                        ForEach(expanded, id: \.id) { acct in
                            CreditCardTile(
                                account: acct,
                                state: state,
                                onRename: onRename,
                                onTag: onTag
                            )
                        }
                    }
                }
            }
            .padding(.leading, 4)
        }
        .padding(.vertical, 4)
    }

    private var head: some View {
        HStack(spacing: 8) {
            ownerBadge
            Text("\(accounts.count) card\(accounts.count == 1 ? "" : "s")")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
            Spacer()
            Text("Balance: \(formatMoneyCents(totalBalance))").font(.appCaption1)
            Text("Limit: \(totalLimit > 0 ? formatMoneyCents(totalLimit) : "—")").font(.appCaption1)
            Text("Util: \(utilText)")
                .font(.appCaption1.weight(.semibold))
                .foregroundStyle(utilColor)
        }
    }

    private var ownerBadge: some View {
        if let owner {
            return Badge(text: "👤 \(owner)", style: .info)
        } else {
            return Badge(text: "Unassigned", style: .neutral)
        }
    }

    private var totalBalance: Int { accounts.reduce(0) { $0 + ($1.balanceCents ?? 0) } }
    private var totalLimit: Int { accounts.reduce(0) { $0 + ($1.creditLimitCents ?? 0) } }
    private var utilization: Double? {
        guard totalLimit > 0 else { return nil }
        return Double(totalBalance) / Double(totalLimit) * 100.0
    }
    private var utilText: String { utilization.map { String(format: "%.1f%%", $0) } ?? "—" }
    private var utilColor: Color { utilizationColor(utilization) }
}

private struct CreditCardStrip: View {
    let accounts: [CardsOverviewAccount]
    let hasExpanded: Bool
    @ObservedObject var state: AccountsState

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if hasExpanded {
                Text("Other Cards · \(accounts.count)")
                    .font(.appCaption1.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 200), spacing: 8)],
                spacing: 8
            ) {
                ForEach(accounts, id: \.id) { acct in
                    CreditCardChip(account: acct, state: state)
                }
            }
        }
    }
}

private struct CreditCardChip: View {
    let account: CardsOverviewAccount
    @ObservedObject var state: AccountsState
    @State private var showPopover = false

    var body: some View {
        Button {
            state.setCardCollapsed(account.plaidAccountId ?? "", collapsed: false)
        } label: {
            HStack(spacing: 6) {
                Rectangle()
                    .fill(issuerColor)
                    .frame(width: 3, height: 22)
                    .cornerRadius(1.5)
                Text(account.displayLabel).font(.appCaption1).lineLimit(1)
                if let mask = account.mask {
                    Text("····\(mask)").font(.appMonoCaption).foregroundStyle(DesignTokens.tertiaryLabel)
                }
                Spacer(minLength: 4)
                UtilBar(value: account.utilizationPct)
                    .frame(width: 56, height: 6)
                Text(account.utilizationPct.map { String(format: "%.0f%%", $0) } ?? "—")
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(utilColor(account.utilizationPct))
                    .frame(width: 36, alignment: .trailing)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(DesignTokens.surface)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(DesignTokens.border, lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            showPopover = hovering
        }
        .popover(isPresented: $showPopover, arrowEdge: .top) {
            ChipPopoverContent(account: account)
                .frame(width: 240)
                .padding(DesignTokens.Spacing.space2)
        }
    }

    private var issuerColor: Color {
        let n = (account.name ?? "").lowercased()
        if n.contains("chase") { return Color(red: 0.04, green: 0.29, blue: 0.56) }
        if n.contains("bank of america") || n.contains("boa ") { return Color(red: 0.8, green: 0.12, blue: 0.10) }
        if n.contains("wells") { return Color(red: 0.84, green: 0.12, blue: 0.16) }
        if n.contains("citi") { return Color(red: 0.0, green: 0.23, blue: 0.44) }
        if n.contains("capital one") { return Color(red: 0.82, green: 0.18, blue: 0.18) }
        if n.contains("discover") { return Color(red: 1.0, green: 0.4, blue: 0.0) }
        if n.contains("amex") || n.contains("american express") { return Color(red: 0.0, green: 0.4, blue: 0.7) }
        return DesignTokens.secondaryLabel
    }
}

private struct ChipPopoverContent: View {
    let account: CardsOverviewAccount

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("\(account.displayLabel) ····\(account.mask ?? "")")
                .font(.appCaption1.weight(.semibold))
            row("Used", formatMoneyCents(account.balanceCents ?? 0))
            row("Available", account.availableCreditCents.map { formatMoneyCents($0) } ?? "—")
            row("Limit", account.creditLimitCents.map { formatMoneyCents($0) } ?? "—")
            row("Utilization",
                account.utilizationPct.map { String(format: "%.1f%%", $0) } ?? "—",
                color: utilColor(account.utilizationPct))
            if let owner = account.ownerLabel, !owner.isEmpty {
                row("Owner", "👤 \(owner)")
            }
        }
    }

    private func row(_ label: String, _ value: String, color: Color = DesignTokens.label) -> some View {
        HStack {
            Text(label).font(.appCaption2).foregroundStyle(DesignTokens.secondaryLabel)
            Spacer()
            Text(value).font(.appMonoCaption).foregroundStyle(color)
        }
    }
}

private struct UtilBar: View {
    let value: Double?
    var body: some View {
        GeometryReader { geo in
            let pct = min(1.0, max(0, (value ?? 0) / 100.0))
            ZStack(alignment: .leading) {
                Capsule().fill(DesignTokens.surface2)
                Capsule()
                    .fill(utilColor(value))
                    .frame(width: geo.size.width * pct)
            }
        }
    }
}

private struct CreditCardTile: View {
    let account: CardsOverviewAccount
    @ObservedObject var state: AccountsState
    let onRename: (CardsOverviewAccount) -> Void
    let onTag: (CardsOverviewAccount) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            head
            hero
            statsGrid
            footer
        }
        .padding(DesignTokens.Spacing.space3)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(DesignTokens.border, lineWidth: 0.5)
        )
    }

    private var head: some View {
        HStack(spacing: 6) {
            Text("💳").font(.appBody)
            Text(account.displayLabel).font(.appBody.weight(.semibold)).lineLimit(1)
            if let mask = account.mask {
                Text("····\(mask)").font(.appMonoCaption).foregroundStyle(DesignTokens.tertiaryLabel)
            }
            ownerBadge
            Spacer()
            Button { onRename(account) } label: {
                Image(systemName: "pencil").font(.caption)
            }
            .buttonStyle(.plain)
            .help("Rename card")
            Button { onTag(account) } label: {
                Image(systemName: "person.crop.circle.badge.plus").font(.caption)
            }
            .buttonStyle(.plain)
            .help("Tag person")
            Button {
                state.setCardCollapsed(account.plaidAccountId ?? "", collapsed: true)
            } label: {
                Image(systemName: "chevron.up").font(.caption)
            }
            .buttonStyle(.plain)
            .help("Collapse to chip")
        }
    }

    @ViewBuilder
    private var ownerBadge: some View {
        if let owner = account.ownerLabel?.trimmingCharacters(in: .whitespaces),
           !owner.isEmpty {
            Badge(text: "👤 \(owner)", style: .info)
        } else {
            Button { onTag(account) } label: {
                Badge(text: "+ tag", style: .neutral)
            }
            .buttonStyle(.plain)
        }
    }

    private var hero: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            UtilizationRing(value: account.utilizationPct, size: 88)
            VStack(alignment: .leading, spacing: 4) {
                if let chip = statusChip {
                    Badge(text: chip.text, style: chip.style)
                }
                Text(account.utilizationPct.map { String(format: "%.0f%% utilization", $0) } ?? "Utilization —")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
            Spacer()
        }
    }

    private var statsGrid: some View {
        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
            GridRow {
                Text("Balance").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                Text(formatMoneyCents(account.balanceCents ?? 0))
                    .font(.appMonoCaption.weight(.semibold))
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            GridRow {
                Text("Limit").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                Text(account.creditLimitCents.map { formatMoneyCents($0) } ?? "—")
                    .font(.appMonoCaption.weight(.semibold))
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            if let avail = account.availableCreditCents {
                GridRow {
                    Text("Available").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    Text(formatMoneyCents(avail))
                        .font(.appMonoCaption.weight(.semibold))
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
        }
    }

    private var footer: some View {
        HStack {
            let spend = account.spendMtdCents ?? 0
            Text("MTD \(formatMoneyCents(spend)) · \(account.txnCountMtd ?? 0) txns")
                .font(.appCaption1)
                .foregroundStyle(spend < 0 ? DesignTokens.warning : DesignTokens.secondaryLabel)
            Spacer()
            Text(account.balanceUpdatedDate.map { relativeTimeAgo($0) } ?? "Not refreshed")
                .font(.appCaption2)
                .foregroundStyle(DesignTokens.tertiaryLabel)
        }
    }

    private struct ChipInfo { let text: String; let style: Badge.Style }
    private var statusChip: ChipInfo? {
        guard let pct = account.utilizationPct else { return nil }
        if pct < 30 { return ChipInfo(text: "Healthy", style: .success) }
        if pct < 70 { return ChipInfo(text: "Watch", style: .warning) }
        return ChipInfo(text: "High", style: .error)
    }
}

private struct UtilizationRing: View {
    let value: Double?
    let size: CGFloat

    var body: some View {
        ZStack {
            Circle()
                .stroke(DesignTokens.surface2, lineWidth: 8)
            if let value {
                let frac = min(1.0, max(0, value / 100.0))
                Circle()
                    .trim(from: 0, to: frac)
                    .stroke(utilColor(value), style: StrokeStyle(lineWidth: 8, lineCap: .round))
                    .rotationEffect(.degrees(-90))
            }
            Text(value.map { String(format: "%.0f%%", $0) } ?? "—")
                .font(.appCaption1.monospacedDigit().weight(.semibold))
                .foregroundStyle(value == nil ? DesignTokens.tertiaryLabel : DesignTokens.label)
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Connections (F-1213..F-1229)

private struct ConnectionsSection: View {
    @ObservedObject var state: AccountsState
    let onRename: (PlaidItem) -> Void
    let onDisconnect: (PlaidItem) -> Void

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                header
                if !state.connectionsCollapsed {
                    Text("Connect a bank or credit card via Plaid to auto-import transactions. Imported transactions land in a review queue and are never saved as receipts without your confirmation.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    if state.isLoadingConnections && state.items.isEmpty {
                        loadingState
                    } else if state.items.isEmpty {
                        noConnectionsState
                    } else {
                        ForEach(state.items, id: \.id) { item in
                            ConnectionItemCard(
                                item: item,
                                subAccounts: state.subAccounts(forItem: item.id),
                                state: state,
                                onRename: { onRename(item) },
                                onDisconnect: { onDisconnect(item) }
                            )
                        }
                    }
                }
            }
        }
    }

    private var header: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            Button {
                state.connectionsCollapsed.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: state.connectionsCollapsed ? "chevron.right" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    Text("🏦 Connected Accounts").font(.appHeadline)
                }
            }
            .buttonStyle(.plain)
            Spacer()
            Button {
                Task {
                    if await state.beginPlaidLink() == nil { return }
                }
            } label: {
                Label("Connect Bank", systemImage: "plus")
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(!state.plaidConfigured)
            .help(state.plaidConfigured ? "Open Plaid Link" : "Plaid not configured on this server")
            Button {
                Task { await state.refreshBalances() }
            } label: {
                Label("Refresh Balances", systemImage: "dollarsign.arrow.circlepath")
            }
            .buttonStyle(GhostButtonStyle())
            .disabled(state.isRefreshingBalances || state.items.isEmpty)
            .help("Refresh balances for all connected banks")
            Button {
                Task { await state.loadConnections() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload without refreshing balances")
        }
    }

    private var loadingState: some View {
        HStack {
            ProgressView().controlSize(.small)
            Text("Loading connected accounts…")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private var noConnectionsState: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            Text("No banks connected yet.")
                .font(.appBody)
            Text(state.plaidConfigured
                 ? "Press Connect Bank above to start the Plaid Link flow."
                 : "This server has no Plaid keys configured. Set PLAID_CLIENT_ID + PLAID_SECRET in .env then reload.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }
}

private struct ConnectionItemCard: View {
    let item: PlaidItem
    let subAccounts: [PlaidAccount]
    @ObservedObject var state: AccountsState
    let onRename: () -> Void
    let onDisconnect: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            titleRow
            syncRow
            if let err = item.lastSyncError, !err.isEmpty {
                errorRow(err)
            }
            subList
            actionsRow
        }
        .padding(DesignTokens.Spacing.space3)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(DesignTokens.border, lineWidth: 0.5)
        )
    }

    private var titleRow: some View {
        HStack(spacing: 6) {
            Text(item.institutionName ?? "Institution").font(.appHeadline)
            if let nickname = item.nickname?.trimmingCharacters(in: .whitespaces),
               !nickname.isEmpty {
                Text("— \(nickname)").font(.appSubheadline).foregroundStyle(DesignTokens.secondaryLabel)
            }
            Spacer()
            statusBadge
        }
    }

    private var statusBadge: some View {
        let raw = (item.status ?? "").lowercased()
        switch raw {
        case "active":          return Badge(text: "Connected", style: .success)
        case "login_required":  return Badge(text: "Login required", style: .error)
        case "":                return Badge(text: "—", style: .neutral)
        default:                return Badge(text: raw.capitalized, style: .neutral)
        }
    }

    private var syncRow: some View {
        HStack(spacing: 6) {
            Text("Last sync \(item.lastSyncDate.map { relativeTimeAgo($0) } ?? "—")")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
            if let statusVal = item.lastSyncStatus, !statusVal.isEmpty, statusVal != "ok" {
                Text("· \(statusVal)")
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.warning)
            }
        }
    }

    private func errorRow(_ err: String) -> some View {
        let lower = err.lowercased()
        let isAuthErr = lower.contains("invalid client_id")
            || lower.contains("invalid_api_keys")
            || lower.contains("invalid api keys")
        return VStack(alignment: .leading, spacing: 2) {
            Text("⚠️ \(err)")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.error)
            if isAuthErr {
                Text("→ Check PLAID_CLIENT_ID and PLAID_SECRET in .env, then disconnect & reconnect this bank.")
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
    }

    @ViewBuilder
    private var subList: some View {
        if subAccounts.isEmpty {
            Text("No sub-accounts found yet. Try Sync Now.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
        } else {
            let anyBalance = subAccounts.contains { $0.balanceCents != nil }
            VStack(alignment: .leading, spacing: 4) {
                ForEach(subAccounts, id: \.id) { acct in
                    HStack(spacing: 6) {
                        Text(subLabel(acct))
                            .font(.appCaption1)
                            .lineLimit(1)
                        Spacer()
                        if let cents = acct.balanceCents {
                            Text(formatMoneyCents(cents, currency: acct.balanceCurrency))
                                .font(.appMonoCaption.weight(.semibold))
                            if let ts = acct.lastSyncedAtDate {
                                Text("· \(relativeTimeAgo(ts))")
                                    .font(.appCaption2)
                                    .foregroundStyle(DesignTokens.tertiaryLabel)
                            }
                        } else if anyBalance {
                            Text("—").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                        }
                    }
                }
                if !anyBalance {
                    Text("💤 Balances not yet refreshed — tap 💵 Refresh Balances above.")
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
    }

    private func subLabel(_ acct: PlaidAccount) -> String {
        var bits: [String] = [acct.accountName]
        if let sub = acct.subtype {
            bits.append(sub.replacingOccurrences(of: "_", with: " "))
        }
        if let mask = acct.mask, !mask.isEmpty {
            bits.append("····\(mask)")
        }
        return bits.joined(separator: " · ")
    }

    private var actionsRow: some View {
        HStack(spacing: 6) {
            if item.isLoginRequired {
                Button {
                    Task {
                        if await state.beginPlaidLink(itemId: item.id) == nil { return }
                    }
                } label: {
                    Label("Re-authenticate", systemImage: "key.fill")
                }
                .buttonStyle(PrimaryButtonStyle())
                .controlSize(.small)
            } else {
                Button {
                    Task { await state.syncItem(item) }
                } label: {
                    Label("Sync Now", systemImage: "arrow.triangle.2.circlepath")
                }
                .buttonStyle(GhostButtonStyle())
                .controlSize(.small)
            }
            Button {
                onRename()
            } label: {
                Label("Rename", systemImage: "pencil")
            }
            .buttonStyle(GhostButtonStyle())
            .controlSize(.small)
            Button {
                onDisconnect()
            } label: {
                Label("Disconnect", systemImage: "xmark.circle")
            }
            .buttonStyle(GhostButtonStyle())
            .controlSize(.small)
            Spacer()
        }
    }
}

// MARK: - Helpers

private func formatMoneyCents(_ cents: Int, currency: String? = "USD") -> String {
    let amount = Double(cents) / 100.0
    let nf = NumberFormatter()
    nf.numberStyle = .currency
    nf.currencyCode = currency ?? "USD"
    nf.minimumFractionDigits = 2
    nf.maximumFractionDigits = 2
    return nf.string(from: NSNumber(value: amount))
        ?? String(format: "$%.2f", amount)
}

private func utilizationColor(_ pct: Double?) -> Color {
    guard let p = pct else { return DesignTokens.secondaryLabel }
    if p >= 70 { return DesignTokens.error }
    if p >= 30 { return DesignTokens.warning }
    return DesignTokens.success
}

private func utilColor(_ pct: Double?) -> Color { utilizationColor(pct) }

private func relativeTimeAgo(_ date: Date) -> String {
    let formatter = RelativeDateTimeFormatter()
    formatter.unitsStyle = .short
    return formatter.localizedString(for: date, relativeTo: Date())
}

#Preview("Accounts") {
    AccountsView().frame(width: 900, height: 700)
}
