import Foundation

/// Receipt — matches the row shape emitted by GET /receipts in
/// src/backend/handle_receipt_upload.py.
///
/// Backend wraps in `{"receipts": [...], "count": N, "filters": {...}, "summary": {...}}`.
/// Decode list via `ReceiptsListResponse`.
struct Receipt: Codable, Identifiable, Equatable, Hashable {
    let id: Int
    let recordId: Int?
    let purchaseId: Int?
    let store: String?
    let total: Double?
    let signedTotal: Double?
    /// Server sends "YYYY-MM-DD" (not ISO8601). Decoded as String, parsed lazily.
    let date: String?
    let status: String?
    let ocrEngine: String?
    let confidence: Double?
    let receiptType: String?
    let transactionType: String?
    let attributionUserId: Int?
    let attributionUserName: String?
    let createdAt: String?
    let source: String?
    let linkedToPlaid: Bool?
    let imageUrl: String?

    var storeName: String? { store }
    var totalAmount: Double { total ?? 0 }
    var domain: String? { receiptType }

    var dateValue: Date? {
        guard let date else { return nil }
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        fmt.timeZone = TimeZone(identifier: "UTC")
        return fmt.date(from: date)
    }

    var isConfirmed: Bool { status == "approved" || status == "confirmed" }
}

struct ReceiptsListResponse: Codable, Equatable {
    let receipts: [Receipt]
    let count: Int?
}

/// Single-receipt detail response (GET /receipts/<id>).
/// Backend likely returns the receipt + items in a single envelope; this
/// captures the minimum we need.
struct ReceiptDetailResponse: Codable, Equatable {
    let receipt: Receipt?
    let items: [ReceiptItem]?
}
