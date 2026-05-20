import Foundation
import os.log

/// HTTP client backbone for LocalOCR macOS.
///
/// Auth strategy per VETO_RESOLUTION_PATCH §2:
///   - Initial login: POST /auth/login → Set-Cookie: session (HTTPCookieStorage.shared)
///   - Once paired: every request carries `X-Trusted-Device-Token: <token>` (from Keychain)
///   - On 401: post `Notification.authSessionExpired` so AuthState can re-auth
///
/// No CSRF token is attached (VETO_RESOLUTION_PATCH §1 — Flask backend has no CSRFProtect).
final class APIClient {

    static let shared = APIClient()

    private let session: URLSession
    private let keychain = KeychainStore()
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "networking")

    /// Reads the base URL directly from UserDefaults so APIClient stays free of MainActor hops.
    /// PreferencesStore is the single writer; APIClient is one of many readers.
    private var baseURL: URL {
        let stored = UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                  ?? AppConstants.defaultAPIBaseURL
        return URL(string: stored) ?? URL(string: AppConstants.defaultAPIBaseURL)!
    }

    init() {
        let config = URLSessionConfiguration.default
        config.httpCookieAcceptPolicy = .always
        config.httpShouldSetCookies = true
        config.httpCookieStorage = HTTPCookieStorage.shared
        config.requestCachePolicy = .useProtocolCachePolicy
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        self.session = URLSession(configuration: config)
    }

    // MARK: - Public API

    /// Standard JSON request — decode to a Codable type.
    @discardableResult
    func request<Response: Decodable>(
        _ method: HTTPMethod,
        path: String,
        query: [URLQueryItem] = [],
        jsonBody: Encodable? = nil,
        as: Response.Type = Response.self
    ) async throws -> Response {
        let data = try await rawRequest(method, path: path, query: query, jsonBody: jsonBody)
        if Response.self == EmptyResponse.self {
            return EmptyResponse() as! Response
        }
        do {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            decoder.dateDecodingStrategy = .iso8601
            return try decoder.decode(Response.self, from: data)
        } catch {
            logger.error("Decode failure for \(path, privacy: .public): \(error.localizedDescription, privacy: .public)")
            throw APIError.decoding(underlying: error)
        }
    }

    /// Fire-and-forget request (no parsed response body).
    func request(
        _ method: HTTPMethod,
        path: String,
        query: [URLQueryItem] = [],
        jsonBody: Encodable? = nil
    ) async throws {
        _ = try await rawRequest(method, path: path, query: query, jsonBody: jsonBody)
    }

    /// Raw bytes — used for image downloads and CSV exports.
    func rawRequest(
        _ method: HTTPMethod,
        path: String,
        query: [URLQueryItem] = [],
        jsonBody: Encodable? = nil
    ) async throws -> Data {
        let request = try buildRequest(method: method, path: path, query: query, jsonBody: jsonBody)
        let (data, response) = try await session.data(for: request)
        return try dispatch(data: data, response: response, path: path)
    }

    /// Multipart form-data upload — used by `/product-snapshots/upload` and any
    /// future endpoint that takes a file plus form fields.
    ///
    /// `fields` are sent as plain text form parts. `file` is sent as one
    /// part named by `fileFieldName` with the supplied mime type.
    func multipartRequest<Response: Decodable>(
        path: String,
        fields: [String: String] = [:],
        fileFieldName: String,
        fileName: String,
        mimeType: String,
        fileData: Data,
        as: Response.Type = Response.self
    ) async throws -> Response {
        let boundary = "Boundary-\(UUID().uuidString)"
        var components = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        ) ?? URLComponents()
        guard let url = components.url else { throw APIError.invalidURL(path: path) }

        var request = URLRequest(url: url)
        request.httpMethod = HTTPMethod.post.rawValue
        request.setValue(userAgent(), forHTTPHeaderField: "User-Agent")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = keychain.loadDeviceToken() {
            request.setValue(token, forHTTPHeaderField: "X-Trusted-Device-Token")
        }
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        let crlf = "\r\n"
        for (key, value) in fields {
            body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(key)\"\(crlf)\(crlf)".data(using: .utf8)!)
            body.append("\(value)\(crlf)".data(using: .utf8)!)
        }
        body.append("--\(boundary)\(crlf)".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(fileFieldName)\"; filename=\"\(fileName)\"\(crlf)".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\(crlf)\(crlf)".data(using: .utf8)!)
        body.append(fileData)
        body.append("\(crlf)--\(boundary)--\(crlf)".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await session.data(for: request)
        let payload = try dispatch(data: data, response: response, path: path)
        if Response.self == EmptyResponse.self {
            return EmptyResponse() as! Response
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .iso8601
        do {
            return try decoder.decode(Response.self, from: payload)
        } catch {
            logger.error("Decode failure for \(path, privacy: .public): \(error.localizedDescription, privacy: .public)")
            throw APIError.decoding(underlying: error)
        }
    }

    // MARK: - Internals

    private func buildRequest(method: HTTPMethod, path: String, query: [URLQueryItem], jsonBody: Encodable?) throws -> URLRequest {
        var components = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        ) ?? URLComponents()
        if !query.isEmpty {
            components.queryItems = (components.queryItems ?? []) + query
        }
        guard let url = components.url else {
            throw APIError.invalidURL(path: path)
        }

        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.setValue(userAgent(), forHTTPHeaderField: "User-Agent")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        if let token = keychain.loadDeviceToken() {
            request.setValue(token, forHTTPHeaderField: "X-Trusted-Device-Token")
        }

        if let jsonBody {
            let encoder = JSONEncoder()
            encoder.keyEncodingStrategy = .convertToSnakeCase
            encoder.dateEncodingStrategy = .iso8601
            request.httpBody = try encoder.encode(AnyEncodable(jsonBody))
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        return request
    }

    private func dispatch(data: Data, response: URLResponse, path: String) throws -> Data {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.transport
        }

        switch http.statusCode {
        case 200..<300:
            return data
        case 401:
            logger.warning("401 on \(path, privacy: .public) — posting authSessionExpired")
            NotificationCenter.default.post(name: .authSessionExpired, object: nil)
            throw APIError.unauthorized
        case 403:
            throw APIError.forbidden(message: serverErrorMessage(data))
        case 404:
            throw APIError.notFound
        case 422:
            throw APIError.validation(message: serverErrorMessage(data))
        case 500..<600:
            throw APIError.server(statusCode: http.statusCode, message: serverErrorMessage(data))
        default:
            throw APIError.unexpected(statusCode: http.statusCode, message: serverErrorMessage(data))
        }
    }

    private func serverErrorMessage(_ data: Data) -> String? {
        struct ErrorEnvelope: Decodable {
            let error: String?
            let message: String?
            let detail: String?
        }
        if let env = try? JSONDecoder().decode(ErrorEnvelope.self, from: data) {
            return env.error ?? env.message ?? env.detail
        }
        return String(data: data, encoding: .utf8)?.prefix(200).description
    }

    private func userAgent() -> String {
        let appVersion = (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String) ?? "1.0.0"
        let osVersion = ProcessInfo.processInfo.operatingSystemVersionString
        return "LocalOCR-macOS/\(appVersion) (\(osVersion))"
    }
}

