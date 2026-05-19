import SwiftUI

struct ReceiptListView: View {
    @StateObject private var state = ReceiptsState.shared
    @EnvironmentObject private var router: Router

    @State private var search = ""
    @State private var selectedId: Int? = nil

    var body: some View {
        Group {
            if state.isLoading && state.receipts.isEmpty {
                ProgressView().controlSize(.regular)
            } else if filtered.isEmpty {
                EmptyStateView(
                    systemImage: "doc.text",
                    title: state.receipts.isEmpty ? "No receipts yet" : "No matches",
                    subtitle: state.receipts.isEmpty
                        ? "Drop a receipt photo on the upload zone, or press ⌘N to start."
                        : "Try clearing your search.",
                    ctaTitle: state.receipts.isEmpty ? "Upload Receipt" : nil
                ) {
                    if state.receipts.isEmpty { router.activeSheet = .ocrUpload }
                }
            } else {
                List(filtered, selection: $selectedId) { r in
                    ReceiptRow(receipt: r)
                        .tag(r.id as Int?)
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Receipts")
        .searchable(text: $search, placement: .toolbar)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { router.activeSheet = .ocrUpload } label: {
                    Label("Upload", systemImage: "plus")
                }
                .keyboardShortcut("n", modifiers: .command)
            }
            ToolbarItem(placement: .primaryAction) {
                Button { Task { await state.loadList() } } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
        }
        .task { await state.loadList() }
    }

    private var filtered: [Receipt] {
        guard !search.isEmpty else { return state.receipts }
        return state.receipts.filter { ($0.storeName ?? "").localizedCaseInsensitiveContains(search) }
    }
}

private struct ReceiptRow: View {
    let receipt: Receipt

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            ReceiptThumbnail(url: receipt.imageUrl.flatMap(URL.init(string:)), size: 44)

            VStack(alignment: .leading, spacing: 2) {
                Text(receipt.storeName ?? "Unknown store").font(.appBody)
                HStack(spacing: 6) {
                    if let d = receipt.date {
                        Text(d.formatted(date: .abbreviated, time: .omitted))
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    if let domain = receipt.domain {
                        CategoryChip(domain: CategoryChip.Domain(rawValue: domain) ?? .unknown)
                    }
                }
            }
            Spacer()
            Text(String(format: "$%.2f", receipt.totalAmount))
                .font(.appMonoBody.weight(.semibold))
                .foregroundStyle(receipt.isConfirmed == true ? DesignTokens.success : DesignTokens.label)
        }
        .padding(.vertical, 4)
    }
}

#Preview("ReceiptList") {
    ReceiptListView()
        .environmentObject(Router.shared)
        .frame(width: 700, height: 500)
}
