import SwiftUI
import AppKit

// F-1400..F-1427 — Household Budget.

struct BudgetView: View {
    @StateObject private var state = BudgetState.shared
    @EnvironmentObject private var appState: AppState
    @State private var draftMonth: String = ""
    @State private var expandedCategory: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                pageHeader                          // F-1400
                editorCard                          // F-1401..F-1409 + F-1427 admin gate
                statusCard                          // F-1410..F-1420
                targetsCard                         // F-1421..F-1423
                historyCard                         // F-1424..F-1426
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .background(DesignTokens.background)
        .navigationTitle("Budget")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    Task { await state.refreshAll() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .keyboardShortcut("r", modifiers: .command)
                .help("Reload budget data")
            }
        }
        .task { await state.refreshAll() }
        .onAppear { draftMonth = state.month }
        .onChange(of: state.month) { new in if draftMonth != new { draftMonth = new } }
    }

    // F-1400
    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Budget").font(.appTitle1)
            Text("Track monthly budgets by category.")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    // F-1401..F-1409
    private var editorCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                editorHeader                        // F-1401..F-1404
                if !state.editorCollapsed {
                    editorForm                      // F-1405..F-1409
                }
            }
        }
    }

    // F-1401 + F-1402 + F-1403 + F-1404
    private var editorHeader: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            Button {
                state.editorCollapsed.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: state.editorCollapsed ? "chevron.right" : "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    Text("⚙ Budget").font(.appHeadline)
                }
            }
            .buttonStyle(.plain)
            .help("Collapse / expand the editor")
            Spacer()
            Button {
                ToastQueue.shared.push(Toast(
                    message: "Manual entry deferred to v1.1 — use the web app for now.",
                    severity: .info
                ))
            } label: {
                Label("Manual Entry", systemImage: "square.and.pencil")
            }
            .buttonStyle(GhostButtonStyle())
            .controlSize(.small)
            .help("Web shows a full receipt-entry modal here — v1.1 surface")
            Button {
                Router.shared.activeSheet = .cashTransaction
            } label: {
                Label("Log Cash", systemImage: "banknote")
            }
            .buttonStyle(PrimaryButtonStyle())
            .controlSize(.small)
            .help("Open the cash-transaction sheet")
        }
    }

    // F-1405..F-1409
    private var editorForm: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.space3) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("MONTH")
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                    TextField("YYYY-MM", text: $draftMonth)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 110)
                        .onSubmit { commitMonth() }
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("BUDGET CATEGORY")
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                    Picker("", selection: Binding(
                        get: { state.selectedCategory },
                        set: { state.selectedCategory = $0 }
                    )) {
                        ForEach(BudgetCategoryCatalog.all, id: \.self) { cat in
                            Text(BudgetCategoryCatalog.label(for: cat)).tag(cat)
                        }
                    }
                    .labelsHidden()
                    .frame(width: 200)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("BUDGET ($)")
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                    TextField("500", text: $state.draftAmount)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 120)
                }
                Spacer()
            }
            HStack(spacing: DesignTokens.Spacing.space2) {
                Button {
                    saveBudget()
                } label: {
                    Label("Save Budget", systemImage: "tray.and.arrow.down")
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!canSave)
                .help(canSave
                      ? "Save the budget target for this category and month"
                      : "Only admins can update budgets")
                Text("Receipt defaults and line-item overrides decide how spending rolls into each budget category.")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
                Spacer()
            }
        }
    }

    private var isAdmin: Bool { appState.currentUser?.isAdmin == true }
    // F-1427 admin gate
    private var canSave: Bool {
        isAdmin && parsedAmount != nil
    }
    private var parsedAmount: Double? {
        let trimmed = state.draftAmount.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let val = Double(trimmed), val >= 0 else { return nil }
        return val
    }

    private func commitMonth() {
        let trimmed = draftMonth.trimmingCharacters(in: .whitespacesAndNewlines)
        guard BudgetState.isValidMonth(trimmed) else {
            ToastQueue.shared.push(Toast(message: "Use YYYY-MM format.", severity: .error))
            draftMonth = state.month
            return
        }
        state.setMonth(trimmed)
    }

    private func saveBudget() {
        guard let amount = parsedAmount else { return }
        Task { await state.saveBudget(amount: amount) }
    }

    // F-1410..F-1420
    private var statusCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                statusHeader
                statusBody
            }
        }
    }

    // F-1410 + F-1411 + F-1412
    private var statusHeader: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            Text("This Month").font(.appHeadline)
            Spacer()
            Text(String(format: "$%.2f", state.totalSpent))
                .font(.appMonoBody.weight(.semibold))
            Button {
                Task { await state.loadSummary() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Refresh status")
        }
    }

    @ViewBuilder
    private var statusBody: some View {
        if state.isLoadingSummary && state.summary == nil {
            HStack {
                ProgressView().controlSize(.small)
                Text("Loading budget…").font(.appSubheadline).foregroundStyle(DesignTokens.secondaryLabel)
            }
        } else if let err = state.summaryError, state.summary == nil {
            Text(err).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        } else if state.summary != nil {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                if !state.activeCategories.isEmpty {
                    Text("Active Categories")
                        .font(.appCaption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    VStack(spacing: 6) {
                        ForEach(state.activeCategories, id: \.id) { row in
                            categoryRow(row)
                        }
                    }
                }
                if !state.inactiveCategories.isEmpty {
                    DisclosureGroup("Other Categories · \(state.inactiveCategories.count)") {
                        VStack(spacing: 6) {
                            ForEach(state.inactiveCategories, id: \.id) { row in
                                categoryRow(row)
                            }
                        }
                        .padding(.top, 4)
                    }
                    .font(.appBody.weight(.semibold))
                }
            }
        } else {
            Text("No budget set for this month.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    // F-1415..F-1419
    private func categoryRow(_ row: BudgetCategoryStatus) -> some View {
        let isExpanded = expandedCategory == row.id
        return VStack(alignment: .leading, spacing: 4) {
            Button {
                state.selectedCategory = row.budgetCategory   // F-1415 sync to editor
                expandedCategory = isExpanded ? nil : row.id
            } label: {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(BudgetCategoryCatalog.label(for: row.budgetCategory))
                            .font(.appBody.weight(.semibold))
                        Spacer()
                        Text(String(format: "$%.2f", row.spent))
                            .font(.appMonoBody.weight(.semibold))
                    }
                    ProgressBar(value: row.pctClamped / 100.0, severity: row.severityColor)
                        .frame(height: 4)
                    HStack {
                        Text("\(Int(row.percentage))% · \(row.remainingLabel)")
                            .font(.appCaption1)
                            .foregroundStyle(row.isOver ? DesignTokens.error : DesignTokens.secondaryLabel)
                        Spacer()
                        Text(row.targetLabel)
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
            }
            .buttonStyle(.plain)
            if isExpanded {
                contributionsList(row)
                    .padding(.top, 4)
            }
        }
        .padding(DesignTokens.Spacing.space2)
        .background(state.selectedCategory == row.budgetCategory ? DesignTokens.accentDim : DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(state.selectedCategory == row.budgetCategory
                        ? DesignTokens.accent : DesignTokens.border,
                        lineWidth: state.selectedCategory == row.budgetCategory ? 1 : 0.5)
        )
    }

    // F-1419
    @ViewBuilder
    private func contributionsList(_ row: BudgetCategoryStatus) -> some View {
        if let contribs = row.contributions, !contribs.isEmpty {
            VStack(spacing: 2) {
                ForEach(Array(contribs.enumerated()), id: \.offset) { _, c in
                    HStack {
                        Text(c.store ?? "—").font(.appCaption1).lineLimit(1)
                        if let s = c.date {
                            Text(s).font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                        }
                        Spacer()
                        let isRefund = (c.transactionType ?? "").lowercased() == "refund"
                        Text(String(format: "$%.2f", c.amount))
                            .font(.appMonoCaption)
                            .foregroundStyle(isRefund ? DesignTokens.warning : DesignTokens.label)
                    }
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(DesignTokens.background)
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                }
            }
        } else {
            Text("No contributing receipts yet.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    // F-1421..F-1423
    private var targetsCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Button {
                    state.targetsCollapsed.toggle()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: state.targetsCollapsed ? "chevron.right" : "chevron.down")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryLabel)
                        Text("Current Budget Targets").font(.appHeadline)
                        Spacer()
                        Text("\(state.targets.count) set")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.secondaryLabel)
                    }
                }
                .buttonStyle(.plain)
                if !state.targetsCollapsed {
                    targetsBody
                }
            }
        }
    }

    @ViewBuilder
    private var targetsBody: some View {
        if let err = state.historyError, state.targets.isEmpty {
            Text("Could not load current budget targets.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.error)
                .help(err)
        } else if state.targets.isEmpty {
            Text("No category targets set for this month.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
        } else {
            VStack(spacing: 4) {
                ForEach(state.targets, id: \.id) { t in
                    HStack {
                        Text(BudgetCategoryCatalog.label(for: t.budgetCategory))
                            .font(.appBody)
                        Spacer()
                        Text(String(format: "$%.2f", t.budgetAmount))
                            .font(.appMonoCaption.weight(.semibold))
                        if let updated = t.updatedAt {
                            Text(prettyDate(updated))
                                .font(.appCaption2)
                                .foregroundStyle(DesignTokens.tertiaryLabel)
                        }
                    }
                    .padding(.horizontal, DesignTokens.Spacing.space2)
                    .padding(.vertical, 4)
                    .background(DesignTokens.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                }
            }
        }
    }

    // F-1424..F-1426
    private var historyCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Button {
                    state.historyCollapsed.toggle()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: state.historyCollapsed ? "chevron.right" : "chevron.down")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryLabel)
                        Text("Budget Change History").font(.appHeadline)
                        Spacer()
                        Text("\(state.history.count) change\(state.history.count == 1 ? "" : "s")")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.secondaryLabel)
                    }
                }
                .buttonStyle(.plain)
                if !state.historyCollapsed {
                    historyBody
                }
            }
        }
    }

    @ViewBuilder
    private var historyBody: some View {
        if let err = state.historyError, state.history.isEmpty {
            Text("Could not load budget history.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.error)
                .help(err)
        } else if state.history.isEmpty {
            Text("No changes yet this month.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
        } else {
            VStack(spacing: 4) {
                ForEach(state.history, id: \.id) { h in
                    HStack {
                        Text(BudgetCategoryCatalog.label(for: h.budgetCategory ?? "—"))
                            .font(.appBody)
                        Spacer()
                        Text(h.deltaLabel)
                            .font(.appMonoCaption)
                        Text(h.changedAtDate.map { relativeTimeAgo($0) } ?? "—")
                            .font(.appCaption2)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                    .padding(.horizontal, DesignTokens.Spacing.space2)
                    .padding(.vertical, 4)
                    .background(DesignTokens.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                }
            }
        }
    }

    private func prettyDate(_ iso: String) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let d = f.date(from: iso) ?? ISO8601DateFormatter().date(from: iso) else { return iso }
        return relativeTimeAgo(d)
    }

    private func relativeTimeAgo(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

private struct ProgressBar: View {
    let value: Double
    let severity: BudgetSeverity
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 3).fill(DesignTokens.surface2)
                RoundedRectangle(cornerRadius: 3)
                    .fill(fillColor)
                    .frame(width: geo.size.width * min(1.0, max(0, value)))
            }
        }
    }
    private var fillColor: Color {
        switch severity {
        case .ok:     return DesignTokens.success
        case .warn:   return DesignTokens.warning
        case .danger: return DesignTokens.error
        }
    }
}

#Preview("Budget") {
    BudgetView()
        .environmentObject(AppState.shared)
        .frame(width: 900, height: 700)
}
