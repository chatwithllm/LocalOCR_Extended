import XCTest

final class InventoryFlowTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// ⌘2 jumps to the Inventory tab.
    func testCommandTwoActivatesInventoryTab() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-LocalOCR.hasCompletedOnboarding", "YES"]
        app.launch()

        let tryDemo = app.buttons["Try Demo Mode"]
        if tryDemo.waitForExistence(timeout: 3) {
            tryDemo.click()
        }

        app.typeKey("2", modifierFlags: .command)

        // Inventory navigationTitle text appears
        let title = app.staticTexts["Inventory"]
        XCTAssertTrue(title.waitForExistence(timeout: 3))
    }
}
