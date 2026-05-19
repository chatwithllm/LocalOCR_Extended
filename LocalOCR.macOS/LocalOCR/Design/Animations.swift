import SwiftUI

/// Animation constants for LocalOCR macOS, mapped from §3.1 of MACOS_APP_PLAN.md.
///
/// Every animation respects `@Environment(\.accessibilityReduceMotion)` —
/// use `AppAnimation.respecting(reduceMotion:)` instead of raw animations in views.
enum AppAnimation {

    static let viewTransition = Animation.easeInOut(duration: 0.2)
    static let sheetPresent = Animation.spring(response: 0.35, dampingFraction: 0.85)
    static let listRow = Animation.easeOut(duration: 0.15)
    static let skeletonShimmerSeconds: Double = 1.2

    /// Fallback used when Reduce Motion is enabled: effectively instant.
    static let instant = Animation.linear(duration: 0.001)

    /// Returns the given animation, or the instant fallback if Reduce Motion is on.
    static func respecting(reduceMotion: Bool, _ animation: Animation) -> Animation {
        reduceMotion ? instant : animation
    }
}

extension View {
    /// Apply an animation that auto-falls-back to instant when Reduce Motion is on.
    /// Use this instead of `.animation(_:value:)` directly for any motion that conveys state change.
    func reduceMotionAnimation<V: Equatable>(_ animation: Animation, value: V) -> some View {
        modifier(ReduceMotionAnimationModifier(animation: animation, value: value))
    }
}

private struct ReduceMotionAnimationModifier<V: Equatable>: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let animation: Animation
    let value: V

    func body(content: Content) -> some View {
        content.animation(AppAnimation.respecting(reduceMotion: reduceMotion, animation), value: value)
    }
}
