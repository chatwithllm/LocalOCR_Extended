import SwiftUI

// F-1500..F-1526 — Contributions screen.

struct ContributionsView: View {
    @StateObject private var state = ContributionsState.shared
    @EnvironmentObject private var router: Router

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                pageHeader                          // F-1500
                explainerCard                       // F-1501..F-1505
                summaryStatsGrid                    // F-1506..F-1511
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 360), spacing: 16)],
                    spacing: 16
                ) {
                    recentActivityCard              // F-1512..F-1516
                    opportunitiesCard               // F-1517..F-1520
                }
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 360), spacing: 16)],
                    spacing: 16
                ) {
                    pointsRulesCard                 // F-1521..F-1522
                    fairScoringCard                 // F-1523..F-1524
                }
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .background(DesignTokens.background)
        .navigationTitle("Contribution")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    Task { await state.refresh() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .keyboardShortcut("r", modifiers: .command)
            }
        }
        .task { await state.refresh() }
    }

    // F-1500
    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Contribution").font(.appTitle1)
            Text("See how scoring works, what you earned, and how you can help the system stay sharp.")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    // F-1501..F-1505
    private var explainerCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("How Low-Stock Validation Works").font(.appHeadline)
                step(1, "Mark an item Low. This starts a pending contribution, but it does not score yet.")
                step(2, "Move that item into the Shopping List.")
                step(3, "When a later receipt confirms the item was bought, the low-stock action is validated.")
                step(4, "If the low flag is quickly cleared or wrong, the pending contribution does not count.")
            }
        }
    }

    private func step(_ n: Int, _ text: String) -> some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.space2) {
            Text("\(n)")
                .font(.appCaption1.weight(.semibold))
                .frame(width: 20, height: 20)
                .background(DesignTokens.accentDim)
                .foregroundStyle(DesignTokens.accent)
                .clipShape(Circle())
            Text(text)
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // F-1506..F-1511
    private var summaryStatsGrid: some View {
        let s = state.summary?.summary
        return LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 180), spacing: 12)],
            spacing: 12
        ) {
            statCard(label: "Total Score",
                     value: "\(s?.totalScore ?? 0)",
                     sub: "Your current household contribution score")
            statCard(label: "Receipts",
                     value: "\(s?.receiptsProcessed ?? 0)",
                     sub: "+\(s?.receiptPoints ?? 0) pts")
            statCard(label: "OCR Fixes",
                     value: "\(s?.ocrFixes ?? 0)",
                     sub: "+\(s?.ocrPoints ?? 0) pts")
            statCard(label: "System Help",
                     value: "+\(s?.bonusPoints ?? 0)",
                     sub: "low-stock · location · shopping upkeep")
            statCard(label: "Floating",
                     value: "+\(s?.floatingPoints ?? 0)",
                     sub: "awaiting real-world follow-through")
        }
    }

    private func statCard(label: String, value: String, sub: String) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 2) {
                Text(label.uppercased())
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                Text(value)
                    .font(.appTitle2.weight(.semibold).monospacedDigit())
                Text(sub)
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.secondaryLabel)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // F-1512..F-1516
    private var recentActivityCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                HStack {
                    Text("Recent Score Activity").font(.appHeadline)
                    Spacer()
                    Button {
                        Task { await state.refresh() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.plain)
                    .help("Reload contribution events")
                }
                if let err = state.lastError, state.summary == nil {
                    Text("Could not load contribution details.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.error)
                        .help(err)
                } else if let events = state.summary?.recentEvents, !events.isEmpty {
                    VStack(spacing: 4) {
                        ForEach(events, id: \.id) { e in
                            eventRow(e)
                        }
                    }
                } else if state.isLoading && state.summary == nil {
                    HStack {
                        ProgressView().controlSize(.small)
                        Text("Loading…").font(.appSubheadline).foregroundStyle(DesignTokens.secondaryLabel)
                    }
                } else {
                    Text("No contribution history yet.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
    }

    private func eventRow(_ e: ContributionsEvent) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(e.description ?? "—")
                    .font(.appBody)
                    .lineLimit(2)
                Spacer()
                Text("+\(e.points) pts")
                    .font(.appMonoCaption.weight(.semibold))
                    .foregroundStyle(e.points > 0 ? DesignTokens.success : DesignTokens.secondaryLabel)
            }
            HStack(spacing: 4) {
                if let t = e.eventType {
                    Text(t.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                    Text("·").foregroundStyle(DesignTokens.tertiaryLabel)
                }
                Text(ContributionStatusLabel.format(e.status))
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                Spacer()
                if let d = e.createdAtDate {
                    Text(d.formatted(date: .abbreviated, time: .shortened))
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.space2)
        .padding(.vertical, 6)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // F-1517..F-1520
    private var opportunitiesCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("Ways To Help Right Now").font(.appHeadline)
                if let opps = state.summary?.opportunities, !opps.isEmpty {
                    VStack(spacing: 4) {
                        ForEach(opps, id: \.id) { o in
                            opportunityRow(o)
                        }
                    }
                } else {
                    Text("No suggested actions right now.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
    }

    private func opportunityRow(_ o: ContributionsOpportunity) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(o.title)
                    .font(.appBody.weight(.semibold))
                if let c = o.count, c > 0 {
                    Text("\(c)")
                        .font(.appCaption2.monospacedDigit())
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(DesignTokens.accentDim)
                        .foregroundStyle(DesignTokens.accent)
                        .clipShape(Capsule())
                }
                Spacer()
                if let cta = o.cta, let page = o.page {
                    Button {
                        navigate(to: page)
                    } label: {
                        Text(cta).font(.appCaption1)
                    }
                    .buttonStyle(GhostButtonStyle())
                    .controlSize(.small)
                }
            }
            if let desc = o.description, !desc.isEmpty {
                Text(desc)
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.space2)
        .padding(.vertical, 6)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func navigate(to page: String) {
        switch page.lowercased() {
        case "receipts":   router.activeTab = .receipts
        case "inventory":  router.activeTab = .inventory
        case "shopping":   router.activeTab = .shopping
        case "kitchen":    router.activeTab = .kitchen
        case "products":   router.activeTab = .products
        case "dashboard":  router.activeTab = .dashboard
        case "settings":
            ToastQueue.shared.push(Toast(
                message: "Settings tab opens in v1.1 — use the web app for catalog cleanup.",
                severity: .info
            ))
        default:
            ToastQueue.shared.push(Toast(
                message: "Open the web app to access \"\(page)\".",
                severity: .info
            ))
        }
    }

    // F-1521..F-1522
    private var pointsRulesCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("How Points Are Earned").font(.appHeadline)
                if let rules = state.summary?.rules, !rules.isEmpty {
                    VStack(spacing: 4) {
                        ForEach(rules, id: \.id) { r in
                            ruleRow(r)
                        }
                    }
                } else {
                    Text("Scoring rules not loaded yet.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
    }

    private func ruleRow(_ r: ContributionsRule) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(r.title).font(.appBody.weight(.semibold))
                Spacer()
                Text("+\(r.points) pts")
                    .font(.appMonoCaption.weight(.semibold))
                    .foregroundStyle(r.points > 0 ? DesignTokens.success : DesignTokens.tertiaryLabel)
            }
            if let desc = r.description, !desc.isEmpty {
                Text(desc)
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.space2)
        .padding(.vertical, 6)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // F-1523..F-1524
    private var fairScoringCard: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                Text("Fair Scoring Rules").font(.appHeadline)
                if let notes = state.summary?.notes, !notes.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(notes.enumerated()), id: \.offset) { _, n in
                            HStack(alignment: .top, spacing: 6) {
                                Text("•")
                                    .font(.appBody)
                                    .foregroundStyle(DesignTokens.tertiaryLabel)
                                Text(n)
                                    .font(.appCaption1)
                                    .foregroundStyle(DesignTokens.secondaryLabel)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                } else {
                    Text("Fairness notes not loaded yet.")
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
    }
}

#Preview("Contributions") {
    ContributionsView()
        .environmentObject(Router.shared)
        .frame(width: 900, height: 700)
}
