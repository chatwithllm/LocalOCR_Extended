import SwiftUI
import Kingfisher

/// Receipt thumbnail with placeholder fallback. Loads from authenticated URLs via
/// Kingfisher's session that inherits HTTPCookieStorage.shared from APIClient.
///
/// Phase 2: visual + placeholder only. The actual authenticated URLSession config
/// is wired in Phase 3 (Networking/ImageCache.swift).
struct ReceiptThumbnail: View {
    let url: URL?
    var size: CGFloat = 56
    var cornerRadius: CGFloat = DesignTokens.Radius.control

    var body: some View {
        Group {
            if let url {
                KFImage(url)
                    .placeholder { placeholder }
                    .fade(duration: 0.2)
                    .cancelOnDisappear(true)
                    .resizable()
                    .scaledToFill()
            } else {
                placeholder
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: cornerRadius)
                .stroke(DesignTokens.border, lineWidth: 0.5)
        )
        .accessibilityLabel(url == nil ? "No receipt image" : "Receipt thumbnail")
    }

    private var placeholder: some View {
        ZStack {
            DesignTokens.surface2
            Image(systemName: "doc.text.image")
                .font(.system(size: size * 0.35, weight: .light))
                .foregroundStyle(DesignTokens.tertiaryLabel)
        }
    }
}

#Preview("ReceiptThumbnail / Placeholder") {
    HStack(spacing: 16) {
        ReceiptThumbnail(url: nil)
        ReceiptThumbnail(url: nil, size: 96)
        ReceiptThumbnail(url: nil, size: 128, cornerRadius: DesignTokens.Radius.card)
    }
    .padding(40)
}
