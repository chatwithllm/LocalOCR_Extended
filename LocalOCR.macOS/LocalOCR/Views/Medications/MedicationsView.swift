import SwiftUI
import AppKit
import os.log

// MARK: - F-1600..F-1638 — Medicine Cabinet
//
// Household medication tracking — name, strength, expiry, member assignment,
// AI warnings. Mirrors web `loadMedicineCabinet`, `_renderMedicineCabinet`,
// `_buildMedTile`, `_openMedicationSheet`, `openMembersSheet`.
//
// Routes verified against `manage_medications.py`. Household roster comes from
// `/auth/household-members` (read-only — backend does not have add/delete
// routes, so F-1635..F-1637 are 🚫 v1.0).

// MARK: - Models

struct Medication: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String
    let brand: String?
    let strength: String?
    let dosageForm: String?
    let activeIngredient: String?
    let ageGroup: String?
    let belongsTo: String?
    let memberId: Int?
    let userId: Int?
    let barcode: String?
    let productId: Int?
    let manufactureDate: String?
    let expiryDate: String?
    let quantity: Double?
    let unit: String?
    let lowThreshold: Double?
    let rxNumber: String?
    let prescribingDoctor: String?
    let aiWarnings: [String]?
    let imagePath: String?
    let status: String?
    let notes: String?
    let createdAt: String?
    let updatedAt: String?
    let isExpired: Bool?
    let isLow: Bool?
}

struct MedicationsListResponse: Codable, Equatable {
    let medications: [Medication]
    let count: Int?
}

struct MedicationWrapper: Codable, Equatable {
    let medication: Medication
}

/// `/auth/household-members` returns `members: [{id, name, role, is_self}]`.
/// The backend has no separate HouseholdMember table; rows are User records.
struct MedicineMember: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String
    let role: String?
    let isSelf: Bool?

    var emoji: String { "👤" }
    /// Chip key — matches web's `p.type + "_" + p.id` pattern.
    var chipKey: String { "user_\(id)" }
}

struct MedicineMembersResponse: Codable, Equatable {
    let members: [MedicineMember]
}

// MARK: - Constants

enum MedicationOptions {
    static let dosageForms: [(value: String, label: String)] = [
        ("tablet", "Tablet"),
        ("capsule", "Capsule"),
        ("liquid", "Liquid/Syrup"),
        ("cream", "Cream/Gel/Ointment"),
        ("spray", "Spray"),
        ("patch", "Patch"),
        ("other", "Other"),
    ]
    static let ageGroups: [(value: String, label: String)] = [
        ("both",  "👪 Everyone (Adult & Kids)"),
        ("adult", "🧑 Adults only"),
        ("child", "👶 Kids only"),
    ]
    static let units: [(value: String, label: String)] = [
        ("tablets", "Tablets"),
        ("capsules", "Capsules"),
        ("ml", "ml"),
        ("oz", "oz"),
        ("count", "Count"),
        ("doses", "Doses"),
    ]
    static let statuses: [(value: String, label: String)] = [
        ("active",   "Active"),
        ("all",      "All"),
        ("expired",  "Expired"),
        ("finished", "Finished"),
    ]
}

// MARK: - MedicationsState

@MainActor
final class MedicationsState: ObservableObject {

    static let shared = MedicationsState()

    @Published private(set) var medications: [Medication] = []
    @Published private(set) var members: [MedicineMember] = []
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?

    /// Status query param — `active` (default) | `all` | `expired` | `finished`.
    @Published var statusFilter: String = "active"
    /// Member filter chip — `nil` = All, `"household"` = unassigned, or `"user_<id>"`.
    @Published var memberFilter: String?

