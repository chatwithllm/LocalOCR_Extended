import Foundation
import os.log

@MainActor
final class ShoppingState: ObservableObject {

    static let shared = ShoppingState()

    @Published private(set) var items: [ShoppingListItem] = []
    @Published private(set) var isLoading = false
    @Published var lastError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "shopping")

    init(api: APIClient = .shared) {
        self.api = api
    }

    var pendingCount: Int { items.filter(\.isPending).count }

    func loadList() async {
        isLoading = true
        defer { isLoading = false }
        do {
            items = try await api.request(.get, path: ShoppingEndpoint.list.path, as: [ShoppingListItem].self)
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadList failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func add(productName: String, quantity: Double, source: String = "manual", productId: Int? = nil) async {
        do {
            try DemoModeGate.guardMutation()
            let body = ShoppingAddBody(productName: productName, quantity: quantity, source: source, productId: productId)
            let created: ShoppingListItem = try await api.request(.post, path: ShoppingEndpoint.list.path, jsonBody: body)
            items.append(created)
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
            try await api.request(.post, path: ShoppingEndpoint.toggle(id: id).path)
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
            try await api.request(.delete, path: ShoppingEndpoint.delete(id: id).path)
            items.removeAll { $0.id == id }
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func populateFromLowStock() async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: ShoppingEndpoint.populateFromLowStock.path)
            await loadList()
            ToastQueue.shared.push(Toast(message: "Populated shopping list from low-stock items", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }
}
