import SwiftUI
import AppKit
import Kingfisher
import os.log

// MARK: - F-300..F-338 — Kitchen screen
//
// Touch-friendly grocery shopping companion. Mirrors web `loadKitchen()`,
// `renderKitchenCatalog()`, `renderKitchenList()`, the item action sheet, the
// long-press context menu, the search popover store filter, and the weather
// widget (Open-Meteo + ipapi.co geo).
//
// Mutations reuse ShoppingState (add/update/delete shopping items, preferred
// store, qty, status) and InventoryState (mark low-stock). The only kitchen-
// specific backend route is GET /api/kitchen/catalog (read-only blueprint).

@MainActor
final class KitchenState: ObservableObject {

    static let shared = KitchenState()

    // MARK: - Catalog payload

    @Published private(set) var frequent: [KitchenTile] = []
    @Published private(set) var categories: [String: [KitchenTile]] = [:]
    @Published private(set) var onListProductIds: Set<Int> = []
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?

    // MARK: - View state

    @Published var activeCategory: String = "frequent"
    @Published var searchQuery: String = ""
    @Published var storeFilter: Set<String> = []
    @Published var searchPopoverOpen: Bool = false

    @Published var catalogCollapsed: Bool {
        didSet { UserDefaults.standard.set(catalogCollapsed, forKey: Defaults.catalogCollapsed) }
    }
    @Published var showNames: Bool {
        didSet { UserDefaults.standard.set(showNames, forKey: Defaults.showNames) }
    }

    // Item action sheet
    @Published var sheetItemId: Int?
    @Published var storePickerOpen: Bool = false
    @Published var presetAction: String?  // "bought" | "low" | "skipped"
    @Published var pendingNoteInput: NoteInputContext?
    @Published var customNoteText: String = ""

    // Variant picker (>1 product per canonical key)
    @Published var variantPicker: [KitchenTile]?

    // Long-press / right-click context menu
    @Published var contextMenu: ContextMenuPayload?

    @Published private(set) var weather: KitchenWeather?

    // MARK: - Internals

