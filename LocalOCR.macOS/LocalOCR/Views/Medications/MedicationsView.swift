import SwiftUI

struct MedicationsView: View {
    var body: some View {
        EmptyStateView(
            systemImage: "pills",
            title: "Medications",
            subtitle: "Medication tracking lands in v1.1."
        )
        .navigationTitle("Medications")
    }
}
