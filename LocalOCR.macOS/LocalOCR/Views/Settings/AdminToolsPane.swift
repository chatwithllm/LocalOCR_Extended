import SwiftUI
import AppKit

// F-1724..F-1730 (Manage Stores), F-1732..F-1758 (Household Users + Invites +
// Service Accounts), F-1759..F-1777 (Trusted Devices CRUD + Pairing modal),
// F-1778..F-1784 (Snapshot Review), F-1785..F-1806 (Environment Backup),
// F-1807..F-1813 (Catalog Review), F-1814..F-1846 (AI Model Registry + Usage),
// F-1847..F-1861 (Image Backfill), F-1862..F-1864 (Chat Audit).
//
// All of these are admin-power surfaces that don't justify a full native
// rewrite for a desktop client (CRUD modals, paginated tables, restore
// progress UIs, model editor with 17 fields). This pane surfaces every web
// section with a one-tap "Open in web app" link instead — deferred to v1.1
// for any user who needs to do the admin work natively.

struct AdminToolsPane: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var prefs = PreferencesStore.shared

    var body: some View {
        Form {
            if appState.currentUser?.isAdmin != true {
                Section {
                    HStack(spacing: 6) {
                        Image(systemName: "lock.fill")
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                        Text("Admin-only tools. Sign in as an admin to manage household power features.")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.secondaryLabel)
                    }
                }
            } else {
                Section("Household") {
                    adminLink("Manage stores",
                             help: "Frequent / Rarely Used / Hidden visibility per store",
                             page: "/settings#manage-stores",
                             systemImage: "storefront")
                    adminLink("Household users + invites",
                             help: "Add password / Google-invite users, edit role, pages, delete",
                             page: "/settings#household-users",
                             systemImage: "person.3")
                    adminLink("Trusted devices + pairing",
                             help: "Pair new device with QR + per-device scope / pages / revoke",
                             page: "/settings#trusted-devices",
                             systemImage: "laptopcomputer.and.iphone")
                }

                Section("Content review") {
                    adminLink("Catalog review queue",
                             help: "Approve / dismiss OCR-heavy product names",
                             page: "/settings#review-queue",
                             systemImage: "checklist")
                    adminLink("Snapshot review queue",
                             help: "Link product snapshots to catalog entries",
                             page: "/settings#snapshot-review",
                             systemImage: "photo.stack")
                }

                Section("System") {
                    adminLink("Environment backup & restore",
                             help: "Create / verify / download / restore .tar.gz bundles",
                             page: "/settings#environment-backup",
                             systemImage: "arrow.clockwise.icloud")
                    adminLink("AI model registry",
                             help: "Add / edit / disable models; provider keys; pricing",
                             page: "/settings#ai-models",
                             systemImage: "cpu")
                    adminLink("AI usage report",
                             help: "Requests / tokens / cost per model over last N days",
                             page: "/settings#ai-usage",
                             systemImage: "chart.bar.xaxis")
                    adminLink("Image backfill scheduler",
                             help: "Bulk generate product images + nightly schedule",
                             page: "/settings#image-backfill",
                             systemImage: "photo.badge.arrow.down")
                    adminLink("Chat audit log",
                             help: "Last N AI chat messages with model + tokens",
                             page: "/settings#chat-audit",
                             systemImage: "doc.text.magnifyingglass")
                }

                Section {
                    Text("These admin surfaces use heavy form/modal infrastructure (paginated tables, CRUD editors, restore-progress streams) that don't justify a native rewrite for v1.0. Each button opens the corresponding section in the web app — same auth session via trusted device token. v1.1 will surface the most-used flows natively.")
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
    }

    private func adminLink(_ title: String, help: String, page: String, systemImage: String) -> some View {
        Button {
            openInWeb(page: page)
        } label: {
            HStack {
                Label(title, systemImage: systemImage)
                Spacer()
                Image(systemName: "arrow.up.right.square")
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
        }
        .buttonStyle(.plain)
        .help(help)
    }

    private func openInWeb(page: String) {
        let base = prefs.apiBaseURL.absoluteString
        let url = URL(string: base + page) ?? prefs.apiBaseURL
        NSWorkspace.shared.open(url)
    }
}