    private let api: APIClient
    private let shopping: ShoppingState
    private let inventory: InventoryState
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "kitchen")
    private var weatherTask: Task<Void, Never>?
    private var presetAutoCloseTask: Task<Void, Never>?

    enum Defaults {
        static let catalogCollapsed = "LocalOCR.kitchen.catalogCollapsed"
        static let showNames        = "LocalOCR.kitchen.showNames"
        static let weatherCache     = "LocalOCR.kitchen.weatherCache"
    }

    static let allCategories = ["Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other"]
    static let categoryEmoji: [String: String] = [
        "Produce": "🥬", "Meat": "🥩", "Dairy": "🥛",
        "Bakery": "🍞", "Pantry": "🥫", "Other": "🧴",
    ]

    init(
        api: APIClient = .shared,
        shopping: ShoppingState = .shared,
        inventory: InventoryState = .shared
    ) {
        self.api = api
        self.shopping = shopping
        self.inventory = inventory
        self.catalogCollapsed = UserDefaults.standard.bool(forKey: Defaults.catalogCollapsed)
        self.showNames = UserDefaults.standard.object(forKey: Defaults.showNames) as? Bool ?? true
    }

    // MARK: - F-300 — catalog + list load

    /// Mirrors web `loadKitchen()` — Promise.all([catalog, shopping-list]).
    /// Rule 3: parallel fan-out via `withTaskGroup`.
    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in await self.loadCatalog() }
            group.addTask { @MainActor in await self.shopping.loadList() }
        }
        kickOffWeather()
    }

    private func loadCatalog() async {
        do {
            let response = try await api.request(
                .get,
                path: KitchenEndpoint.catalog.path,
                as: KitchenCatalogResponse.self
            )
            frequent = response.frequent
            categories = response.categories
            onListProductIds = Set(response.onListProductIds)
            let total = response.categories.values.reduce(0) { $0 + $1.count }
            logger.info("loaded \(response.frequent.count, privacy: .public) frequent + \(total, privacy: .public) catalog kitchen tiles")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadCatalog failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - F-301 / F-315 toggles

    func toggleCatalog() { catalogCollapsed.toggle() }
    func toggleNames()   { showNames.toggle() }

    // MARK: - F-303 / F-304 chip + search

    func setActiveCategory(_ key: String) { activeCategory = key }
    func setSearchQuery(_ q: String) {
        searchQuery = q
        if !q.isEmpty && catalogCollapsed { catalogCollapsed = false }
    }

    // MARK: - F-305..F-307 store filter

    func openStorePopover()  { searchPopoverOpen = true }
    func closeStorePopover() { searchPopoverOpen = false }
    func toggleStoreFilter(_ name: String) {
        if storeFilter.contains(name) { storeFilter.remove(name) }
        else { storeFilter.insert(name) }
    }
    func clearStoreFilter() { storeFilter.removeAll() }
    func setStoreFilter(_ names: [String]) { storeFilter = Set(names) }

    // MARK: - Derived collections

    private func allTiles() -> [KitchenTile] {
        var seen = Set<Int>()
        var out: [KitchenTile] = []
        for list in categories.values {
            for tile in list where seen.insert(tile.productId).inserted {
                out.append(tile)
            }
        }
        return out
    }

    /// Available store names ordered by purchase volume — fuels F-307 chip row.
    func availableStores() -> [String] {
        var counts: [String: Int] = [:]
        for tile in allTiles() {
            for store in tile.stores ?? [] {
                counts[store, default: 0] += tile.purchaseCount ?? 0
            }
        }
        return counts.sorted { $0.value > $1.value }.map(\.key)
    }

    /// F-310 — tiles for the active chip with search + store filter, grouped
    /// by canonical key (matches web `_kitchenGroupTiles`).
    func tilesForActiveChip() -> [KitchenTileGroup] {
        let q = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let raw: [KitchenTile]
        if !q.isEmpty {
            raw = allTiles().filter { $0.name.lowercased().contains(q) }
        } else if activeCategory == "frequent" {
            raw = frequent
        } else {
            raw = categories[activeCategory] ?? []
        }
        let filtered = applyStoreFilter(raw)
        return groupByCanonicalKey(filtered)
    }

    private func applyStoreFilter(_ tiles: [KitchenTile]) -> [KitchenTile] {
        guard !storeFilter.isEmpty else { return tiles }
        return tiles.filter { tile in
            guard let stores = tile.stores else { return false }
            return stores.contains(where: storeFilter.contains)
        }
    }

    private func groupByCanonicalKey(_ tiles: [KitchenTile]) -> [KitchenTileGroup] {
        var groups: [String: [KitchenTile]] = [:]
        var order: [String] = []
        for tile in tiles {
            let key = Self.canonicalKey(tile.name).isEmpty
                ? "__\(tile.productId)"
                : Self.canonicalKey(tile.name)
            if groups[key] == nil { order.append(key) }
            groups[key, default: []].append(tile)
        }
        let result: [KitchenTileGroup] = order.compactMap { key in
            guard var variants = groups[key], !variants.isEmpty else { return nil }
            variants.sort { ($0.purchaseCount ?? 0) > ($1.purchaseCount ?? 0) }
            return KitchenTileGroup(primary: variants[0], variants: variants, canonicalKey: key)
        }
        return result.sorted { ($0.primary.purchaseCount ?? 0) > ($1.primary.purchaseCount ?? 0) }
    }

    /// Mirrors `_kitchenCanonicalKey()` in index.html.
    static func canonicalKey(_ name: String) -> String {
        var s = name.lowercased()
        let stripWords = ["organic", "org", "ks", "kirkland", "signature", "natural",
                          "fresh", "raw", "frozen", "pure", "whole", "baby",
                          "mini", "jumbo", "small", "large"]
        for word in stripWords {
            s = s.replacingOccurrences(of: "\\b\(word)\\b", with: "", options: .regularExpression)
        }
        s = s.replacingOccurrences(
            of: "\\b\\d+\\s?(lb|oz|ct|count|pack|pk|gal|gallon|kg|g|ml|l)\\b",
            with: "",
            options: .regularExpression
        )
        s = s.replacingOccurrences(of: "\\b\\d+\\b", with: "", options: .regularExpression)
        s = s.replacingOccurrences(of: "[^a-z\\s]+", with: " ", options: .regularExpression)
        s = s.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
             .trimmingCharacters(in: .whitespaces)
        guard !s.isEmpty else { return "" }
        let parts = s.split(separator: " ").map(String.init)
        var head = parts.last ?? ""
        if head.hasSuffix("ies") {
            head = String(head.dropLast(3)) + "y"
        } else if head.hasSuffix("es") {
            head = String(head.dropLast(2))
        } else if head.hasSuffix("s") {
            head = String(head.dropLast())
        }
        return head
    }

    /// Look up a catalog tile by product id across frequent + categories.
    func catalogTile(forProductId pid: Int) -> KitchenTile? {
        if let hit = frequent.first(where: { $0.productId == pid }) { return hit }
        for list in categories.values {
            if let hit = list.first(where: { $0.productId == pid }) { return hit }
        }
        return nil
    }

    /// Returns sibling variants for the same canonical key — used by context menu
    /// to decide whether to offer "Pick variant".
    func variantCount(forCanonicalKey key: String) -> Int {
        guard !key.isEmpty else { return 1 }
        let raw: [KitchenTile] = activeCategory == "frequent"
            ? frequent
            : (categories[activeCategory] ?? [])
        return raw.filter { Self.canonicalKey($0.name) == key }.count
    }

    // MARK: - F-311 / F-313 — add to list

    func addToList(_ tile: KitchenTile) async {
        await shopping.add(
            productName: tile.name,
            quantity: 1,
            source: "kitchen",
            productId: tile.productId
        )
        onListProductIds.insert(tile.productId)
    }

    // MARK: - F-312 variant picker

    func openVariantPicker(canonicalKey key: String) {
        let raw: [KitchenTile] = activeCategory == "frequent"
            ? frequent
            : (categories[activeCategory] ?? [])
        let variants = raw.filter { Self.canonicalKey($0.name) == key }
        if variants.count <= 1 {
            if let v = variants.first {
                Task { await addToList(v) }
            }
            return
        }
        variantPicker = variants.sorted { ($0.purchaseCount ?? 0) > ($1.purchaseCount ?? 0) }
    }

    func closeVariantPicker() { variantPicker = nil }

    // MARK: - F-320..F-336 — item action sheet

    func openSheet(itemId: Int) {
        cancelPresetAutoClose()
        presetAction = nil
        storePickerOpen = false
        sheetItemId = itemId
    }

    func closeSheet() {
        cancelPresetAutoClose()
        sheetItemId = nil
        presetAction = nil
        storePickerOpen = false
    }

    var sheetItem: ShoppingListItem? {
        guard let id = sheetItemId else { return nil }
        return shopping.items.first(where: { $0.id == id })
    }

    func toggleStorePicker() { storePickerOpen.toggle() }

    // F-326 / F-327
    func pickStore(_ storeName: String?) async {
        guard let id = sheetItemId else { return }
        let normalized = (storeName?.isEmpty == false) ? storeName : nil
        await shopping.updatePreferredStore(id: id, store: normalized)
        storePickerOpen = false
    }

    // F-328 / F-329 / F-330 — qty buttons (web floor-clamps to 1, doesn't delete)
    func qtyDelta(_ delta: Int) async {
        guard let id = sheetItemId,
              let item = shopping.items.first(where: { $0.id == id }) else { return }
        let next = max(1, Int(item.quantity) + delta)
        if next == Int(item.quantity) { return }
        if delta > 0 {
            await shopping.increaseQuantity(id: id)
        } else {
            await updateQuantityRaw(id: id, quantity: Double(next))
        }
    }

    private func updateQuantityRaw(id: Int, quantity: Double) async {
        do {
            try DemoModeGate.guardMutation()
            let body = ShoppingUpdateBody(
                name: nil, category: nil, quantity: quantity, status: nil,
                note: nil, preferredStore: nil, manualEstimatedPrice: nil, actualPrice: nil,
                unit: nil, sizeLabel: nil, persistLatestPrice: nil, priceStore: nil
            )
            try await api.request(
                .put,
                path: ShoppingEndpoint.updateItem(id: id).path,
                jsonBody: body
            )
            await shopping.loadList()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            logger.error("qty update failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // F-331 / F-332 / F-333 / F-334 / F-335
    func runAction(_ action: KitchenAction) async {
        guard let id = sheetItemId,
              let item = shopping.items.first(where: { $0.id == id }) else { return }
        cancelPresetAutoClose()
        switch action {
        case .bought:
            await shopping.toggleStatus(id: id, nextStatus: "purchased")
            ToastQueue.shared.push(Toast(message: "Marked Bought ✓", severity: .success))
            presetAction = "bought"
            schedulePresetAutoClose()
        case .skipped:
            await shopping.toggleStatus(id: id, nextStatus: "skipped")
            ToastQueue.shared.push(Toast(message: "Skipped ⏭", severity: .success))
            presetAction = "skipped"
        case .open:
            await shopping.toggleStatus(id: id, nextStatus: "open")
            ToastQueue.shared.push(Toast(message: "Re-opened", severity: .success))
            closeSheet()
        case .low:
            // F-332 — web POSTs /inventory/products/<id>/low which 404s on the
            // backend (only PUT /low-status exists). mac routes to the correct
            // endpoint via InventoryState.markLow.
            guard let pid = item.productId else {
                ToastQueue.shared.push(Toast(
                    message: "This item has no linked product — cannot mark low",
                    severity: .error
                ))
                return
            }
            await inventory.markLow(productId: pid, manualLow: true)
            ToastQueue.shared.push(Toast(message: "Marked Low ✓", severity: .success))
            presetAction = "low"
        case .delete:
            await shopping.remove(id: id)
            closeSheet()
        }
    }

    private func schedulePresetAutoClose() {
        presetAutoCloseTask?.cancel()
        presetAutoCloseTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            guard !Task.isCancelled,
                  let self,
                  self.presetAction == "bought" else { return }
            self.closeSheet()
            await self.refresh()
        }
    }

    private func cancelPresetAutoClose() {
        presetAutoCloseTask?.cancel()
        presetAutoCloseTask = nil
    }

    // F-336 preset note chips
    func stampNote(_ text: String?) async {
        guard let id = sheetItemId else { return }
        let value = (text?.isEmpty == false) ? text : nil
        await shopping.updateNote(id: id, note: value)
        if let text, !text.isEmpty {
            ToastQueue.shared.push(Toast(message: "Noted: \(text)", severity: .success))
        } else {
            ToastQueue.shared.push(Toast(message: "Note cleared", severity: .success))
        }
    }

    // MARK: - F-321 / F-337 / F-338 — context menu

    func openContextMenu(forCatalog tile: KitchenTile) {
        var rows: [ContextMenuRow] = []
        rows.append(ContextMenuRow(icon: "➕", label: "Add to list", action: .addCatalog(tile)))
        let key = Self.canonicalKey(tile.name)
        let count = variantCount(forCanonicalKey: key)
        if count > 1 {
            rows.append(ContextMenuRow(
                icon: "⭐", label: "Pick variant (\(count))",
                action: .openVariantPicker(canonicalKey: key)
            ))
        }
        if let stores = tile.stores, !stores.isEmpty {
            let label = stores.count == 1 ? "Show only \(stores[0])" : "Show only this product's stores"
            rows.append(ContextMenuRow(icon: "🏪", label: label, action: .setStoreFilter(stores)))
        }
        contextMenu = ContextMenuPayload(title: tile.name, rows: rows)
    }

    func openContextMenu(forListItem item: ShoppingListItem) {
        var rows: [ContextMenuRow] = [
            ContextMenuRow(icon: "−", label: "Decrease qty", action: .qtyDelta(id: item.id, delta: -1)),
            ContextMenuRow(icon: "+", label: "Increase qty", action: .qtyDelta(id: item.id, delta: +1)),
        ]
        if item.status != "skipped" {
            rows.append(ContextMenuRow(icon: "✓", label: "Bought", action: .runAction(id: item.id, action: .bought)))
            rows.append(ContextMenuRow(icon: "📝", label: "Low",    action: .runAction(id: item.id, action: .low)))
            rows.append(ContextMenuRow(icon: "⏭", label: "Skip",    action: .runAction(id: item.id, action: .skipped)))
        } else {
            rows.append(ContextMenuRow(icon: "↩", label: "Open",    action: .runAction(id: item.id, action: .open)))
        }
        rows.append(ContextMenuRow(icon: "🗑", label: "Delete",      action: .runAction(id: item.id, action: .delete)))
        rows.append(ContextMenuRow(icon: "✎", label: "Edit details…", action: .openSheet(id: item.id)))
        contextMenu = ContextMenuPayload(title: item.name, rows: rows)
    }

    func closeContextMenu() { contextMenu = nil }

    func runContextAction(_ action: ContextMenuAction) async {
        closeContextMenu()
        switch action {
        case .addCatalog(let tile):
            await addToList(tile)
        case .openVariantPicker(let key):
            openVariantPicker(canonicalKey: key)
        case .setStoreFilter(let stores):
            setStoreFilter(stores)
        case .qtyDelta(let id, let delta):
            sheetItemId = id
            await qtyDelta(delta)
            sheetItemId = nil
        case .runAction(let id, let action):
            sheetItemId = id
            await runAction(action)
        case .openSheet(let id):
            openSheet(itemId: id)
        }
    }

    // MARK: - F-317 — weather widget

    private struct WeatherCache: Codable {
        let lat: Double
        let lon: Double
        let temp: Double
        let code: Int
        let fetchedAt: TimeInterval
    }

    private func kickOffWeather() {
        weatherTask?.cancel()
        weatherTask = Task { [weak self] in await self?.loadWeather() }
    }

    private func loadWeather() async {
        if let cached = readWeatherCache(), !Task.isCancelled {
            weather = KitchenWeather(temp: cached.temp, code: cached.code)
            return
        }
        guard let coords = await ipGeo() else { return }
        do {
            let url = URL(string: "https://api.open-meteo.com/v1/forecast?latitude=\(coords.lat)&longitude=\(coords.lon)&current_weather=true&temperature_unit=fahrenheit")!
            var req = URLRequest(url: url, timeoutInterval: 5)
            req.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await Self.publicSession.data(for: req)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { return }
            struct WX: Decodable {
                struct CW: Decodable { let temperature: Double; let weathercode: Int }
                let current_weather: CW
            }
            let decoded = try JSONDecoder().decode(WX.self, from: data)
            let payload = WeatherCache(
                lat: coords.lat, lon: coords.lon,
                temp: decoded.current_weather.temperature,
                code: decoded.current_weather.weathercode,
                fetchedAt: Date().timeIntervalSince1970
            )
            writeWeatherCache(payload)
            if !Task.isCancelled {
                weather = KitchenWeather(temp: payload.temp, code: payload.code)
            }
        } catch {
            logger.info("weather fetch skipped: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func ipGeo() async -> (lat: Double, lon: Double)? {
        do {
            let url = URL(string: "https://ipapi.co/json/")!
            var req = URLRequest(url: url, timeoutInterval: 5)
            req.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await Self.publicSession.data(for: req)
            if let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) {
                struct R: Decodable { let latitude: Double?; let longitude: Double? }
                if let r = try? JSONDecoder().decode(R.self, from: data),
                   let lat = r.latitude, let lon = r.longitude {
                    return (lat, lon)
                }
            }
        } catch { /* fall through */ }
        do {
            let url = URL(string: "https://ipwho.is/")!
            var req = URLRequest(url: url, timeoutInterval: 5)
            req.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await Self.publicSession.data(for: req)
            if let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) {
                struct R: Decodable { let success: Bool?; let latitude: Double?; let longitude: Double? }
                if let r = try? JSONDecoder().decode(R.self, from: data),
                   r.success == true,
                   let lat = r.latitude, let lon = r.longitude {
                    return (lat, lon)
                }
            }
        } catch { /* give up */ }
        return nil
    }

    private func readWeatherCache() -> WeatherCache? {
        guard let data = UserDefaults.standard.data(forKey: Defaults.weatherCache),
              let cache = try? JSONDecoder().decode(WeatherCache.self, from: data) else {
            return nil
        }
        if Date().timeIntervalSince1970 - cache.fetchedAt > 30 * 60 { return nil }
        return cache
    }

    private func writeWeatherCache(_ cache: WeatherCache) {
        if let data = try? JSONEncoder().encode(cache) {
            UserDefaults.standard.set(data, forKey: Defaults.weatherCache)
        }
    }

    /// Dedicated URLSession for 3rd-party endpoints. No cookies so device-pairing
    /// session doesn't leak to ipapi.co / Open-Meteo.
    private static let publicSession: URLSession = {
        let cfg = URLSessionConfiguration.default
        cfg.httpCookieAcceptPolicy = .never
        cfg.httpShouldSetCookies = false
        cfg.httpCookieStorage = nil
        cfg.timeoutIntervalForRequest = 5
        cfg.timeoutIntervalForResource = 8
        return URLSession(configuration: cfg)
    }()
}

// MARK: - Support types

struct KitchenTileGroup: Equatable, Hashable, Identifiable {
    let primary: KitchenTile
    let variants: [KitchenTile]
    let canonicalKey: String
    var id: Int { primary.productId }
    var variantCount: Int { variants.count }
}

struct KitchenWeather: Equatable {
    let temp: Double
    let code: Int

    var emoji: String {
        switch code {
        case 0:           return "☀️"
        case ...3:        return "⛅"
        case 45, 48:      return "🌫️"
        case 51...67:     return "🌧️"
        case 71...77:     return "🌨️"
        case 80...82:     return "🌧️"
        case 85, 86:      return "🌨️"
        case 95...:       return "⛈️"
        default:          return "🌡️"
        }
    }
    var desc: String {
        switch code {
        case 0:           return "Clear"
        case ...3:        return "Cloudy"
        case 45, 48:      return "Fog"
        case 51...67:     return "Rain"
        case 71...77:     return "Snow"
        case 80...82:     return "Showers"
        case 85, 86:      return "Snow"
        case 95...:       return "Storm"
        default:          return ""
        }
    }
}

enum KitchenAction {
    case bought, skipped, open, low, delete
}

struct ContextMenuPayload: Equatable {
    let title: String
    let rows: [ContextMenuRow]
}

struct ContextMenuRow: Equatable {
    let id = UUID()
    let icon: String
    let label: String
    let action: ContextMenuAction
}

enum ContextMenuAction: Equatable {
    case addCatalog(KitchenTile)
    case openVariantPicker(canonicalKey: String)
    case setStoreFilter([String])
    case qtyDelta(id: Int, delta: Int)
    case runAction(id: Int, action: KitchenAction)
    case openSheet(id: Int)
}

struct NoteInputContext: Identifiable {
    let id = UUID()
    let itemId: Int
}

/// Mirrors `KITCHEN_PRESETS` in index.html.
enum KitchenPresets {
    static let bought  = ["Paid more", "Paid less", "Different brand", "Different size"]
    static let low     = ["Almost out", "Restock soon"]
    static let skipped = ["Too expensive", "Out of stock", "Changed mind", "Got from elsewhere"]
    static func chips(for action: String) -> [String] {
        switch action {
        case "bought":  return bought
        case "low":     return low
        case "skipped": return skipped
        default:        return []
        }
    }
}

// MARK: - F-300..F-338 — KitchenView

struct KitchenView: View {
    @StateObject private var state = KitchenState.shared
    @StateObject private var shopping = ShoppingState.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                CatalogCard(state: state)
                CurrentListCard(state: state, shopping: shopping)
                PageNavStrip()
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Kitchen")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await state.refresh() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Refresh kitchen catalog and shopping list")
            }
        }
        .onAppear {
            // RULE 3 — detached, not .task. Heavy fetch survives view-identity churn.
            Task.detached(priority: .userInitiated) {
                await KitchenState.shared.refresh()
            }
        }
        .sheet(
            item: Binding(
                get: { state.sheetItemId.map { SheetWrapper(id: $0) } },
                set: { wrap in if wrap == nil { state.closeSheet() } }
            )
        ) { _ in
            if let item = state.sheetItem {
                ItemActionSheet(state: state, item: item)
            } else {
                EmptyView()
            }
        }
        .sheet(
            item: Binding(
                get: { state.variantPicker.flatMap { _ in VariantWrapper(id: state.variantPicker?.first?.productId ?? 0) } },
                set: { wrap in if wrap == nil { state.closeVariantPicker() } }
            )
        ) { _ in
            if let variants = state.variantPicker {
                VariantPickerSheet(state: state, variants: variants)
            }
        }
        .sheet(
            item: Binding(
                get: { state.contextMenu.map { _ in ContextWrapper() } },
                set: { wrap in if wrap == nil { state.closeContextMenu() } }
            )
        ) { _ in
            if let payload = state.contextMenu {
                ContextMenuSheet(state: state, payload: payload)
            }
        }
        .alert(
            "Note for this item",
            isPresented: Binding(
                get: { state.pendingNoteInput != nil },
                set: { if !$0 { state.pendingNoteInput = nil } }
            ),
            presenting: state.pendingNoteInput
        ) { _ in
            TextField("Note", text: $state.customNoteText)
            Button("Save") {
                let text = state.customNoteText
                state.customNoteText = ""
                state.pendingNoteInput = nil
                Task { await state.stampNote(text) }
            }
            Button("Cancel", role: .cancel) {
                state.customNoteText = ""
                state.pendingNoteInput = nil
            }
        } message: { _ in
            Text("Add a free-form note to this shopping item.")
        }
    }
}

