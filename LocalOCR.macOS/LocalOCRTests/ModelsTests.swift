import XCTest
@testable import LocalOCR

/// JSON decode round-trips for every Codable model. Uses snake_case conversion
/// to match server emission.
final class ModelsTests: XCTestCase {

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }()

    func testUserDecodesFromSnakeCase() throws {
        let json = #"""
        {"id":1,"name":"Nik","email":"n@example.com","role":"admin","is_active":true,
         "google_sub":null,"allowed_pages":["dashboard"],"allow_write":true,
         "avatar_emoji":"👨","active_ai_model_config_id":3,"has_api_token":false}
        """#.data(using: .utf8)!
        let user = try decoder.decode(User.self, from: json)
        XCTAssertEqual(user.id, 1)
        XCTAssertEqual(user.role, "admin")
        XCTAssertTrue(user.isAdmin)
        XCTAssertEqual(user.activeAiModelConfigId, 3)
    }

    func testInventoryItemLowStockComputed() throws {
        let json = #"""
        {"id":42,"product_id":7,"product":null,"quantity":1.0,"location":"Fridge",
         "threshold":2.0,"manual_low":false,"is_active_window":true,
         "expires_at":null,"last_purchased_at":null}
        """#.data(using: .utf8)!
        let item = try decoder.decode(InventoryItem.self, from: json)
        XCTAssertTrue(item.isLowStock, "quantity <= threshold should report low stock")
    }

    func testInventoryItemManualLowOverridesThreshold() throws {
        let json = #"""
        {"id":1,"product_id":1,"product":null,"quantity":50.0,"location":null,
         "threshold":null,"manual_low":true,"is_active_window":true,
         "expires_at":null,"last_purchased_at":null}
        """#.data(using: .utf8)!
        let item = try decoder.decode(InventoryItem.self, from: json)
        XCTAssertTrue(item.isLowStock, "manual_low flag must override quantity/threshold")
    }

    func testReceiptDecodesISODate() throws {
        let json = #"""
        {"id":99,"store_id":3,"store_name":"Whole Foods","total_amount":47.23,
         "date":"2026-05-19T00:00:00Z","domain":"grocery","transaction_type":"card",
         "user_id":1,"attribution_user_id":2,"image_url":null,"is_confirmed":true}
        """#.data(using: .utf8)!
        let receipt = try decoder.decode(Receipt.self, from: json)
        XCTAssertEqual(receipt.totalAmount, 47.23, accuracy: 0.001)
        XCTAssertNotNil(receipt.date)
        XCTAssertEqual(receipt.isConfirmed, true)
    }

    func testShoppingListItemIsPending() throws {
        let pending = ShoppingListItem(id: 1, productId: nil, productName: "Milk",
                                       quantity: 1, status: "pending", source: "manual",
                                       note: nil, manualEstimatedPrice: nil, actualPrice: nil,
                                       createdAt: nil)
        XCTAssertTrue(pending.isPending)

        let purchased = ShoppingListItem(id: 2, productId: nil, productName: "Bread",
                                         quantity: 1, status: "purchased", source: "manual",
                                         note: nil, manualEstimatedPrice: nil, actualPrice: nil,
                                         createdAt: nil)
        XCTAssertFalse(purchased.isPending)
    }

    func testAuthMeResponseEncodesAndDecodes() throws {
        let json = #"""
        {"user":{"id":1,"name":"Mira","email":"m@example.com","role":"member",
                 "is_active":true,"google_sub":null,"allowed_pages":null,
                 "allow_write":true,"avatar_emoji":null,
                 "active_ai_model_config_id":null,"has_api_token":false},
         "household":{"id":7,"name":"Home","member_count":3}}
        """#.data(using: .utf8)!
        let me = try decoder.decode(AuthMeResponse.self, from: json)
        XCTAssertEqual(me.user.email, "m@example.com")
        XCTAssertEqual(me.household?.id, 7)
    }

    func testSpendingCategoryTotalIdMatchesCategoryName() {
        let cat = SpendingCategoryTotal(category: "Groceries", total: 420, receiptCount: 12)
        XCTAssertEqual(cat.id, "Groceries")
    }
}
