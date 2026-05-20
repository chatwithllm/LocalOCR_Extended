import SwiftUI
import AppKit
import Kingfisher
import UniformTypeIdentifiers
import os.log

// MARK: - F-400..F-430 — Products screen
//
// Catalog management for the whole household: add / search / sort / filter
// products, edit details, upload photos, see price history, run AI enrichment.
// Two admin-only sections at the bottom (Review Queue + Snapshot Review Queue)
// mirror the web screen exactly.
//
// Routes verified against `manage_product_catalog.py` + `manage_product_snapshots.py`.
// All mutations go through APIClient + DemoModeGate.

// MARK: - Codable types (mirror `_serialize_product` exactly)

struct CatalogProduct: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String
    let rawName: String?
    let displayName: String?
    let brand: String?
    let size: String?
    let defaultUnit: String?
    let defaultSizeLabel: String?
    let enrichmentConfidence: Double?
    let reviewState: String?
    let reviewedAt: String?
    let category: String?
    let barcode: String?
    let createdAt: String?
    let recentReceipts: [CatalogReceiptLink]?
    let lastPurchaseDate: String?
    let latestPrice: LatestPrice?
    let latestSnapshot: ProductLatestSnapshot?
    let inventoryItemId: Int?
    let inventoryQuantity: Double?
    let inventoryThreshold: Double?
    let manualLow: Bool?
    let isLow: Bool?
    let isRegularUse: Bool?
    let suggestedReview: Bool?  // review-queue only

    var displayLabel: String { displayName ?? name }
    var family: String {
        let raw = displayLabel.trimmingCharacters(in: .whitespaces)
        return raw.isEmpty ? name : raw
    }
}

struct CatalogReceiptLink: Codable, Equatable, Hashable {
    let receiptId: Int?
    let date: String?
    let total: Double?
    let store: String?
}

struct ProductLatestSnapshot: Codable, Equatable, Hashable {
    let id: Int?
    let imageUrl: String?
    let createdAt: String?
}

struct ProductsListResponse: Codable, Equatable {
    let products: [CatalogProduct]
    let total: Int?
    let page: Int?
    let perPage: Int?
}

struct ProductSearchListResponse: Codable, Equatable {
    let query: String?
    let results: [CatalogProduct]
    let count: Int?
}

struct ProductReviewQueueResponse: Codable, Equatable {
    let items: [CatalogProduct]
    let count: Int?
}

struct ProductBulkEnhanceResponse: Codable, Equatable {
    let updated: [CatalogProduct]
    let count: Int?
}

struct ProductWrapper: Codable, Equatable {
    let product: CatalogProduct
}

struct ProductPriceHistoryResponse: Codable, Equatable {
    let productId: Int
    let productName: String
    let prices: [ProductPricePoint]
    let avgPrice: Double?
    let minPrice: Double?
    let maxPrice: Double?
}

struct ProductPricePoint: Codable, Equatable, Hashable {
    let price: Double
    let storeId: Int?
    let date: String?
}

struct AutoDedupTokensResponse: Codable, Equatable {
    let merged: Int?
    let scanned: Int?
    // groups omitted — only counts surface in toast
}

// MARK: - Snapshot review queue

struct SnapshotReviewItem: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let imageUrl: String?
    let status: String?
    let sourceContext: String?
    let capturedAt: String?
    let createdAt: String?
    let notes: String?
    let productName: String?
    let shoppingItemName: String?
    let storeName: String?
    let linkedProduct: SnapshotLinkedProduct?
}

struct SnapshotLinkedProduct: Codable, Equatable, Hashable {
    let id: Int?
    let name: String?
    let category: String?
}

struct SnapshotReviewQueueResponse: Codable, Equatable {
    let items: [SnapshotReviewItem]
    let count: Int?
}

struct SnapshotWrapper: Codable, Equatable {
    let snapshot: SnapshotReviewItem
}

// MARK: - Constants

enum ProductCategoryOptions {
    static let all: [String] = [
        "produce", "dairy", "meat", "seafood", "bakery", "grains", "frozen",
        "beverages", "snacks", "canned", "condiments", "household",
        "personal_care", "apparel", "restaurant", "beauty", "health",
        "gift", "fees", "service", "retail", "general_expense", "other",
    ]
    static func label(_ key: String) -> String {
        key.split(separator: "_").map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined(separator: " ")
    }
}

enum ProductsSort: String, CaseIterable {
    case nameAsc       = "name_asc"
    case nameDesc      = "name_desc"
    case categoryAsc   = "category_asc"
    case variantsDesc  = "variants_desc"
    case recentDesc    = "recent_desc"

    var label: String {
        switch self {
        case .nameAsc:      return "Name A–Z"
        case .nameDesc:     return "Name Z–A"
        case .categoryAsc:  return "Category"
        case .variantsDesc: return "Most variants"
        case .recentDesc:   return "Recently purchased"
        }
    }
}

// MARK: - ProductsState

@MainActor
final class ProductsState: ObservableObject {

    static let shared = ProductsState()

    @Published private(set) var products: [CatalogProduct] = []
    @Published private(set) var total: Int = 0
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?

    @Published var searchQuery: String = ""
    @Published var sortMode: ProductsSort = .nameAsc {
        didSet { UserDefaults.standard.set(sortMode.rawValue, forKey: Defaults.sortMode) }
    }
    @Published var categoryFilter: Set<String> = []

    // Review queues
    @Published var reviewStatusFilter: String = "pending"  // "pending"|"resolved"|"dismissed"|"all"
    @Published private(set) var reviewItems: [CatalogProduct] = []
    @Published private(set) var isLoadingReview = false

    @Published private(set) var snapshotReviewItems: [SnapshotReviewItem] = []
    @Published private(set) var isLoadingSnapshotReview = false

    // Edit / price-history / inline edit state
    @Published var editProduct: CatalogProduct?
    @Published var priceHistoryProduct: CatalogProduct?
    @Published private(set) var priceHistory: ProductPriceHistoryResponse?
    @Published private(set) var photosForEdit: [SnapshotReviewItem] = []

    // Per-review-item input drafts (admin-only Review Queue)
    @Published var reviewDrafts: [Int: String] = [:]
    // Per-snapshot-review-item drafts (Snapshot Review Queue)
    @Published var snapshotDrafts: [Int: SnapshotDraft] = [:]

