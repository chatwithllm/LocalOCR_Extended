import SwiftUI

/// Shimmer-animated rounded rectangle used as a loading placeholder.
/// Respects Reduce Motion: shimmer becomes a static gray block when the user prefers reduced motion.
struct SkeletonView: View {
    let width: CGFloat?
    let height: CGFloat
    var cornerRadius: CGFloat = DesignTokens.Radius.control

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var phase: CGFloat = -1

    var body: some View {
        Rectangle()
            .fill(baseFill)
            .overlay(shimmerOverlay)
            .frame(width: width, height: height)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .accessibilityHidden(true)
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(
                    .linear(duration: AppAnimation.skeletonShimmerSeconds).repeatForever(autoreverses: false)
                ) {
                    phase = 1
                }
            }
    }

    private var baseFill: Color {
        DesignTokens.surface2
    }

    @ViewBuilder
    private var shimmerOverlay: some View {
        if reduceMotion {
            EmptyView()
        } else {
            GeometryReader { proxy in
                let bandWidth = proxy.size.width * 0.4
                LinearGradient(
                    stops: [
                        .init(color: .clear, location: 0),
                        .init(color: Color.white.opacity(0.20), location: 0.5),
                        .init(color: .clear, location: 1)
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(width: bandWidth, height: proxy.size.height)
                .offset(x: phase * (proxy.size.width + bandWidth) - bandWidth)
                .blendMode(.plusLighter)
            }
        }
    }
}

#Preview("Skeleton / Stacked") {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
        SkeletonView(width: 240, height: 18)
        SkeletonView(width: 180, height: 14)
        SkeletonView(width: nil, height: 56, cornerRadius: DesignTokens.Radius.card)
        SkeletonView(width: nil, height: 56, cornerRadius: DesignTokens.Radius.card)
    }
    .padding(40)
    .frame(width: 380)
}
