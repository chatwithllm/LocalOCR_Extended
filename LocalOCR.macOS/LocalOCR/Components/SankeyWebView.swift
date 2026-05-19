import SwiftUI
import WebKit

/// WKWebView host for the Sankey chart used on Spending by Category (§3.7 view spec).
/// HTML template + D3/Vega rendering is v1.1 (§4.2).
///
/// Phase 2: structural stub that loads a placeholder local HTML. The actual
/// template (`Resources/HTML/sankey-template.html`) is filled in v1.1.
/// Per VETO_RESOLUTION_PATCH risk R-02: file:// loads must pass
/// `decidePolicyFor navigationAction` explicitly on macOS 14+; the wrapper here
/// guards that.
struct SankeyWebView: NSViewRepresentable {
    let data: SankeyData

    struct SankeyData: Equatable {
        let nodes: [String]
        let links: [(source: String, target: String, value: Double)]

        static func == (lhs: SankeyData, rhs: SankeyData) -> Bool {
            lhs.nodes == rhs.nodes &&
            lhs.links.count == rhs.links.count &&
            zip(lhs.links, rhs.links).allSatisfy { l, r in
                l.source == r.source && l.target == r.target && l.value == r.value
            }
        }
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = context.coordinator
        view.setValue(false, forKey: "drawsBackground")
        loadPlaceholder(into: view)
        return view
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
        context.coordinator.setData(data, on: nsView)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    private func loadPlaceholder(into view: WKWebView) {
        let html = """
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><style>
          html, body { margin: 0; padding: 0; background: transparent; color: #888; font: 13px -apple-system, sans-serif; height: 100%; }
          .placeholder { display: flex; align-items: center; justify-content: center; height: 100%; }
        </style></head>
        <body><div class="placeholder">Sankey diagram (v1.1)</div></body></html>
        """
        view.loadHTMLString(html, baseURL: nil)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        // R-02 guard — explicitly allow file:// loads when v1.1 HTML template is added.
        func webView(_ webView: WKWebView,
                     decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            decisionHandler(.allow)
        }

        func setData(_ data: SankeyData, on view: WKWebView) {
            // v1.1: serialise data to JSON and call window.setSankeyData(data).
            // Phase 2 placeholder: no-op.
        }
    }
}

#Preview("Sankey / Placeholder") {
    SankeyWebView(data: .init(nodes: [], links: []))
        .frame(width: 480, height: 240)
        .padding(40)
}