    struct SnapshotDraft: Equatable {
        var productName: String
        var category: String
    }

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "products")
    private var searchDebounceTask: Task<Void, Never>?

    enum Defaults {
        static let sortMode = "LocalOCR.products.sortMode"
    }

    init(api: APIClient = .shared) {
        self.api = api
        if let raw = UserDefaults.standard.string(forKey: Defaults.sortMode),
           let mode = ProductsSort(rawValue: raw) {
            self.sortMode = mode
        }
    }

    // MARK: - F-406 catalog load

    func refresh() async {
        await loadCatalog()
        if AppState.shared.currentUser?.isAdmin == true {
            await withTaskGroup(of: Void.self) { group in
                group.addTask { @MainActor in await self.loadReviewQueue() }
                group.addTask { @MainActor in await self.loadSnapshotReviewQueue() }
            }
        }
    }

    func loadCatalog() async {
        let q = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        isLoading = true
        defer { isLoading = false }
        do {
            if q.count >= 2 {
                let endpoint = ProductsEndpoint.search(query: q)
                let response = try await api.request(
                    .get,
                    path: endpoint.path,
                    query: endpoint.query,
                    as: ProductSearchListResponse.self
                )
                products = response.results
                total = response.count ?? response.results.count
                logger.info("search '\(q, privacy: .public)' returned \(response.results.count, privacy: .public)")
            } else {
                let endpoint = ProductsEndpoint.list(page: 1, perPage: 500, category: nil)
                let response = try await api.request(
                    .get,
                    path: endpoint.path,
                    query: endpoint.query,
                    as: ProductsListResponse.self
                )
                products = response.products
                total = response.total ?? response.products.count
                logger.info("loaded \(response.products.count, privacy: .public) products (total=\(response.total ?? -1, privacy: .public))")
            }
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadCatalog failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // F-407 — debounce 300 ms (matches web)
    func setSearch(_ q: String) {
        searchQuery = q
        searchDebounceTask?.cancel()
        searchDebounceTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard let self, !Task.isCancelled else { return }
            await self.loadCatalog()
        }
    }

    // F-410
    func toggleCategoryFilter(_ category: String) {
        if categoryFilter.contains(category) { categoryFilter.remove(category) }
        else { categoryFilter.insert(category) }
    }
    func clearCategoryFilters() { categoryFilter.removeAll() }

    // MARK: - Derived

    /// Group by category::family-lowercased key (mirrors `groupProducts`).
    func groupedProducts() -> [ProductCategoryGroup] {
        let filtered: [CatalogProduct]
        if searchQuery.trimmingCharacters(in: .whitespaces).count >= 2 {
            filtered = products
        } else if categoryFilter.isEmpty {
            filtered = products
        } else {
            filtered = products.filter { p in
                categoryFilter.contains((p.category ?? "").lowercased())
            }
        }
        var groups: [String: ProductGroup] = [:]
        var order: [String] = []
        for product in filtered {
            let category = (product.category ?? "other").lowercased()
            let family = (product.displayName ?? product.name).trimmingCharacters(in: .whitespaces)
            let key = "\(category)::\(family.lowercased())"
            if groups[key] == nil {
                order.append(key)
                groups[key] = ProductGroup(
                    key: key,
                    family: family.isEmpty ? product.name : family,
                    category: category,
                    items: []
                )
            }
            groups[key]?.items.append(product)
        }
        let sortedGroups: [ProductGroup] = order.compactMap {
            guard var g = groups[$0] else { return nil }
            g.items.sort { $0.name < $1.name }
            return g
        }
        let final = sortGroups(sortedGroups)
        return regroupByCategory(final)
    }

    private func sortGroups(_ groups: [ProductGroup]) -> [ProductGroup] {
        switch sortMode {
        case .nameAsc:
            return groups.sorted { $0.family.localizedCaseInsensitiveCompare($1.family) == .orderedAscending }
        case .nameDesc:
            return groups.sorted { $0.family.localizedCaseInsensitiveCompare($1.family) == .orderedDescending }
        case .categoryAsc:
            return groups.sorted {
                let l = $0.category
                let r = $1.category
                if l == r { return $0.family.localizedCaseInsensitiveCompare($1.family) == .orderedAscending }
                return l < r
            }
        case .variantsDesc:
            return groups.sorted {
                if $0.items.count == $1.items.count {
                    return $0.family.localizedCaseInsensitiveCompare($1.family) == .orderedAscending
                }
                return $0.items.count > $1.items.count
            }
        case .recentDesc:
            return groups.sorted {
                let l = $0.items.map { $0.lastPurchaseDate ?? "" }.max() ?? ""
                let r = $1.items.map { $0.lastPurchaseDate ?? "" }.max() ?? ""
                if l == r { return $0.family.localizedCaseInsensitiveCompare($1.family) == .orderedAscending }
                return l > r
            }
        }
    }

    private func regroupByCategory(_ groups: [ProductGroup]) -> [ProductCategoryGroup] {
        var byCategory: [String: [ProductGroup]] = [:]
        var order: [String] = []
        for g in groups {
            if byCategory[g.category] == nil { order.append(g.category) }
            byCategory[g.category, default: []].append(g)
        }
        return order.compactMap {
            guard let list = byCategory[$0] else { return nil }
            return ProductCategoryGroup(category: $0, groups: list)
        }
    }

    // MARK: - F-405 create

    @discardableResult
    func createProduct(name: String, category: String, barcode: String?) async -> Bool {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            ToastQueue.shared.push(Toast(message: "Enter a product name", severity: .error))
            return false
        }
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .post,
                path: ProductsEndpoint.create.path,
                jsonBody: ProductCreateBody(
                    name: trimmed,
                    category: category,
                    barcode: (barcode?.isEmpty == false) ? barcode : nil
                )
            )
            ToastQueue.shared.push(Toast(message: "\(trimmed) created ✅", severity: .success))
            await loadCatalog()
            return true
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
            return false
        } catch is CancellationError {
            return false
        } catch {
            lastError = (error as? APIError)?.errorDescription
            ToastQueue.shared.push(Toast(message: lastError ?? "Could not create product", severity: .error))
            return false
        }
    }

    // MARK: - F-414 rename

    func renameProduct(id: Int, newName: String) async {
        let trimmed = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            ToastQueue.shared.push(Toast(message: "Product name cannot be blank", severity: .error))
            return
        }
        await updateProduct(id: id, body: ProductUpdateBody(
            name: trimmed, category: nil, barcode: nil,
            defaultUnit: nil, defaultSizeLabel: nil
        ))
    }

    // MARK: - F-415 / F-418 update product (name + category + unit + size)

    func updateProduct(id: Int, body: ProductUpdateBody) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .put,
                path: ProductsEndpoint.update(id: id).path,
                jsonBody: body
            )
            ToastQueue.shared.push(Toast(message: "Updated ✅", severity: .success))
            await loadCatalog()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Could not update product",
                severity: .error
            ))
        }
    }

    // MARK: - F-417 delete

    func deleteProduct(_ product: CatalogProduct) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .delete,
                path: ProductsEndpoint.delete(id: product.id).path
            )
            ToastQueue.shared.push(Toast(message: "Deleted '\(product.displayLabel)' ✅", severity: .success))
            products.removeAll { $0.id == product.id }
            await loadCatalog()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Could not delete",
                severity: .error
            ))
        }
    }

    // MARK: - F-419 price history

    func openPriceHistory(_ product: CatalogProduct) async {
        priceHistoryProduct = product
        priceHistory = nil
        do {
            let response = try await api.request(
                .get,
                path: ProductsEndpoint.priceHistory(id: product.id).path,
                as: ProductPriceHistoryResponse.self
            )
            priceHistory = response
        } catch is CancellationError {
            return
        } catch {
            logger.error("priceHistory failed: \(error.localizedDescription, privacy: .public)")
            ToastQueue.shared.push(Toast(message: "Could not load price history", severity: .error))
        }
    }

    func closePriceHistory() {
        priceHistoryProduct = nil
        priceHistory = nil
    }

    // MARK: - F-420 AI enhance

    func enhanceProduct(id: Int) async {
        do {
            try DemoModeGate.guardMutation()
            let response = try await api.request(
                .post,
                path: ProductsEndpoint.enhance(id: id).path,
                jsonBody: EmptyBody(),
                as: ProductWrapper.self
            )
            ToastQueue.shared.push(Toast(
                message: "Enhanced '\(response.product.displayLabel)' ✨",
                severity: .success
            ))
            await loadCatalog()
            await loadReviewQueue()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch APIError.forbidden(let message) {
            ToastQueue.shared.push(Toast(
                message: message ?? "Admin role required",
                severity: .error
            ))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Enhance failed",
                severity: .error
            ))
        }
    }

    // MARK: - F-421 review status

    func setReviewState(id: Int, state: String) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .put,
                path: ProductsEndpoint.reviewStatus(id: id).path,
                jsonBody: ProductReviewStatusBody(reviewState: state)
            )
            ToastQueue.shared.push(Toast(message: "Marked \(state) ✓", severity: .success))
            await loadReviewQueue()
            await loadCatalog()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch APIError.validation(let message) {
            ToastQueue.shared.push(Toast(
                message: message ?? "Cannot change review state",
                severity: .error
            ))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Could not update state",
                severity: .error
            ))
        }
    }

    /// F-414 Review Queue: save a corrected name → PUT /products/<id>/update
    /// (mirrors web's `saveReviewedProduct`)
    func saveReviewedProduct(id: Int) async {
        guard let name = reviewDrafts[id]?.trimmingCharacters(in: .whitespacesAndNewlines),
              !name.isEmpty else {
            ToastQueue.shared.push(Toast(message: "Enter a final name first", severity: .error))
            return
        }
        await updateProduct(id: id, body: ProductUpdateBody(
            name: name, category: nil, barcode: nil,
            defaultUnit: nil, defaultSizeLabel: nil
        ))
        await loadReviewQueue()
    }

    // MARK: - F-422 review queue load

    func loadReviewQueue() async {
        guard AppState.shared.currentUser?.isAdmin == true else {
            reviewItems = []
            return
        }
        isLoadingReview = true
        defer { isLoadingReview = false }
        do {
            let response = try await api.request(
                .get,
                path: ProductsEndpoint.reviewQueue(status: reviewStatusFilter).path,
                query: ProductsEndpoint.reviewQueue(status: reviewStatusFilter).query,
                as: ProductReviewQueueResponse.self
            )
            reviewItems = response.items
            // Pre-fill name drafts
            for item in response.items where reviewDrafts[item.id] == nil {
                reviewDrafts[item.id] = item.name
            }
            logger.info("loaded \(response.items.count, privacy: .public) review-queue items")
        } catch APIError.forbidden {
            reviewItems = []
        } catch is CancellationError {
            return
        } catch {
            logger.error("loadReviewQueue failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func setReviewStatusFilter(_ status: String) {
        reviewStatusFilter = status
        Task { await loadReviewQueue() }
    }

    // MARK: - F-423 bulk enhance

    func bulkEnhanceReviewQueue() async {
        do {
            try DemoModeGate.guardMutation()
            let response = try await api.request(
                .post,
                path: ProductsEndpoint.bulkEnhance.path,
                jsonBody: ProductBulkEnhanceBody(limit: 10, provider: "gemini"),
                as: ProductBulkEnhanceResponse.self
            )
            ToastQueue.shared.push(Toast(
                message: "Enhanced \(response.count ?? response.updated.count) products ✨",
                severity: .success
            ))
            await loadReviewQueue()
            await loadCatalog()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch APIError.forbidden(let m) {
            ToastQueue.shared.push(Toast(message: m ?? "Admin only", severity: .error))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Bulk enhance failed",
                severity: .error
            ))
        }
    }

    // MARK: - F-424 auto-dedup-tokens

    func autoDedup() async {
        do {
            try DemoModeGate.guardMutation()
            let response = try await api.request(
                .post,
                path: ProductsEndpoint.autoDedupTokens.path,
                jsonBody: EmptyBody(),
                as: AutoDedupTokensResponse.self
            )
            let merged = response.merged ?? 0
            let scanned = response.scanned ?? 0
            ToastQueue.shared.push(Toast(
                message: merged > 0
                    ? "Merged \(merged) duplicate group\(merged == 1 ? "" : "s") (scanned \(scanned))"
                    : "No duplicates found (scanned \(scanned))",
                severity: .success
            ))
            await loadCatalog()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Dedup failed",
                severity: .error
            ))
        }
    }

    // MARK: - F-416 / F-425 snapshot upload

    @discardableResult
    func uploadSnapshot(productId: Int, fileURL: URL) async -> Bool {
        do {
            try DemoModeGate.guardMutation()
            let data = try Data(contentsOf: fileURL)
            let mime = mimeType(for: fileURL.pathExtension)
            _ = try await api.multipartRequest(
                path: ProductSnapshotEndpoint.upload.path,
                fields: [
                    "product_id": String(productId),
                    "source_context": "manual",
                    "status": "linked",
                ],
                fileFieldName: "image",
                fileName: fileURL.lastPathComponent,
                mimeType: mime,
                fileData: data,
                as: SnapshotWrapper.self
            )
            ToastQueue.shared.push(Toast(message: "Photo added 📷", severity: .success))
            await loadCatalog()
            if editProduct?.id == productId {
                await refreshPhotosForEdit(productId: productId)
            }
            return true
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
            return false
        } catch is CancellationError {
            return false
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Photo upload failed",
                severity: .error
            ))
            return false
        }
    }

    private func mimeType(for ext: String) -> String {
        switch ext.lowercased() {
        case "jpg", "jpeg":  return "image/jpeg"
        case "png":          return "image/png"
        case "heic":         return "image/heic"
        case "heif":         return "image/heif"
        case "gif":          return "image/gif"
        case "webp":         return "image/webp"
        default:             return "application/octet-stream"
        }
    }

    // MARK: - F-415 edit sheet photos

    func openEdit(_ product: CatalogProduct) async {
        editProduct = product
        await refreshPhotosForEdit(productId: product.id)
    }

    func closeEdit() {
        editProduct = nil
        photosForEdit = []
    }

    func refreshPhotosForEdit(productId: Int) async {
        do {
            let endpoint = ProductSnapshotEndpoint.list(productId: productId)
            let response = try await api.request(
                .get,
                path: endpoint.path,
                query: endpoint.query,
                as: SnapshotsListResponse.self
            )
            photosForEdit = response.snapshots
        } catch is CancellationError {
            return
        } catch {
            logger.warning("refreshPhotosForEdit failed: \(error.localizedDescription, privacy: .public)")
            photosForEdit = []
        }
    }

    struct SnapshotsListResponse: Codable, Equatable {
        let snapshots: [SnapshotReviewItem]
        let count: Int?
    }

    // MARK: - F-428 promote snapshot

    func promoteSnapshot(_ snap: SnapshotReviewItem) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .post,
                path: ProductSnapshotEndpoint.promote(id: snap.id).path,
                jsonBody: EmptyBody()
            )
            ToastQueue.shared.push(Toast(message: "Photo restored 📷", severity: .success))
            if let pid = editProduct?.id {
                await refreshPhotosForEdit(productId: pid)
            }
            await loadCatalog()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Promote failed",
                severity: .error
            ))
        }
    }

    // MARK: - F-429 delete snapshot

    func deleteSnapshot(_ snap: SnapshotReviewItem) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .delete,
                path: ProductSnapshotEndpoint.delete(id: snap.id).path
            )
            ToastQueue.shared.push(Toast(message: "Photo removed", severity: .success))
            if let pid = editProduct?.id {
                await refreshPhotosForEdit(productId: pid)
            }
            await loadCatalog()
            await loadSnapshotReviewQueue()
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

    // MARK: - F-426 snapshot review queue load

    func loadSnapshotReviewQueue() async {
        guard AppState.shared.currentUser?.isAdmin == true else {
            snapshotReviewItems = []
            return
        }
        isLoadingSnapshotReview = true
        defer { isLoadingSnapshotReview = false }
        do {
            let response = try await api.request(
                .get,
                path: ProductSnapshotEndpoint.reviewQueue(status: "pending").path,
                query: ProductSnapshotEndpoint.reviewQueue(status: "pending").query,
                as: SnapshotReviewQueueResponse.self
            )
            snapshotReviewItems = response.items
            for item in response.items where snapshotDrafts[item.id] == nil {
                let name = item.linkedProduct?.name ?? item.productName ?? item.shoppingItemName ?? ""
                let category = item.linkedProduct?.category ?? "other"
                snapshotDrafts[item.id] = SnapshotDraft(productName: name, category: category)
            }
            logger.info("loaded \(response.items.count, privacy: .public) snapshot review items")
        } catch APIError.forbidden {
            snapshotReviewItems = []
        } catch is CancellationError {
            return
        } catch {
            logger.error("loadSnapshotReviewQueue failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - F-427 snapshot link / archive

    func linkSnapshot(_ item: SnapshotReviewItem) async {
        guard let draft = snapshotDrafts[item.id],
              !draft.productName.trimmingCharacters(in: .whitespaces).isEmpty else {
            ToastQueue.shared.push(Toast(message: "Enter a product name first", severity: .error))
            return
        }
        await reviewSnapshot(item: item, body: SnapshotReviewBody(
            productName: draft.productName,
            category: draft.category,
            status: "linked",
            productId: nil,
            notes: nil
        ))
    }

    func archiveSnapshot(_ item: SnapshotReviewItem) async {
        await reviewSnapshot(item: item, body: SnapshotReviewBody(
            productName: nil, category: nil,
            status: "archived",
            productId: nil, notes: nil
        ))
    }

    private func reviewSnapshot(item: SnapshotReviewItem, body: SnapshotReviewBody) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .put,
                path: ProductSnapshotEndpoint.review(id: item.id).path,
                jsonBody: body
            )
            ToastQueue.shared.push(Toast(
                message: body.status == "linked" ? "Linked to product ✅" : "Snapshot archived",
                severity: .success
            ))
            await loadSnapshotReviewQueue()
            await loadCatalog()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch APIError.forbidden(let m) {
            ToastQueue.shared.push(Toast(message: m ?? "Admin only", severity: .error))
        } catch is CancellationError {
            return
        } catch {
            ToastQueue.shared.push(Toast(
                message: (error as? APIError)?.errorDescription ?? "Snapshot review failed",
                severity: .error
            ))
        }
    }
}

