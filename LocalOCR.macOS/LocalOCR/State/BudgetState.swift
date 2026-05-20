import Foundation
import os.log

// F-1400..F-1427 — Household Budget state.

@MainActor
final class BudgetState: ObservableObject {

    static let shared = BudgetState()

    @Published var month: String {
        didSet { UserDefaults.standard.set(month, forKey: Defaults.month) }
    }
    @Published var selectedCategory: String {
        didSet {
            UserDefaults.standard.set(selectedCategory, forKey: Defaults.selectedCategory)
            // Re-prefill the amount field from the latest summary when the
            // category changes (mirrors web's loadBudgetEditorDefaults).
            seedAmountFromSelection()
        }
    }
    @Published var draftAmount: String = ""
    @Published var editorCollapsed: Bool {
        didSet { UserDefaults.standard.set(editorCollapsed, forKey: Defaults.editorCollapsed) }
    }
    @Published var targetsCollapsed: Bool {
        didSet { UserDefaults.standard.set(targetsCollapsed, forKey: Defaults.targetsCollapsed) }
    }
    @Published var historyCollapsed: Bool {
        didSet { UserDefaults.standard.set(historyCollapsed, forKey: Defaults.historyCollapsed) }
    }

    @Published private(set) var summary: BudgetCategorySummaryResponse?
    @Published private(set) var targets: [BudgetTargetRow] = []
    @Published private(set) var history: [BudgetHistoryRow] = []

    @Published var isLoadingSummary = false
    @Published var isLoadingHistory = false
    @Published var summaryError: String?
    @Published var historyError: String?

    enum Defaults {
        static let month            = "LocalOCR.budget.month"
        static let selectedCategory = "LocalOCR.budget.selectedCategory"
        static let editorCollapsed  = "LocalOCR.budget.editor.collapsed"
        static let targetsCollapsed = "LocalOCR.budget.targets.collapsed"
        static let historyCollapsed = "LocalOCR.budget.history.collapsed"
    }

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "budget")

    init(api: APIClient = .shared) {
        self.api = api
        let d = UserDefaults.standard
        if let m = d.string(forKey: Defaults.month), Self.isValidMonth(m) {
            self.month = m
        } else {
            self.month = Self.currentYearMonth()
        }
        self.selectedCategory = d.string(forKey: Defaults.selectedCategory) ?? "grocery"
        // Editor open by default on first load to match web's expanded UX.
        self.editorCollapsed  = d.bool(forKey: Defaults.editorCollapsed)
        // Web defaults Targets + History collapsed.
        if d.object(forKey: Defaults.targetsCollapsed) == nil {
            self.targetsCollapsed = true
        } else {
            self.targetsCollapsed = d.bool(forKey: Defaults.targetsCollapsed)
        }
        if d.object(forKey: Defaults.historyCollapsed) == nil {
            self.historyCollapsed = true
        } else {
            self.historyCollapsed = d.bool(forKey: Defaults.historyCollapsed)
        }
    }

    // MARK: - Refresh

    func refreshAll() async {
        await withTaskGroup(of: Void.self) { group in
            group.addTask { @MainActor in await self.loadSummary() }
            group.addTask { @MainActor in await self.loadTargetHistory() }
        }
    }

    func setMonth(_ m: String) {
        guard Self.isValidMonth(m) else { return }
        month = m
        Task { @MainActor in await self.refreshAll() }
    }

    // MARK: - Loads

    func loadSummary() async {
        isLoadingSummary = true
        defer { isLoadingSummary = false }
        do {
            let endpoint = BudgetEndpoint.categorySummary(month: month)
            let resp = try await api.request(
                .get, path: endpoint.path,
                query: endpoint.query,
                as: BudgetCategorySummaryResponse.self
            )
            summary = resp
            summaryError = nil
            seedAmountFromSelection()
            logger.info("loaded budget summary — \(resp.categories.count, privacy: .public) categories (active=\(resp.activeCount ?? 0, privacy: .public))")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            summaryError = (error as? APIError)?.errorDescription ?? "No budget set for this month."
            logger.warning("loadSummary failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadTargetHistory() async {
        isLoadingHistory = true
        defer { isLoadingHistory = false }
        do {
            let endpoint = BudgetEndpoint.targetHistory(month: month)
            let resp = try await api.request(
                .get, path: endpoint.path,
                query: endpoint.query,
                as: BudgetTargetHistoryResponse.self
            )
            targets = resp.currentTargets
            history = resp.history
            historyError = nil
            logger.info("loaded budget targets — \(resp.currentTargets.count, privacy: .public) current · \(resp.history.count, privacy: .public) history entries")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            historyError = (error as? APIError)?.errorDescription ?? "Could not load budget history."
        }
    }

    // MARK: - Mutations

    func saveBudget(amount: Double) async {
        do {
            try DemoModeGate.guardMutation()
            let body = BudgetSetMonthlyBody(
                month: month,
                budgetCategory: selectedCategory,
                domain: nil,
                budgetAmount: amount
            )
            let resp = try await api.request(
                .post, path: BudgetEndpoint.setMonthly.path,
                jsonBody: body,
                as: BudgetSetMonthlyResponse.self
            )
            ToastQueue.shared.push(Toast(
                message: resp.message ?? "Budget saved",
                severity: .success
            ))
            await refreshAll()
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch APIError.forbidden {
            ToastQueue.shared.push(Toast(message: "Only admins can update budgets.", severity: .error))
        } catch {
            let msg = (error as? APIError)?.errorDescription ?? "Could not save budget"
            ToastQueue.shared.push(Toast(message: msg, severity: .error))
        }
    }

    // MARK: - Derived

    var activeCategories: [BudgetCategoryStatus] {
        (summary?.categories ?? []).filter { $0.isActive }
    }

    var inactiveCategories: [BudgetCategoryStatus] {
        (summary?.categories ?? []).filter { !$0.isActive }
    }

    var totalSpent: Double {
        (summary?.categories ?? []).reduce(0) { $0 + $1.spent }
    }

    // MARK: - Helpers

    private func seedAmountFromSelection() {
        guard let row = summary?.categories.first(where: { $0.budgetCategory == selectedCategory }),
              row.budgetAmount > 0 else { return }
        draftAmount = String(format: "%g", row.budgetAmount)
    }

    static func currentYearMonth(_ now: Date = Date()) -> String {
        let cal = Calendar(identifier: .gregorian)
        let comps = cal.dateComponents([.year, .month], from: now)
        return String(format: "%04d-%02d", comps.year ?? 1970, comps.month ?? 1)
    }

    static func isValidMonth(_ s: String) -> Bool {
        guard s.count == 7,
              let dash = s.firstIndex(of: "-"),
              s.distance(from: s.startIndex, to: dash) == 4 else { return false }
        let y = Int(s[..<dash])
        let m = Int(s[s.index(after: dash)...])
        return y != nil && m != nil && (1...12).contains(m!) && y! >= 1970
    }
}
