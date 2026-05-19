import SwiftUI

/// Horizontal bar with two values: actual vs expected (or paid vs unpaid).
/// Used on Fixed Bills and Dining/Household Budget cards.
///
/// Color flips automatically:
///   actual <= expected * 0.5  → success (green)
///   actual <= expected        → warning (amber) [under or at budget]
///   actual >  expected        → error (red)     [over budget]
struct ProgressBarView: View {
    let actual: Double
    let expected: Double
    var height: CGFloat = 8
    var inverted: Bool = false   // if true, "filling" the bar is positive (paid = good).

    private var ratio: Double {
        guard expected > 0 else { return 0 }
        return min(max(actual / expected, 0), 1.5)
    }

    private var fillColor: Color {
        if inverted {
            // "Filling" is good (paid). Color by completeness.
            if ratio < 0.5 { return DesignTokens.warning }
            if ratio < 1.0 { return DesignTokens.success }
            return DesignTokens.success
        } else {
            // Filling = spending. Color by how close to budget.
            if ratio <= 0.5 { return DesignTokens.success }
            if ratio <= 1.0 { return DesignTokens.warning }
            return DesignTokens.error
        }
    }

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: height / 2)
                    .fill(DesignTokens.surface2)
                RoundedRectangle(cornerRadius: height / 2)
                    .fill(fillColor)
                    .frame(width: proxy.size.width * min(ratio, 1.0))
            }
        }
        .frame(height: height)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Progress")
        .accessibilityValue(formattedRatio)
    }

    private var formattedRatio: String {
        let pct = Int(ratio * 100)
        return "\(pct)% of budget"
    }
}

#Preview("ProgressBar / Under budget") {
    VStack(alignment: .leading, spacing: 16) {
        ProgressBarView(actual: 100, expected: 500)
        ProgressBarView(actual: 350, expected: 500)
        ProgressBarView(actual: 600, expected: 500)
        ProgressBarView(actual: 300, expected: 500, inverted: true)
    }
    .padding(40)
    .frame(width: 360)
}
