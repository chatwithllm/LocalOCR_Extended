import SwiftUI

/// Application menu commands per §3.3 + §5.4. Wires keyboard shortcuts to
/// Router actions. Phase 5 covers the highest-value subset; remaining
/// domain-specific menus land in later phase passes.
struct AppMenuCommands: Commands {
    @ObservedObject var router: Router

    var body: some Commands {
        // App menu — replace About with our custom panel
        CommandGroup(replacing: .appInfo) {
            Button("About LocalOCR") { AboutPanel.show() }
        }

        // File menu
        CommandGroup(replacing: .newItem) {
            Button("New Receipt Upload…") { router.openOCRUpload() }
                .keyboardShortcut("n", modifiers: .command)

            Button("New Cash Transaction") { router.activeSheet = .cashTransaction }
                .keyboardShortcut("n", modifiers: [.command, .control])

            Divider()

            Button("Open Receipt File…") {
                openReceiptFile()
            }
            .keyboardShortcut("o", modifiers: .command)
        }

        // View menu — tab navigation shortcuts
        CommandGroup(after: .toolbar) {
            Button("Dashboard")     { router.activeTab = .dashboard   }
                .keyboardShortcut("1", modifiers: .command)
            Button("Inventory")     { router.activeTab = .inventory   }
                .keyboardShortcut("2", modifiers: .command)
            Button("Receipts")      { router.activeTab = .receipts    }
                .keyboardShortcut("3", modifiers: .command)
            Button("Shopping")      { router.activeTab = .shopping    }
                .keyboardShortcut("4", modifiers: .command)
            Button("Kitchen")       { router.activeTab = .kitchen     }
                .keyboardShortcut("5", modifiers: .command)
            Button("Finance")       { router.activeTab = .finance     }
                .keyboardShortcut("6", modifiers: .command)
            Button("Restaurants")   { router.activeTab = .restaurant  }
                .keyboardShortcut("7", modifiers: .command)
            Button("AI Chat")       { router.activeTab = .chat        }
                .keyboardShortcut("8", modifiers: .command)
            Button("Medications")   { router.activeTab = .medications }
                .keyboardShortcut("9", modifiers: .command)
            Button("Products")      { router.activeTab = .products    }
                .keyboardShortcut("0", modifiers: .command)
            Button("Balances")      { router.activeTab = .balances    }
                .keyboardShortcut("-", modifiers: .command)
            Button("Contacts")      { router.activeTab = .contacts    }
                .keyboardShortcut("=", modifiers: .command)
            Button("Expenses")      { router.activeTab = .expenses    }
                .keyboardShortcut("e", modifiers: [.command, .shift])

            Divider()

            Button("Reload Data") {
                Task { await reloadCurrentTab() }
            }
            .keyboardShortcut("r", modifiers: .command)
        }

        // Help menu — features doc link
        CommandGroup(replacing: .help) {
            Button("LocalOCR Help") {
                if let url = URL(string: "\(UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL) ?? AppConstants.defaultAPIBaseURL)/features") {
                    NSWorkspace.shared.open(url)
                }
            }
            .keyboardShortcut("?", modifiers: .command)
        }
    }

    private func openReceiptFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.jpeg, .png, .heic, .heif, .pdf]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            router.handleDroppedFiles([url])
        }
    }

    @MainActor
    private func reloadCurrentTab() async {
        switch router.activeTab {
        case .dashboard:
            // RULE 3: `async let _ =` cancels its children on scope exit (I-6).
            // Use `withTaskGroup` so every reload actually completes before we
            // hand control back to the menu command.
            await withTaskGroup(of: Void.self) { group in
                group.addTask { @MainActor in await InventoryState.shared.loadInventory() }
                group.addTask { @MainActor in await ShoppingState.shared.loadList() }
                group.addTask { @MainActor in await FinanceState.shared.loadBills() }
            }
        case .inventory:    await InventoryState.shared.loadInventory()
        case .receipts:     await ReceiptsState.shared.loadList()
        case .shopping:     await ShoppingState.shared.loadList()
        case .kitchen:      await KitchenState.shared.refresh()
        case .products:     await ProductsState.shared.refresh()
        case .finance:      await FinanceState.shared.loadBills()
        case .balances:     await SharedDiningState.shared.loadBalances()
        case .contacts:     await SharedDiningState.shared.loadContacts()
        case .expenses:     await ExpensesState.shared.refresh()
        case .restaurant, .chat, .medications: break
        }
    }
}
