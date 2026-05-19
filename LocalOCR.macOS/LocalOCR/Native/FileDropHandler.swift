import AppKit
import UniformTypeIdentifiers

/// Validates and extracts file URLs from drops onto the Dock icon or
/// app windows. Accepted UTTypes match §4.6 Integration 8.
enum FileDropHandler {

    static let acceptedTypes: [UTType] = [.jpeg, .png, .heic, .heif, .pdf]

    /// True if the URL's path extension matches one of the accepted UTI types.
    static func isAccepted(_ url: URL) -> Bool {
        guard let type = UTType(filenameExtension: url.pathExtension) else { return false }
        return acceptedTypes.contains(where: { type.conforms(to: $0) })
    }

    /// Filters an array of URLs down to the accepted ones.
    static func filter(_ urls: [URL]) -> [URL] {
        urls.filter(isAccepted)
    }
}
