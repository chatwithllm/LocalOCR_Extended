import SwiftUI

// Phase 1: compile-only stubs. Full implementations land in Phase 2 (§5.8, §5.1).

/// Inline-editable text field — no border until focused. Used in Fixed Bills rename, inventory inline edits.
struct InlineEditableTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
    }
}

/// Search field styling — rounded, leading magnifying-glass icon. Used in lists.
struct SearchFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
    }
}