private struct SheetWrapper: Identifiable, Hashable   { let id: Int }
private struct VariantWrapper: Identifiable, Hashable { let id: Int }
private struct ContextWrapper: Identifiable, Hashable { let id = UUID() }

// MARK: - F-300..F-313 — Catalog card

private struct CatalogCard: View {
    @ObservedObject var state: KitchenState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                header
                if !state.catalogCollapsed {
                    chipBar
                    searchRow
                    if state.searchPopoverOpen {
                        storePopover
                    }
                    productGrid
                }
            }
        }
    }

    // F-301 + F-315
    private var header: some View {
        HStack(alignment: .center, spacing: DesignTokens.Spacing.space2) {
            Button {
                state.toggleCatalog()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: state.catalogCollapsed ? "chevron.right" : "chevron.down")
                        .font(.appCaption2.weight(.semibold))
                    Text("Browse products").font(.appHeadline)
                }
                .foregroundStyle(DesignTokens.label)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Toggle catalog")

            Spacer()

            Button {
                state.toggleNames()
            } label: {
                Image(systemName: "tag")
                    .foregroundStyle(state.showNames ? DesignTokens.accent : DesignTokens.tertiaryLabel)
                    .padding(6)
                    .background(
                        Circle().fill(state.showNames ? DesignTokens.accentDim : Color.clear)
                    )
            }
            .buttonStyle(.plain)
            .help("Show / hide product names")
        }
    }

    // F-302 / F-303
    private var chipBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: DesignTokens.Spacing.space2) {
                chipButton(key: "frequent", label: "⭐ Frequent")
                ForEach(KitchenState.allCategories, id: \.self) { cat in
                    chipButton(
                        key: cat,
                        label: "\(KitchenState.categoryEmoji[cat] ?? "") \(cat)"
                    )
                }
            }
            .padding(.vertical, 2)
        }
    }

    private func chipButton(key: String, label: String) -> some View {
        let active = state.activeCategory == key
        return Button {
            state.setActiveCategory(key)
        } label: {
            Text(label)
                .font(.appCaption1.weight(active ? .semibold : .regular))
                .foregroundStyle(active ? .white : DesignTokens.label)
                .padding(.horizontal, DesignTokens.Spacing.space3)
                .padding(.vertical, 6)
                .background(active ? DesignTokens.accent : DesignTokens.surface2)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    // F-304 + F-305 + F-308 + F-309
    private var searchRow: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                TextField("Search products", text: Binding(
                    get: { state.searchQuery },
                    set: { state.setSearchQuery($0) }
                ))
                .textFieldStyle(.plain)
                if !state.searchQuery.isEmpty {
                    Button { state.setSearchQuery("") } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, DesignTokens.Spacing.space3)
            .padding(.vertical, 6)
            .background(DesignTokens.surface2)
            .clipShape(Capsule())

            Button {
                state.searchPopoverOpen ? state.closeStorePopover() : state.openStorePopover()
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                    if !state.storeFilter.isEmpty {
                        Text("\(state.storeFilter.count)").font(.appCaption2.weight(.semibold))
                    }
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
                .foregroundStyle(state.storeFilter.isEmpty ? DesignTokens.label : DesignTokens.accent)
                .background(DesignTokens.surface2)
                .clipShape(Capsule())
            }
            .buttonStyle(.plain)
            .help("Filter products by store")

            Button { NotificationCenter.default.post(name: .kitchenGridScroll, object: -1) } label: {
                Image(systemName: "chevron.left.circle.fill")
                    .font(.title3)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            .buttonStyle(.plain)
            .help("Scroll left")
            Button { NotificationCenter.default.post(name: .kitchenGridScroll, object: 1) } label: {
                Image(systemName: "chevron.right.circle.fill")
                    .font(.title3)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            .buttonStyle(.plain)
            .help("Scroll right")
        }
    }

    // F-306 / F-307
    private var storePopover: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Filter by store")
                    .font(.appCaption1.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
                Spacer()
                Button("Close") { state.closeStorePopover() }
                    .buttonStyle(.plain)
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.accent)
            }
            let stores = state.availableStores()
            if stores.isEmpty {
                Text("No store history yet.")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        storeChip(name: "All", active: state.storeFilter.isEmpty) {
                            state.clearStoreFilter()
                        }
                        ForEach(stores, id: \.self) { name in
                            storeChip(name: name, active: state.storeFilter.contains(name)) {
                                state.toggleStoreFilter(name)
                            }
                        }
                    }
                }
            }
        }
        .padding(DesignTokens.Spacing.space2)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
    }

    private func storeChip(name: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(name)
                .font(.appCaption1.weight(active ? .semibold : .regular))
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .foregroundStyle(active ? .white : DesignTokens.label)
                .background(active ? DesignTokens.accent : DesignTokens.surface)
                .clipShape(Capsule())
                .overlay(
                    Capsule().stroke(DesignTokens.border, lineWidth: active ? 0 : 0.5)
                )
        }
        .buttonStyle(.plain)
    }

    // F-310
    private var productGrid: some View {
        let groups = state.tilesForActiveChip()
        return Group {
            if groups.isEmpty {
                EmptyStateView(
                    systemImage: "tray",
                    title: "No products in this category yet."
                )
                .frame(height: 140)
            } else {
                KitchenHorizontalScroll(groups: groups, state: state)
                    .frame(height: 210)
            }
        }
    }
}

