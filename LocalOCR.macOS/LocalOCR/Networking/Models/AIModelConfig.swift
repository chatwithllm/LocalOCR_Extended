import Foundation

struct AIModelConfig: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let name: String
    let provider: String
    let modelString: String
    let priceTier: String      // "free" | "paid" | "premium"
    let isEnabled: Bool
    let supportsVision: Bool
    let supportsPdf: Bool
    let inputCostPerMillion: Double?
}
