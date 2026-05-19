import AppKit

/// Customizes the standard NSApp About panel with credits, copyright, and version info.
@MainActor
enum AboutPanel {

    static func show() {
        let info = Bundle.main.infoDictionary
        let version = info?["CFBundleShortVersionString"] as? String ?? "1.0.0"
        let build   = info?["CFBundleVersion"] as? String ?? "1"
        let copyright = info?["NSHumanReadableCopyright"] as? String ?? "Copyright © 2026"

        let creditsText = """
        Native macOS client for LocalOCR Extended.
        Receipts, inventory, finance — at home.

        Built with SwiftUI + AppKit.
        \(copyright)
        """

        let credits = NSAttributedString(
            string: creditsText,
            attributes: [
                .font: NSFont.systemFont(ofSize: 11),
                .foregroundColor: NSColor.secondaryLabelColor
            ]
        )

        let options: [NSApplication.AboutPanelOptionKey: Any] = [
            .applicationName:    "LocalOCR",
            .applicationVersion: version,
            .version:            "Build \(build)",
            .credits:            credits
        ]

        NSApp.orderFrontStandardAboutPanel(options: options)
    }
}
