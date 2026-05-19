import SwiftUI

/// Branded text-field styles per §3.6.

/// No visible border until the field gains focus. Used in Fixed Bills inline rename
/// and inventory inline edits.
struct InlineEditableTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        InlineEditableContent { configuration }
    }
}

private struct InlineEditableContent<Content: View>: View {
    @FocusState private var focused: Bool
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .focused($focused)
            .textFieldStyle(.plain)
            .font(.appBody)
            .padding(.horizontal, DesignTokens.Spacing.space2)
            .padding(.vertical, DesignTokens.Spacing.space1)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.control)
                    .fill(focused ? DesignTokens.surface : .clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radius.control)
                    .stroke(focused ? DesignTokens.accent : .clear, lineWidth: 1.5)
            )
    }
}

/// Search field with leading magnifier icon, rounded corners.
struct SearchFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(DesignTokens.secondaryLabel)
                .accessibilityHidden(true)
            configuration
                .textFieldStyle(.plain)
                .font(.appBody)
        }
        .padding(.horizontal, DesignTokens.Spacing.space3)
        .padding(.vertical, DesignTokens.Spacing.space2)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.control))
    }
}

#Preview("TextField styles") {
    struct Wrapper: View {
        @State var inline = "Verizon Wireless"
        @State var query = ""
        var body: some View {
            VStack(alignment: .leading, spacing: 16) {
                TextField("Bill name", text: $inline).textFieldStyle(InlineEditableTextFieldStyle())
                TextField("Search receipts", text: $query).textFieldStyle(SearchFieldStyle())
            }
            .padding(40)
            .frame(width: 380)
        }
    }
    return Wrapper()
}
