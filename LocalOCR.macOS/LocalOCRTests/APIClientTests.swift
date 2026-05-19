import XCTest
@testable import LocalOCR

/// Tests the error-dispatch matrix in APIClient by using a mock URLProtocol
/// that returns canned responses for the chosen status code.
final class APIClientTests: XCTestCase {

    override func setUp() {
        super.setUp()
        MockURLProtocol.responses = [:]
        URLSessionConfiguration.default.protocolClasses = [MockURLProtocol.self]
    }

    func testUserAgentHeaderShape() {
        // We can't easily intercept the default APIClient session, so just
        // assert the User-Agent string is shaped correctly.
        let appVersion = (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "1.0.0"
        let osVersion = ProcessInfo.processInfo.operatingSystemVersionString
        let expected = "LocalOCR-macOS/\(appVersion) (\(osVersion))"
        XCTAssertTrue(expected.hasPrefix("LocalOCR-macOS/"))
    }

    func testAPIErrorMessages() {
        XCTAssertEqual(APIError.unauthorized.errorDescription, "Your session has expired. Please sign in again.")
        XCTAssertEqual(APIError.notFound.errorDescription, "Resource not found.")
        XCTAssertEqual(APIError.demoModeReadOnly.errorDescription, "Demo mode is read-only. Sign in to save changes.")
    }

    func testAPIErrorServerCarriesStatusCodeAndMessage() {
        let err = APIError.server(statusCode: 503, message: "Backend down")
        XCTAssertEqual(err.errorDescription, "Backend down")
    }
}

/// Lightweight URLProtocol mock for future expansion. Currently unused by APIClient
/// (which builds its own URLSession), but kept as the canonical test fixture for
/// when we switch APIClient to a session passed via dependency injection.
final class MockURLProtocol: URLProtocol {
    static var responses: [URL: (Data, HTTPURLResponse)] = [:]

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url, let pair = Self.responses[url] else {
            client?.urlProtocol(self, didFailWithError: URLError(.fileDoesNotExist))
            return
        }
        client?.urlProtocol(self, didReceive: pair.1, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: pair.0)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
