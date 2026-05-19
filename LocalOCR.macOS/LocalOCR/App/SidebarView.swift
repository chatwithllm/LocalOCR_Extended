import SwiftUI

/// Sidebar list bound to `Router.activeTab`. Per §3.2.
///
/// Sections:
///   - Workspaces — Dashboard, Inventory, Receipts, Shopping, Finance, Restaurants
///   - Tools — AI Chat, Medications
struct SidebarView: View {
    @Binding var active: Router.TabDestination

    var body: some View {
        List(selection: $active) {
            Section("Workspace") {
                ForEach(workspaceTabs) { row($0) }
            }
            Section("Tools") {
                ForEach(toolTabs) { row($0) }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("LocalOCR")
    }

    private var workspaceTabs: [Router.TabDestination] {
        [.dashboard, .inventory, .receipts, .shopping, .finance, .restaurant]
    }

    private var toolTabs: [Router.TabDestination] {
        [.chat, .medications]
    }

    private func row(_ tab: Router.TabDestination) -> some View {
        Label(tab.displayName, systemImage: tab.systemImage)
            .tag(tab)
            .accessibilityLabel(tab.displayName)
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