    @Published var editing: MedicationEditState?
    @Published var membersSheetOpen: Bool = false

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "medications")

    init(api: APIClient = .shared) {
        self.api = api
    }

    func setMemberFilter(_ key: String?) {
        memberFilter = key
        Task { await loadMedications() }
    }

    func setStatusFilter(_ status: String) {
        statusFilter = status
        Task { await loadMedications() }
    }

    func refresh() async {
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in await self.loadMedications() }
            group.addTask { @MainActor in await self.loadMembers() }
        }
    }

    func loadMedications() async {
        isLoading = true
        defer { isLoading = false }
        do {
            var userId: Int?
            var memberId: String?
            if let key = memberFilter {
                if key == "household" {
                    memberId = "none"
                } else if key.hasPrefix("user_") {
                    userId = Int(key.dropFirst("user_".count))
                } else if key.hasPrefix("member_") {
                    memberId = String(key.dropFirst("member_".count))
                }
            }
            let endpoint = MedicationEndpoint.list(status: statusFilter, userId: userId, memberId: memberId)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: MedicationsListResponse.self
            )
            medications = response.medications
            logger.info("loaded \(response.medications.count, privacy: .public) medications (status=\(self.statusFilter, privacy: .public))")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadMedications failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadMembers() async {
        do {
            let response = try await api.request(
                .get,
                path: AuthEndpoint.householdMembers.path,
                as: MedicineMembersResponse.self
            )
            members = response.members
            logger.info("loaded \(response.members.count, privacy: .public) household members")
        } catch is CancellationError {
            return
        } catch {
            logger.warning("loadMembers failed: \(error.localizedDescription, privacy: .public)")
            members = []
        }
    }

    func openAdd() {
        editing = MedicationEditState(existing: nil, members: members)
    }
    func openEdit(_ med: Medication) {
        editing = MedicationEditState(existing: med, members: members)
    }
    func closeSheet() {
        editing = nil
    }

    @discardableResult
    func barcodeLookup(name: String?, barcode: String?) async -> MedicationLookupFields? {
        let trimmedName = name?.trimmingCharacters(in: .whitespaces)
        let trimmedBarcode = barcode?.trimmingCharacters(in: .whitespaces)
        guard (trimmedName?.isEmpty == false) || (trimmedBarcode?.isEmpty == false) else {
            ToastQueue.shared.push(Toast(message: "Enter a name or barcode first", severity: .error))
            return nil
        }
        do {
            let body = BarcodeLookupBody(
                barcode: trimmedBarcode?.isEmpty == false ? trimmedBarcode : nil,
                name: trimmedName?.isEmpty == false ? trimmedName : nil
            )
            let response = try await api.request(
                .post,
                path: MedicationEndpoint.barcodeLookup.path,
                jsonBody: body,
                as: BarcodeLookupResponse.self
            )
            if response.found, let fields = response.fields {
                ToastQueue.shared.push(Toast(message: "Filled from drug database ✅", severity: .success))
                return fields
            }
            ToastQueue.shared.push(Toast(message: "Not found in drug database", severity: .info))
            return nil
        } catch is CancellationError {
            return nil
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Lookup failed",
                severity: .error
            ))
            return nil
        }
    }

    func save(_ draft: MedicationEditState) async -> Bool {
        let name = draft.name.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else {
            ToastQueue.shared.push(Toast(message: "Name is required", severity: .error))
            return false
        }
        do {
            try DemoModeGate.guardMutation()
            let body = draft.toBody()
            if let med = draft.existing {
                try await api.request(
                    .put,
                    path: MedicationEndpoint.update(id: med.id).path,
                    jsonBody: body
                )
                ToastQueue.shared.push(Toast(message: "Updated ✅", severity: .success))
            } else {
                try await api.request(
                    .post,
                    path: MedicationEndpoint.create.path,
                    jsonBody: body
                )
                ToastQueue.shared.push(Toast(message: "Added ✅", severity: .success))
            }
            await loadMedications()
            return true
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
            return false
        } catch APIError.validation(let m) {
            ToastQueue.shared.push(Toast(message: m ?? "Invalid medication data", severity: .error))
            return false
        } catch is CancellationError {
            return false
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Save failed",
                severity: .error
            ))
            return false
        }
    }

    func markDone(_ med: Medication) async {
        do {
            try DemoModeGate.guardMutation()
            let body = MedicationBody(
                name: nil, brand: nil, strength: nil, activeIngredient: nil,
                dosageForm: nil, ageGroup: nil, belongsTo: nil,
                memberId: nil, userId: nil, quantity: nil, unit: nil, lowThreshold: nil,
                expiryDate: nil, manufactureDate: nil, barcode: nil, notes: nil,
                status: "finished"
            )
            try await api.request(
                .put,
                path: MedicationEndpoint.update(id: med.id).path,
                jsonBody: body
            )
            ToastQueue.shared.push(Toast(message: "Marked as finished ✅", severity: .success))
            await loadMedications()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Update failed",
                severity: .error
            ))
        }
    }

    func delete(_ med: Medication) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.delete, path: MedicationEndpoint.delete(id: med.id).path)
            ToastQueue.shared.push(Toast(message: "Deleted", severity: .success))
            medications.removeAll { $0.id == med.id }
            await loadMedications()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Delete failed",
                severity: .error
            ))
        }
    }

    func memberLabel(for med: Medication) -> String? {
        if let uid = med.userId, let m = members.first(where: { $0.id == uid }) {
            return "\(m.emoji) \(m.name)"
        }
        if med.belongsTo == "household" {
            return "🏠 Household"
        }
        return nil
    }
}

