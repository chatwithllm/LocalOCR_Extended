import SwiftUI
import WebKit
import os.log

// F-1214 / F-1225 / F-1278 / F-1279 — WKWebView-embedded Plaid Link.
//
// Loads `plaid-link.html` from the app bundle into a WKWebView. The page
// itself pulls Plaid's link-initialize.js from the CDN (Plaid's terms
// require their JS to load from cdn.plaid.com — not allowed to bundle).
// After the page is ready, Swift calls `window.startPlaidLink(token)` to
// open the modal. Plaid's onSuccess / onExit / onEvent callbacks post
// messages back via `webkit.messageHandlers.<channel>`.

struct PlaidLinkSheet: View {
    let linkToken: String
    let onSuccess: (String, PlaidLinkMetadata?) -> Void
    let onExit: () -> Void

    @State private var didExit = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Connect Bank")
                    .font(.appHeadline)
                Spacer()
                Button("Done", action: dismiss)
                    .keyboardShortcut(.escape, modifiers: [])
            }
            .padding(.horizontal, DesignTokens.Spacing.space4)
            .padding(.vertical, DesignTokens.Spacing.space3)
            .background(DesignTokens.background)
            Divider()
            PlaidLinkWebView(
                linkToken: linkToken,
                onSuccess: { token, meta in
                    guard !didExit else { return }
                    didExit = true
                    onSuccess(token, meta)
                },
                onExit: {
                    guard !didExit else { return }
                    didExit = true
                    onExit()
                }
            )
        }
        .frame(minWidth: 460, minHeight: 600)
    }

    private func dismiss() {
        guard !didExit else { return }
        didExit = true
        onExit()
    }
}

struct PlaidLinkWebView: NSViewRepresentable {
    let linkToken: String
    let onSuccess: (String, PlaidLinkMetadata?) -> Void
    let onExit: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onSuccess: onSuccess, onExit: onExit)
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "plaidSuccess")
        controller.add(context.coordinator, name: "plaidExit")
        controller.add(context.coordinator, name: "plaidEvent")
        config.userContentController = controller
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        // Inject the token via window.startPlaidLink after the DOM is ready.
        let script = WKUserScript(
            source: "window.__LOCALOCR_LINK_TOKEN = \(escapedJSString(linkToken));",
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        )
        controller.addUserScript(script)

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.setValue(true, forKey: "drawsTransparentBackground")
        if let url = Bundle.main.url(forResource: "plaid-link", withExtension: "html") {
            webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        } else {
            let html = #"<html><body><p style="font-family:-apple-system;color:#d33;padding:24px">Plaid Link HTML missing from bundle.</p></body></html>"#
            webView.loadHTMLString(html, baseURL: nil)
        }
        context.coordinator.webView = webView
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
        // Re-fire startPlaidLink if the token changed.
        if context.coordinator.lastToken != linkToken {
            context.coordinator.lastToken = linkToken
            context.coordinator.startWhenReady(token: linkToken)
        }
    }

    static func dismantleNSView(_ nsView: WKWebView, coordinator: Coordinator) {
        let controller = nsView.configuration.userContentController
        controller.removeScriptMessageHandler(forName: "plaidSuccess")
        controller.removeScriptMessageHandler(forName: "plaidExit")
        controller.removeScriptMessageHandler(forName: "plaidEvent")
    }

    private func escapedJSString(_ s: String) -> String {
        let escaped = s
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\r", with: "\\r")
        return "\"\(escaped)\""
    }

    @MainActor
    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        let onSuccess: (String, PlaidLinkMetadata?) -> Void
        let onExit: () -> Void
        weak var webView: WKWebView?
        var lastToken: String?
        private var pageLoaded = false
        private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "plaid-link")

        init(onSuccess: @escaping (String, PlaidLinkMetadata?) -> Void,
             onExit: @escaping () -> Void) {
            self.onSuccess = onSuccess
            self.onExit = onExit
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            pageLoaded = true
            if let t = lastToken {
                startWhenReady(token: t)
            } else {
                // First load — fire from the injected token.
                webView.evaluateJavaScript("window.startPlaidLink(window.__LOCALOCR_LINK_TOKEN);") { _, err in
                    if let err {
                        self.logger.warning("startPlaidLink JS error: \(err.localizedDescription, privacy: .public)")
                    }
                }
            }
        }

        func startWhenReady(token: String) {
            guard pageLoaded, let webView else { return }
            let js = "window.startPlaidLink(\(jsString(token)));"
            webView.evaluateJavaScript(js, completionHandler: nil)
        }

        nonisolated func userContentController(_ userContentController: WKUserContentController,
                                               didReceive message: WKScriptMessage) {
            let name = message.name
            let body = message.body
            Task { @MainActor in
                self.handle(name: name, body: body)
            }
        }

        private func handle(name: String, body: Any) {
            switch name {
            case "plaidSuccess":
                guard let payload = body as? [String: Any],
                      let token = payload["public_token"] as? String else {
                    logger.warning("plaidSuccess message missing public_token")
                    return
                }
                let metadata = parseMetadata(payload["metadata"])
                onSuccess(token, metadata)
            case "plaidExit":
                onExit()
            case "plaidEvent":
                if let payload = body as? [String: Any],
                   let event = payload["event"] as? String {
                    logger.info("plaid event \(event, privacy: .public)")
                }
            default:
                break
            }
        }

        private func parseMetadata(_ raw: Any?) -> PlaidLinkMetadata? {
            guard let raw = raw as? [String: Any] else { return nil }
            let institutionDict = raw["institution"] as? [String: Any]
            let institution = institutionDict.map {
                PlaidInstitutionMeta(
                    name: $0["name"] as? String,
                    institutionId: $0["institution_id"] as? String
                )
            }
            let accountsRaw = raw["accounts"] as? [[String: Any]] ?? []
            let accounts: [PlaidAccountMeta] = accountsRaw.map {
                PlaidAccountMeta(
                    id: $0["id"] as? String,
                    name: $0["name"] as? String,
                    mask: $0["mask"] as? String,
                    type: $0["type"] as? String,
                    subtype: $0["subtype"] as? String
                )
            }
            return PlaidLinkMetadata(institution: institution, accounts: accounts)
        }

        private func jsString(_ s: String) -> String {
            let escaped = s
                .replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "\"", with: "\\\"")
                .replacingOccurrences(of: "\n", with: "\\n")
                .replacingOccurrences(of: "\r", with: "\\r")
            return "\"\(escaped)\""
        }
    }
}