// MARK: - Support types

struct ProductGroup: Equatable, Hashable, Identifiable {
    let key: String
    let family: String
    let category: String
    var items: [CatalogProduct]
    var id: String { key }
    var count: Int { items.count }
    var primaryItem: CatalogProduct? { items.first }
    var examples: [String] { items.prefix(3).map(\.name) }
    var displayCategory: String {
        let first = items.first?.category ?? "other"
        if items.allSatisfy({ ($0.category ?? "other") == first }) {
            return first
        }
        return "mixed"
    }
}

struct ProductCategoryGroup: Equatable, Hashable, Identifiable {
    let category: String
    let groups: [ProductGroup]
    var id: String { category }
}

private struct EmptyBody: Encodable {}

// MARK: - ProductsView

struct ProductsView: View {
    @StateObject private var state = ProductsState.shared
    @EnvironmentObject private var appState: AppState
    @State private var expandedGroupIds: Set<String> = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                pageHeader
                AddProductCard(state: state)
                CatalogToolbar(state: state)
                CategoryChipRow(state: state)
                CatalogBody(
                    state: state,
                    expandedGroupIds: $expandedGroupIds
                )
                if appState.currentUser?.isAdmin == true {
                    ReviewQueueCard(state: state)
                    SnapshotReviewCard(state: state)
                }
                PageNavStrip()
            }
            .padding(DesignTokens.Spacing.space4)
        }
        .background(DesignTokens.background)
        .navigationTitle("Products")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    Task { await state.autoDedup() }
                } label: {
                    Label("Merge duplicates", systemImage: "rectangle.stack.badge.minus")
                }
                .help("Auto-merge products with matching token fingerprints")

                Button {
                    Task { await state.refresh() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .help("Reload catalog and review queues")
            }
        }
        .onAppear {
            // RULE 3 — detached, not .task.
            Task.detached(priority: .userInitiated) {
                await ProductsState.shared.refresh()
            }
        }
        .sheet(item: $state.editProduct) { product in
            EditProductSheet(state: state, product: product)
        }
        .sheet(item: $state.priceHistoryProduct) { product in
            PriceHistorySheet(state: state, product: product)
        }
    }

    // F-400
    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Products").font(.appTitle2)
            Text("Full catalog — everything ever purchased, OCR-normalized")
                .font(.appSubheadline)
                .foregroundStyle(DesignTokens.secondaryLabel)
        }
    }
}