// MARK: - MedicationEditState

@MainActor
final class MedicationEditState: ObservableObject, Identifiable {
    nonisolated let id = UUID()
    let existing: Medication?
    let members: [MedicineMember]

    @Published var name: String
    @Published var brand: String
    @Published var strength: String
    @Published var activeIngredient: String
    @Published var dosageForm: String
    @Published var ageGroup: String
    @Published var memberKey: String      // "household" | "user_<id>" | "member_<id>"
    @Published var quantityText: String
    @Published var unit: String
    @Published var expiryDate: String     // YYYY-MM-DD
    @Published var manufactureDate: String
    @Published var barcode: String
    @Published var notes: String

    init(existing: Medication?, members: [MedicineMember]) {
        self.existing = existing
        self.members = members
        self.name = existing?.name ?? ""
        self.brand = existing?.brand ?? ""
        self.strength = existing?.strength ?? ""
        self.activeIngredient = existing?.activeIngredient ?? ""
        self.dosageForm = existing?.dosageForm ?? "tablet"
        self.ageGroup = existing?.ageGroup ?? "both"
        if let uid = existing?.userId {
            self.memberKey = "user_\(uid)"
        } else if let mid = existing?.memberId {
            self.memberKey = "member_\(mid)"
        } else {
            self.memberKey = "household"
        }
        self.quantityText = existing?.quantity.map { String(Int($0)) } ?? ""
        self.unit = existing?.unit ?? "tablets"
        self.expiryDate = existing?.expiryDate ?? ""
        self.manufactureDate = existing?.manufactureDate ?? ""
        self.barcode = existing?.barcode ?? ""
        self.notes = existing?.notes ?? ""
    }

    /// Apply auto-fill fields from POST /medications/barcode-lookup result.
    func apply(lookup fields: MedicationLookupFields) {
        if let v = fields.name, !v.isEmpty { name = v }
        if let v = fields.brand, !v.isEmpty { brand = v }
        if let v = fields.strength, !v.isEmpty { strength = v }
        if let v = fields.activeIngredient, !v.isEmpty { activeIngredient = v }
        if let v = fields.dosageForm, !v.isEmpty { dosageForm = v }
        if let v = fields.ageGroup, !v.isEmpty { ageGroup = v }
        if let v = fields.barcode, !v.isEmpty { barcode = v }
    }

    func toBody() -> MedicationBody {
        var userId: Int?
        var memberId: Int?
        let belongs: String
        if memberKey == "household" {
            belongs = "household"
        } else if memberKey.hasPrefix("user_"), let uid = Int(memberKey.dropFirst("user_".count)) {
            userId = uid
            belongs = memberKey
        } else if memberKey.hasPrefix("member_"), let mid = Int(memberKey.dropFirst("member_".count)) {
            memberId = mid
            belongs = memberKey
        } else {
            belongs = "household"
        }
        return MedicationBody(
            name: name.trimmingCharacters(in: .whitespaces),
            brand: brand.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            strength: strength.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            activeIngredient: activeIngredient.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            dosageForm: dosageForm,
            ageGroup: ageGroup,
            belongsTo: belongs,
            memberId: memberId,
            userId: userId,
            quantity: Double(quantityText.trimmingCharacters(in: .whitespaces)),
            unit: unit,
            lowThreshold: nil,
            expiryDate: expiryDate.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            manufactureDate: manufactureDate.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            barcode: barcode.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            notes: notes.trimmingCharacters(in: .whitespaces).nilIfEmpty,
            status: existing?.status ?? "active"
        )
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

// MARK: - MedicationsView

struct MedicationsView: View {
    @StateObject private var state = MedicationsState.shared
    @EnvironmentObject private var appState: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                header
                MemberChipRow(state: state)
                MedicationsListBody(state: state)
                PageNavStrip()
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Medicine Cabinet")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    state.membersSheetOpen = true
                } label: { Label("Members", systemImage: "person.2") }
                .help("View household roster")
                Button {
                    state.openAdd()
                } label: { Label("Add Medication", systemImage: "plus") }
                .keyboardShortcut("n", modifiers: .command)
                .help("Add a new medication")
            }
        }
        .onAppear {
            // RULE 3 — detached fetch survives view-identity churn.
            Task.detached(priority: .userInitiated) {
                await MedicationsState.shared.refresh()
            }
        }
        .sheet(item: $state.editing) { draft in
            MedicationEditSheet(state: state, draft: draft)
        }
        .sheet(isPresented: $state.membersSheetOpen) {
            MembersSheet(state: state)
        }
    }

    // F-1600 + F-1603
    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Medicine Cabinet").font(.appTitle2)
                Text("Track household medications, expiry dates, and members")
                    .font(.appSubheadline)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
            HStack(spacing: 8) {
                Picker("Status", selection: Binding(
                    get: { state.statusFilter },
                    set: { state.setStatusFilter($0) }
                )) {
                    ForEach(MedicationOptions.statuses, id: \.value) { opt in
                        Text(opt.label).tag(opt.value)
                    }
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 360)
                Spacer()
                Text("\(state.medications.count) medication\(state.medications.count == 1 ? "" : "s")")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
        }
    }
}

