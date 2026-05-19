import AppKit
import SwiftUI
import Combine

/// NSStatusItem-backed menu bar icon with a popover showing low-stock count + quick actions.
@MainActor
final class MenuBarController: NSObject {

    static let shared = MenuBarController()

    private var statusItem: NSStatusItem?
    private var popover: NSPopover?
    private var lowStockObserver: AnyCancellable?
    private var prefsObserver: AnyCancellable?

    private override init() { super.init() }

    func install() {
        guard PreferencesStore.shared.menuBarIconEnabled else { return }
        guard statusItem == nil else { return }

        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = NSImage(systemSymbolName: "doc.text.viewfinder", accessibilityDescription: "LocalOCR")
        item.button?.action = #selector(togglePopover(_:))
        item.button?.target = self
        statusItem = item

        let pop = NSPopover()
        pop.contentSize = NSSize(width: 320, height: 360)
        pop.behavior = .transient
        pop.contentViewController = NSHostingController(
            rootView: MenuBarPopoverView()
                .environmentObject(AppState.shared)
                .environmentObject(Router.shared)
        )
        popover = pop

        // React to lowStockCount changes for badge text.
        lowStockObserver = AppState.shared.$lowStockCount
            .receive(on: DispatchQueue.main)
            .sink { [weak self] count in
                self?.updateBadge(count: count)
            }
    }

    func uninstall() {
        if let item = statusItem {
            NSStatusBar.system.removeStatusItem(item)
            statusItem = nil
        }
        popover = nil
        lowStockObserver = nil
    }

    @objc private func togglePopover(_ sender: NSStatusBarButton) {
        guard let popover, let button = statusItem?.button else { return }
        if popover.isShown {
            popover.performClose(sender)
        } else {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            popover.contentViewController?.view.window?.makeKey()
        }
    }

    private func updateBadge(count: Int) {
        statusItem?.button?.title = count > 0 ? " \(count)" : ""
    }
}
