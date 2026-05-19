import Foundation
import SwiftUI
import os.log

/// Owns the Shopping List screen state — items, current session, sort/filter,
/// past trips, and all mutation flows. Mirrors web `loadShoppingList()` +
/// `renderShoppingListTable()` semantics from src/frontend/index.html.
///
/// Concurrency follows RULE 3:
///   - parallel fan-outs use `withTaskGroup`
///   - heavy fetches are kicked off from `.onAppear { Task.detached { ... } }`
@MainActor
final class ShoppingState: ObservableObject {

    static let shared = ShoppingState()

    // MARK: - List payload

    @Published private(set) var items: [ShoppingListItem] = []
    @Published private(set) var openCount: Int = 0
    @Published private(set) var purchasedCount: Int = 0
    @Published private(set) var estimatedTotalCost: Double = 0
    @Published private(set) var boughtEstimatedTotal: Double = 0
    @Published private(set) var actualTotal: Double = 0
    @Published private(set) var variance: Double = 0
    @Published private(set) var actualsEnteredCount: Int = 0
    @Published private(set) var suggestedStores: [SuggestedStore] = []
    @Published private(set) var availableStores: [String] = []
    @Published private(set) var storeBuckets: AvailableStoreBuckets = .init(frequent: [], lowFreq: [])
    @Published private(set) var session: ShoppingSession?

    // MARK: - View state

    @Published var listFilter: ShoppingListFilter = .open
    @Published var sortMode: ShoppingSort = .nameAsc
    @Published var searchQuery: String = ""
    @Published var quickFindQuery: String = ""
    @Published var quickFindStoreFilter: String = ""
    @Published var quickFindResults: [Product] = []
    @Published var recommendations: [Recommendation] = []
    @Published var pastTrips: [ShoppingPastTrip] = []
    @Published var pastTripDetails: [Int: ShoppingSessionDetailResponse] = [:]
    @Published var expandedTripIds: Set<Int> = []

    // Collapsible cards (persisted to UserDefaults).
    @Published var quickFindCollapsed: Bool = UserDefaults.standard.bool(forKey: Defaults.quickFindCollapsed)
    @Published var recommendationsCollapsed: Bool = UserDefaults.standard.bool(forKey: Defaults.recsCollapsed)
    @Published var currentListCollapsed: Bool = UserDefaults.standard.bool(forKey: Defaults.currentListCollapsed)
    @Published var pastTripsCollapsed: Bool = true
    @Published var manualAddVisible: Bool = false
    @Published var storeGroupCollapsed: [String: Bool] = [:]

