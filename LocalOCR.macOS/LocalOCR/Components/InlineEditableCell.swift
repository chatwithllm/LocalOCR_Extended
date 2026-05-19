import SwiftUI

/// Double-click to edit. Used in Fixed Bills rename and inventory inline edits.
///
/// Behavior:
///  - Renders Text. Double-click swaps to a TextField, focused immediately.
///  - Enter commits, Esc cancels. Both restore Text mode.
///  - Loss of focus also commits.
struct InlineEditableCell: View {
    @Binding var text: String
    var onCommit: (String) -> Void = { _ in }
    var placeholder: String = ""

    @State private var isEditing = false
    @State private var draft = ""
    @FocusState private var fieldFocused: Bool

    var body: some View {
        Group {
            if isEditing {
                TextField(placeholder, text: $draft)
                    .textFieldStyle(.roundedBorder)
                    .focused($fieldFocused)
                    .onSubmit(commit)
                    .onExitCommand(perform: cancel)
                    .onChange(of: fieldFocused) { focused in
                        if !focused { commit() }
                    }
            } else {
                Text(text)
                    .foregroundStyle(text.isEmpty ? DesignTokens.tertiaryLabel : DesignTokens.label)
                    .onTapGesture(count: 2) { startEditing() }
                    .accessibilityHint("Double-click to edit")
            }
        }
    }

    private func startEditing() {
        draft = text
        isEditing = true
        DispatchQueue.main.async { fieldFocused = true }
    }

    private func commit() {
        guard isEditing else { return }
        let trimmed = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty && trimmed != text {
            text = trimmed
            onCommit(trimmed)
        }
        isEditing = false
    }

    private func cancel() {
        isEditing = false
    }
}

#Preview("InlineEditableCell") {
    struct Wrapper: View {
        @State var name = "Verizon Wireless"
        var body: some View {
            Card {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Obligation name").font(.appCaption1).foregroundStyle(.secondary)
                    InlineEditableCell(text: $name, placeholder: "Bill name") { newValue in
                        print("Committed: \(newValue)")
                    }
                }
            }
            .padding(40)
            .frame(width: 360)
        }
    }
    return Wrapper()
}
