import SwiftUI

struct KitchenView: View {
    @StateObject private var state = InventoryState.shared

    var body: some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 12)], alignment: .leading, spacing: 12) {
                ForEach(state.categories, id: \.self) { cat in
                    Card {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(cat).font(.appHeadline)
                            Text("\(state.items.filter { $0.category == cat }.count) items")
                                .font(.appCaption1)
                                .foregroundStyle(DesignTokens.secondaryLabel)
                        }
                    }
                }
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .navigationTitle("Kitchen")
        .task { await state.loadInventory() }
    }
}

#Preview("KitchenView") {
    KitchenView().frame(width: 700, height: 500)
}
