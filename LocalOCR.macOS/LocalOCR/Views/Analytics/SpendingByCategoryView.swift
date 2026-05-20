import SwiftUI

// F-1300..F-1321 — Analytics (Spending Overview + Deals Captured).

struct SpendingByCategoryView: View {
    @StateObject private var state = AnalyticsState.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                pageHeader                   // F-1300
                spendingOverviewCard         // F-1301..F-1317
                dealsCapturedCard            // F-1318..F-1320
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .background(DesignTokens.background)
        .navigationTitle("Analytics")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { Task { await state.refreshAll() } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Recompute analytics")
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .task { await state.refreshAll() }
    }

    // F-1300
    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Analytics").font(.appTitle1)
            Text("Understand spending patterns by module.")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    // F-1301..F-1317
    private var spendingOverviewCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                toolbar
                if state.totalRefundCount > 0 {
                    refundSummary                // F-1313
                }
                analyticsBody                    // F-1314..F-1317
            }
        }
    }

    // F-1302..F-1312 (filters + Review Refunds)
    private var toolbar: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            Text("Spending Overview").font(.appHeadline)
            Spacer()
            Picker("", selection: Binding(get: { state.period }, set: { state.period = $0 })) {
                ForEach(AnalyticsState.Period.allCases) { p in
                    Text(p.label).tag(p)
                }
            }
            .labelsHidden()
            .frame(maxWidth: 120)
            .help("Bucket size")
            Picker("", selection: Binding(get: { state.domain }, set: { state.domain = $0 })) {
                ForEach(AnalyticsState.Domain.allCases) { d in
                    Text(d.label).tag(d)
                }
            }
            .labelsHidden()
            .frame(maxWidth: 170)
            .help("Module domain")
            Picker("", selection: Binding(get: { state.sort }, set: { state.sort = $0 })) {
                ForEach(AnalyticsState.Sort.allCases) { s in
                    Text(s.label).tag(s)
                }
            }
            .labelsHidden()
            .frame(maxWidth: 170)
            .help("Sort order")
            Button {
                NotificationCenter.default.post(
                    name: .openRefundReceipts,
                    object: nil
                )
            } label: {
                Label("Review Refunds", systemImage: "arrow.uturn.backward")
            }
            .buttonStyle(GhostButtonStyle())
            .controlSize(.small)
            .help("Jump to Receipts page filtered to refunds")
        }
    }

    // F-1313
    private var refundSummary: some View {
        HStack(spacing: 6) {
            Text("↩")
                .foregroundStyle(DesignTokens.warning)
            Text("\(state.totalRefundCount) refund\(state.totalRefundCount == 1 ? "" : "s") · \(String(format: "$%.2f", state.totalRefundAmount)) returned")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.warning)
            Spacer()
        }
        .padding(.horizontal, DesignTokens.Spacing.space2)
        .padding(.vertical, DesignTokens.Spacing.space1)
        .background(DesignTokens.warningDim)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // F-1314..F-1317
    @ViewBuilder
    private var analyticsBody: some View {
        if state.isLoadingSpending && state.spending == nil {
            HStack {
                ProgressView().controlSize(.small)
                Text("Loading spending…")
                    .font(.appSubheadline)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
        } else if let err = state.spendingError {
            Text(err).font(.appCaption1).foregroundStyle(DesignTokens.error)
        } else if state.sortedRows.isEmpty {
            VStack(spacing: 6) {
                Text("📊").font(.system(size: 32))
                Text("No spending data yet. Upload a receipt to get started.")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, DesignTokens.Spacing.space4)
        } else {
            periodTable
            grandTotal
        }
    }

    // F-1314
    private var periodTable: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Text("PERIOD").frame(width: 110, alignment: .leading)
                Text("NET").frame(maxWidth: .infinity, alignment: .trailing)
                Text("PURCHASES").frame(width: 120, alignment: .trailing)
                Text("REFUNDS").frame(width: 110, alignment: .trailing)
                Text("RECEIPTS").frame(width: 90, alignment: .trailing)
            }
            .font(.appCaption2)
            .foregroundStyle(DesignTokens.tertiaryLabel)
            .padding(.horizontal, 6)
            .padding(.bottom, 4)
            Divider()
            ForEach(state.sortedRows) { row in
                periodRow(row)
            }
        }
    }

    private func periodRow(_ row: AnalyticsPeriodRow) -> some View {
        HStack(spacing: 8) {
            Text(prettyPeriod(row.id))
                .font(.appBody.monospacedDigit())
                .frame(width: 110, alignment: .leading)
            Text(String(format: "$%.2f", row.net))
                .font(.appMonoBody.weight(.semibold))
                .frame(maxWidth: .infinity, alignment: .trailing)
            Text("\(row.purchaseCount)")
                .font(.appMonoCaption)
                .frame(width: 120, alignment: .trailing)
                .help(String(format: "$%.2f purchases", row.purchaseTotal))
            refundCell(row)
                .frame(width: 110, alignment: .trailing)
            Text("\(row.receiptCount)")
                .font(.appMonoCaption)
                .frame(width: 90, alignment: .trailing)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 6)
        .background(rowBackground)
        .clipShape(RoundedRectangle(cornerRadius: 4))
    }

    @ViewBuilder
    private func refundCell(_ row: AnalyticsPeriodRow) -> some View {
        if row.refundCount > 0 {
            Text("\(row.refundCount)")
                .font(.appMonoCaption)
                .foregroundStyle(DesignTokens.warning)
                .help(String(format: "$%.2f returned", row.refundTotal))
        } else {
            Text("0")
                .font(.appMonoCaption)
                .foregroundStyle(DesignTokens.tertiaryLabel)
        }
    }

    private var grandTotal: some View {
        HStack {
            Spacer()
            Text("Grand total: \(String(format: "$%.2f", state.spending?.grandTotal ?? 0))")
                .font(.appBody.weight(.semibold))
        }
        .padding(.top, DesignTokens.Spacing.space2)
    }

    // F-1318..F-1320
    private var dealsCapturedCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("💎 Deals Captured").font(.appHeadline)
                if !state.showsDealsBody {
                    Text("Restaurant / general-expense spend is tracked separately from grocery deal detection.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                } else if state.isLoadingDeals && state.deals == nil {
                    HStack {
                        ProgressView().controlSize(.small)
                        Text("Loading deals…").font(.appSubheadline)
                    }
                } else if let err = state.dealsError {
                    Text(err).font(.appCaption1).foregroundStyle(DesignTokens.error)
                } else if let d = state.deals, d.dealCount == 0 {
                    Text("No deals tracked yet.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                } else if let d = state.deals {
                    Text("\(String(format: "$%.2f", d.totalSaved)) saved")
                        .font(.appTitle2.weight(.semibold))
                        .foregroundStyle(DesignTokens.success)
                    Text("in the last month from \(d.dealCount) deal\(d.dealCount == 1 ? "" : "s")")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                    DisclosureGroup("Item breakdown") {
                        VStack(spacing: 4) {
                            ForEach(d.deals.prefix(20)) { item in
                                dealRow(item)
                            }
                            if d.deals.count > 20 {
                                Text("…and \(d.deals.count - 20) more deals.")
                                    .font(.appCaption2)
                                    .foregroundStyle(DesignTokens.secondaryLabel)
                            }
                        }
                        .padding(.top, 4)
                    }
                    .font(.appCaption1)
                }
            }
        }
    }

    private func dealRow(_ item: AnalyticsDealItem) -> some View {
        HStack(spacing: 8) {
            Text(item.productName ?? "—")
                .font(.appBody)
                .lineLimit(1)
            Spacer()
            Text("paid \(String(format: "$%.2f", item.paid))")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.secondaryLabel)
            Text("avg \(String(format: "$%.2f", item.avgPrice))")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.tertiaryLabel)
            Text("saved \(String(format: "$%.2f", item.saved))")
                .font(.appMonoCaption.weight(.semibold))
                .foregroundStyle(DesignTokens.success)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 4))
    }

    private var rowBackground: Color { DesignTokens.surface }

    // F-1314 row label — pretty-print period keys.
    private func prettyPeriod(_ key: String) -> String {
        // Daily "YYYY-MM-DD" → "MMM d, yyyy"
        if key.count == 10, key[key.index(key.startIndex, offsetBy: 4)] == "-",
           key[key.index(key.startIndex, offsetBy: 7)] == "-" {
            let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.timeZone = TimeZone(identifier: "UTC")
            if let d = f.date(from: key) {
                let out = DateFormatter(); out.dateFormat = "MMM d, yyyy"
                return out.string(from: d)
            }
        }
        // Weekly "YYYY-W##"
        if key.contains("-W") { return key.replacingOccurrences(of: "-W", with: " · week ") }
        // Monthly "YYYY-MM"
        if key.count == 7, key[key.index(key.startIndex, offsetBy: 4)] == "-" {
            let f = DateFormatter(); f.dateFormat = "yyyy-MM"
            if let d = f.date(from: key) {
                let out = DateFormatter(); out.dateFormat = "MMM yyyy"
                return out.string(from: d)
            }
        }
        return key
    }
}

extension Notification.Name {
    static let openRefundReceipts = Notification.Name("LocalOCR.openRefundReceipts")
}

#Preview("Analytics") {
    SpendingByCategoryView().frame(width: 900, height: 700)
}
