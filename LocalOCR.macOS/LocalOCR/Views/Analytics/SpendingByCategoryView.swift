import SwiftUI

struct SpendingByCategoryView: View {
    @StateObject private var state = FinanceState.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                Text("Spending by Category").font(.appTitle1)

                if let s = state.spending {
                    Card {
                        SpendingRingView(slices: ringSlices(from: s))
                            .frame(width: 180, height: 180)
                            .padding(.bottom, 8)
                        ForEach(s.categories) { cat in
                            HStack {
                                Text(cat.category).font(.appBody)
                                Spacer()
                                Text("\(cat.receiptCount) receipts").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                                Text(String(format: "$%.2f", cat.total))
                                    .font(.appMonoBody)
                                    .foregroundStyle(DesignTokens.label)
                            }
                            .padding(.vertical, 4)
                        }
                    }

                    if !s.topMerchants.isEmpty {
                        Card {
                            Text("Top merchants").font(.appHeadline).padding(.bottom, 4)
                            ForEach(s.topMerchants) { m in
                                HStack {
                                    Text(m.name).font(.appBody)
                                    Spacer()
                                    Text("× \(m.visitCount)").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                                    Text(String(format: "avg $%.2f", m.avgAmount)).font(.appMonoBody)
                                }
                                .padding(.vertical, 3)
                            }
                        }
                    }
                } else {
                    EmptyStateView(systemImage: "chart.pie", title: "Loading analytics…", subtitle: "Spending breakdown will appear once data loads.")
                }
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .navigationTitle("Analytics")
        .task { await state.loadSpending() }
    }

    private func ringSlices(from s: SpendingAnalytics) -> [SpendingRingView.Slice] {
        let palette: [Color] = [
            DesignTokens.accent, DesignTokens.warning, DesignTokens.success,
            DesignTokens.error, DesignTokens.secondaryLabel
        ]
        return s.categories.prefix(palette.count).enumerated().map { idx, cat in
            .init(id: cat.category, label: cat.category, amount: cat.total, color: palette[idx])
        }
    }
}

#Preview("Analytics") {
    SpendingByCategoryView().frame(width: 700, height: 600)
}
