import SwiftUI

// MARK: - F-900..F-921 — Dining Contacts
//
// Saved contacts for splitting restaurant receipts. Mirrors web
// `loadContacts` + `saveContact`. State reuses SharedDiningState.

struct ContactsView: View {
    @StateObject private var state = SharedDiningState.shared
    @State private var draftName: String = ""
    @State private var draftPhone: String = ""
    @State private var draftEmail: String = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                header
                AddContactCard(
                    state: state,
                    name: $draftName,
                    phone: $draftPhone,
                    email: $draftEmail
                )
                SavedContactsCard(state: state)
                PageNavStrip()
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Dining Contacts")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await state.loadContacts() }
                } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                .help("Reload contacts list")
            }
        }
        .onAppear {
            Task.detached(priority: .userInitiated) {
                await SharedDiningState.shared.loadContacts()
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Dining Contacts").font(.appTitle2)
            Text("Saved contacts for splitting restaurant receipts")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }
}

// MARK: - F-903..F-911 add contact card

private struct AddContactCard: View {
    @ObservedObject var state: SharedDiningState
    @Binding var name: String
    @Binding var phone: String
    @Binding var email: String

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                Text("Add Contact").font(.appHeadline)
                HStack(alignment: .bottom, spacing: 8) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Name *").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                        TextField("e.g. Priya Patel", text: $name).textFieldStyle(.roundedBorder)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Phone").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                        TextField("+1 555 000 0000", text: $phone).textFieldStyle(.roundedBorder)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Email").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                        TextField("name@example.com", text: $email).textFieldStyle(.roundedBorder)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text("").font(.appCaption2)
                        Button {
                            Task {
                                let ok = await state.createContact(
                                    name: name,
                                    phone: phone,
                                    email: email
                                )
                                if ok {
                                    name = ""
                                    phone = ""
                                    email = ""
                                }
                            }
                        } label: { Text("Add Contact") }
                        .buttonStyle(PrimaryButtonStyle())
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
            }
        }
    }
}

// MARK: - F-912..F-921 saved contacts card

private struct SavedContactsCard: View {
    @ObservedObject var state: SharedDiningState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Saved Contacts").font(.appHeadline)
                    Spacer()
                    if !state.contacts.isEmpty {
                        Text("\(state.contacts.count)")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
                content
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if state.contacts.isEmpty {
            EmptyStateView(
                systemImage: "person.crop.circle.badge.plus",
                title: "No saved contacts yet.",
                subtitle: "Add one above."
            )
            .frame(height: 160)
        } else {
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 220), spacing: 10)],
                alignment: .leading,
                spacing: 10
            ) {
                ForEach(state.contacts) { c in
                    ContactCard(contact: c)
                }
            }
        }
    }
}

private struct ContactCard: View {
    let contact: DiningContactRow

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            // F-918 avatar initial
            Text(initial)
                .font(.appTitle3.weight(.bold))
                .foregroundStyle(.white)
                .frame(width: 36, height: 36)
                .background(DesignTokens.accent)
                .clipShape(Circle())
            VStack(alignment: .leading, spacing: 2) {
                // F-919 name
                Text(contact.name)
                    .font(.appCallout.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
                    .lineLimit(1)
                // F-920 meta (phone · email)
                let metaBits = [contact.phone, contact.email]
                    .compactMap { $0 }
                    .filter { !$0.isEmpty }
                if !metaBits.isEmpty {
                    Text(metaBits.joined(separator: " · "))
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                        .lineLimit(2)
                        .truncationMode(.tail)
                }
            }
            Spacer()
        }
        .padding(10)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .stroke(DesignTokens.border, lineWidth: 0.5)
        )
    }

    private var initial: String {
        String(contact.name.prefix(1)).uppercased()
    }
}

#Preview("ContactsView") {
    ContactsView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 900, height: 600)
}