// MARK: - F-1604 member chip row

private struct MemberChipRow: View {
    @ObservedObject var state: MedicationsState

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                chip(label: "All", active: state.memberFilter == nil) {
                    state.setMemberFilter(nil)
                }
                ForEach(state.members) { person in
                    chip(
                        label: "\(person.emoji) \(person.name)",
                        active: state.memberFilter == person.chipKey
                    ) {
                        state.setMemberFilter(person.chipKey)
                    }
                }
                chip(label: "🏠 Household", active: state.memberFilter == "household") {
                    state.setMemberFilter("household")
                }
            }
        }
    }

    private func chip(label: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.appCaption1.weight(active ? .semibold : .regular))
                .foregroundStyle(active ? .white : DesignTokens.label)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .background(active ? DesignTokens.accent : DesignTokens.surface2)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - F-1605..F-1617 list body + medication rows

private struct MedicationsListBody: View {
    @ObservedObject var state: MedicationsState

    var body: some View {
        if state.isLoading && state.medications.isEmpty {
            EmptyStateView(systemImage: "hourglass", title: "Loading…").frame(height: 200)
        } else if state.medications.isEmpty {
            EmptyStateView(
                systemImage: "pills",
                title: "No medications.",
                subtitle: "Tap + Add Medication to get started."
            )
            .frame(height: 200)
        } else {
            VStack(spacing: 8) {
                ForEach(state.medications) { med in
                    MedicationRow(med: med, state: state)
                }
            }
        }
    }
}

private struct MedicationRow: View {
    let med: Medication
    @ObservedObject var state: MedicationsState

