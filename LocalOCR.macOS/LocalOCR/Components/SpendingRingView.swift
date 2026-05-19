import SwiftUI

/// Ring chart (donut) showing top-N spending categories by share.
/// Added per VETO_RESOLUTION_PATCH §3 — UC-029.
///
/// Empty state: renders a placeholder ring with an inline message.
struct SpendingRingView: View {
    struct Slice: Identifiable, Equatable {
        let id: String
        let label: String
        let amount: Double
        let color: Color
    }

    let slices: [Slice]
    var thickness: CGFloat = 14

    private var total: Double {
        slices.reduce(0) { $0 + $1.amount }
    }

    var body: some View {
        ZStack {
            if slices.isEmpty || total <= 0 {
                emptyRing
            } else {
                segments
            }
            centerLabel
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(slices.isEmpty ? "No spending data" : "Spending by category")
        .accessibilityValue(accessibilityValue)
    }

    private var segments: some View {
        ZStack {
            ForEach(Array(slices.enumerated()), id: \.element.id) { idx, slice in
                let start = startAngle(for: idx)
                let end   = endAngle(for: idx)
                Circle()
                    .trim(from: start, to: end)
                    .stroke(slice.color, style: StrokeStyle(lineWidth: thickness, lineCap: .butt))
                    .rotationEffect(.degrees(-90))
            }
        }
    }

    private var emptyRing: some View {
        Circle()
            .stroke(DesignTokens.surface2, style: StrokeStyle(lineWidth: thickness))
    }

    private var centerLabel: some View {
        VStack(spacing: 2) {
            if total > 0 {
                Text(formatCurrency(total))
                    .font(.appTitle3)
                    .foregroundStyle(DesignTokens.label)
                Text("this month")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            } else {
                Text("No data")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
        }
    }

    private func startAngle(for index: Int) -> CGFloat {
        guard total > 0 else { return 0 }
        let prior = slices.prefix(index).reduce(0) { $0 + $1.amount }
        return CGFloat(prior / total)
    }

    private func endAngle(for index: Int) -> CGFloat {
        guard total > 0 else { return 0 }
        let upTo = slices.prefix(index + 1).reduce(0) { $0 + $1.amount }
        return CGFloat(upTo / total)
    }

    private func formatCurrency(_ value: Double) -> String {
        let fmt = NumberFormatter()
        fmt.numberStyle = .currency
        fmt.maximumFractionDigits = 0
        return fmt.string(from: NSNumber(value: value)) ?? "$\(Int(value))"
    }

    private var accessibilityValue: String {
        guard !slices.isEmpty else { return "Empty" }
        let parts = slices.map { "\($0.label) \(Int($0.amount / total * 100))%" }
        return parts.joined(separator: ", ")
    }
}

#Preview("SpendingRing / Populated") {
    Card {
        HStack(spacing: 24) {
            SpendingRingView(slices: [
                .init(id: "groc", label: "Groceries",   amount: 420, color: DesignTokens.accent),
                .init(id: "rest", label: "Restaurants", amount: 180, color: DesignTokens.warning),
                .init(id: "util", label: "Utilities",   amount: 240, color: DesignTokens.success),
                .init(id: "other", label: "Other",      amount: 90,  color: DesignTokens.secondaryLabel)
            ])
            .frame(width: 140, height: 140)

            VStack(alignment: .leading, spacing: 6) {
                ForEach(["Groceries", "Restaurants", "Utilities", "Other"], id: \.self) { name in
                    HStack(spacing: 6) {
                        Circle().fill(DesignTokens.accent).frame(width: 8, height: 8)
                        Text(name).font(.appCaption1)
                    }
                }
            }
        }
    }
    .padding(40)
    .frame(width: 420)
}

#Preview("SpendingRing / Empty") {
    Card {
        SpendingRingView(slices: [])
            .frame(width: 140, height: 140)
    }
    .padding(40)
    .frame(width: 240)
}
