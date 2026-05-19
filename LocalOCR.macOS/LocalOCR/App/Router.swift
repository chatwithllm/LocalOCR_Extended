import Foundation
import SwiftUI

/// Coordinates tab selection, deep-link routing, and window-opening intents.
///
/// Phase 1: enum + empty methods. Real routing logic lands in Phase 5
/// (when URL scheme handling + global shortcuts are wired in).
@MainActor
final class Router: ObservableObject {

    static let shared = Router()

    // MARK: - Sidebar / tab destination

    enum TabDestination: String, CaseIterable, Identifiable {
        case dashboard
        case inventory
        case receipts
        case shopping
        case finance
        case restaurant
        case chat
        case medications

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

    // MARK: - Deep-link entry point — wired in Phase 5

    /// Handle `localocr://` URL invocations from Info.plist URL types.
    /// Phase 1: no-op stub.
    func handleURL(_ url: URL) {
        // TODO Phase 5: pattern-match url.host against AppConstants.URLHost cases.
    }

    /// Open the OCR Upload sheet over the main window, or as standalone panel
    /// if the main window is hidden. Phase 1: no-op stub.
    func openOCRUpload() {
        // TODO Phase 5.
    }
}
