import SwiftUI

/// Sidebar list bound to `Router.activeTab`. Per §3.2.
///
/// Section headers use explicit header views with leading padding so the
/// "Workspace" / "Tools" labels align under the row icons instead of
/// rendering with SwiftUI's default narrower section inset (which clipped the
/// first character at small column widths on macOS 13.3+).
struct SidebarView: View {
    @Binding var active: Router.TabDestination

    var body: some View {
        List(selection: $active) {
            Section {
                ForEach(workspaceTabs) { row($0) }
            } header: {
                sectionHeader("Workspace")
            }

            Section {
                ForEach(toolTabs) { row($0) }
            } header: {
                sectionHeader("Tools")
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("LocalOCR")
    }

    private var workspaceTabs: [Router.TabDestination] {
        [.dashboard, .inventory, .products, .receipts, .shopping, .kitchen, .finance, .restaurant, .balances]
    }

    private var toolTabs: [Router.TabDestination] {
        [.chat, .medications]
    }

    private func row(_ tab: Router.TabDestination) -> some View {
        Label(tab.displayName, systemImage: tab.systemImage)
            .tag(tab)
            .accessibilityLabel(tab.displayName)
    }

    /// Section header tuned to align with row text. The `.padding(.leading, 4)`
    /// nudges the label so the leading edge sits in the same vertical column
    /// as the row icons, instead of getting clipped by the column boundary.
    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(DesignTokens.secondaryLabel)
            .padding(.leading, 4)
            .padding(.top, DesignTokens.Spacing.space1)
    }
}

#Preview("Sidebar") {
    struct Wrapper: View {
        @State var active: Router.TabDestination = .dashboard
        var body: some View {
            NavigationSplitView {
                SidebarView(active: $active)
            } detail: {
                Text("Detail: \(active.displayName)").padding()
            }
            .frame(width: 800, height: 500)
        }
    }
    return Wrapper()
}