extension Notification.Name {
    static let kitchenGridScroll = Notification.Name("LocalOCR.kitchen.gridScroll")
}

// MARK: - F-308 / F-309 / F-310 — Horizontal scroll body

private struct KitchenHorizontalScroll: View {
    let groups: [KitchenTileGroup]
    @ObservedObject var state: KitchenState
    @State private var lastTargetId: Int = 0

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: true) {
                HStack(spacing: 10) {
                    ForEach(groups) { group in
                        CatalogTileButton(group: group, state: state)
                            .id(group.primary.productId)
                    }
                }
                .padding(.vertical, 4)
            }
            .onReceive(NotificationCenter.default.publisher(for: .kitchenGridScroll)) { note in
                guard let dir = note.object as? Int, !groups.isEmpty else { return }
                let count = groups.count
                let centerIdx = groups.firstIndex(where: { $0.primary.productId == lastTargetId }) ?? 0
                let next = max(0, min(count - 1, centerIdx + dir * 3))
                let target = groups[next].primary.productId
                lastTargetId = target
                withAnimation(.easeOut(duration: 0.5)) {
                    proxy.scrollTo(target, anchor: .leading)
                }
            }
            .onAppear {
                if let first = groups.first?.primary.productId {
                    lastTargetId = first
                }
            }
        }
    }
}

