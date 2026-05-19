import SwiftUI

/// Picker for receipt attribution (§1.7 rule 6). Selects which household member
/// "owns" a receipt. Phase 2 uses placeholder member data; Phase 4 wires to
/// `HouseholdState.users`.
struct AttributionPicker: View {
    /// Lightweight DTO. Real `User` Codable model lands in Phase 3.
    struct Member: Identifiable, Hashable {
        let id: Int
        let name: String
        let avatarEmoji: String?
    }

    let members: [Member]
    @Binding var selectedId: Int?
    var label: String = "Attributed to"

    var body: some View {
        Picker(label, selection: $selectedId) {
            Text("Unassigned").tag(Int?.none)
            ForEach(members) { m in
                HStack(spacing: 6) {
                    Text(m.avatarEmoji ?? "👤")
                    Text(m.name)
                }
                .tag(Int?.some(m.id))
            }
        }
        .pickerStyle(.menu)
        .accessibilityLabel(label)
    }
}

#Preview("AttributionPicker") {
    struct Wrapper: View {
        @State var selected: Int? = 1
        var body: some View {
            Card {
                AttributionPicker(
                    members: [
                        .init(id: 1, name: "Nik",  avatarEmoji: "👨"),
                        .init(id: 2, name: "Mira", avatarEmoji: "👩"),
                        .init(id: 3, name: "Eli",  avatarEmoji: "🧒")
                    ],
                    selectedId: $selected
                )
            }
            .padding(40)
            .frame(width: 360)
        }
    }
    return Wrapper()
}