// MARK: - F-401..F-405 Add Product card

private struct AddProductCard: View {
    @ObservedObject var state: ProductsState
    @State private var name: String = ""
    @State private var category: String = "other"
    @State private var barcode: String = ""

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                Text("Add Product").font(.appHeadline)
                HStack(spacing: DesignTokens.Spacing.space2) {
                    TextField("e.g. Whole Wheat Bread", text: $name)
                        .textFieldStyle(.roundedBorder)
                        .frame(minWidth: 200)
                    Picker("", selection: $category) {
                        ForEach(ProductCategoryOptions.all, id: \.self) { c in
                            Text(ProductCategoryOptions.label(c)).tag(c)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 160)
                    TextField("Barcode (optional)", text: $barcode)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 180)
                    Button {
                        Task {
                            let ok = await state.createProduct(
                                name: name,
                                category: category,
                                barcode: barcode.isEmpty ? nil : barcode
                            )
                            if ok {
                                name = ""
                                barcode = ""
                            }
                        }
                    } label: {
                        Text("Add to Catalog")
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .keyboardShortcut(.return, modifiers: .command)
                    .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }
}

// MARK: - F-406..F-409 toolbar

private struct CatalogToolbar: View {
    @ObservedObject var state: ProductsState

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space2) {
            Text("Catalog").font(.appHeadline)
            // F-406 count badge
            Text("\(state.total)")
                .font(.appCaption1.weight(.semibold))
                .padding(.horizontal, 8).padding(.vertical, 2)
                .background(DesignTokens.accentDim)
                .foregroundStyle(DesignTokens.accent)
                .clipShape(Capsule())

            Spacer()

            // F-407 search
            HStack(spacing: 4) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                TextField("Search products", text: Binding(
                    get: { state.searchQuery },
                    set: { state.setSearch($0) }
                ))
                .textFieldStyle(.plain)
                .frame(minWidth: 180, maxWidth: 280)
                if !state.searchQuery.isEmpty {
                    Button {
                        state.setSearch("")
                    } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(DesignTokens.tertiaryLabel)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(DesignTokens.surface2)
            .clipShape(Capsule())

            // F-408 sort
            Picker("Sort", selection: $state.sortMode) {
                ForEach(ProductsSort.allCases, id: \.self) { sort in
                    Text(sort.label).tag(sort)
                }
            }
            .pickerStyle(.menu)
            .frame(width: 180)

            // F-409 refresh
            Button {
                Task { await state.loadCatalog() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.borderless)
            .help("Reload catalog")
        }
    }
}

// MARK: - F-410 category chip row

private struct CategoryChipRow: View {
    @ObservedObject var state: ProductsState

