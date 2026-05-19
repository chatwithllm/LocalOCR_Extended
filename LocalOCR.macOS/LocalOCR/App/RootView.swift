import SwiftUI

/// Top-level container. Switches between LoginView (Phase 2 static) and
/// MainSplitView based on `AppState.authStatus`. Hosts the global ToastHost.
///
/// Phase 2: visual shell only. Real auth flow lands in Phase 3.
struct RootView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var router: Router
    @StateObject private var auth = AuthState.shared

    var body: some View {
        ZStack {
            switch appState.authStatus {
            case .unauthenticated, .authenticating:
                LoginView()
            case .authenticated, .demoMode:
                MainSplitView()
            }

            // Demo mode banner overlay (renders only when isDemoMode)
            if appState.isDemoMode {
                VStack(spacing: 0) {
                    DemoModeBanner(onSignIn: { /* Phase 3 */ })
                    Spacer()
                }
                .allowsHitTesting(false)
            }

            // Global toast host (always mounted; renders only when queue has items)
            ToastHost()
        }
        .frame(minWidth: 900, minHeight: 600)
        .background(DesignTokens.background.ignoresSafeArea())
        .sheet(isPresented: $showOnboarding) {
            OnboardingSheet()
        }
        .task {
            // Phase 3: probe session on first appear. ImageCache configured here too
            // so Kingfisher downloader shares the cookie jar.
            ImageCache.configureSharedCookies()
            if !PreferencesStore.shared.hasCompletedOnboarding {
                showOnboarding = true
            }
            await auth.checkSession()
        }
    }

    @State private var showOnboarding = false
}

#Preview("RootView / Unauthenticated") {
    RootView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 1200, height: 800)
}
