import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct OCRUploadView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var receipts = ReceiptsState.shared
    @StateObject private var prefs = PreferencesStore.shared
    @StateObject private var household = HouseholdState.shared

    @State private var fileURL: URL?
    @State private var receiptType = "auto"
    @State private var selectedModelId: Int? = nil
    @State private var isUploading = false

    private let receiptTypes: [(String, String)] = [
        ("auto", "Auto"), ("grocery", "Grocery"), ("restaurant", "Restaurant"), ("expense", "Expense")
    ]

    var body: some View {
        VStack(spacing: DesignTokens.Spacing.space4) {
            header

            DropZone(
                title: fileURL == nil ? "Drop a receipt here" : (fileURL?.lastPathComponent ?? ""),
                subtitle: fileURL == nil ? "JPEG, PNG, HEIC, or PDF — or click Browse" : "Ready to upload",
                systemImage: fileURL == nil ? "tray.and.arrow.down" : "doc.text.image"
            ) { urls in
                fileURL = urls.first
            }
            .frame(height: 200)

            HStack(spacing: 8) {
                Button("Browse…", action: showOpenPanel)
                    .buttonStyle(SecondaryButtonStyle())
                if fileURL != nil {
                    Button("Clear") { fileURL = nil }
                        .buttonStyle(GhostButtonStyle())
                }
            }

            optionsGrid

            Spacer()

            HStack {
                Button("Cancel") { dismiss() }
                    .buttonStyle(SecondaryButtonStyle())
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button {
                    Task { await upload() }
                } label: {
                    HStack {
                        if isUploading { ProgressView().controlSize(.small) }
                        Text(isUploading ? "Uploading…" : "Upload & OCR")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .keyboardShortcut(.defaultAction)
                .disabled(fileURL == nil || isUploading)
            }
        }
        .padding(DesignTokens.Spacing.space5)
        .frame(width: 480, height: 460)
        .task {
            await household.loadAIModels()
            if selectedModelId == nil, let first = household.aiModels.first(where: { $0.supportsVision })?.id {
                selectedModelId = first
            }
        }
    }

    private var header: some View {
        HStack {
            Image(systemName: "doc.text.viewfinder")
                .font(.system(size: 22, weight: .light))
                .foregroundStyle(DesignTokens.accent)
            VStack(alignment: .leading) {
                Text("New Receipt Upload").font(.appTitle3)
                Text("Photo or PDF → AI extracts → you review")
                    .font(.appCaption1)
                    .foregroundStyle(DesignTokens.secondaryLabel)
            }
            Spacer()
        }
    }

    private var optionsGrid: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Receipt type")
                    .font(.appCaption1.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
                Spacer()
                Picker("Type", selection: $receiptType) {
                    ForEach(receiptTypes, id: \.0) { code, label in
                        Text(label).tag(code)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(maxWidth: 280)
            }

            HStack {
                Text("AI model")
                    .font(.appCaption1.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryLabel)
                Spacer()
                ModelPicker(
                    options: household.aiModels.map { m in
                        .init(id: m.id, name: m.name, provider: m.provider,
                              priceTier: m.priceTier, supportsVision: m.supportsVision, supportsPdf: m.supportsPdf)
                    },
                    selectedId: $selectedModelId,
                    requiresVision: true
                )
                .frame(maxWidth: 280)
            }
        }
    }

    private func showOpenPanel() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.jpeg, .png, .heic, .heif, .pdf]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK { fileURL = panel.url }
    }

    private func upload() async {
        guard let url = fileURL else { return }
        isUploading = true
        await receipts.uploadReceipt(fileURL: url, receiptType: receiptType, modelId: selectedModelId)
        isUploading = false
        dismiss()
    }
}

#Preview("OCRUpload") {
    OCRUploadView().frame(width: 520, height: 480)
}