    private var isExpired: Bool { med.isExpired == true || med.status == "expired" }
    private var isLow: Bool { med.isLow == true }
    private var ageLabel: String {
        switch med.ageGroup {
        case "child": return "👶 Kids"
        case "adult": return "🧑 Adult"
        default:      return "👪 All"
        }
    }
    private var qtyText: String {
        guard let q = med.quantity else { return "" }
        let intPart = Int(q)
        let unit = (med.unit ?? "count") != "count" ? " \(med.unit ?? "")" : ""
        return "×\(intPart)\(unit)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Text(ageLabel)
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                if isExpired {
                    statusChip(label: "Expired", color: DesignTokens.error, dim: DesignTokens.errorDim)
                } else if isLow {
                    statusChip(label: "Low", color: DesignTokens.warning, dim: DesignTokens.warningDim)
                }
                Spacer()
                if !qtyText.isEmpty {
                    Text(qtyText)
                        .font(.appCaption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
            }
            Text(med.name + (med.strength.map { " · \($0)" } ?? ""))
                .font(.appCallout.weight(.semibold))
                .foregroundStyle(DesignTokens.label)
                .lineLimit(2)
            VStack(alignment: .leading, spacing: 2) {
                if let exp = med.expiryDate {
                    Text("🍂 Exp: \(exp)")
                        .font(.appCaption1)
                        .foregroundStyle(isExpired ? DesignTokens.error : DesignTokens.tertiaryLabel)
                }
                if let label = state.memberLabel(for: med) {
                    Text(label).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                }
                if let warnings = med.aiWarnings, let first = warnings.first {
                    Text("⚠️ \(first)")
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.warning)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }
            HStack(spacing: 4) {
                iconButton(systemName: "pencil", tint: DesignTokens.accent, help: "Edit") {
                    state.openEdit(med)
                }
                if med.status == "active" {
                    iconButton(systemName: "checkmark.circle.fill", tint: DesignTokens.success, help: "Mark finished") {
                        Task { await state.markDone(med) }
                    }
                }
                Spacer()
                iconButton(systemName: "trash", tint: DesignTokens.error, help: "Delete") {
                    Task { await state.delete(med) }
                }
            }
            .contextMenu {
                Button("Edit") { state.openEdit(med) }
                if med.status == "active" {
                    Button("Mark finished") { Task { await state.markDone(med) } }
                }
                Divider()
                Button("Delete", role: .destructive) { Task { await state.delete(med) } }
            }
        }
        .padding(10)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .stroke(borderColor, lineWidth: 0.5)
        )
    }

    private var borderColor: Color {
        if isExpired { return DesignTokens.error.opacity(0.5) }
        if isLow     { return DesignTokens.warning.opacity(0.4) }
        return DesignTokens.border
    }

    private func statusChip(label: String, color: Color, dim: Color) -> some View {
        Text(label)
            .font(.appCaption2.weight(.semibold))
            .padding(.horizontal, 5).padding(.vertical, 1)
            .background(dim)
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    private func iconButton(
        systemName: String,
        tint: Color,
        help: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 13, weight: .medium))
                .frame(width: 28, height: 24)
                .foregroundStyle(tint)
                .background(DesignTokens.surface2)
                .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .buttonStyle(.plain)
        .help(help)
    }
}

// MARK: - F-1618..F-1634 add/edit sheet

