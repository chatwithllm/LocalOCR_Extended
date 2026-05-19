import XCTest
@testable import LocalOCR

/// Verifies DemoModeGate intercepts mutations at the API layer (veto §3 R-04).
@MainActor
final class DemoModeGateTests: XCTestCase {

    override func tearDown() {
        // Reset state so other tests aren't affected.
        AppState.shared.setDemoMode(false)
        super.tearDown()
    }

    func testGuardThrowsWhenDemoModeOn() {
        AppState.shared.setDemoMode(true)
        XCTAssertThrowsError(try DemoModeGate.guardMutation()) { error in
            guard case APIError.demoModeReadOnly = error else {
                return XCTFail("Expected demoModeReadOnly, got \(error)")
            }
        }
    }

    func testGuardPassesWhenDemoModeOff() {
        AppState.shared.setDemoMode(false)
        XCTAssertNoThrow(try DemoModeGate.guardMutation())
    }
}
