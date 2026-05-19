import SwiftUI

struct SpendingByCategoryView: View {
    @StateObject private var state = FinanceState.shared

    var body: some View {
        Group {
            if state.spending == nil {
                loadingView
            } else if let s = state.spending, s.categories.isEmpty {
                emptyStateView
            } else if let s = state.spending {
                populatedView(s)
            }
        }
        .navigationTitle("Analytics")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button { Task { await state.loadSpending() } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Recompute analytics")
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .task { await state.loadSpending() }
    }

    private var loadingView: some View {
        VStack(spacing: DesignTokens.Spacing.space2) {
            SkeletonView(width: nil, height: 220, cornerRadius: DesignTokens.Radius.card)
            SkeletonView(width: nil, height: 120, cornerRadius: DesignTokens.Radius.card)
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }

    private var emptyStateView: some View {
        EmptyStateView(
            systemImage: "chart.pie",
            title: "No spending yet",
            subtitle: "Confirm a few receipts and analytics will populate here."
        )
    }

    private func populatedView(_ s: SpendingAnalytics) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                periodHeader(s)
                ringCard(s)
                if !s.topMerchants.isEmpty {
                    merchantsCard(s)
                }
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .background(DesignTokens.background)
    }

    private func periodHeader(_ s: SpendingAnalytics) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(s.periodLabel).font(.appTitle1)
                Text("\(s.categories.count) categor\(s.categories.count == 1 ? "y" : "ies")")
                    .font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(String(format: "$%.2f", s.categories.reduce(0) { $0 + $1.total }))
                    .font(.appTitle1.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
                Text("total").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
            }
        }
    }

    private func ringCard(_ s: SpendingAnalytics) -> some View {
        Card {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.space5) {
                SpendingRingView(slices: ringSlices(from: s))
                    .frame(width: 160, height: 160)
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(s.categories.enumerated()), id: \.element.id) { idx, cat in
                        HStack(spacing: 6) {
                            Circle().fill(palette[idx % palette.count]).frame(width: 8, height: 8)
                            Text(cat.category).font(.appBody)
                            Spacer()
                            Text("\(cat.receiptCount)").font(.appCaption2.monospaced()).foregroundStyle(DesignTokens.tertiaryLabel)
                            Text(String(format: "$%.2f", cat.total))
                                .font(.appMonoBody).foregroundStyle(DesignTokens.label)
                        }
                    }
                }
            }
        }
    }

    private func merchantsCard(_ s: SpendingAnalytics) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text("Top merchants").font(.appHeadline).padding(.bottom, 2)
                ForEach(s.topMerchants) { m in
                    HStack {
                        Text(m.name).font(.appBody)
                        Spacer()
                        Text("× \(m.visitCount)").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                        Text(String(format: "avg $%.2f", m.avgAmount)).font(.appMonoCaption)
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    private var palette: [Color] {
        [DesignTokens.accent, DesignTokens.warning, DesignTokens.success, DesignTokens.error, DesignTokens.secondaryLabel]
    }

    private func ringSlices(from s: SpendingAnalytics) -> [SpendingRingView.Slice] {
        s.categories.prefix(palette.count).enumerated().map { idx, cat in
            .init(id: cat.category, label: cat.category, amount: cat.total, color: palette[idx])
        }
    }
}

#Preview("Analytics") {
    SpendingByCategoryView().frame(width: 700, height: 600)
}
