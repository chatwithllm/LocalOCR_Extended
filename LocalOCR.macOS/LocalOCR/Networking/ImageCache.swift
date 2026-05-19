import Foundation
import Kingfisher

/// Configures Kingfisher's image loader to share the same cookie jar as APIClient
/// so authenticated image URLs (receipt images served from the Flask app) work
/// without manual token plumbing.
enum ImageCache {

    static func configureSharedCookies() {
        // Mutating sub-properties on `sessionConfiguration` in place does NOT rebuild
        // Kingfisher's URLSession — the session is created lazily from the config object
        // captured at first access, so later in-place writes are ignored. Build a fresh
        // config and assign the whole property so Kingfisher's setter rebuilds the session
        // with our shared cookie jar.
        let config = URLSessionConfiguration.default
        config.httpCookieAcceptPolicy = .always
        config.httpShouldSetCookies = true
        config.httpCookieStorage = HTTPCookieStorage.shared
        config.requestCachePolicy = .useProtocolCachePolicy
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        KingfisherManager.shared.downloader.sessionConfiguration = config
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
