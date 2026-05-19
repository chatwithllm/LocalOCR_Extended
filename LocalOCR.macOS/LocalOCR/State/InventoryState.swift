import Foundation
import os.log

/// Inventory state — backs every F-row on Inventory screen.
///
/// Concurrency rules (Rules 3, 6, 7):
///   - All API methods are `async` and routed through `APIClient.request`.
///   - View must call `loadInventory()` via `.onAppear { Task.detached { await ... } }` —
///     not `.task { ... }` (I-7).
///   - Bulk operations fan out with `withTaskGroup` to avoid the `async let _ =` trap (I-6).
@MainActor
final class InventoryState: ObservableObject {

    static let shared = InventoryState()

    // MARK: - Live data

    @Published private(set) var items: [InventoryItem] = []
    @Published private(set) var recentlyUsedUp: [RecentlyUsedUpItem] = []
    @Published private(set) var windowLabel: String?
    @Published private(set) var windowStart: String?
    @Published private(set) var isLoading = false
    @Published private(set) var isLoadingRecentlyUsedUp = false
    @Published var lastError: String?

    // MARK: - View preferences (persisted to UserDefaults)

    @Published var addCardCollapsed: Bool {
        didSet { defaults.set(addCardCollapsed, forKey: Keys.addCollapsed) }
    }
    @Published var addCardDetailsExpanded: Bool {
        didSet { defaults.set(addCardDetailsExpanded, forKey: Keys.addDetails) }
    }
    @Published var restoreSectionVisible: Bool = false

    @Published var searchText: String = ""
    @Published var locationFilter: String? = nil
    @Published var groupBy: GroupBy {
        didSet { defaults.set(groupBy.rawValue, forKey: Keys.groupBy) }
    }
    @Published var sortBy: SortBy {
        didSet { defaults.set(sortBy.rawValue, forKey: Keys.sortBy) }
    }
    @Published var showEmpty: Bool {
        didSet { defaults.set(showEmpty, forKey: Keys.showEmpty) }
    }
    @Published var lowStockOnly: Bool = false
    @Published var categoryFilter: String? = nil

    @Published var selectedItemIds: Set<Int> = []

    // MARK: - Internals

