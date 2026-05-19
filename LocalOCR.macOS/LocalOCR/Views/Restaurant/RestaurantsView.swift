import SwiftUI

struct RestaurantsView: View {
    var body: some View {
        EmptyStateView(
            systemImage: "fork.knife",
            title: "Restaurants",
            subtitle: "Restaurant receipts, repeat orders, and dining budget land in v1.1."
        )
        .navigationTitle("Restaurants")
    }
}
