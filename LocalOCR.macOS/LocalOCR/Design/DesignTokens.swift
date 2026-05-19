import SwiftUI
import AppKit

/// Design tokens for LocalOCR macOS, mapped from §3.1 of MACOS_APP_PLAN.md.
///
/// Tokens prefer NSColor semantic colors (auto light/dark adapt) over hardcoded hex.
/// Brand-specific colors (accent, success, warning, error, low-stock, etc.) use
/// explicit hex pairs and adapt via NSColor(name:dynamicProvider:).
enum DesignTokens {

    // MARK: - Brand color (hex pairs)

    /// Brand blue. Used as default accent; user may override via System Settings.
    static let accent = Color(nsColor: dynamic(light: 0x3b82f6, dark: 0x3b82f6))

    // MARK: - Surface / background

    static let background = Color(nsColor: NSColor.windowBackgroundColor)
    static let sidebarBackground = Color(nsColor: dynamic(light: 0xf5f5f7, dark: 0x1a1a1e))
    static let surface = Color(nsColor: NSColor.controlBackgroundColor)
    // §3.1 surface2 maps to .quaternarySystemFill, but that semantic color is macOS 14+.
    // Hardcode the dynamic light/dark hex pair from §3.1 to stay on min target 13.3.
    static let surface2 = Color(nsColor: dynamic(light: 0xf2f2f7, dark: 0x222226))

    // MARK: - Borders / labels

    static let border = Color(nsColor: NSColor.separatorColor)
    static let label = Color(nsColor: NSColor.labelColor)
    static let secondaryLabel = Color(nsColor: NSColor.secondaryLabelColor)
    static let tertiaryLabel = Color(nsColor: NSColor.tertiaryLabelColor)
    static let quaternaryLabel = Color(nsColor: NSColor.quaternaryLabelColor)

    // MARK: - Semantic state

    static let success = Color(nsColor: NSColor.systemGreen)
    static let successDim = Color(nsColor: dynamic(light: 0xedfaf3, dark: 0x162820))
    static let warning = Color(nsColor: NSColor.systemOrange)
    static let warningDim = Color(nsColor: dynamic(light: 0xfffbeb, dark: 0x1a1500))
    static let error = Color(nsColor: NSColor.systemRed)
    static let errorDim = Color(nsColor: dynamic(light: 0xfef2f2, dark: 0x2d0a0a))
    static let accentDim = Color(nsColor: dynamic(light: 0xeff6ff, dark: 0x1e3a5f))

    // MARK: - Row / drop-target / bill states

    static let receiptHover = Color(nsColor: dynamic(light: 0xf5f5f7, dark: 0x202024))
    static let dropTarget = Color(nsColor: dynamic(light: 0xeff6ff, dark: 0x1e3a5f))
    static let lowStockPillBackground = Color(nsColor: dynamic(light: 0xfff7ed, dark: 0x27190a))
    static let paidBill = Color(nsColor: dynamic(light: 0xecfdf5, dark: 0x0a2318))
    static let unpaidBill = Color(nsColor: dynamic(light: 0xfffbeb, dark: 0x1a1500))
    static let overdueBill = Color(nsColor: dynamic(light: 0xfef2f2, dark: 0x2d0a0a))

    // MARK: - Spacing (§3.1 8-pt grid)

    enum Spacing {
        static let space1: CGFloat = 4
        static let space2: CGFloat = 8
        static let space3: CGFloat = 12
        static let space4: CGFloat = 16
        static let space5: CGFloat = 20
        static let space6: CGFloat = 24
        static let space8: CGFloat = 32
        static let space10: CGFloat = 40
    }

    // MARK: - Corner radius

    enum Radius {
        static let control: CGFloat = 6
        static let card: CGFloat = 10
        static let pill: CGFloat = 4
        static let dropZone: CGFloat = 8
    }

    // MARK: - Helpers

    /// Build an NSColor that switches between two hex values based on the effective appearance.
    private static func dynamic(light: UInt32, dark: UInt32) -> NSColor {
        NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .vibrantDark]) != nil
            return NSColor(hex: isDark ? dark : light)
        }
    }
}

private extension NSColor {
    /// Initialize from a 0xRRGGBB hex value (alpha = 1.0).
    convenience init(hex: UInt32) {
        let red = CGFloat((hex >> 16) & 0xFF) / 255.0
        let green = CGFloat((hex >> 8) & 0xFF) / 255.0
        let blue = CGFloat(hex & 0xFF) / 255.0
        self.init(srgbRed: red, green: green, blue: blue, alpha: 1.0)
    }
}
