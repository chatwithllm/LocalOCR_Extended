import AppKit
import Combine

/// Mirrors `AppState.lowStockCount` to the Dock tile badge (§4.6 Integration 7).
@MainActor
final class DockBadge {

    static let shared = DockBadge()

    private var observer: AnyCancellable?

    private init() {}

    func start() {
        observer = AppState.shared.$lowStockCount
            .receive(on: DispatchQueue.main)
            .sink { count in
                NSApplication.shared.dockTile.badgeLabel = count > 0 ? "\(count)" : nil
            }
    }
}
