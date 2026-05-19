import XCTest

final class LoginFlowTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// Launch → LoginView visible (unless a session is auto-restored from Keychain).
    /// Skeleton check only — full flow requires a seeded backend.
    func testLaunchShowsAuthOrMainSurface() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-LocalOCR.hasCompletedOnboarding", "YES"]   // skip onboarding
        app.launch()

        // Either LoginView (Sign In button) or MainSplitView (sidebar Dashboard row) must render.
        let signInButton = app.buttons["Sign In"]
        let dashboardLabel = app.staticTexts["Dashboard"]

        let predicate = NSPredicate(format: "exists == true")
        let signInExpect = expectation(for: predicate, evaluatedWith: signInButton)
        let dashboardExpect = expectation(for: predicate, evaluatedWith: dashboardLabel)
        wait(for: [signInExpect, dashboardExpect], timeout: 5, enforceOrder: false)

        XCTAssertTrue(signInButton.exists || dashboardLabel.exists,
                      "Either LoginView or MainSplitView must be visible after launch")
    }

    /// Demo mode entry — clicking "Try Demo Mode" enters demoMode (DemoModeBanner visible).
    func testTryDemoModeShowsDemoBanner() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-LocalOCR.hasCompletedOnboarding", "YES"]
        app.launch()

        let tryDemo = app.buttons["Try Demo Mode"]
        guard tryDemo.waitForExistence(timeout: 3) else {
            // App auto-signed in via Keychain — skip this test.
            throw XCTSkip("App already signed in via Keychain; demo mode path not reachable.")
        }
        tryDemo.click()

        // DemoModeBanner has accessibility label "Demo mode banner. Changes will not be saved."
        let banner = app.otherElements["Demo mode banner. Changes will not be saved."]
        XCTAssertTrue(banner.waitForExistence(timeout: 3), "DemoModeBanner should be visible")
    }
}
