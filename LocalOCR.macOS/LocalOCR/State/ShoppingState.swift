import Foundation
import os.log

@MainActor
final class ShoppingState: ObservableObject {

    static let shared = ShoppingState()

    @Published private(set) var items: [ShoppingListItem] = []
    @Published private(set) var openCount: Int = 0
    @Published private(set) var purchasedCount: Int = 0
    @Published private(set) var estimatedTotal: Double = 0
    @Published private(set) var isLoading = false
    @Published var lastError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "shopping")

    init(api: APIClient = .shared) {
        self.api = api
    }

    var pendingCount: Int { openCount }

    func loadList() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await api.request(
                .get,
                path: ShoppingEndpoint.list.path,
                as: ShoppingListResponse.self
            )
            items = response.items
            openCount = response.openCount ?? items.filter(\.isPending).count
            purchasedCount = response.purchasedCount ?? items.filter { !$0.isPending }.count
            estimatedTotal = response.estimatedTotalCost ?? 0
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadList failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func add(productName: String, quantity: Double, source: String? = "manual", productId: Int? = nil) async {
        do {
            try DemoModeGate.guardMutation()
            let body = ShoppingAddBody(name: productName, quantity: quantity, source: source, productId: productId)
            try await api.request(.post, path: ShoppingEndpoint.addItem(name: productName, quantity: quantity, source: source ?? "manual", productId: productId).path, jsonBody: body)
            await loadList()
            ToastQueue.shared.push(Toast(message: "Added \"\(productName)\" to shopping list", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func togglePurchased(id: Int) async {
        do {
            try DemoModeGate.guardMutation()
            // Find the item; flip "open" <-> "purchased"
            guard let current = items.first(where: { $0.id == id }) else { return }
            let nextStatus = current.isPending ? "purchased" : "open"
            try await api.request(
                .put,
                path: ShoppingEndpoint.updateItem(id: id, status: nextStatus).path,
                jsonBody: ShoppingUpdateBody(status: nextStatus)
            )
            await loadList()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func remove(id: Int) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.delete, path: ShoppingEndpoint.deleteItem(id: id).path)
            items.removeAll { $0.id == id }
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    /// Server doesn't expose a single "populate from low stock" endpoint — this is a
    /// client-side helper that no-ops with a friendly toast for now.
    func populateFromLowStock() async {
        ToastQueue.shared.push(Toast(
            message: "Auto-populate runs server-side via the web app's Recommendations tab.",
            severity: .info
        ))
    }
}
