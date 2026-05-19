import XCTest
@testable import LocalOCR
import KeychainAccess

/// Verifies Keychain read/write/delete for both credentials and device token.
/// Uses the same service identifiers the app uses; teardown wipes any test residue.
final class KeychainStoreTests: XCTestCase {

    override func tearDown() {
        // Ensure no test residue lingers in real Keychain after the run.
        KeychainStore().wipeAll()
        super.tearDown()
    }

    func testSaveAndLoadCredentialsRoundTrip() throws {
        let store = KeychainStore()
        let creds = KeychainStore.Credentials(email: "test@example.com", password: "p@ssw0rd!")
        try store.saveCredentials(creds)
        let loaded = store.loadCredentials()
        XCTAssertEqual(loaded?.email, "test@example.com")
        XCTAssertEqual(loaded?.password, "p@ssw0rd!")
    }

    func testDeleteCredentialsClearsStorage() throws {
        let store = KeychainStore()
        try store.saveCredentials(.init(email: "x@y.com", password: "abc"))
        store.deleteCredentials()
        XCTAssertNil(store.loadCredentials())
    }

    func testSaveAndLoadDeviceTokenRoundTrip() throws {
        let store = KeychainStore()
        let token = "trusted-device-abc-123"
        try store.saveDeviceToken(token)
        XCTAssertEqual(store.loadDeviceToken(), token)
    }

    func testDeleteDeviceTokenClearsStorage() throws {
        let store = KeychainStore()
        try store.saveDeviceToken("temp-token")
        store.deleteDeviceToken()
        XCTAssertNil(store.loadDeviceToken())
    }

    func testWipeAllClearsBothServices() throws {
        let store = KeychainStore()
        try store.saveCredentials(.init(email: "a@b.com", password: "p"))
        try store.saveDeviceToken("t")
        store.wipeAll()
        XCTAssertNil(store.loadCredentials())
        XCTAssertNil(store.loadDeviceToken())
    }
}
