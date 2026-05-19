import Foundation

/// Dashboard untagged-receipts banner data — matches
/// `_compute_attribution_stats` returned by GET /receipts/attribution-stats.
struct AttributionStats: Codable, Equatable {
    let untaggedCount: Int
    let taggedCount: Int
    let untaggedSampleIds: [Int]?
}