    var body: some View {
        let categories: [String] = Array(Set(state.products.compactMap {
            ($0.category ?? "").lowercased().isEmpty ? nil : ($0.category ?? "").lowercased()
        })).sorted()
        if categories.isEmpty {
            EmptyView()
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    chip(name: "All", active: state.categoryFilter.isEmpty) {
                        state.clearCategoryFilters()
                    }
                    ForEach(categories, id: \.self) { cat in
                        chip(
                            name: ProductCategoryOptions.label(cat),
                            active: state.categoryFilter.contains(cat)
                        ) {
                            state.toggleCategoryFilter(cat)
                        }
                    }
                }
            }
        }
    }

    private func chip(name: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
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

// MARK: - F-411 / F-412 / F-413 / F-430 catalog body

private struct CatalogBody: View {
    @ObservedObject var state: ProductsState
    @Binding var expandedGroupIds: Set<String>

    var body: some View {
        if state.isLoading && state.products.isEmpty {
            // F-411 loading
            EmptyStateView(systemImage: "hourglass", title: "Loading…")
                .frame(height: 200)
        } else if let err = state.lastError, state.products.isEmpty {
            // F-412 error
            EmptyStateView(systemImage: "exclamationmark.triangle", title: "Could not load products.", subtitle: err)
                .frame(height: 200)
        } else {
            let categoryGroups = state.groupedProducts()
            if categoryGroups.isEmpty {
                // F-430 empty
                EmptyStateView(
                    systemImage: "barcode",
                    title: state.searchQuery.isEmpty ? "No products yet." : "No products match this search."
                )
                .frame(height: 200)
            } else {
                // F-413 product groups list — single-column vertical stack (matches
                // web's `inv-tiles` flex-column layout in `renderProductTiles`).
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.space4) {
                    ForEach(categoryGroups) { catGroup in
                        VStack(alignment: .leading, spacing: 6) {
                            // 🏷️ Other · N products — matches web `inv-group-header`
                            Text("🏷️ \(ProductCategoryOptions.label(catGroup.category)) · \(catGroup.groups.count) product\(catGroup.groups.count == 1 ? "" : "s")")
                                .font(.appCallout.weight(.semibold))
                                .foregroundStyle(DesignTokens.label)
                                .padding(.bottom, 4)
                            VStack(spacing: 8) {
                                ForEach(catGroup.groups) { group in
                                    ProductTile(
                                        group: group,
                                        state: state,
                                        isExpanded: expandedGroupIds.contains(group.key)
                                    ) {
                                        if expandedGroupIds.contains(group.key) {
                                            expandedGroupIds.remove(group.key)
                                        } else {
                                            expandedGroupIds.insert(group.key)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

// MARK: - F-413 / F-414..F-419 product tile (web `_buildProductTile` clone —
// vertical stack of compact rows, no leading thumb; optional image strip on top
// only when `latest_snapshot` is present).

private struct ProductTile: View {
    let group: ProductGroup
    @ObservedObject var state: ProductsState
    @EnvironmentObject private var appState: AppState
    let isExpanded: Bool
    let onToggleExpand: () -> Void

    var body: some View {
        let primary = group.primaryItem
        let isLow = (primary?.manualLow ?? false) || (primary?.isLow ?? false)

        VStack(alignment: .leading, spacing: 6) {
            // Optional image strip — only when snapshot exists (matches web's
            // `if (imageUrl && isAdmin)` gate; mac shows for any user when image
            // is loaded so non-admin users still see their own uploads).
            if let snap = primary?.latestSnapshot, snap.imageUrl != nil {
                ProductTileImageStrip(snapshot: snap, alt: group.family)
            }

            // Head row: category label LEFT + Low chip + ×count RIGHT
            HStack(spacing: 6) {
                Text(ProductCategoryOptions.label(group.displayCategory))
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                if isLow {
                    Text("Low")
                        .font(.appCaption2.weight(.semibold))
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(DesignTokens.warningDim)
                        .foregroundStyle(DesignTokens.warning)
                        .clipShape(Capsule())
                }
                Spacer()
                Text("×\(group.count)")
                    .font(.appCaption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }

            // Name
            HStack(spacing: 4) {
                if primary?.isRegularUse == true {
                    Text("⭐").font(.appCallout)
                }
                Text(group.family)
                    .font(.appCallout.weight(.semibold))
                    .foregroundStyle(DesignTokens.label)
                    .lineLimit(2)
            }

            // Meta: 📅 date + variant examples
            if let last = primary?.lastPurchaseDate {
                Text("📅 \(last)")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            if group.count > 1 {
                Text(group.examples.prefix(2).joined(separator: ", ") + (group.count > 2 ? " …" : ""))
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }

            // Actions row — small icon buttons (matches web `inv-tile-actions`).
            // Order mirrors web: ✎  🛒  ✨(admin only when no image)  🗑  [▾count]
            if let primary {
                HStack(spacing: 4) {
                    iconButton(systemName: "pencil", tint: DesignTokens.accent, help: "Edit") {
                        Task { await state.openEdit(primary) }
                    }
                    iconButton(systemName: "cart.badge.plus", tint: DesignTokens.accent, help: "Add to shopping list") {
                        Task {
                            await ShoppingState.shared.add(
                                productName: primary.name,
                                quantity: 1,
                                source: "product",
                                productId: primary.id
                            )
                        }
                    }
                    if appState.currentUser?.isAdmin == true,
                       primary.latestSnapshot?.imageUrl == nil {
                        iconButton(systemName: "sparkles", tint: DesignTokens.warning, help: "AI enrich") {
                            Task { await state.enhanceProduct(id: primary.id) }
                        }
                    }
                    iconButton(systemName: "chart.line.uptrend.xyaxis", tint: DesignTokens.secondaryLabel, help: "Price history") {
                        Task { await state.openPriceHistory(primary) }
                    }
                    Spacer()
                    if group.count > 1 {
                        Button(action: onToggleExpand) {
                            Label("\(group.count)", systemImage: isExpanded ? "chevron.up" : "chevron.down")
                                .font(.appCaption2.weight(.semibold))
                                .padding(.horizontal, 6).padding(.vertical, 3)
                        }
                        .buttonStyle(.borderless)
                        .help("Show variants")
                    }
                    iconButton(systemName: "trash", tint: DesignTokens.error, help: "Delete") {
                        Task { await state.deleteProduct(primary) }
                    }
                }
                .contextMenu {
                    Button("Edit") { Task { await state.openEdit(primary) } }
                    Button("Add to shopping list") {
                        Task {
                            await ShoppingState.shared.add(
                                productName: primary.name,
                                quantity: 1,
                                source: "product",
                                productId: primary.id
                            )
                        }
                    }
                    Button("Price history") { Task { await state.openPriceHistory(primary) } }
                    if appState.currentUser?.isAdmin == true {
                        Button("Run AI enhance") { Task { await state.enhanceProduct(id: primary.id) } }
                    }
                    Divider()
                    Button("Delete", role: .destructive) {
                        Task { await state.deleteProduct(primary) }
                    }
                }
            }

            if isExpanded && group.count > 1 {
                VStack(alignment: .leading, spacing: 4) {
                    Divider().padding(.vertical, 2)
                    ForEach(group.items) { item in
                        VariantRow(item: item, state: state)
                    }
                }
            }
        }
        .padding(10)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radius.card)
                .stroke(isLow ? DesignTokens.warning.opacity(0.4) : DesignTokens.border, lineWidth: 0.5)
        )
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

/// Optional top image strip — matches web's `inv-tile-img` band.
private struct ProductTileImageStrip: View {
    let snapshot: ProductLatestSnapshot
    let alt: String

    private var resolvedURL: URL? {
        guard let path = snapshot.imageUrl, !path.isEmpty else { return nil }
        let base = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                ?? AppConstants.defaultAPIBaseURL
        return URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                   + (path.hasPrefix("/") ? path : "/" + path))
    }

    var body: some View {
        if let url = resolvedURL {
            KFImage(url)
                .requestModifier(ImageCache.tokenModifier)
                .resizable()
                .scaledToFill()
                .frame(height: 120)
                .frame(maxWidth: .infinity)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }
}

private struct VariantRow: View {
    let item: CatalogProduct
    @ObservedObject var state: ProductsState

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text(item.name).font(.appCaption1.weight(.semibold))
                if item.manualLow == true || item.isLow == true {
                    Text("Low")
                        .font(.appCaption2.weight(.semibold))
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(DesignTokens.warningDim)
                        .foregroundStyle(DesignTokens.warning)
                        .clipShape(Capsule())
                }
                Spacer()
            }
            let meta = [item.defaultSizeLabel, item.lastPurchaseDate.map { "Bought \($0)" }]
                .compactMap { $0 }.filter { !$0.isEmpty }
            if !meta.isEmpty {
                Text(meta.joined(separator: " · "))
                    .font(.appCaption2)
                    .foregroundStyle(DesignTokens.tertiaryLabel)
            }
            HStack(spacing: 6) {
                Button { Task { await state.openEdit(item) } } label: {
                    Label("Edit", systemImage: "pencil").font(.appCaption2)
                }
                .buttonStyle(.borderless)
                Button {
                    Task {
                        await ShoppingState.shared.add(
                            productName: item.name,
                            quantity: 1,
                            source: "product",
                            productId: item.id
                        )
                    }
                } label: {
                    Label("Add", systemImage: "cart.badge.plus").font(.appCaption2)
                }
                .buttonStyle(.borderless)
                Button { Task { await state.openPriceHistory(item) } } label: {
                    Label("Prices", systemImage: "chart.line.uptrend.xyaxis").font(.appCaption2)
                }
                .buttonStyle(.borderless)
                Spacer()
                Button { Task { await state.deleteProduct(item) } } label: {
                    Image(systemName: "trash")
                        .foregroundStyle(DesignTokens.error)
                }
                .buttonStyle(.borderless)
                .help("Delete variant")
            }
        }
        .padding(8)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private struct ProductThumb: View {
    let snapshot: ProductLatestSnapshot?
    let fallback: String
    var size: CGFloat = 56

    private var resolvedURL: URL? {
        guard let path = snapshot?.imageUrl, !path.isEmpty else { return nil }
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
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var placeholder: some View {
        ZStack {
            Rectangle().fill(DesignTokens.surface2)
            Text(initials).font(.appCaption1.weight(.semibold)).foregroundStyle(DesignTokens.secondaryLabel)
        }
        .frame(width: size, height: size)
    }
    private var initials: String {
        let parts = fallback.split(separator: " ").prefix(2)
        return parts.map { $0.first.map(String.init) ?? "" }.joined()
    }
}

// MARK: - F-415 / F-416 / F-428 / F-429 edit sheet

private struct EditProductSheet: View {
    @ObservedObject var state: ProductsState
    let product: CatalogProduct
    @State private var name: String = ""
    @State private var category: String = "other"
    @State private var defaultUnit: String = "each"
    @State private var defaultSizeLabel: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            HStack {
                Text("Edit product").font(.appTitle3)
                Spacer()
                Button { state.closeEdit() } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(DesignTokens.tertiaryLabel)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.cancelAction)
            }
            // Name + photo row
            VStack(alignment: .leading, spacing: 4) {
                Text("Name").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                HStack(spacing: 8) {
                    TextField("Product name", text: $name)
                        .textFieldStyle(.roundedBorder)
                    Button {
                        Task { await pickAndUploadPhoto() }
                    } label: {
                        Image(systemName: "camera.fill")
                            .padding(.horizontal, 8).padding(.vertical, 4)
                    }
                    .buttonStyle(.borderedProminent)
                    .help("Upload a product photo")
                }
            }
            // Photo gallery
            if !state.photosForEdit.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Photos").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(Array(state.photosForEdit.enumerated()), id: \.element.id) { idx, snap in
                                SnapshotGalleryCell(
                                    snap: snap,
                                    isPrimary: idx == 0,
                                    onTap: {
                                        guard idx != 0 else { return }
                                        Task { await state.promoteSnapshot(snap) }
                                    },
                                    onDelete: { Task { await state.deleteSnapshot(snap) } }
                                )
                            }
                        }
                    }
                }
            }
            // Category + unit
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Category").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    Picker("", selection: $category) {
                        ForEach(ProductCategoryOptions.all, id: \.self) { c in
                            Text(ProductCategoryOptions.label(c)).tag(c)
                        }
                    }
                    .pickerStyle(.menu)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("Default unit").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    TextField("each", text: $defaultUnit).textFieldStyle(.roundedBorder)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("Size label").font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                    TextField("e.g. 18 count, 1 gal", text: $defaultSizeLabel).textFieldStyle(.roundedBorder)
                }
            }
            HStack {
                Spacer()
                Button("Cancel") { state.closeEdit() }
                    .buttonStyle(GhostButtonStyle())
                    .keyboardShortcut(.cancelAction)
                Button("Save") {
                    Task {
                        await state.updateProduct(
                            id: product.id,
                            body: ProductUpdateBody(
                                name: name == product.name ? nil : name,
                                category: category == (product.category ?? "other") ? nil : category,
                                barcode: nil,
                                defaultUnit: defaultUnit == (product.defaultUnit ?? "each") ? nil : defaultUnit,
                                defaultSizeLabel: defaultSizeLabel == (product.defaultSizeLabel ?? "")
                                    ? nil
                                    : defaultSizeLabel
                            )
                        )
                        state.closeEdit()
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .keyboardShortcut(.defaultAction)
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 520, idealWidth: 600, minHeight: 380)
        .onAppear {
            name = product.displayLabel
            category = product.category ?? "other"
            defaultUnit = product.defaultUnit ?? "each"
            defaultSizeLabel = product.defaultSizeLabel ?? ""
        }
    }

    private func pickAndUploadPhoto() async {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.jpeg, .png, .heic, .heif, .gif, .webP, .image]
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            await state.uploadSnapshot(productId: product.id, fileURL: url)
        }
    }
}

private struct SnapshotGalleryCell: View {
    let snap: SnapshotReviewItem
    let isPrimary: Bool
    let onTap: () -> Void
    let onDelete: () -> Void

    private var resolvedURL: URL? {
        guard let path = snap.imageUrl, !path.isEmpty else { return nil }
        let base = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                ?? AppConstants.defaultAPIBaseURL
        return URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                   + (path.hasPrefix("/") ? path : "/" + path))
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Button(action: onTap) {
                Group {
                    if let url = resolvedURL {
                        KFImage(url)
                            .requestModifier(ImageCache.tokenModifier)
                            .resizable()
                            .scaledToFill()
                            .frame(width: 64, height: 64)
                            .clipped()
                    } else {
                        Color.gray.opacity(0.2).frame(width: 64, height: 64)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isPrimary ? DesignTokens.accent : Color.clear, lineWidth: 2)
                )
            }
            .buttonStyle(.plain)
            .help(isPrimary ? "Primary photo" : "Click to promote to primary")
            Button(action: onDelete) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.white)
                    .background(Circle().fill(.black.opacity(0.6)))
            }
            .buttonStyle(.plain)
            .padding(2)
            .help("Delete photo")
        }
    }
}

