import XCTest
@testable import LocalOCR

@MainActor
final class RouterTests: XCTestCase {

    /// localocr://receipt/<id> → activeTab = .receipts AND detail = .receipt(<id>)
    func testReceiptDeepLink() {
        let router = Router.shared
        router.activeTab = .dashboard
        router.activeDetailDestination = .none

        router.handleURL(URL(string: "localocr://receipt/42")!)
        XCTAssertEqual(router.activeTab, .receipts)
        XCTAssertEqual(router.activeDetailDestination, .receipt(42))
    }

    /// localocr://shopping → activeTab = .shopping
    func testShoppingDeepLink() {
        let router = Router.shared
        router.activeTab = .dashboard
        router.handleURL(URL(string: "localocr://shopping")!)
        XCTAssertEqual(router.activeTab, .shopping)
    }

    /// localocr://inventory → activeTab = .inventory
    func testInventoryDeepLink() {
        let router = Router.shared
        router.activeTab = .dashboard
        router.handleURL(URL(string: "localocr://inventory")!)
        XCTAssertEqual(router.activeTab, .inventory)
    }

    /// localocr://unknown → no change to activeTab.
    func testUnknownHostDoesNotMutate() {
        let router = Router.shared
        router.activeTab = .finance
        router.handleURL(URL(string: "localocr://gibberish")!)
        XCTAssertEqual(router.activeTab, .finance)
    }

    /// Non-localocr scheme is ignored.
    func testForeignSchemeIgnored() {
        let router = Router.shared
        router.activeTab = .receipts
        router.handleURL(URL(string: "https://example.com/receipt/1")!)
        XCTAssertEqual(router.activeTab, .receipts)
    }

    /// handleDroppedFiles filters by UTType then activates upload sheet.
    func testDroppedFileFilteredAndOpensSheet() throws {
        let router = Router.shared
        router.activeSheet = nil

        let dir = FileManager.default.temporaryDirectory
        let pdf = dir.appendingPathComponent("test-receipt.pdf")
        try Data("PDF stub".utf8).write(to: pdf)
        defer { try? FileManager.default.removeItem(at: pdf) }

        let exe = dir.appendingPathComponent("not-an-image.bin")
        try Data("binary".utf8).write(to: exe)
        defer { try? FileManager.default.removeItem(at: exe) }

        router.handleDroppedFiles([exe, pdf])
        XCTAssertEqual(router.pendingDropFiles.count, 1, "only the PDF should pass FileDropHandler.filter")
        XCTAssertEqual(router.pendingDropFiles.first?.pathExtension, "pdf")
        XCTAssertEqual(router.activeSheet, .ocrUpload)
    }
}

extension Router.Sheet: Equatable {
    public static func == (lhs: Router.Sheet, rhs: Router.Sheet) -> Bool { lhs.id == rhs.id }
}
