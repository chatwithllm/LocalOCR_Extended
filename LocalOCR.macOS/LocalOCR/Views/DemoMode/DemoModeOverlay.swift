import SwiftUI

/// Persistent banner overlay reused at the top of every workspace when demo mode is on.
/// The actual banner component is `DemoModeBanner`; this file is the binding glue.
struct DemoModeOverlay: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        if appState.isDemoMode {
            DemoModeBanner(onSignIn: { Task { await AuthState.shared.logout() } })
                .accessibilityElement(children: .contain)
        }
    }
}
