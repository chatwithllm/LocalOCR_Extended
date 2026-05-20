import Foundation
import os.log

// F-1500..F-1526 — Contributions screen state.

@MainActor
final class ContributionsState: ObservableObject {

    static let shared = ContributionsState()

    @Published private(set) var summary: ContributionsSummaryResponse?
    @Published var isLoading = false
    @Published var lastError: String?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "contributions")

    init(api: APIClient = .shared) {
        self.api = api
    }

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let resp = try await api.request(
                .get, path: ContributionsEndpoint.summary.path,
                as: ContributionsSummaryResponse.self
            )
            summary = resp
            lastError = nil
            logger.info("loaded contributions — total=\(resp.summary.totalScore, privacy: .public) events=\(resp.recentEvents?.count ?? 0, privacy: .public) opps=\(resp.opportunities?.count ?? 0, privacy: .public)")
        } catch is CancellationError {
            return
        } catch {
            let ns = error as NSError
            if ns.domain == NSURLErrorDomain, ns.code == NSURLErrorCancelled { return }
            lastError = (error as? APIError)?.errorDescription ?? "Could not load contribution details."
            logger.warning("loadContributions failed: \(error.localizedDescription, privacy: .public)")
        }
    }
}