// MARK: - F-419 price history sheet

private struct PriceHistorySheet: View {
    @ObservedObject var state: ProductsState
    let product: CatalogProduct

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Price history").font(.appTitle3)
                    Text(product.displayLabel).font(.appCaption1).foregroundStyle(DesignTokens.tertiaryLabel)
                }
                Spacer()
                Button { state.closePriceHistory() } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(DesignTokens.tertiaryLabel)
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.cancelAction)
            }
            if let history = state.priceHistory {
                if history.prices.isEmpty {
                    EmptyStateView(systemImage: "chart.line.flattrend.xyaxis", title: "No price history yet.")
                        .frame(height: 160)
                } else {
                    HStack(spacing: 16) {
                        statCell("Avg", history.avgPrice)
                        statCell("Min", history.minPrice)
                        statCell("Max", history.maxPrice)
                    }
                    ScrollView {
                        VStack(spacing: 4) {
                            ForEach(Array(history.prices.enumerated()), id: \.offset) { _, pt in
                                HStack {
                                    Text(pt.date ?? "—")
                                        .font(.appCaption1.monospaced())
                                        .foregroundStyle(DesignTokens.secondaryLabel)
                                    Spacer()
                                    Text("$\(pt.price, specifier: "%.2f")")
                                        .font(.appCallout.weight(.semibold))
                                }
                                .padding(.vertical, 4)
                                .padding(.horizontal, 8)
                                .background(DesignTokens.surface)
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                            }
                        }
                    }
                }
            } else {
                ProgressView().frame(maxWidth: .infinity, minHeight: 160)
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(minWidth: 420, idealWidth: 480, minHeight: 320, idealHeight: 400)
    }

    private func statCell(_ label: String, _ value: Double?) -> some View {
        VStack(spacing: 2) {
            Text(label).font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
            Text(value.map { String(format: "$%.2f", $0) } ?? "—")
                .font(.appHeadline)
        }
        .frame(maxWidth: .infinity)
        .padding(8)
        .background(DesignTokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - F-422 / F-421 / F-414 / F-420 / F-423 Review Queue card (admin)

private struct ReviewQueueCard: View {
    @ObservedObject var state: ProductsState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Review Queue").font(.appHeadline)
                    Text("\(state.reviewItems.count)")
                        .font(.appCaption1.weight(.semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(DesignTokens.warningDim)
                        .foregroundStyle(DesignTokens.warning)
                        .clipShape(Capsule())
                    Spacer()
                    Picker("Status", selection: Binding(
                        get: { state.reviewStatusFilter },
                        set: { state.setReviewStatusFilter($0) }
                    )) {
                        Text("Pending").tag("pending")
                        Text("Resolved").tag("resolved")
                        Text("Dismissed").tag("dismissed")
                        Text("All").tag("all")
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 280)
                    Button {
                        Task { await state.bulkEnhanceReviewQueue() }
                    } label: {
                        Label("Bulk AI", systemImage: "sparkles")
                    }
                    .buttonStyle(GhostButtonStyle())
                    .help("Run AI enrichment on pending products (admin)")
                }
                Text("Use this queue to clean up OCR-heavy names. Correct them yourself, ask Gemini, or dismiss.")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)

                if state.isLoadingReview {
                    ProgressView().frame(maxWidth: .infinity, minHeight: 60)
                } else if state.reviewItems.isEmpty {
                    EmptyStateView(systemImage: "checkmark.seal", title: "No products need review for this filter.")
                        .frame(height: 140)
                } else {
                    VStack(spacing: 6) {
                        ForEach(state.reviewItems) { item in
                            ReviewRow(item: item, state: state)
                        }
                    }
                }
            }
        }
    }
}

