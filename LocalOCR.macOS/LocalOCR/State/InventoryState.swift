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
        Array(Set(items.compactMap { $0.category })).sorted()
    }

    var lowStockItems: [InventoryItem] {
        items.filter { $0.isLowStock }
    }

    func loadInventory() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await api.request(
                .get,
                path: InventoryEndpoint.list.path,
                as: InventoryListResponse.self
            )
            items = response.inventory
            AppState.shared.setLowStockCount(lowStockItems.count)
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
            logger.error("loadInventory failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func consume(itemId: Int, delta: Double) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .put,
                path: InventoryEndpoint.consume(itemId: itemId, delta: delta).path,
                jsonBody: ConsumeBody(delta: delta)
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func markLow(productId: Int) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .put,
                path: InventoryEndpoint.markLow(productId: productId).path,
                jsonBody: MarkLowBody(manualLow: true)
            )
            await loadInventory()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }
}
