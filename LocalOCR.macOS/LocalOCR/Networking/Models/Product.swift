import Foundation

struct Product: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String
    let rawName: String?
    let displayName: String?
    let brand: String?
    let size: String?
    let category: String?
    let barcode: String?
    let isRegularUse: Bool?
    let reviewState: String?
    let expectedShelfDays: Int?
    let imageUrl: String?
}