    private let api: APIClient
    private let defaults: UserDefaults
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "inventory")

    enum GroupBy: String, CaseIterable, Identifiable {
        case lowFirst = "low_first"
        case domain
        case location
        var id: String { rawValue }
        var label: String {
            switch self {
            case .lowFirst: return "Running low first"
            case .domain:   return "Domain"
            case .location: return "Location"
            }
        }
    }

    enum SortBy: String, CaseIterable, Identifiable {
        case expiryAsc = "expiry_asc"
        case name
        case quantity
        var id: String { rawValue }
        var label: String {
            switch self {
            case .expiryAsc: return "Expiry (soonest)"
            case .name:      return "Name"
            case .quantity:  return "Quantity"
            }
        }
    }

    private enum Keys {
        static let addCollapsed = "LocalOCR.inventory.addCollapsed"
        static let addDetails   = "LocalOCR.inventory.addDetails"
        static let groupBy      = "LocalOCR.inventory.groupBy"
        static let sortBy       = "LocalOCR.inventory.sortBy"
        static let showEmpty    = "LocalOCR.inventory.showEmpty"
    }

    init(api: APIClient = .shared, defaults: UserDefaults = .standard) {
        self.api = api
        self.defaults = defaults
        self.addCardCollapsed = defaults.object(forKey: Keys.addCollapsed) as? Bool ?? true
        self.addCardDetailsExpanded = defaults.bool(forKey: Keys.addDetails)
        self.groupBy = GroupBy(rawValue: defaults.string(forKey: Keys.groupBy) ?? "") ?? .lowFirst
        self.sortBy  = SortBy(rawValue: defaults.string(forKey: Keys.sortBy) ?? "") ?? .expiryAsc
        self.showEmpty = defaults.bool(forKey: Keys.showEmpty)
    }

    // MARK: - Derived

    var categories: [String] {
        Array(Set(items.compactMap { $0.category })).sorted()
    }

    var lowStockItems: [InventoryItem] {
        items.filter { $0.isLowStock }
    }

    var lowStockCount: Int { lowStockItems.count }

    // MARK: - Loads

    /// GET /inventory — list of all inventory rows in the active window.
    func loadInventory() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let endpoint = InventoryEndpoint.list(location: nil, lowStockOnly: false)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: InventoryListResponse.self
            )
            items = response.inventory
            windowStart = response.windowStart
            windowLabel = response.windowLabel
            AppState.shared.setLowStockCount(lowStockItems.count)
            logger.info("loaded \(self.items.count) inventory rows; window=\(self.windowStart ?? "nil", privacy: .public)")
        } catch is CancellationError {
            return
        } catch {
            if (error as NSError).domain == NSURLErrorDomain,
               (error as NSError).code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
            logger.error("loadInventory failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    /// GET /inventory/recently-used-up?days=30
    func loadRecentlyUsedUp(days: Int = 30) async {
        isLoadingRecentlyUsedUp = true
        defer { isLoadingRecentlyUsedUp = false }
        do {
            let endpoint = InventoryEndpoint.recentlyUsedUp(days: days)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: RecentlyUsedUpResponse.self
            )
            recentlyUsedUp = response.items
            logger.info("loaded \(self.recentlyUsedUp.count) recently-used-up entries")
        } catch is CancellationError {
            return
        } catch {
            if (error as NSError).domain == NSURLErrorDomain,
               (error as NSError).code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
            logger.error("loadRecentlyUsedUp failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - Mutations

    /// POST /inventory/add-item
    func addItem(productName: String,
                 quantity: Double,
                 location: String,
                 threshold: Double?,
                 category: String?,
                 size: String?,
                 alsoAddToShopping: Bool) async {
        do {
            try DemoModeGate.guardMutation()
            let body = InventoryAddBody(
                productName: productName,
                quantity: quantity,
                location: location,
                threshold: threshold,
                category: category,
                size: size
            )
            _ = try await api.request(
                .post,
                path: InventoryEndpoint.addItem.path,
                jsonBody: body,
                as: InventoryAddResponse.self
            )
            if alsoAddToShopping {
                await ShoppingState.shared.add(
                    productName: productName,
                    quantity: quantity,
                    source: "manual",
                    productId: nil
                )
            }
            await loadInventory()
            ToastQueue.shared.push(Toast(message: "Added \"\(productName)\" to inventory", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
            ToastQueue.shared.push(Toast(message: lastError ?? "Could not add item", severity: .error))
        }
    }

    /// PUT /inventory/<id>/consume — decrement by `amount` (default 1).
    func consume(itemId: Int, amount: Double = 1) async {
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .put,
                path: InventoryEndpoint.consume(itemId: itemId).path,
                jsonBody: ConsumeBody(amount: amount),
                as: InventoryConsumeResponse.self
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// PUT /inventory/<id>/update — set quantity/location/threshold directly.
    func updateItem(itemId: Int,
                    quantity: Double? = nil,
                    location: String? = nil,
                    threshold: Double? = nil) async {
        do {
            try DemoModeGate.guardMutation()
            let body = InventoryUpdateBody(
                quantity: quantity,
                location: location,
                threshold: threshold,
                consumedPctOverride: nil
            )
            _ = try await api.request(
                .put,
                path: InventoryEndpoint.updateItem(itemId: itemId).path,
                jsonBody: body,
                as: InventoryUpdateResponse.self
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// DELETE /inventory/<id> — remove an inventory row entirely.
    func deleteItem(itemId: Int) async {
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .delete,
                path: InventoryEndpoint.delete(itemId: itemId).path,
                as: InventoryDeleteResponse.self
            )
            items.removeAll { $0.id == itemId }
            selectedItemIds.remove(itemId)
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// PUT /inventory/products/<id>/low-status
    func markLow(productId: Int, manualLow: Bool = true) async {
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .put,
                path: InventoryEndpoint.markLow(productId: productId).path,
                jsonBody: MarkLowBody(manualLow: manualLow),
                as: InventoryLowStatusResponse.self
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// POST /inventory/products/<id>/confirm-low
    func confirmLow(productId: Int) async {
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .post,
                path: InventoryEndpoint.confirmLow(productId: productId).path,
                as: InventoryConfirmLowResponse.self
            )
            await loadInventory()
            ToastQueue.shared.push(Toast(message: "Low-stock call confirmed", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// PUT /inventory/products/<id>/regular-use
    /// (Web app calls /products/<id>/regular-use — that path doesn't exist on the
    /// server; the only registered route is under the inventory blueprint.)
    func toggleRegularUse(productId: Int, isRegular: Bool) async {
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .put,
                path: InventoryEndpoint.regularUse(productId: productId).path,
                jsonBody: RegularUseBody(isRegularUse: isRegular),
                as: InventoryRegularUseResponse.self
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// PATCH /inventory/products/<id> — generic product-level patch.
    /// Pass `quantity: 0` to mark used-up (backend deletes the row).
    func patch(productId: Int, body: InventoryPatchBody) async {
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .patch,
                path: InventoryEndpoint.patchProduct(productId: productId).path,
                jsonBody: body,
                as: InventoryPatchResponse.self
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// PUT /inventory/<id>/update { consumed_pct_override: 100 - remainingPct }
    /// — backs the draggable RemainingSlider (F-156) and tap-cycle (F-159).
    /// `remainingPct` is what the user just set in the UI (0...100); the
    /// backend stores its inverse as the consumed override.
    func setRemainingOverride(itemId: Int, remainingPct: Double) async {
        let clamped = max(0, min(100, remainingPct))
        let consumed = 100 - clamped
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .put,
                path: InventoryEndpoint.updateItem(itemId: itemId).path,
                jsonBody: InventoryUpdateBody(
                    quantity: nil, location: nil, threshold: nil,
                    consumedPctOverride: consumed
                ),
                as: InventoryUpdateResponse.self
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// Tap-cycle the row's status (F-159). Mirrors web's `_invCycleStatus`:
    /// fresh → low → out → fresh, with remaining-pct buckets 80 / 40 / 10.
    func cycleStatus(itemId: Int, currentStatus: String?) async {
        let order = ["fresh", "low", "out"]
        let bucket: [String: Double] = ["fresh": 80, "low": 40, "out": 10]
        let curIdx = order.firstIndex(of: currentStatus ?? "fresh") ?? 0
        let next = order[(curIdx + 1) % order.count]
        await setRemainingOverride(itemId: itemId, remainingPct: bucket[next] ?? 80)
    }

    /// Per-row `−1` (F-160). PATCH /inventory/products/<pid> { quantity: q-1 }.
    /// Mirrors web's `invDecrement`: optimistic local update, then server PATCH.
    /// Quantity floors at 0; reaching 0 makes the backend delete the row.
    func decrementOne(productId: Int) async {
        let cur = items.first(where: { $0.productId == productId })?.quantity ?? 0
        let next = max(0, cur - 1)
        await patch(productId: productId, body: InventoryPatchBody(
            displayName: nil, unit: nil, sizeLabel: nil,
            quantity: next, location: nil, threshold: nil,
            expiresAt: nil, deferDays: nil
        ))
    }

    /// Per-row `✓` used-up (F-155 used-up path). PATCH `{ quantity: 0 }` — backend
    /// deletes the inventory row and preserves an audit trail.
    func markUsedUp(productId: Int) async {
        await patch(productId: productId, body: InventoryPatchBody(
            displayName: nil, unit: nil, sizeLabel: nil,
            quantity: 0, location: nil, threshold: nil,
            expiresAt: nil, deferDays: nil
        ))
    }

    /// Per-row `✓` clear-low path (F-155). When the row is `manual_low`, clear the
    /// flag via /low-status. When it's threshold-low, zero the threshold via the
    /// per-row PUT /inventory/<id>/update endpoint — backend's `apply_manual_patch`
    /// (PATCH /products) ignores threshold entirely, so we must hit the item-level
    /// route which handles `threshold` at manage_inventory.py:388-389. A threshold
    /// of 0 is falsy in `(item.threshold and qty < threshold)` → effectively cleared.
    func clearLow(item: InventoryItem) async {
        var jobs: [@Sendable () async -> Void] = []
        if item.manualLow == true {
            jobs.append { [weak self] in await self?.markLow(productId: item.productId, manualLow: false) }
        }
        if item.manualLow != true, item.threshold != nil {
            let itemId = item.id
            jobs.append { [weak self] in
                await self?.updateItem(itemId: itemId, threshold: 0)
            }
        }
        await withTaskGroup(of: Void.self) { group in
            for job in jobs { group.addTask { await job() } }
        }
    }

    /// Per-row defer — PATCH /inventory/products/<pid> { defer_days: N }.
    /// Same backend path the bulk action uses, but for a single row (F-146).
    func deferExpiry(productId: Int, days: Int) async {
        await patch(productId: productId, body: InventoryPatchBody(
            displayName: nil, unit: nil, sizeLabel: nil,
            quantity: nil, location: nil, threshold: nil,
            expiresAt: nil, deferDays: days
        ))
    }

    /// Count of items in `rows` that are expired or expiring within 3 days
    /// (matches web's `_invClassifyExpiry` threshold — F-147 group header).
    static func expiringSoonCount(_ rows: [InventoryItem]) -> Int {
        rows.filter { item in
            guard let days = item.daysLeft else { return false }
            return days <= 3
        }.count
    }

    /// DELETE /inventory/products/<id>/expiry-override
    func clearExpiryOverride(productId: Int) async {
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .delete,
                path: InventoryEndpoint.deleteExpiryOverride(productId: productId).path,
                as: InventoryPatchResponse.self
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    /// POST /inventory/products/<id>/restore — bring a used-up product back into inventory.
    func restore(productId: Int, quantity: Double? = nil) async {
        do {
            try DemoModeGate.guardMutation()
            _ = try await api.request(
                .post,
                path: InventoryEndpoint.restore(productId: productId).path,
                jsonBody: InventoryRestoreBody(quantity: quantity),
                as: InventoryPatchResponse.self
            )
            await loadInventory()
            await loadRecentlyUsedUp()
            ToastQueue.shared.push(Toast(message: "Item restored to inventory", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    // MARK: - Selection / bulk (F-124..F-130)

    func toggleSelection(_ itemId: Int) {
        if selectedItemIds.contains(itemId) { selectedItemIds.remove(itemId) }
        else { selectedItemIds.insert(itemId) }
    }

    func clearSelection() {
        selectedItemIds.removeAll()
    }

    /// Bulk decrement by 1 on every selected item — parallel fan-out via withTaskGroup
    /// (RULE 3: never `async let _ =`).
    func bulkDecrement() async {
        let ids = Array(selectedItemIds)
        guard !ids.isEmpty else { return }
        await withTaskGroup(of: Void.self) { group in
            for id in ids {
                group.addTask { @MainActor in await self.consume(itemId: id, amount: 1) }
            }
        }
        clearSelection()
        ToastQueue.shared.push(Toast(message: "−1 applied to \(ids.count) items", severity: .success))
    }

    /// Bulk defer expiry by N days — uses PATCH /inventory/products/<pid> { defer_days: N }.
    func bulkDefer(days: Int) async {
        let ids = Array(selectedItemIds)
        guard !ids.isEmpty else { return }
        let productIds = items.filter { ids.contains($0.id) }.map(\.productId)
        await withTaskGroup(of: Void.self) { group in
            for pid in productIds {
                group.addTask { @MainActor in
                    await self.patch(productId: pid, body: InventoryPatchBody(
                        displayName: nil, unit: nil, sizeLabel: nil,
                        quantity: nil, location: nil, threshold: nil,
                        expiresAt: nil, deferDays: days
                    ))
                }
            }
        }
        clearSelection()
        ToastQueue.shared.push(Toast(message: "+\(days)d applied to \(productIds.count) items", severity: .success))
    }

    /// Bulk mark used-up — PATCH /inventory/products/<pid> { quantity: 0 } per row.
    func bulkUsedUp() async {
        let ids = Array(selectedItemIds)
        guard !ids.isEmpty else { return }
        let productIds = items.filter { ids.contains($0.id) }.map(\.productId)
        await withTaskGroup(of: Void.self) { group in
            for pid in productIds {
                group.addTask { @MainActor in
                    await self.patch(productId: pid, body: InventoryPatchBody(
                        displayName: nil, unit: nil, sizeLabel: nil,
                        quantity: 0, location: nil, threshold: nil,
                        expiresAt: nil, deferDays: nil
                    ))
                }
            }
        }
        clearSelection()
        ToastQueue.shared.push(Toast(message: "Marked \(productIds.count) items used up", severity: .success))
    }

    // MARK: - Filtering / grouping (F-116..F-119, F-123)

    /// Apply search/location/category/low/show-empty filters then sort.
    var filteredItems: [InventoryItem] {
        var rows = items

        if !showEmpty {
            rows = rows.filter { $0.quantity > 0 }
        }
        if lowStockOnly {
            rows = rows.filter(\.isLowStock)
        }
        if let location = locationFilter, !location.isEmpty {
            rows = rows.filter { ($0.location ?? "").caseInsensitiveCompare(location) == .orderedSame }
        }
        if let category = categoryFilter, !category.isEmpty {
            rows = rows.filter { ($0.category ?? "").caseInsensitiveCompare(category) == .orderedSame }
        }
        if !searchText.isEmpty {
            rows = rows.filter { $0.displayName.localizedCaseInsensitiveContains(searchText) }
        }

        switch sortBy {
        case .expiryAsc:
            rows.sort { (a, b) in
                switch (a.daysLeft, b.daysLeft) {
                case (let x?, let y?): return x < y
                case (_?, nil):        return true
                case (nil, _?):        return false
                default:               return a.displayName < b.displayName
                }
            }
        case .name:
            rows.sort { $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
        case .quantity:
            rows.sort { $0.quantity < $1.quantity }
        }
        return rows
    }

    /// Items grouped by the current `groupBy` selection.
    /// Returns ordered (header, rows) pairs.
    func groupedItems() -> [(String, [InventoryItem])] {
        let rows = filteredItems
        switch groupBy {
        case .lowFirst:
            let low = rows.filter(\.isLowStock)
            let ok  = rows.filter { !$0.isLowStock }
            var groups: [(String, [InventoryItem])] = []
            if !low.isEmpty { groups.append(("Running low", low)) }
            if !ok.isEmpty  { groups.append(("Well stocked", ok)) }
            return groups
        case .domain:
            let domains = Dictionary(grouping: rows) { ($0.category?.capitalized ?? "Other") }
            return domains.keys.sorted().map { ($0, domains[$0] ?? []) }
        case .location:
            let locs = Dictionary(grouping: rows) { ($0.location ?? "Pantry") }
            return locs.keys.sorted().map { ($0, locs[$0] ?? []) }
        }
    }
}
