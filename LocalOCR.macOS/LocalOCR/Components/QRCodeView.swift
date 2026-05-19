import SwiftUI
import CoreImage.CIFilterBuiltins

/// QR code renderer using CoreImage's CIQRCodeGenerator (§2.3 native win).
/// Used by Share Shopping List and Trusted Device pairing flows.
struct QRCodeView: View {
    let payload: String
    var size: CGFloat = 220
    var correctionLevel: CorrectionLevel = .medium

    enum CorrectionLevel: String {
        case low = "L", medium = "M", quartile = "Q", high = "H"
    }

    var body: some View {
        Group {
            if let cg = generateCGImage() {
                Image(decorative: cg, scale: 1, orientation: .up)
                    .interpolation(.none)
                    .resizable()
                    .scaledToFit()
            } else {
                placeholder
            }
        }
        .frame(width: size, height: size)
        .padding(DesignTokens.Spacing.space3)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.card))
        .accessibilityLabel("QR code")
        .accessibilityHint(payload)
    }

    private var placeholder: some View {
        ZStack {
            DesignTokens.surface2
            Image(systemName: "qrcode")
                .font(.system(size: size * 0.5, weight: .light))
                .foregroundStyle(DesignTokens.tertiaryLabel)
        }
    }

    private func generateCGImage() -> CGImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(payload.utf8)
        filter.correctionLevel = correctionLevel.rawValue
        guard let output = filter.outputImage else { return nil }
        // Scale up so the QR isn't pixel-tiny.
        let scaled = output.transformed(by: .init(scaleX: 10, y: 10))
        return context.createCGImage(scaled, from: scaled.extent)
    }
}

#Preview("QRCode / Sample payload") {
    VStack(spacing: 16) {
        QRCodeView(payload: "https://localocr.example/share/abc123")
        QRCodeView(payload: "localocr://pair/eyJ0b2tlbiI6Ii4uLiJ9", size: 140)
    }
    .padding(40)
}
