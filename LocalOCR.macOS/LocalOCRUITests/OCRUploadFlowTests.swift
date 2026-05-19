import XCTest

final class OCRUploadFlowTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// ⌘N invokes the New Receipt Upload menu → OCRUploadView sheet appears.
    /// Skeleton check only — actual upload requires a seeded backend.
    func testCommandNOpensOCRUploadSheet() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-LocalOCR.hasCompletedOnboarding", "YES"]
        app.launch()

        // Enter demo mode first so we have a MainSplitView.
        let tryDemo = app.buttons["Try Demo Mode"]
        if tryDemo.waitForExistence(timeout: 3) {
            tryDemo.click()
        }

        // Fire ⌘N
        app.typeKey("n", modifierFlags: .command)

        // OCRUploadView header reads "New Receipt Upload"
        let header = app.staticTexts["New Receipt Upload"]
        XCTAssertTrue(header.waitForExistence(timeout: 3), "OCRUploadView header should appear")
    }
}
