import Foundation
import SwiftUI

/// Coordinates tab selection, deep-link routing, and window-opening intents.
@MainActor
final class Router: ObservableObject {

    static let shared = Router()

    enum TabDestination: String, CaseIterable, Identifiable {
        case dashboard, inventory, receipts, shopping, kitchen, finance, restaurant, chat, medications
        var id: String { rawValue }
    }

    enum DetailDestination: Equatable {
        case none
        case receipt(Int)
        case inventoryItem(Int)
        case bill(Int)
    }

    @Published var activeTab: TabDestination = .dashboard
    @Published var activeDetailDestination: DetailDestination = .none
    @Published var activeSheet: Sheet?
    @Published var pendingDropFiles: [URL] = []

    enum Sheet: Identifiable {
        case ocrUpload
        case cashTransaction
        case shareQR
        case onboarding

        var id: String {
            switch self {
            case .ocrUpload:        return "ocrUpload"
            case .cashTransaction:  return "cashTransaction"
            case .shareQR:          return "shareQR"
            case .onboarding:       return "onboarding"
            }
        }
    }

    private init() {}

    // MARK: - Deep-link entry point

    /// Handle `localocr://` URL invocations from Info.plist URL types.
    func handleURL(_ url: URL) {
        guard url.scheme == AppConstants.urlScheme else { return }

        switch url.host {
        case AppConstants.URLHost.receipt:
            // localocr://receipt/<id>
            let pathParts = url.pathComponents.filter { $0 != "/" }
            if let first = pathParts.first, let id = Int(first) {
                activeTab = .receipts
                activeDetailDestination = .receipt(id)
            }
        case AppConstants.URLHost.upload:
            openOCRUpload()
        case AppConstants.URLHost.shopping:
            activeTab = .shopping
        case AppConstants.URLHost.inventory:
            activeTab = .inventory
        case AppConstants.URLHost.kitchen:
            activeTab = .kitchen
        case AppConstants.URLHost.oauthCallback:
            // localocr://oauth/google?state=...&code=...
            let comps = URLComponents(url: url, resolvingAgainstBaseURL: false)
            let state = comps?.queryItems?.first(where: { $0.name == "state" })?.value
            let code  = comps?.queryItems?.first(where: { $0.name == "code"  })?.value
            if let state, let code {
                Task { await AuthState.shared.completeGoogleOAuth(state: state, code: code) }
            }
        default:
            break
        }
    }

    func handleDroppedFiles(_ urls: [URL]) {
        let accepted = FileDropHandler.filter(urls)
        guard !accepted.isEmpty else { return }
        pendingDropFiles = accepted
        openOCRUpload()
    }

    func openOCRUpload() {
        NSApp.activate(ignoringOtherApps: true)
        NSApp.windows.first(where: { $0.title == "LocalOCR" })?.makeKeyAndOrderFront(nil)
        activeSheet = .ocrUpload
    }
}