private struct ReviewRow: View {
    let item: CatalogProduct
    @ObservedObject var state: ProductsState

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(item.name).font(.appCallout.weight(.semibold))
                Spacer()
                Text(item.reviewState ?? "pending")
                    .font(.appCaption2.weight(.semibold))
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(stateColor(item.reviewState).opacity(0.18))
                    .foregroundStyle(stateColor(item.reviewState))
                    .clipShape(Capsule())
            }
            HStack(spacing: 6) {
                Text("Raw:").font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                Text(item.rawName ?? item.name).font(.appCaption2).foregroundStyle(DesignTokens.tertiaryLabel)
                if let cat = item.category {
                    Text("·").foregroundStyle(DesignTokens.tertiaryLabel)
                    Text(ProductCategoryOptions.label(cat))
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
                if let last = item.lastPurchaseDate {
                    Text("· Last \(last)")
                        .font(.appCaption2)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
            }
            HStack(spacing: 6) {
                TextField("Enter final human-readable name", text: Binding(
                    get: { state.reviewDrafts[item.id] ?? item.name },
                    set: { state.reviewDrafts[item.id] = $0 }
                ))
                .textFieldStyle(.roundedBorder)
                Button("Save") { Task { await state.saveReviewedProduct(id: item.id) } }
                    .buttonStyle(PrimaryButtonStyle())
                Button {
                    Task { await state.enhanceProduct(id: item.id) }
                } label: { Label("Gemini", systemImage: "sparkles") }
                .buttonStyle(GhostButtonStyle())
                .help("Run AI enrichment")
                Button("Dismiss") {
                    Task { await state.setReviewState(id: item.id, state: "dismissed") }
                }
                .buttonStyle(GhostButtonStyle())
                Button("Resolve") {
                    Task { await state.setReviewState(id: item.id, state: "resolved") }
                }
                .buttonStyle(GhostButtonStyle())
            }
        }
        .padding(10)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func stateColor(_ state: String?) -> Color {
        switch state ?? "pending" {
        case "resolved":  return DesignTokens.success
        case "dismissed": return DesignTokens.tertiaryLabel
        default:          return DesignTokens.warning
        }
    }
}

