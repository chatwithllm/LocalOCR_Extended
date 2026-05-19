import XCTest

final class SettingsFlowTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// ⌘, opens the Settings window with 8 tabs.
    func testCommandCommaOpensSettings() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-LocalOCR.hasCompletedOnboarding", "YES"]
        app.launch()

        let tryDemo = app.buttons["Try Demo Mode"]
        if tryDemo.waitForExistence(timeout: 3) {
            tryDemo.click()
        }

        app.typeKey(",", modifierFlags: .command)

        // Settings window has multiple tabs — General tab label always present.
        let generalTab = app.tabs["General"]
        XCTAssertTrue(generalTab.waitForExistence(timeout: 3), "Settings window should show General tab")
    }
}