private struct CatalogTileButton: View {
    let group: KitchenTileGroup
    @ObservedObject var state: KitchenState

    var body: some View {
        let tile = group.primary
        let isOnList = state.onListProductIds.contains(tile.productId)
        Button {
            if isOnList { return }
            if group.variantCount > 1 {
                state.openVariantPicker(canonicalKey: group.canonicalKey)
            } else {
                Task { await state.addToList(tile) }
            }
        } label: {
            VStack(spacing: 6) {
                ZStack(alignment: .topTrailing) {
                    KitchenTileImage(tile: tile, size: 110)
                    if group.variantCount > 1 {
                        Text("+\(group.variantCount - 1)")
                            .font(.appCaption2.weight(.semibold))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(DesignTokens.warning.opacity(0.85))
                            .foregroundStyle(.white)
                            .clipShape(Capsule())
                            .padding(4)
                            .help("\(group.variantCount) variants")
                    }
                    if isOnList {
                        Image(systemName: "checkmark.seal.fill")
                            .foregroundStyle(DesignTokens.success)
                            .background(Circle().fill(.white).padding(2))
                            .padding(4)
                    }
                }
                if state.showNames {
                    Text(tile.name)
                        .font(.appCaption1.weight(.medium))
                        .foregroundStyle(DesignTokens.label)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                        .frame(width: 110)
                }
                HStack(spacing: 4) {
                    if let price = tile.latestUnitPrice {
                        Text("$\(price, specifier: "%.2f")")
                            .font(.appCaption1.weight(.semibold))
                            .foregroundStyle(DesignTokens.label)
                    } else {
                        Text("—")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                    if let n = tile.purchaseCount, n > 0 {
                        Text("\(n)×")
                            .font(.appCaption2.weight(.semibold))
                            .padding(.horizontal, 5).padding(.vertical, 2)
                            .background(DesignTokens.accentDim)
                            .foregroundStyle(DesignTokens.accent)
                            .clipShape(Capsule())
                            .help("Bought \(n)× in last 90 days")
                    }
                }
            }
            .padding(8)
            .frame(width: 130)
            .background(DesignTokens.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isOnList ? DesignTokens.success.opacity(0.5) : DesignTokens.border, lineWidth: 0.5)
            )
            .opacity(isOnList ? 0.65 : 1.0)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(tile.name + (isOnList ? " — already on list" : ""))
        // F-321 right-click + long-press → context menu
        .contextMenu {
            Button("Add to list") { Task { await state.addToList(tile) } }
                .disabled(isOnList)
            if group.variantCount > 1 {
                Button("Pick variant (\(group.variantCount))") {
                    state.openVariantPicker(canonicalKey: group.canonicalKey)
                }
            }
            if let stores = tile.stores, !stores.isEmpty {
                let label = stores.count == 1 ? "Show only \(stores[0])" : "Show only this product's stores"
                Button(label) { state.setStoreFilter(stores) }
            }
        }
        .simultaneousGesture(LongPressGesture(minimumDuration: 0.9).onEnded { _ in
            state.openContextMenu(forCatalog: tile)
        })
    }
}

private struct KitchenTileImage: View {
    let tile: KitchenTile
    let size: CGFloat

