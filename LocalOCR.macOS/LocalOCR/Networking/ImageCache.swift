import Foundation
import Kingfisher

/// Configures Kingfisher's image loader to share the same cookie jar as APIClient
/// so authenticated image URLs (receipt images served from the Flask app) work
/// without manual token plumbing.
enum ImageCache {

    static func configureSharedCookies() {
        // Kingfisher's downloader uses URLSession.shared.configuration by default.
        // We point its modifier at HTTPCookieStorage.shared (already shared with APIClient).
        KingfisherManager.shared.downloader.sessionConfiguration.httpCookieAcceptPolicy = .always
        KingfisherManager.shared.downloader.sessionConfiguration.httpShouldSetCookies = true
        KingfisherManager.shared.downloader.sessionConfiguration.httpCookieStorage = HTTPCookieStorage.shared
    }

    /// Modifier that attaches `X-Trusted-Device-Token` if available. Apply to KFImage
    /// loads that hit authenticated routes:
    ///     KFImage(url).requestModifier(ImageCache.tokenModifier)
    static let tokenModifier = AnyModifier { request in
        var mutable = request
        if let token = KeychainStore().loadDeviceToken() {
            mutable.setValue(token, forHTTPHeaderField: "X-Trusted-Device-Token")
        }
        return mutable
    }
}
