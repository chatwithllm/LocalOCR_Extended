import Foundation
import os.log

@MainActor
final class HouseholdState: ObservableObject {

    static let shared = HouseholdState()

    @Published private(set) var members: [HouseholdMember] = []
    @Published private(set) var users: [User] = []
    @Published private(set) var aiModels: [AIModelConfig] = []

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "household")

    init(api: APIClient = .shared) {
        self.api = api
    }

    func loadAll() async {
        async let m: () = loadMembers()
        async let u: () = loadUsers()
        async let a: () = loadAIModels()
        _ = await (m, u, a)
    }

    func loadMembers() async {
        do {
            members = try await api.request(.get, path: HouseholdEndpoint.members.path, as: [HouseholdMember].self)
        } catch {
            logger.error("loadMembers: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadUsers() async {
        do {
            users = try await api.request(.get, path: HouseholdEndpoint.users.path, as: [User].self)
        } catch {
            logger.error("loadUsers: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadAIModels() async {
        do {
            aiModels = try await api.request(.get, path: HouseholdEndpoint.aiModels.path, as: [AIModelConfig].self)
        } catch {
            logger.error("loadAIModels: \(error.localizedDescription, privacy: .public)")
        }
    }
}
