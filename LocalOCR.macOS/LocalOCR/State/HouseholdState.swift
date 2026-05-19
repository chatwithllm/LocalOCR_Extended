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

    struct MembersResponse: Codable { let members: [HouseholdMember]? }
    struct UsersResponse: Codable { let users: [User]? }
    struct AIModelsResponse: Codable { let models: [AIModelConfig]? }

    func loadAll() async {
        async let m: () = loadMembers()
        async let u: () = loadUsers()
        async let a: () = loadAIModels()
        _ = await (m, u, a)
    }

    func loadMembers() async {
        do {
            // Try the envelope-wrapped shape first; fall back to bare array.
            let data = try await api.rawRequest(.get, path: AuthEndpoint.householdMembers.path)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            if let wrapped = try? decoder.decode(MembersResponse.self, from: data), let arr = wrapped.members {
                members = arr
            } else if let bare = try? decoder.decode([HouseholdMember].self, from: data) {
                members = bare
            }
        } catch {
            logger.error("loadMembers: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadUsers() async {
        do {
            let data = try await api.rawRequest(.get, path: AuthEndpoint.householdUsers.path)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            if let wrapped = try? decoder.decode(UsersResponse.self, from: data), let arr = wrapped.users {
                users = arr
            } else if let bare = try? decoder.decode([User].self, from: data) {
                users = bare
            }
        } catch {
            logger.error("loadUsers: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadAIModels() async {
        // Backend's AI-models endpoint shape varies — best-effort decode.
        do {
            let data = try await api.rawRequest(.get, path: "/ai-models")
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            if let wrapped = try? decoder.decode(AIModelsResponse.self, from: data), let arr = wrapped.models {
                aiModels = arr
            } else if let bare = try? decoder.decode([AIModelConfig].self, from: data) {
                aiModels = bare
            }
        } catch {
            // Non-fatal — leave aiModels empty
        }
    }
}
