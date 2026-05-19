import SwiftUI

/// Container for the Finance tab — Bills + Cash + Plaid + Spending Analytics
/// as a TabView so each subview is its own page (§3.7 finance spec).
struct FinanceTabView: View {
    enum Section: String, CaseIterable, Identifiable {
        case bills, cash, plaid, analytics
        var id: String { rawValue }
        var label: String {
            switch self {
            case .bills:     return "Fixed Bills"
            case .cash:      return "Cash"
            case .plaid:     return "Plaid"
            case .analytics: return "Analytics"
            }
        }
        var systemImage: String {
            switch self {
            case .bills:     return "doc.text"
            case .cash:      return "banknote"
            case .plaid:     return "creditcard"
            case .analytics: return "chart.pie"
            }
        }
    }

    @State private var section: Section = .bills

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $section) {
                ForEach(Section.allCases) { s in
                    Label(s.label, systemImage: s.systemImage).tag(s)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(DesignTokens.Spacing.space3)
            .background(DesignTokens.surface2)

            Divider()

            Group {
                switch section {
                case .bills:     FixedBillsView()
                case .cash:      CashTransactionsView()
                case .plaid:     PlaidAccountsView()
                case .analytics: SpendingByCategoryView()
                }
            }
        }
        .navigationTitle("Finance")
    }
}

#Preview("Finance tab") {
    FinanceTabView().frame(width: 900, height: 600)
}
