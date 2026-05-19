import Foundation
import os.log

@MainActor
final class InventoryState: ObservableObject {

    static let shared = InventoryState()

    @Published private(set) var items: [InventoryItem] = []
    @Published private(set) var isLoading = false
    @Published var lastError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "inventory")

    init(api: APIClient = .shared) {
        self.api = api
    }

    var categories: [String] {
        let set = Set(items.compactMap { $0.product?.category })
        return Array(set).sorted()
    }

    var lowStockItems: [InventoryItem] {
        items.filter { $0.isLowStock }
    }

    func loadInventory() async {
        isLoading = true
        defer { isLoading = false }
        do {
            items = try await api.request(.get, path: InventoryEndpoint.list.path, as: [InventoryItem].self)
            AppState.shared.setLowStockCount(lowStockItems.count)
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
            logger.error("loadInventory failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func adjustQuantity(id: Int, delta: Double) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: InventoryEndpoint.adjustQuantity(id: id, delta: delta).path,
                                  jsonBody: AdjustQuantityBody(delta: delta))
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func markLowStock(id: Int) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: InventoryEndpoint.markLowStock(id: id).path)
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }
}
