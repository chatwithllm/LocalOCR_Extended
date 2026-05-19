import SwiftUI

/// Typography roles for LocalOCR macOS, mapped from §3.1 of MACOS_APP_PLAN.md.
///
/// All roles use SF Pro (system font). Dynamic Type is respected — no fixed sizes.
/// SF Pro Display (≥ 20pt) and SF Pro Text (< 20pt) are auto-selected by the system.
extension Font {

    /// 26pt Bold — screen titles (Login hero, onboarding).
    static let appLargeTitle = Font.largeTitle.weight(.bold)

    /// 22pt Bold — section headers in main content area.
    static let appTitle1 = Font.title.weight(.bold)

    /// 17pt Semibold — card headers, panel titles.
    static let appTitle2 = Font.title2.weight(.semibold)

    /// 15pt Semibold — subsection headers, group labels.
    static let appTitle3 = Font.title3.weight(.semibold)

    /// 13pt Semibold — column headers, badge labels.
    static let appHeadline = Font.headline

    /// 13pt Regular — default body text, list row primary label.
    static let appBody = Font.body

    /// 12pt Regular — toolbar labels, secondary actions.
    static let appCallout = Font.callout

    /// 11pt Regular — list row secondary label, metadata.
    static let appSubheadline = Font.subheadline

    /// 11pt Regular — status text, timestamps.
    static let appFootnote = Font.footnote

    /// 10pt Regular — pill labels, badge text.
    static let appCaption1 = Font.caption

    /// 10pt Regular — fine print, version strings.
    static let appCaption2 = Font.caption2

    /// 13pt Regular monospaced — receipt line-item amounts, currency values.
    static let appMonoBody = Font.body.monospaced()

    /// 10pt Regular monospaced — transaction IDs, token/model stats.
    static let appMonoCaption = Font.caption.monospaced()
}
