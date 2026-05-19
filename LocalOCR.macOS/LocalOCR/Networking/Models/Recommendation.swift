import Foundation

/// Recommendation row from /recommendations (deals / seasonal / low-inventory).
struct Recommendation: Codable, Identifiable, Equatable, Hashable {
    var id: String { "\(reason ?? "?")-\(productName ?? "?")-\(productId ?? 0)" }
    let productId: Int?
    let productName: String?
    let displayName: String?
    let reason: String?               // "price_deal" | "seasonal" | "low_inventory" | ...
    let confidence: Double?
    let suggestedQuantity: Double?
    let category: String?
    let lastPrice: Double?
    let savings: Double?

    var label: String { displayName ?? productName ?? "Recommendation" }

    var badgeStyle: Badge.Style {
        switch reason {
        case "price_deal":     return .success
        case "seasonal":       return .info
        case "low_inventory":  return .warning
        default:               return .neutral
        }
    }

    var badgeLabel: String {
        switch reason {
        case "price_deal":     return "Deal"
        case "seasonal":       return "Seasonal"
        case "low_inventory":  return "Low"
        default:               return reason?.capitalized ?? "Tip"
        }
    }
}

struct RecommendationsResponse: Codable, Equatable {
    let recommendations: [Recommendation]
    let count: Int?
}
