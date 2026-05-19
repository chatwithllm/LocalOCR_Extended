import SwiftUI
import Combine

/// Non-modal transient overlay. Severity-coded, auto-dismisses after 4 seconds.
/// Used app-wide via `ToastHost` mounted on `RootView`.

// MARK: - Model

struct Toast: Identifiable, Equatable {
    enum Severity {
        case info, success, warning, error

        var icon: String {
            switch self {
            case .info:    return "info.circle.fill"
            case .success: return "checkmark.circle.fill"
            case .warning: return "exclamationmark.triangle.fill"
            case .error:   return "xmark.octagon.fill"
            }
        }

        var tint: Color {
            switch self {
            case .info:    return DesignTokens.accent
            case .success: return DesignTokens.success
            case .warning: return DesignTokens.warning
            case .error:   return DesignTokens.error
            }
        }

        var background: Color {
            switch self {
            case .info:    return DesignTokens.accentDim
            case .success: return DesignTokens.successDim
            case .warning: return DesignTokens.warningDim
            case .error:   return DesignTokens.errorDim
            }
        }
    }

    let id = UUID()
    let message: String
    let severity: Severity
    let duration: TimeInterval

    init(message: String, severity: Severity = .info, duration: TimeInterval = 4) {
        self.message = message
        self.severity = severity
        self.duration = duration
    }
}

// MARK: - Queue

@MainActor
final class ToastQueue: ObservableObject {
    static let shared = ToastQueue()

    @Published private(set) var visible: Toast? = nil
    private var pending: [Toast] = []
    private var dismissTask: Task<Void, Never>? = nil

    private init() {}

    func push(_ toast: Toast) {
        if visible == nil {
            present(toast)
        } else {
            pending.append(toast)
        }
    }

    func dismiss() {
        dismissTask?.cancel()
        visible = nil
        if let next = pending.first {
            pending.removeFirst()
            present(next)
        }
    }

    private func present(_ toast: Toast) {
        visible = toast
        dismissTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(toast.duration * 1_000_000_000))
            guard !Task.isCancelled else { return }
            await MainActor.run { self?.dismiss() }
        }
    }
}

// MARK: - Host view

struct ToastHost: View {
    @StateObject private var queue = ToastQueue.shared
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack {
            if let toast = queue.visible {
                ToastRowView(toast: toast) {
                    queue.dismiss()
                }
                .transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
                .padding(.top, DesignTokens.Spacing.space3)
                .padding(.horizontal, DesignTokens.Spacing.space3)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .top)
        .allowsHitTesting(queue.visible != nil)
        .animation(AppAnimation.respecting(reduceMotion: reduceMotion, AppAnimation.sheetPresent), value: queue.visible)
        .accessibilityElement(children: .contain)
    }
}

private struct ToastRowView: View {
    let toast: Toast
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            Image(systemName: toast.severity.icon)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(toast.severity.tint)
            Text(toast.message)
                .font(.appBody)
                .foregroundStyle(DesignTokens.label)
                .lineLimit(2)
            Spacer(minLength: 0)
            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.borderless)
            .foregroundStyle(DesignTokens.secondaryLabel)
            .accessibilityLabel("Dismiss notification")
        }
        .padding(.horizontal, DesignTokens.Spacing.space4)
        .padding(.vertical, DesignTokens.Spacing.space3)
        .background(toast.severity.background)
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .stroke(toast.severity.tint.opacity(0.4), lineWidth: 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .shadow(color: .black.opacity(0.12), radius: 12, y: 4)
        .frame(maxWidth: 460)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(severityLabel): \(toast.message)")
    }

    private var severityLabel: String {
        switch toast.severity {
        case .info:    return "Info"
        case .success: return "Success"
        case .warning: return "Warning"
        case .error:   return "Error"
        }
    }
}

#Preview("Toast / Each severity") {
    VStack(spacing: 12) {
        ForEach([Toast.Severity.info, .success, .warning, .error], id: \.icon) { s in
            ToastHostPreviewWrapper(severity: s)
        }
    }
    .frame(width: 520, height: 280)
}

private struct ToastHostPreviewWrapper: View {
    let severity: Toast.Severity
    var body: some View {
        ZStack {
            DesignTokens.background
            ToastHost()
        }
        .frame(height: 64)
        .onAppear {
            ToastQueue.shared.push(Toast(message: "Sample \(severity.icon) toast", severity: severity, duration: 60))
        }
    }
}