// MARK: - F-426 / F-427 Snapshot Review card (admin)

private struct SnapshotReviewCard: View {
    @ObservedObject var state: ProductsState

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
                HStack {
                    Text("Snapshot Review").font(.appHeadline)
                    Text("\(state.snapshotReviewItems.count)")
                        .font(.appCaption1.weight(.semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(DesignTokens.warningDim)
                        .foregroundStyle(DesignTokens.warning)
                        .clipShape(Capsule())
                    Spacer()
                    Button {
                        Task { await state.loadSnapshotReviewQueue() }
                    } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.borderless)
                    .help("Reload snapshot queue")
                }
                Text("Link captured photos to products, or archive ones that aren't useful.")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.tertiaryLabel)

                if state.isLoadingSnapshotReview {
                    ProgressView().frame(maxWidth: .infinity, minHeight: 60)
                } else if state.snapshotReviewItems.isEmpty {
                    EmptyStateView(systemImage: "camera", title: "No pending item photos right now.")
                        .frame(height: 140)
                } else {
                    VStack(spacing: 8) {
                        ForEach(state.snapshotReviewItems) { snap in
                            SnapshotReviewRow(snap: snap, state: state)
                        }
                    }
                }
            }
        }
    }
}

private struct SnapshotReviewRow: View {
    let snap: SnapshotReviewItem
    @ObservedObject var state: ProductsState

    private var resolvedURL: URL? {
        guard let path = snap.imageUrl, !path.isEmpty else { return nil }
        let base = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                ?? AppConstants.defaultAPIBaseURL
        return URL(string: base.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                   + (path.hasPrefix("/") ? path : "/" + path))
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Group {
                if let url = resolvedURL {
                    KFImage(url)
                        .requestModifier(ImageCache.tokenModifier)
                        .resizable()
                        .scaledToFill()
                } else {
                    Rectangle().fill(DesignTokens.surface)
                }
            }
            .frame(width: 130, height: 130)
            .clipped()
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .onTapGesture {
                if let url = resolvedURL { NSWorkspace.shared.open(url) }
            }
            .help("Click to open full image")

            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(snap.productName ?? snap.shoppingItemName ?? "Unlinked snapshot")
                        .font(.appCallout.weight(.semibold))
                    Spacer()
                    Text(snap.status ?? "pending")
                        .font(.appCaption2.weight(.semibold))
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(snap.status == "linked" ? DesignTokens.successDim : DesignTokens.warningDim)
                        .foregroundStyle(snap.status == "linked" ? DesignTokens.success : DesignTokens.warning)
                        .clipShape(Capsule())
                }
                let meta = [snap.storeName, snap.sourceContext.map { ProductCategoryOptions.label($0) }, snap.capturedAt, snap.notes]
                    .compactMap { $0 }.filter { !$0.isEmpty }
                if !meta.isEmpty {
                    Text(meta.joined(separator: " · "))
                        .font(.appCaption1)
                        .foregroundStyle(DesignTokens.tertiaryLabel)
                }
                HStack(spacing: 6) {
                    TextField("Product name", text: Binding(
                        get: { state.snapshotDrafts[snap.id]?.productName ?? "" },
                        set: { newValue in
                            var d = state.snapshotDrafts[snap.id] ?? .init(productName: "", category: "other")
                            d.productName = newValue
                            state.snapshotDrafts[snap.id] = d
                        }
                    ))
                    .textFieldStyle(.roundedBorder)
                    Picker("", selection: Binding(
                        get: { state.snapshotDrafts[snap.id]?.category ?? "other" },
                        set: { newValue in
                            var d = state.snapshotDrafts[snap.id] ?? .init(productName: "", category: "other")
                            d.category = newValue
                            state.snapshotDrafts[snap.id] = d
                        }
                    )) {
                        ForEach(ProductCategoryOptions.all, id: \.self) { c in
                            Text(ProductCategoryOptions.label(c)).tag(c)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(width: 140)
                }
                HStack(spacing: 6) {
                    Button("Link Product") { Task { await state.linkSnapshot(snap) } }
                        .buttonStyle(PrimaryButtonStyle())
                    Button("Open Photo") {
                        if let url = resolvedURL { NSWorkspace.shared.open(url) }
                    }
                    .buttonStyle(GhostButtonStyle())
                    Button("Archive", role: .destructive) {
                        Task { await state.archiveSnapshot(snap) }
                    }
                    .buttonStyle(DestructiveButtonStyle())
                    Spacer()
                }
            }
        }
        .padding(10)
        .background(DesignTokens.surface2)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

#Preview("ProductsView") {
    ProductsView()
        .environmentObject(AppState.shared)
        .environmentObject(Router.shared)
        .frame(width: 1100, height: 800)
}
