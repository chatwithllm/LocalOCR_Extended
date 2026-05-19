import SwiftUI
import Kingfisher

struct AdvancedPane: View {
    @State private var cacheSizeMB: Double = 0

    var body: some View {
        Form {
            Section("Cache") {
                HStack {
                    Text("Image cache size")
                    Spacer()
                    Text(String(format: "%.1f MB", cacheSizeMB))
                        .font(.appMonoCaption)
                        .foregroundStyle(DesignTokens.secondaryLabel)
                }
                Button("Clear image cache") {
                    KingfisherManager.shared.cache.clearCache { Task { await refreshCacheSize() } }
                }
                .buttonStyle(SecondaryButtonStyle())
            }

            Section("Diagnostics") {
                Button("Open Console.app log") {
                    NSWorkspace.shared.launchApplication("Console")
                }
                .buttonStyle(SecondaryButtonStyle())
                Text("Filter Console by subsystem: \(AppConstants.Keychain.credentialsService)")
                    .font(.appCaption1.monospaced())
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }

            Section("About") {
                LabeledContent("Version",  value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0")
                LabeledContent("Build",    value: Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1")
                LabeledContent("macOS",    value: ProcessInfo.processInfo.operatingSystemVersionString)
            }
        }
        .formStyle(.grouped)
        .padding(DesignTokens.Spacing.space4)
        .task { await refreshCacheSize() }
    }

    private func refreshCacheSize() async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            KingfisherManager.shared.cache.calculateDiskStorageSize { result in
                switch result {
                case .success(let bytes):
                    cacheSizeMB = Double(bytes) / 1_048_576.0
                case .failure:
                    cacheSizeMB = 0
                }
                cont.resume()
            }
        }
    }
}