    private var resolvedURL: URL? {
        guard let path = tile.imageUrl, !path.isEmpty else { return nil }
        let base = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                ?? AppConstants.defaultAPIBaseURL
        return URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                   + (path.hasPrefix("/") ? path : "/" + path))
    }

    var body: some View {
        Group {
            if let url = resolvedURL {
                KFImage(url)
                    .requestModifier(ImageCache.tokenModifier)
                    .placeholder { placeholder }
                    .resizable()
                    .scaledToFill()
                    .frame(width: size, height: size)
                    .clipped()
            } else {
                placeholder
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var placeholder: some View {
        ZStack {
            Rectangle().fill(DesignTokens.surface)
            Text(tile.fallbackEmoji ?? "🛒")
                .font(.system(size: size * 0.55))
        }
        .frame(width: size, height: size)
    }
}

// MARK: - F-314..F-321 — Current List card

private struct CurrentListCard: View {
    @ObservedObject var state: KitchenState
    @ObservedObject var shopping: ShoppingState

    var body: some View {
        let items = shopping.items.filter { $0.status == "open" || $0.status == "skipped" }
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                header(items: items)
                if items.isEmpty {
                    emptyState
                } else {
                    listBody(items: items)
                }
            }
        }
    }

    private func header(items: [ShoppingListItem]) -> some View {
        HStack(alignment: .center) {
            Text("Current List").font(.appHeadline)
            let total = listTotal(items)
            if total > 0 {
                Text("Total $\(total, specifier: "%.2f")")
                    .font(.appCaption1.weight(.semibold))
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .background(DesignTokens.accentDim)
                    .foregroundStyle(DesignTokens.accent)
                    .clipShape(Capsule())
            }
            Spacer()
            if let w = state.weather {
                HStack(spacing: 4) {
                    Text(w.emoji)
                    Text("\(Int(round(w.temp)))°F")
                        .font(.appCaption1.weight(.semibold))
                        .foregroundStyle(DesignTokens.label)
                    if !w.desc.isEmpty {
                        Text(w.desc)
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                }
                .help("Local weather (Open-Meteo via IP geo)")
            }
        }
    }

    // F-318
    private var emptyState: some View {
        EmptyStateView(
            systemImage: "cart",
            title: "Your shopping list is empty.",
            subtitle: "Tap a product above to add it."
        )
        .frame(maxWidth: .infinity)
    }

    // F-319 grouped grid
    private func listBody(items: [ShoppingListItem]) -> some View {
        let groups = groupByStore(items)
        return VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            ForEach(groups, id: \.store) { group in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(group.store).font(.appCallout.weight(.semibold))
                        Text("\(group.items.count) item\(group.items.count == 1 ? "" : "s")")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                        Spacer()
                        let storeTotal = groupTotal(group.items)
                        if storeTotal > 0 {
                            Text("$\(storeTotal, specifier: "%.2f")")
                                .font(.appCaption1.weight(.semibold))
                                .foregroundStyle(DesignTokens.label)
                        }
                    }
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 130), spacing: 10)],
                        alignment: .leading,
                        spacing: 10
                    ) {
                        ForEach(group.items) { item in
                            KitchenListTile(item: item, state: state, shopping: shopping)
                        }
                    }
                }
            }
        }
    }

    private func groupByStore(_ items: [ShoppingListItem]) -> [(store: String, items: [ShoppingListItem])] {
        let grouped = Dictionary(grouping: items, by: { item -> String in
            if let s = item.preferredStore, !s.isEmpty { return s }
            if let s = item.latestPrice?.store, !s.isEmpty { return s }
            return "Unassigned"
        })
        let sorted = grouped.sorted { l, r in
            if l.key == "Unassigned" { return false }
            if r.key == "Unassigned" { return true }
            return l.key.localizedCaseInsensitiveCompare(r.key) == .orderedAscending
        }
        return sorted.map { (store: $0.key, items: $0.value) }
    }

    private func listTotal(_ items: [ShoppingListItem]) -> Double {
        items.reduce(0) { $0 + tileUnitPrice($1) * $1.quantity }
    }
    private func groupTotal(_ items: [ShoppingListItem]) -> Double {
        items.reduce(0) { $0 + tileUnitPrice($1) * $1.quantity }
    }
    private func tileUnitPrice(_ i: ShoppingListItem) -> Double {
        if let p = i.manualEstimatedPrice { return p }
        if let p = i.latestPrice?.price { return p }
        if let pid = i.productId, let p = state.catalogTile(forProductId: pid)?.latestUnitPrice {
            return p
        }
        return 0
    }
}

