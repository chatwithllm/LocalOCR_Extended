import SwiftUI
import AppKit

struct MenuBarPopoverView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var router: Router

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.space3) {
            // Header
            HStack {
                Image(systemName: "doc.text.viewfinder")
                    .foregroundStyle(DesignTokens.accent)
                Text("LocalOCR").font(.appHeadline)
                Spacer()
            }

            // Status tile
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.circle.fill")
                    .foregroundStyle(appState.lowStockCount > 0 ? DesignTokens.warning : DesignTokens.success)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Low stock").font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
                    Text(appState.lowStockCount > 0
                         ? "\(appState.lowStockCount) item\(appState.lowStockCount == 1 ? "" : "s") below threshold"
                         : "All stocked")
                        .font(.appBody)
                }
                Spacer()
            }
            .padding(DesignTokens.Spacing.space3)
            .background(DesignTokens.surface2)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radius.control))

            Divider()

            // Quick actions
            VStack(spacing: 6) {
                actionRow("Upload Receipt", systemImage: "tray.and.arrow.down") {
                    activateAndUploadReceipt()
                }
                actionRow("Open LocalOCR", systemImage: "rectangle.stack") {
                    activateMainWindow()
                }
                actionRow("Quit", systemImage: "power") {
                    NSApp.terminate(nil)
                }
            }

            Spacer()
        }
        .padding(DesignTokens.Spacing.space3)
        .frame(width: 320, height: 360, alignment: .topLeading)
    }

    private func actionRow(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: systemImage).frame(width: 18)
                Text(title)
                Spacer()
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .foregroundStyle(DesignTokens.label)
    }

    private func activateMainWindow() {
        NSApp.activate(ignoringOtherApps: true)
        NSApp.windows.first(where: { $0.title == "LocalOCR" })?.makeKeyAndOrderFront(nil)
    }

    private func activateAndUploadReceipt() {
        activateMainWindow()
        router.activeSheet = .ocrUpload
    }
}
