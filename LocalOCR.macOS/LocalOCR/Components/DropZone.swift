import SwiftUI
import UniformTypeIdentifiers

/// Drag-from-Finder file drop target. Accepts JPEG / PNG / HEIC / PDF (§4.6 Integration 8).
/// Emits an array of URLs via `onDrop`. Dashed border highlights on hover.
struct DropZone: View {
    let title: String
    let subtitle: String
    let systemImage: String
    let onDrop: ([URL]) -> Void

    @State private var isTargeted = false

    private let acceptedTypes: [UTType] = [.jpeg, .png, .heic, .heif, .pdf]

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: DesignTokens.Radius.dropZone)
                .fill(isTargeted ? DesignTokens.dropTarget : DesignTokens.surface)

            RoundedRectangle(cornerRadius: DesignTokens.Radius.dropZone)
                .strokeBorder(
                    isTargeted ? DesignTokens.accent : DesignTokens.border,
                    style: StrokeStyle(lineWidth: isTargeted ? 2 : 1, dash: [6, 4])
                )

            VStack(spacing: DesignTokens.Spacing.space3) {
                Image(systemName: systemImage)
                    .font(.system(size: 36, weight: .light))
                    .foregroundStyle(isTargeted ? DesignTokens.accent : DesignTokens.tertiaryLabel)
                VStack(spacing: DesignTokens.Spacing.space1) {
                    Text(title)
                        .font(.appTitle3)
                        .foregroundStyle(DesignTokens.label)
                    Text(subtitle)
                        .font(.appSubheadline)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                        .multilineTextAlignment(.center)
                }
            }
            .padding(DesignTokens.Spacing.space5)
        }
        .frame(maxWidth: .infinity, minHeight: 180)
        .onDrop(of: acceptedTypes, isTargeted: $isTargeted) { providers in
            handleDrop(providers: providers)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title). \(subtitle)")
        .accessibilityAddTraits(.isButton)
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        let group = DispatchGroup()
        var urls: [URL] = []
        let lock = NSLock()

        for provider in providers {
            for type in acceptedTypes {
                guard provider.hasItemConformingToTypeIdentifier(type.identifier) else { continue }
                group.enter()
                _ = provider.loadObject(ofClass: URL.self) { url, _ in
                    if let url {
                        lock.lock()
                        urls.append(url)
                        lock.unlock()
                    }
                    group.leave()
                }
                break
            }
        }

        group.notify(queue: .main) {
            guard !urls.isEmpty else { return }
            onDrop(urls)
        }
        return true
    }
}

#Preview("DropZone") {
    DropZone(
        title: "Drop a receipt here",
        subtitle: "JPEG, PNG, HEIC, or PDF — or click Browse",
        systemImage: "tray.and.arrow.down"
    ) { urls in
        print("Dropped: \(urls)")
    }
    .padding(40)
    .frame(width: 480)
}