    @Published private(set) var isLoading = false
    @Published private(set) var isLoadingPastTrips = false
    @Published var lastError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "shopping")

    private enum Defaults {
        static let quickFindCollapsed   = "LocalOCR.shopping.quickFindCollapsed"
        static let recsCollapsed        = "LocalOCR.shopping.recsCollapsed"
        static let currentListCollapsed = "LocalOCR.shopping.currentListCollapsed"
        static let sortMode             = "LocalOCR.shopping.sortMode"
        static let storeGroupCollapsed  = "LocalOCR.shopping.storeGroupCollapsed"
    }

    init(api: APIClient = .shared) {
        self.api = api
        if let raw = UserDefaults.standard.string(forKey: Defaults.sortMode),
           let mode = ShoppingSort(rawValue: raw) {
            self.sortMode = mode
        }
        if let raw = UserDefaults.standard.dictionary(forKey: Defaults.storeGroupCollapsed) as? [String: Bool] {
            self.storeGroupCollapsed = raw
        }
    }

    var pendingCount: Int { openCount }

    /// Back-compat alias for the dashboard + inventory views that referenced the
    /// old single-field total. Same value as `estimatedTotalCost` (open items only).
    var estimatedTotal: Double { estimatedTotalCost }

    /// Back-compat shim — pre-Shopping-parity callers still use this signature.
    /// New code should call `addItem(...)` directly.
    @discardableResult
    func add(productName: String, quantity: Double, source: String? = "manual", productId: Int? = nil) async -> Bool {
        await addItem(
            name: productName,
            quantity: quantity,
            productId: productId,
            source: source ?? "manual"
        )
    }

    // MARK: - Load

    /// Full reload — sends one GET. Single source of truth for items, session,
    /// counts, and store buckets. Web web calls this any time mutations happen.
    func loadList() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await api.request(
                .get,
                path: ShoppingEndpoint.list(statusFilter: nil).path,
                query: ShoppingEndpoint.list(statusFilter: nil).query,
                as: ShoppingListResponse.self
            )
            apply(response)
            logger.info("loaded \(response.items.count, privacy: .public) shopping items, session=\(response.session?.status ?? "-", privacy: .public)")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadList failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func apply(_ response: ShoppingListResponse) {
        items = response.items
        openCount = response.openCount ?? items.filter(\.isPending).count
        purchasedCount = response.purchasedCount ?? items.filter(\.isPurchased).count
        estimatedTotalCost = response.estimatedTotalCost ?? 0
        boughtEstimatedTotal = response.boughtEstimatedTotal ?? 0
        actualTotal = response.actualTotal ?? 0
        variance = response.variance ?? 0
        actualsEnteredCount = response.actualsEnteredCount ?? 0
        suggestedStores = response.suggestedStores ?? []
        availableStores = response.availableStores ?? []
        storeBuckets = response.availableStoreBuckets ?? AvailableStoreBuckets(frequent: [], lowFreq: [])
        session = response.session
    }

    // MARK: - F-204 / F-206 view filter

    func setFilter(_ filter: ShoppingListFilter) {
        listFilter = filter
    }

    // MARK: - F-235..F-237 sort

    func setSort(_ sort: ShoppingSort) {
        sortMode = sort
        UserDefaults.standard.set(sort.rawValue, forKey: Defaults.sortMode)
    }

    /// F-237 — tap on the $ chip toggles between price_desc and price_asc.
    func togglePriceSort() {
        setSort(sortMode == .priceDesc ? .priceAsc : .priceDesc)
    }

    // MARK: - F-201 / F-227 / F-233 / F-253 collapse toggles

    func toggleQuickFind() {
        quickFindCollapsed.toggle()
        UserDefaults.standard.set(quickFindCollapsed, forKey: Defaults.quickFindCollapsed)
    }
    func toggleRecommendations() {
        recommendationsCollapsed.toggle()
        UserDefaults.standard.set(recommendationsCollapsed, forKey: Defaults.recsCollapsed)
    }
    func toggleCurrentList() {
        currentListCollapsed.toggle()
        UserDefaults.standard.set(currentListCollapsed, forKey: Defaults.currentListCollapsed)
    }
    func togglePastTrips() {
        pastTripsCollapsed.toggle()
        if !pastTripsCollapsed { Task { await loadPastTrips() } }
    }
    func toggleManualAdd() { manualAddVisible.toggle() }

    /// F-264 store group header (per (sectionKey, storeName) — sectionKey omitted
    /// here because mac uses one section at a time).
    func toggleStoreGroup(_ storeName: String) {
        let key = storeName
        let next = !(storeGroupCollapsed[key] ?? false)
        storeGroupCollapsed[key] = next
        UserDefaults.standard.set(storeGroupCollapsed, forKey: Defaults.storeGroupCollapsed)
    }
    func isStoreGroupCollapsed(_ storeName: String) -> Bool {
        storeGroupCollapsed[storeName] ?? false
    }

    // MARK: - Derived collections

    /// Items after view-filter + search-query, grouped + sorted like
    /// `renderShoppingListTable()`.
    var filteredItems: [ShoppingListItem] {
        let base = items.filter { item in
            switch listFilter {
            case .open:      return item.status != "purchased" && item.status != "skipped"
            case .purchased: return item.isPurchased
            case .all:       return true
            }
        }
        let q = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return base }
        return base.filter { item in
            for candidate in [item.name, item.category ?? "", item.source ?? "",
                              item.note ?? "", item.latestPrice?.store ?? ""] {
                if candidate.lowercased().contains(q) { return true }
            }
            return false
        }
    }

    /// Items whose status is "skipped" — surfaced in a dedicated <details>
    /// at the end of the list per web behavior.
    var skippedItems: [ShoppingListItem] { items.filter(\.isSkipped) }

    /// Groups by group key (preferred_store > effective_store > Unassigned),
    /// each sorted per `sortMode`.
    func groupedFilteredItems() -> [(store: String, items: [ShoppingListItem])] {
        let grouped = Dictionary(grouping: filteredItems, by: \.groupKey)
        let groups: [(String, [ShoppingListItem])] = grouped.map { ($0.key, sortItems($0.value)) }
        return sortGroups(groups)
    }

    private func sortItems(_ list: [ShoppingListItem]) -> [ShoppingListItem] {
        let sorted = list.sorted { lhs, rhs in
            switch sortMode {
            case .nameAsc:
                return lhs.productName.lowercased() < rhs.productName.lowercased()
            case .nameDesc:
                return lhs.productName.lowercased() > rhs.productName.lowercased()
            case .priceAsc:
                let l = lhs.estimateLineTotal ?? 0
                let r = rhs.estimateLineTotal ?? 0
                if l == r { return lhs.productName.lowercased() < rhs.productName.lowercased() }
                return l < r
            case .priceDesc:
                let l = lhs.estimateLineTotal ?? 0
                let r = rhs.estimateLineTotal ?? 0
                if l == r { return lhs.productName.lowercased() < rhs.productName.lowercased() }
                return l > r
            }
        }
        return sorted
    }

    private func sortGroups(_ groups: [(String, [ShoppingListItem])]) -> [(store: String, items: [ShoppingListItem])] {
        let totals: (String, [ShoppingListItem]) -> Double = { _, items in
            items.reduce(0) { $0 + ($1.estimateLineTotal ?? 0) }
        }
        let mapped: [(String, [ShoppingListItem])]
        switch sortMode {
        case .priceDesc:
            mapped = groups.sorted { totals($0.0, $0.1) > totals($1.0, $1.1) }
        case .priceAsc:
            mapped = groups.sorted { totals($0.0, $0.1) < totals($1.0, $1.1) }
        default:
            mapped = groups.sorted { $0.0.localizedCaseInsensitiveCompare($1.0) == .orderedAscending }
        }
        return mapped.map { (store: $0.0, items: $0.1) }
    }

    // MARK: - F-219 manual add / F-311 product-tap add (kitchen reuses)

    /// POST /shopping-list/items.
    /// Returns true on success so view callers can clear inputs.
    @discardableResult
    func addItem(
        name: String,
        quantity: Double,
        category: String? = nil,
        unit: String? = nil,
        sizeLabel: String? = nil,
        note: String? = nil,
        preferredStore: String? = nil,
        manualEstimatedPrice: Double? = nil,
        productId: Int? = nil,
        source: String = "manual",
        snapshotId: Int? = nil
    ) async -> Bool {
        do {
            try DemoModeGate.guardMutation()
            let body = ShoppingAddBody(
                name: name,
                quantity: quantity,
                source: source,
                productId: productId,
                category: category,
                unit: unit,
                sizeLabel: sizeLabel,
                note: note,
                preferredStore: preferredStore,
                manualEstimatedPrice: manualEstimatedPrice,
                snapshotId: snapshotId
            )
            try await api.request(.post, path: ShoppingEndpoint.addItem.path, jsonBody: body)
            await loadList()
            ToastQueue.shared.push(Toast(message: "Added \"\(name)\" to shopping list", severity: .success))
            return true
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
            return false
        } catch is CancellationError {
            return false
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("addItem failed: \(error.localizedDescription, privacy: .public)")
            return false
        }
    }

    // MARK: - F-239 / F-240 / F-260 / F-261 status changes

    func toggleStatus(id: Int, nextStatus: String) async {
        await update(id: id, body: ShoppingUpdateBody(
            name: nil, category: nil, quantity: nil, status: nextStatus,
            note: nil, preferredStore: nil, manualEstimatedPrice: nil, actualPrice: nil,
            unit: nil, sizeLabel: nil, persistLatestPrice: nil, priceStore: nil
        ))
    }

    func togglePurchased(id: Int) async {
        guard let item = items.first(where: { $0.id == id }) else { return }
        await toggleStatus(id: id, nextStatus: item.isPurchased ? "open" : "purchased")
    }

    func markOutOfStock(id: Int, currentStatus: String) async {
        let next = currentStatus == "out_of_stock" ? "open" : "out_of_stock"
        await toggleStatus(id: id, nextStatus: next)
    }

    // MARK: - F-241 / F-265 quantity

    func increaseQuantity(id: Int) async {
        guard let item = items.first(where: { $0.id == id }) else { return }
        let next = max(1, item.quantity + 1)
        await update(id: id, body: ShoppingUpdateBody(
            name: nil, category: nil, quantity: next, status: nil,
            note: nil, preferredStore: nil, manualEstimatedPrice: nil, actualPrice: nil,
            unit: nil, sizeLabel: nil, persistLatestPrice: nil, priceStore: nil
        ))
    }

    /// F-265 — −1 button. When current quantity is 1, the row is deleted.
    func decreaseQuantity(id: Int) async {
        guard let item = items.first(where: { $0.id == id }) else { return }
        let next = item.quantity - 1
        if next <= 0 {
            await remove(id: id)
            return
        }
        await update(id: id, body: ShoppingUpdateBody(
            name: nil, category: nil, quantity: next, status: nil,
            note: nil, preferredStore: nil, manualEstimatedPrice: nil, actualPrice: nil,
            unit: nil, sizeLabel: nil, persistLatestPrice: nil, priceStore: nil
        ))
    }

    // MARK: - F-242 note inline edit

    func updateNote(id: Int, note: String?) async {
        await update(id: id, body: ShoppingUpdateBody(
            name: nil, category: nil, quantity: nil, status: nil,
            note: note ?? "", preferredStore: nil, manualEstimatedPrice: nil, actualPrice: nil,
            unit: nil, sizeLabel: nil, persistLatestPrice: nil, priceStore: nil
        ))
    }

    // MARK: - F-243 / F-267 actual price (ready_to_bill)

    func updateActualPrice(id: Int, value: Double?) async {
        await update(id: id, body: ShoppingUpdateBody(
            name: nil, category: nil, quantity: nil, status: nil,
            note: nil, preferredStore: nil, manualEstimatedPrice: nil, actualPrice: value,
            unit: nil, sizeLabel: nil, persistLatestPrice: nil, priceStore: nil
        ))
    }

    // MARK: - F-263 preferred store

    func updatePreferredStore(id: Int, store: String?) async {
        await update(id: id, body: ShoppingUpdateBody(
            name: nil, category: nil, quantity: nil, status: nil,
            note: nil, preferredStore: store ?? "", manualEstimatedPrice: nil, actualPrice: nil,
            unit: nil, sizeLabel: nil, persistLatestPrice: nil, priceStore: nil
        ))
    }

    // MARK: - F-258 unit / size / unit price + Update

    func updateUnitSizePrice(
        id: Int,
        unit: String?,
        sizeLabel: String?,
        unitPrice: Double?,
        priceStore: String?
    ) async {
        await update(id: id, body: ShoppingUpdateBody(
            name: nil, category: nil, quantity: nil, status: nil,
            note: nil, preferredStore: nil,
            manualEstimatedPrice: unitPrice,
            actualPrice: nil,
            unit: unit,
            sizeLabel: sizeLabel,
            persistLatestPrice: unitPrice != nil,
            priceStore: priceStore
        ))
    }

    // MARK: - F-262 rename (item name + product fallback)

    func renameItem(id: Int, newName: String) async {
        await update(id: id, body: ShoppingUpdateBody(
            name: newName, category: nil, quantity: nil, status: nil,
            note: nil, preferredStore: nil, manualEstimatedPrice: nil, actualPrice: nil,
            unit: nil, sizeLabel: nil, persistLatestPrice: nil, priceStore: nil
        ))
    }

    private func update(id: Int, body: ShoppingUpdateBody) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .put,
                path: ShoppingEndpoint.updateItem(id: id).path,
                jsonBody: body
            )
            await loadList()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("update item failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - F-244 delete

    func remove(id: Int) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.delete, path: ShoppingEndpoint.deleteItem(id: id).path)
            items.removeAll { $0.id == id }
            ToastQueue.shared.push(Toast(message: "Item removed", severity: .success))
            await loadList()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("delete item failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - F-249 / F-250 / F-251 session lifecycle

    func markReadyToBill() async {
        do {
            try DemoModeGate.guardMutation()
            let response = try await api.request(
                .post,
                path: ShoppingEndpoint.sessionReadyToBill.path,
                jsonBody: EmptyBody(),
                as: ShoppingSessionWrapper.self
            )
            if let session = response.session { self.session = session }
            ToastQueue.shared.push(Toast(message: "Ready to bill — enter actual prices below 🧾", severity: .success))
            await loadList()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("ready-to-bill failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func reopenSession(sessionId: Int? = nil) async {
        do {
            try DemoModeGate.guardMutation()
            let body = ShoppingReopenBody(sessionId: sessionId)
            try await api.request(
                .post,
                path: ShoppingEndpoint.sessionReopen.path,
                jsonBody: body
            )
            ToastQueue.shared.push(Toast(
                message: sessionId == nil ? "Back to shopping ✅" : "Trip reopened ✅",
                severity: .success
            ))
            await loadList()
            if !pastTripsCollapsed { await loadPastTrips() }
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("reopen failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func finalizeSession() async {
        do {
            try DemoModeGate.guardMutation()
            let response = try await api.request(
                .post,
                path: ShoppingEndpoint.sessionFinalize.path,
                jsonBody: EmptyBody(),
                as: ShoppingSessionFinalizeResponse.self
            )
            let carried = response.carriedOverCount ?? 0
            let msg = carried > 0
                ? "Session finalized ✅ · \(carried) item\(carried == 1 ? "" : "s") carried to your next list"
                : "Session finalized ✅"
            ToastQueue.shared.push(Toast(message: msg, severity: .success))
            await loadList()
            if !pastTripsCollapsed { await loadPastTrips() }
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("finalize failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - F-252..F-256 past trips

    func loadPastTrips() async {
        isLoadingPastTrips = true
        defer { isLoadingPastTrips = false }
        do {
            let response = try await api.request(
                .get,
                path: ShoppingEndpoint.sessionsList(statusFilter: "closed").path,
                query: ShoppingEndpoint.sessionsList(statusFilter: "closed").query,
                as: ShoppingPastTripsResponse.self
            )
            pastTrips = response.sessions
            logger.info("loaded \(response.sessions.count, privacy: .public) past trips")
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadPastTrips failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func togglePastTrip(_ tripId: Int) async {
        if expandedTripIds.contains(tripId) {
            expandedTripIds.remove(tripId)
            return
        }
        expandedTripIds.insert(tripId)
        if pastTripDetails[tripId] != nil { return }
        do {
            let detail = try await api.request(
                .get,
                path: ShoppingEndpoint.sessionDetail(id: tripId).path,
                as: ShoppingSessionDetailResponse.self
            )
            pastTripDetails[tripId] = detail
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadPastTripDetail failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - F-226..F-231 recommendations

    func loadRecommendations() async {
        do {
            let response = try await api.request(
                .get,
                path: DashboardEndpoint.recommendations.path,
                as: RecommendationsResponse.self
            )
            recommendations = response.recommendations
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadRecommendations failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func confirmRecommendation(productId: Int) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .post,
                path: ShoppingEndpoint.confirmRecommendation(productId: productId).path,
                jsonBody: EmptyBody()
            )
            ToastQueue.shared.push(Toast(message: "Recommendation confirmed ✅", severity: .success))
            await loadList()
            await loadRecommendations()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("confirmRecommendation failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - F-222 / F-225 quick find

    /// Search /products/search?q= — returns up to 20 matches.
    /// v1.0: no scored "suggestions on focus" branch (web's pre-query suggestions
    /// require additional product fields not exposed by /products list payload).
    func runQuickFindSearch() async {
        let q = quickFindQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard q.count >= 2 else {
            quickFindResults = []
            return
        }
        do {
            let response = try await api.request(
                .get,
                path: "/products/search",
                query: [.init(name: "q", value: q)],
                as: ProductSearchResponse.self
            )
            quickFindResults = response.results
        } catch is CancellationError {
            return
        } catch {
            quickFindResults = []
            logger.error("quickFind failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func matchingShoppingEntry(productId: Int?, name: String?) -> ShoppingListItem? {
        if let productId, productId > 0 {
            if let byProduct = items.first(where: { $0.productId == productId && $0.isPending }) {
                return byProduct
            }
        }
        if let n = name?.lowercased(), !n.isEmpty {
            return items.first { $0.name.lowercased() == n && $0.isPending }
        }
        return nil
    }
}

// MARK: - Helpers

private struct EmptyBody: Encodable {}

/// `/products/search?q=` → `{query, results, count}`.
struct ProductSearchResponse: Codable, Equatable {
    let query: String?
    let results: [Product]
    let count: Int?
}
