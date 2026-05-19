import SwiftUI

struct AIChatView: View {
    var body: some View {
        EmptyStateView(
            systemImage: "bubble.left.and.bubble.right",
            title: "AI Chat",
            subtitle: "Natural-language queries about spending + inventory land in v1.1."
        )
        .navigationTitle("AI Chat")
    }
}
