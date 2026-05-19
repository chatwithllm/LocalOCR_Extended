import Foundation
import os.log

@MainActor
final class ReceiptsState: ObservableObject {

    static let shared = ReceiptsState()

    @Published private(set) var receipts: [Receipt] = []
    @Published private(set) var detail: Receipt?
    @Published private(set) var detailItems: [ReceiptItem] = []
    @Published private(set) var isLoading = false
    @Published var lastError: String?
    @Published var lastUploadedReceiptId: Int?

    private let api: APIClient
    private let logger = Logger(subsystem: AppConstants.Keychain.credentialsService, category: "receipts")

    init(api: APIClient = .shared) {
        self.api = api
    }

    func loadList() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await api.request(
                .get,
                path: ReceiptEndpoint.list.path,
                as: ReceiptsListResponse.self
            )
            receipts = response.receipts
        } catch {
            lastError = (error as? APIError)?.errorDescription
            logger.error("loadList: \(error.localizedDescription, privacy: .public)")
        }
    }

    func loadDetail(id: Int) async {
        do {
            let response = try await api.request(
                .get,
                path: ReceiptEndpoint.detail(id: id).path,
                as: ReceiptDetailResponse.self
            )
            detail = response.receipt
            detailItems = response.items ?? []
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func confirm(id: Int) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(.post, path: ReceiptEndpoint.approve(id: id).path)
            await loadList()
            ToastQueue.shared.push(Toast(message: "Receipt approved", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    func uploadReceipt(fileURL: URL, receiptType: String, modelId: Int?) async {
        do {
            try DemoModeGate.guardMutation()

            let data = try Data(contentsOf: fileURL)
            let mimeType = mimeTypeFor(fileURL: fileURL)
            let response: Receipt = try await uploadMultipart(
                path: "/receipts/upload",
                fileData: data,
                fileName: fileURL.lastPathComponent,
                mimeType: mimeType,
                fields: [
                    "receipt_intent": receiptType,
                    "model_id": modelId.map(String.init) ?? ""
                ]
            )
            lastUploadedReceiptId = response.id
            await loadList()
            ToastQueue.shared.push(Toast(message: "Receipt uploaded — review when ready", severity: .success))
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — uploads disabled.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription ?? error.localizedDescription
            logger.error("uploadReceipt failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    func rerunOCR(id: Int, modelId: Int?) async {
        do {
            try DemoModeGate.guardMutation()
            try await api.request(
                .post,
                path: ReceiptEndpoint.reprocess(id: id).path,
                jsonBody: ReprocessBody(modelId: modelId)
            )
            await loadDetail(id: id)
        } catch APIError.demoModeReadOnly {
            ToastQueue.shared.push(Toast(message: "Demo mode — changes not saved.", severity: .warning))
        } catch {
            lastError = (error as? APIError)?.errorDescription
        }
    }

    // MARK: - Multipart helper (image field, not generic "file")

    private func mimeTypeFor(fileURL: URL) -> String {
        switch fileURL.pathExtension.lowercased() {
        case "pdf":           return "application/pdf"
        case "png":           return "image/png"
        case "heic", "heif":  return "image/heic"
        case "jpg", "jpeg":   return "image/jpeg"
        default:              return "application/octet-stream"
        }
    }

    private func uploadMultipart<T: Decodable>(
        path: String,
        fileData: Data,
        fileName: String,
        mimeType: String,
        fields: [String: String]
    ) async throws -> T {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()

        for (key, value) in fields where !value.isEmpty {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }
        // Backend expects the file under field name "image" per
        // handle_receipt_upload.py docstring.
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"image\"; filename=\"\(fileName)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

        let baseURL = URL(string: UserDefaults.standard.string(forKey: AppConstants.Defaults.apiBaseURL)
                          ?? AppConstants.defaultAPIBaseURL)!
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = KeychainStore().loadDeviceToken() {
            request.setValue(token, forHTTPHeaderField: "X-Trusted-Device-Token")
        }
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.transport }
        guard (200..<300).contains(http.statusCode) else {
            if http.statusCode == 401 {
                NotificationCenter.default.post(name: .authSessionExpired, object: nil)
                throw APIError.unauthorized
            }
            throw APIError.unexpected(statusCode: http.statusCode, message: String(data: data, encoding: .utf8))
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
}
