import Foundation

struct Receipt: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let storeId: Int?
    let storeName: String?
    let totalAmount: Double
    let date: Date?
    let domain: String?           // "grocery" | "restaurant" | "expense"
    let transactionType: String?
    let userId: Int?
    let attributionUserId: Int?
    let imageUrl: String?
    let isConfirmed: Bool?
}
