import Foundation

/// Floor obligation (a.k.a. "fixed bill") — matches `_serialize` in
/// src/backend/handle_floor_obligations.py.
///
/// Backend wraps in `{"obligations": [...]}`. URL `/floor-obligations/` (note trailing slash).
struct FixedBill: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let label: String
    let expectedMonthlyAmount: Double
    let isActive: Bool
    let billProviderId: Int?
    let source: String?               // "bill_provider" | "manual"
    let createdAt: String?
    let updatedAt: String?
    let avg6mo: Double?
    let latestActual: Double?
    let providerCategory: String?

    /// Derived "payment status" for UI display — server doesn't emit one.
    /// Approximated from history: if latest actual is set, treat as paid;
    /// otherwise unpaid for the current month.
    var paymentStatus: String {
        latestActual != nil ? "paid" : "unpaid"
    }
}

struct ObligationsListResponse: Codable, Equatable {
    let obligations: [FixedBill]
}
