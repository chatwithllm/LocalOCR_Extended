import Foundation

/// Demo-mode enforcement (§1.7 rule 10, VETO_RESOLUTION_PATCH §3 R-04).
/// Must intercept at the APIClient layer, not just UI — otherwise context menus
/// or keyboard shortcuts could bypass the UI gate.
///
/// Usage pattern in State files:
///     try DemoModeGate.guardMutation()
///     try await api.request(.post, path: …)
@MainActor
enum DemoModeGate {

    static func guardMutation() throws {
        if AppState.shared.isDemoMode {
            throw APIError.demoModeReadOnly
        }
    }
}