// MARK: - Supporting types

enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case patch = "PATCH"
    case delete = "DELETE"
}

/// Placeholder Decodable for endpoints with no parsed return.
struct EmptyResponse: Codable, Equatable {}

enum APIError: LocalizedError {
    case invalidURL(path: String)
    case transport
    case unauthorized
    case forbidden(message: String?)
    case notFound
    case validation(message: String?)
    case server(statusCode: Int, message: String?)
    case unexpected(statusCode: Int, message: String?)
    case decoding(underlying: Error)
    case demoModeReadOnly

    var errorDescription: String? {
        switch self {
        case .invalidURL(let p):           return "Invalid URL for \(p)"
        case .transport:                   return "Cannot reach server."
        case .unauthorized:                return "Your session has expired. Please sign in again."
        case .forbidden(let m):            return m ?? "You don't have permission for that action."
        case .notFound:                    return "Resource not found."
        case .validation(let m):           return m ?? "The data is invalid."
        case .server(let code, let m):     return m ?? "Server error (\(code))."
        case .unexpected(let code, let m): return m ?? "Unexpected response (\(code))."
        case .decoding:                    return "Couldn't read server response."
        case .demoModeReadOnly:            return "Demo mode is read-only. Sign in to save changes."
        }
    }
}

/// Erases concrete Encodable conformance so we can carry `Encodable?` through APIClient
/// without making every endpoint generic in its body type.
private struct AnyEncodable: Encodable {
    let wrapped: Encodable
    init(_ wrapped: Encodable) { self.wrapped = wrapped }
    func encode(to encoder: Encoder) throws { try wrapped.encode(to: encoder) }
}