private struct MedicationEditSheet: View {
    @ObservedObject var state: MedicationsState
    @ObservedObject var draft: MedicationEditState

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
                HStack {
                    Text(draft.existing == nil ? "Add Medication" : "Edit Medication")
                        .font(.appTitle3)
                    Spacer()
                    Button {
                        state.closeSheet()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                    .buttonStyle(.plain)
                    .keyboardShortcut(.cancelAction)
                }
                if draft.existing == nil {
                    HStack(spacing: 6) {
                        Button {
                            Task { await runBarcodeLookupFromFile() }
                        } label: { Text("📷 Photo") }
                        .buttonStyle(GhostButtonStyle())
                        .help("Pick an image of the barcode (image OCR coming v1.1)")
                        Button {
                            Task { await runBarcodeLookupFromFile() }
                        } label: { Text("🖼 Gallery") }
                        .buttonStyle(GhostButtonStyle())
                        .help("Pick a barcode photo from disk (v1.1)")
                        Button {
                            Task {
                                if let fields = await state.barcodeLookup(name: draft.name, barcode: draft.barcode) {
                                    draft.apply(lookup: fields)
                                }
                            }
                        } label: { Text("🔍 Lookup") }
                        .buttonStyle(GhostButtonStyle())
                        .help("Lookup by name or barcode")
                    }
                }
            }
            .padding(.horizontal, DesignTokens.Spacing.space4)
            .padding(.top, DesignTokens.Spacing.space3)
            .padding(.bottom, DesignTokens.Spacing.space2)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    field(label: "Name *") {
                        TextField("e.g. Ibuprofen", text: $draft.name).textFieldStyle(.roundedBorder)
                    }
                    field(label: "Active Ingredient") {
                        TextField("e.g. Ibuprofen", text: $draft.activeIngredient).textFieldStyle(.roundedBorder)
                    }
                    field(label: "Brand / Manufacturer") {
                        TextField("e.g. Advil", text: $draft.brand).textFieldStyle(.roundedBorder)
                    }
                    field(label: "Strength") {
                        TextField("e.g. 200mg", text: $draft.strength).textFieldStyle(.roundedBorder)
                    }
                    field(label: "Dosage Form") {
                        Picker("", selection: $draft.dosageForm) {
                            ForEach(MedicationOptions.dosageForms, id: \.value) { o in
                                Text(o.label).tag(o.value)
                            }
                        }
                        .pickerStyle(.menu)
                    }
                    field(label: "For") {
                        Picker("", selection: $draft.ageGroup) {
                            ForEach(MedicationOptions.ageGroups, id: \.value) { o in
                                Text(o.label).tag(o.value)
                            }
                        }
                        .pickerStyle(.menu)
                    }
                    field(label: "Belongs To") {
                        Picker("", selection: $draft.memberKey) {
                            Text("🏠 Household (shared)").tag("household")
                            ForEach(draft.members) { person in
                                Text("\(person.emoji) \(person.name)").tag(person.chipKey)
                            }
                        }
                        .pickerStyle(.menu)
                    }
                    HStack(alignment: .bottom, spacing: 8) {
                        field(label: "Quantity") {
                            TextField("e.g. 30", text: $draft.quantityText).textFieldStyle(.roundedBorder)
                        }
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Unit").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                            Picker("", selection: $draft.unit) {
                                ForEach(MedicationOptions.units, id: \.value) { o in
                                    Text(o.label).tag(o.value)
                                }
                            }
                            .pickerStyle(.menu)
                        }
                        .frame(width: 160)
                    }
                    field(label: "Expiry Date") {
                        TextField("YYYY-MM-DD", text: $draft.expiryDate).textFieldStyle(.roundedBorder)
                    }
                    field(label: "Manufacture Date (optional)") {
                        TextField("YYYY-MM-DD", text: $draft.manufactureDate).textFieldStyle(.roundedBorder)
                    }
                    field(label: "Barcode (optional)") {
                        TextField("UPC/NDC", text: $draft.barcode).textFieldStyle(.roundedBorder)
                    }
                    field(label: "Notes (optional)") {
                        TextField("e.g. Take with food", text: $draft.notes).textFieldStyle(.roundedBorder)
                    }
                }
                .padding(DesignTokens.Spacing.space4)
            }

            Divider()
            HStack {
                Spacer()
                Button("Cancel") { state.closeSheet() }
                    .buttonStyle(GhostButtonStyle())
                    .keyboardShortcut(.cancelAction)
                Button(draft.existing == nil ? "Add" : "Save") {
                    Task {
                        let ok = await state.save(draft)
                        if ok { state.closeSheet() }
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .keyboardShortcut(.defaultAction)
                .disabled(draft.name.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(DesignTokens.Spacing.space3)
        }
        .frame(minWidth: 460, idealWidth: 520, minHeight: 560, idealHeight: 640)
    }

    private func field<Content: View>(label: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
            content()
        }
    }

    /// F-1631/F-1632 — web reads a barcode from a chosen image via Html5Qrcode
    /// then POSTs the text barcode. Mac has no in-process decoder for v1.0, so
    /// surface a clear v1.1 toast and direct the user to manual entry + Lookup.
    private func runBarcodeLookupFromFile() async {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.jpeg, .png, .heic, .heif, .image]
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, panel.url != nil {
            ToastQueue.shared.push(Toast(
                message: "Photo barcode decode coming v1.1 — type the barcode below and tap Lookup.",
                severity: .info
            ))
        }
    }
}

// MARK: - F-1635 / F-1636 / F-1637 Members sheet (read-only on mac)

private struct MembersSheet: View {
    @ObservedObject var state: MedicationsState

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            HStack {
                Text("Household Members").font(.appTitle3)
                Spacer()
                Button {
                    state.membersSheetOpen = false
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.cancelAction)
            }
            Text("Roster fetched from `/auth/household-members`. Adding or deleting members is not yet exposed by the backend — manage household users via Settings.")
                .font(.appCaption1)
                .foregroundStyle(DesignTokens.tertiaryLabel)
            if state.members.isEmpty {
                EmptyStateView(systemImage: "person.2", title: "No members yet.")
                    .frame(height: 140)
            } else {
                ScrollView {
                    VStack(spacing: 6) {
                        ForEach(state.members) { m in
                            HStack(spacing: 8) {
                                Text(m.emoji).font(.appHeadline)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(m.name).font(.appCallout.weight(.medium))
                                    Text((m.role ?? "member").capitalized + (m.isSelf == true ? " · You" : ""))
                                        .font(.appCaption2)
                                        .foregroundStyle(DesignTokens.tertiaryLabel)
                                }
                                Spacer()
                            }
                            .padding(10)
                            .background(DesignTokens.surface2)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                        }
                    }
                }
            }
            HStack {
                Spacer()
                Button("Done") { state.membersSheetOpen = false }
                    .buttonStyle(PrimaryButtonStyle())
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 400, idealWidth: 460, minHeight: 320, idealHeight: 420)
    }
}

#Preview("MedicationsView") {
    MedicationsView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 900, height: 720)
}