// MARK: - F-320 / F-321 — list tile

private struct KitchenListTile: View {
    let item: ShoppingListItem
    @ObservedObject var state: KitchenState
    @ObservedObject var shopping: ShoppingState

    var body: some View {
        Button {
            state.openSheet(itemId: item.id)
        } label: {
            VStack(spacing: 6) {
                tileImage
                if state.showNames {
                    Text(item.name)
                        .font(.appCaption1.weight(.medium))
                        .foregroundStyle(DesignTokens.label)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                        .frame(width: 110)
                }
                HStack(spacing: 4) {
                    let price = unitPrice
                    if price > 0 {
                        Text("$\(price, specifier: "%.2f")")
                            .font(.appCaption1.weight(.semibold))
                            .foregroundStyle(DesignTokens.label)
                    } else {
                        Text("—")
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                    Text("×\(Int(item.quantity))")
                        .font(.appCaption2.weight(.semibold))
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(DesignTokens.surface)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                        .clipShape(Capsule())
                        .help("quantity")
                }
            }
            .padding(8)
            .frame(width: 130)
            .background(item.isSkipped ? DesignTokens.surface : DesignTokens.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(DesignTokens.border, lineWidth: 0.5)
            )
            .opacity(item.isSkipped ? 0.55 : 1.0)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(item.name)
        // F-321 right-click context menu (web's long-press equivalent)
        .contextMenu {
            Button("Decrease qty") { perform(qtyDelta: -1) }
            Button("Increase qty") { perform(qtyDelta: +1) }
            if item.status != "skipped" {
                Button("Bought") { runAction(.bought) }
                Button("Low")    { runAction(.low) }
                Button("Skip")   { runAction(.skipped) }
            } else {
                Button("Open") { runAction(.open) }
            }
            Button("Delete", role: .destructive) { runAction(.delete) }
            Divider()
            Button("Edit details…") { state.openSheet(itemId: item.id) }
        }
        // F-321 long-press → custom sheet menu (matches web behavior)
        .simultaneousGesture(LongPressGesture(minimumDuration: 0.9).onEnded { _ in
            state.openContextMenu(forListItem: item)
        })
    }

    private func perform(qtyDelta delta: Int) {
        Task {
            state.sheetItemId = item.id
            await state.qtyDelta(delta)
            state.sheetItemId = nil
        }
    }

    private func runAction(_ action: KitchenAction) {
        Task {
            state.sheetItemId = item.id
            await state.runAction(action)
            if action == .delete || action == .open { state.sheetItemId = nil }
        }
    }

    private var tileImage: some View {
        Group {
            if let url = resolvedURL {
                KFImage(url)
                    .requestModifier(ImageCache.tokenModifier)
                    .placeholder { placeholder }
                    .resizable()
                    .scaledToFill()
                    .frame(width: 110, height: 110)
                    .clipped()
            } else {
                placeholder
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var resolvedURL: URL? {
        let path = item.latestSnapshot?.imageUrl
            ?? item.productId.flatMap { state.catalogTile(forProductId: $0)?.imageUrl }
        guard let path, !path.isEmpty else { return nil }
        let base = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                ?? AppConstants.defaultAPIBaseURL
        return URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                   + (path.hasPrefix("/") ? path : "/" + path))
    }

    private var placeholder: some View {
        ZStack {
            Rectangle().fill(DesignTokens.surface)
            Text(emojiForItem).font(.system(size: 56))
        }
        .frame(width: 110, height: 110)
    }

    private var emojiForItem: String {
        if let pid = item.productId,
           let tile = state.catalogTile(forProductId: pid),
           let e = tile.fallbackEmoji {
            return e
        }
        return "🛒"
    }

    private var unitPrice: Double {
        if let p = item.manualEstimatedPrice { return p }
        if let p = item.latestPrice?.price { return p }
        if let pid = item.productId, let p = state.catalogTile(forProductId: pid)?.latestUnitPrice {
            return p
        }
        return 0
    }
}

// MARK: - F-322..F-336 — Item action sheet

private struct ItemActionSheet: View {
    @ObservedObject var state: KitchenState
    let item: ShoppingListItem

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            header
            metaLine
            storeButton
            if state.storePickerOpen {
                storePicker
            }
            qtyRow
            actionRow
            if let action = state.presetAction {
                presetChips(action: action)
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 380, idealWidth: 440)
    }

    // F-323 + F-324
    private var header: some View {
        HStack(alignment: .top) {
            Text(item.name).font(.appTitle3).foregroundStyle(DesignTokens.label)
            Spacer()
            Button {
                state.closeSheet()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title3)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.cancelAction)
            .accessibilityLabel("Close")
        }
    }

    // F-325
    private var metaLine: some View {
        let parts: [String] = [
            item.manualEstimatedPrice.map { String(format: "$%.2f", $0) } ?? "",
            item.preferredStore ?? item.latestPrice?.store ?? "",
            item.category ?? "",
        ].filter { !$0.isEmpty }
        return Text(parts.joined(separator: " · "))
            .font(.appCaption1)
            .foregroundStyle(DesignTokens.secondaryLabel)
    }

    // F-326
    private var storeButton: some View {
        Button {
            state.toggleStorePicker()
        } label: {
            HStack {
                Image(systemName: "storefront")
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                Text("Store").font(.appCallout).foregroundStyle(DesignTokens.label)
                Spacer()
                Text(item.preferredStore ?? "—")
                    .font(.appCallout.weight(.medium))
                    .foregroundStyle(DesignTokens.secondaryLabel)
                Image(systemName: state.storePickerOpen ? "chevron.down" : "chevron.right")
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            .padding(DesignTokens.Spacing.space2)
            .background(DesignTokens.surface2)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // F-327
    private var storePicker: some View {
        let buckets = ShoppingState.shared.storeBuckets
        let frequent = Array(Set(buckets.frequent ?? [])).sorted()
        let lowFreq = Array(Set((buckets.lowFreq ?? []).filter { !frequent.contains($0) })).sorted()
        return VStack(alignment: .leading, spacing: 6) {
            if !frequent.isEmpty {
                Text("⭐ Frequent")
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
                chipRow(stores: frequent)
            }
            if !lowFreq.isEmpty {
                Text("Rarely Used")
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
                chipRow(stores: lowFreq)
            }
            Button {
                Task { await state.pickStore(nil) }
            } label: {
                Text("— Clear store —")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(DesignTokens.surface)
                    .clipShape(Capsule())
            }
            .buttonStyle(.plain)
        }
        .padding(DesignTokens.Spacing.space2)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func chipRow(stores: [String]) -> some View {
        FlowLayout(spacing: 6) {
            ForEach(stores, id: \.self) { name in
                let active = (item.preferredStore ?? "").caseInsensitiveCompare(name) == .orderedSame
                Button {
                    Task { await state.pickStore(name) }
                } label: {
                    Text(name)
                        .font(.appCaption1.weight(active ? .semibold : .regular))
                        .foregroundStyle(active ? .white : DesignTokens.label)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(active ? DesignTokens.accent : DesignTokens.surface2)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }

    // F-328 / F-329 / F-330
    private var qtyRow: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            Button { Task { await state.qtyDelta(-1) } } label: {
                Image(systemName: "minus.circle.fill")
                    .font(.title)
                    .foregroundStyle(DesignTokens.accent)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Decrease quantity")

            Text("\(Int(item.quantity))")
                .font(.appTitle3.weight(.semibold))
                .frame(minWidth: 30)

            Button { Task { await state.qtyDelta(+1) } } label: {
                Image(systemName: "plus.circle.fill")
                    .font(.title)
                    .foregroundStyle(DesignTokens.accent)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Increase quantity")
            Spacer()
        }
    }

    // F-331 / F-332 / F-333 / F-334 / F-335
    private var actionRow: some View {
        HStack(spacing: 6) {
            if item.isSkipped {
                Button {
                    Task { await state.runAction(.open) }
                } label: { Text("↩ Open") }
                .buttonStyle(PrimaryButtonStyle())
            } else {
                Button {
                    Task { await state.runAction(.bought) }
                } label: { Text("✓ Bought") }
                .buttonStyle(PrimaryButtonStyle())
                Button {
                    Task { await state.runAction(.low) }
                } label: { Text("📝 Low") }
                .buttonStyle(GhostButtonStyle())
                .disabled(item.productId == nil)
                .help(item.productId == nil ? "Item has no linked product" : "Mark linked product as low-stock")
                Button {
                    Task { await state.runAction(.skipped) }
                } label: { Text("⏭ Skip") }
                .buttonStyle(GhostButtonStyle())
            }
            Spacer()
            Button {
                Task { await state.runAction(.delete) }
            } label: {
                Image(systemName: "trash")
            }
            .buttonStyle(DestructiveButtonStyle())
            .accessibilityLabel("Delete item")
        }
    }

    // F-336
    private func presetChips(action: String) -> some View {
        let chips = KitchenPresets.chips(for: action)
        return FlowLayout(spacing: 6) {
            ForEach(chips, id: \.self) { chip in
                Button {
                    Task { await state.stampNote(chip) }
                } label: {
                    Text(chip)
                        .font(.appCaption1)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(DesignTokens.accentDim)
                        .foregroundStyle(DesignTokens.accent)
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
            Button {
                if let id = state.sheetItemId {
                    state.customNoteText = ""
                    state.pendingNoteInput = NoteInputContext(itemId: id)
                }
            } label: {
                Text("✏️ custom")
                    .font(.appCaption1)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(DesignTokens.surface2)
                    .foregroundStyle(DesignTokens.label)
                    .clipShape(Capsule())
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - F-312 variant picker sheet

private struct VariantPickerSheet: View {
    @ObservedObject var state: KitchenState
    let variants: [KitchenTile]

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            HStack {
                Text("Pick a variant").font(.appTitle3)
                Spacer()
                Button {
                    state.closeVariantPicker()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.cancelAction)
                .accessibilityLabel("Close")
            }
            ScrollView {
                VStack(spacing: 6) {
                    ForEach(variants) { tile in
                        Button {
                            Task {
                                await state.addToList(tile)
                                state.closeVariantPicker()
                            }
                        } label: {
                            HStack(spacing: 10) {
                                KitchenTileImage(tile: tile, size: 48)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(tile.name)
                                        .font(.appCallout.weight(.medium))
                                        .foregroundStyle(DesignTokens.label)
                                    HStack(spacing: 6) {
                                        if let p = tile.latestUnitPrice {
                                            Text("$\(p, specifier: "%.2f")")
                                                .font(.appCaption1)
                                                .foregroundStyle(DesignTokens.secondaryLabel)
                                        } else {
                                            Text("—")
                                                .font(.appCaption1)
                                                .foregroundStyle(DesignTokens.tertiaryLabel)
                                        }
                                        Text("·").foregroundStyle(DesignTokens.tertiaryLabel)
                                        Text("\(tile.purchaseCount ?? 0)×")
                                            .font(.appCaption1)
                                            .foregroundStyle(DesignTokens.secondaryLabel)
                                    }
                                }
                                Spacer()
                            }
                            .padding(DesignTokens.Spacing.space2)
                            .background(DesignTokens.surface2)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 380, idealWidth: 460, minHeight: 320, idealHeight: 420)
    }
}

// MARK: - F-337 / F-338 — context menu sheet

private struct ContextMenuSheet: View {
    @ObservedObject var state: KitchenState
    let payload: ContextMenuPayload

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space2) {
            HStack {
                Text(payload.title).font(.appHeadline)
                Spacer()
                Button {
                    state.closeContextMenu()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.cancelAction)
                .accessibilityLabel("Close menu")
            }
            ForEach(payload.rows, id: \.id) { row in
                Button {
                    Task { await state.runContextAction(row.action) }
                } label: {
                    HStack {
                        Text(row.icon).font(.title3)
                        Text(row.label).font(.appCallout).foregroundStyle(DesignTokens.label)
                        Spacer()
                    }
                    .padding(DesignTokens.Spacing.space2)
                    .background(DesignTokens.surface2)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 320, idealWidth: 360)
    }
}

// MARK: - FlowLayout — wraps chip rows to multiple lines

private struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        return arrange(subviews: subviews, width: width).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let layout = arrange(subviews: subviews, width: bounds.width)
        for (idx, frame) in layout.frames.enumerated() {
            let origin = CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY)
            subviews[idx].place(at: origin, proposal: .init(frame.size))
        }
    }

    private func arrange(subviews: Subviews, width: CGFloat) -> (frames: [CGRect], size: CGSize) {
        var frames: [CGRect] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalWidth: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x + size.width > width && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            frames.append(CGRect(origin: CGPoint(x: x, y: y), size: size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
            totalWidth = max(totalWidth, x)
        }
        return (frames, CGSize(width: totalWidth, height: y + rowHeight))
    }
}

#Preview("KitchenView") {
    KitchenView()
        .environmentObject(Router.shared)
        .frame(width: 1000, height: 700)
}
