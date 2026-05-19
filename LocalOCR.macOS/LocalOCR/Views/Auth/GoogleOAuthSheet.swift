import SwiftUI
import AuthenticationServices

/// ASWebAuthenticationSession wrapper for Google OAuth.
///
/// Flow:
///   1. Caller hits `GET /auth/google/start` → server returns an `authUrl`
///   2. We present `ASWebAuthenticationSession(url: authUrl, callbackURLScheme: "localocr")`
///   3. Browser redirects to `localocr://oauth/google?state=...&code=...`
///   4. We extract `state` + `code` and call `AuthState.completeGoogleOAuth(...)`
///
/// SwiftUI bridge: hosted in a transparent `ViewControllerRepresentable` so the
/// sheet can present from any view. Phase 3 implementation; full OAuth start
/// endpoint is server-side.
struct GoogleOAuthSheet: NSViewControllerRepresentable {
    let authURL: URL
    let onCompletion: (Result<(state: String, code: String), Error>) -> Void

    func makeNSViewController(context: Context) -> NSViewController {
        let vc = NSViewController()
        vc.view = NSView()
        DispatchQueue.main.async {
            context.coordinator.start(from: vc, url: authURL, completion: onCompletion)
        }
        return vc
    }

    func updateNSViewController(_ nsViewController: NSViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, ASWebAuthenticationPresentationContextProviding {
        private var session: ASWebAuthenticationSession?

        func start(
            from vc: NSViewController,
            url: URL,
            completion: @escaping (Result<(state: String, code: String), Error>) -> Void
        ) {
            session = ASWebAuthenticationSession(
                url: url,
                callbackURLScheme: AppConstants.urlScheme
            ) { callback, error in
                if let error {
                    completion(.failure(error))
                    return
                }
                guard let callback,
                      let components = URLComponents(url: callback, resolvingAgainstBaseURL: false),
                      let state = components.queryItems?.first(where: { $0.name == "state" })?.value,
                      let code  = components.queryItems?.first(where: { $0.name == "code" })?.value
                else {
                    completion(.failure(NSError(domain: "GoogleOAuth", code: -1, userInfo: [
                        NSLocalizedDescriptionKey: "Missing state or code in OAuth callback."
                    ])))
                    return
                }
                completion(.success((state, code)))
            }
            session?.presentationContextProvider = self
            session?.prefersEphemeralWebBrowserSession = false
            session?.start()
        }

        func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
            NSApp.keyWindow ?? ASPresentationAnchor()
        }
    }
}
