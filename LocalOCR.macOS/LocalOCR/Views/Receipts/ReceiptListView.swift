import SwiftUI

struct ReceiptListView: View {
    @StateObject private var state = ReceiptsState.shared
    @EnvironmentObject private var router: Router

    @State private var search = ""
    @State private var selectedId: Int? = nil
    @State private var domainFilter: String? = nil

    var body: some View {
        Group {
            if state.isLoading && state.receipts.isEmpty {
                loadingView
            } else if state.receipts.isEmpty {
                emptyStateView
            } else if filtered.isEmpty {
                noMatchesView
            } else {
                listView
            }
        }
        .navigationTitle("Receipts")
        .searchable(text: $search, placement: .toolbar, prompt: "Search store names")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Picker("Domain", selection: $domainFilter) {
                    Text("All").tag(String?.none)
                    Text("Grocery").tag(String?.some("grocery"))
                    Text("Restaurant").tag(String?.some("restaurant"))
                    Text("Expense").tag(String?.some("expense"))
                }
                .pickerStyle(.menu)
                .disabled(state.receipts.isEmpty)

                Button {
                    Task { await state.loadList() }
                } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                .help("Refresh receipt list")
                .keyboardShortcut("r", modifiers: .command)

                Button {
                    router.activeSheet = .ocrUpload
                } label: { Label("Upload", systemImage: "plus") }
                .help("Upload a new receipt (⌘N)")
                .keyboardShortcut("n", modifiers: .command)
            }
        }
        .task { await state.loadList() }
    }

    // MARK: - State subviews

    private var loadingView: some View {
        VStack(spacing: DesignTokens.Spacing.space2) {
            ForEach(0..<5, id: \.self) { _ in
                SkeletonView(width: nil, height: 64, cornerRadius: DesignTokens.Radius.card)
            }
        }
        .padding(DesignTokens.Spacing.space4)
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }

    private var emptyStateView: some View {
        EmptyStateView(
            systemImage: "doc.text",
            title: "No receipts yet",
            subtitle: "Drop a receipt photo on the Dashboard upload zone, or press ⌘N to start.",
            ctaTitle: "Upload Receipt"
        ) {
            router.activeSheet = .ocrUpload
        }
    }

    private var noMatchesView: some View {
        EmptyStateView(
            systemImage: "magnifyingglass",
            title: "No matches",
            subtitle: search.isEmpty ? "Try clearing the domain filter." : "Try clearing search or the domain filter."
        )
    }

    private var listView: some View {
        VStack(spacing: 0) {
            summaryBar
            Divider()
            List(filtered, selection: $selectedId) { r in
                ReceiptRow(receipt: r)
                    .tag(r.id as Int?)
            }
            .listStyle(.plain)
        }
        .background(DesignTokens.background)
    }

    private var summaryBar: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            summaryChip(label: "Total", value: "\(state.receipts.count)", color: DesignTokens.label)
            summaryChip(label: "Grocery", value: "\(state.receipts.filter { $0.domain == "grocery" }.count)", color: DesignTokens.accent)
            summaryChip(label: "Restaurant", value: "\(state.receipts.filter { $0.domain == "restaurant" }.count)", color: DesignTokens.warning)
            summaryChip(label: "Expense", value: "\(state.receipts.filter { $0.domain == "expense" }.count)", color: DesignTokens.success)
            Spacer()
            Text(String(format: "$%.2f", state.receipts.reduce(0) { $0 + $1.totalAmount }))
                .font(.appMonoBody.weight(.semibold))
                .foregroundStyle(DesignTokens.label)
        }
        .padding(.horizontal, DesignTokens.Spacing.space4)
        .padding(.vertical, DesignTokens.Spacing.space2)
        .background(DesignTokens.surface2)
    }

    private func summaryChip(label: String, value: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Text(value).font(.appMonoCaption.weight(.semibold)).foregroundStyle(color)
            Text(label).font(.appCaption1).foregroundStyle(DesignTokens.secondaryLabel)
        }
    }

    private var filtered: [Receipt] {
        state.receipts.filter { r in
            if let d = domainFilter, r.domain != d { return false }
            if !search.isEmpty {
                if (r.storeName ?? "").localizedCaseInsensitiveContains(search) == false { return false }
            }
            return true
        }
    }
}

private struct ReceiptRow: View {
    let receipt: Receipt

    var body: some View {
        HStack(spacing: DesignTokens.Spacing.space3) {
            ReceiptThumbnail(url: receipt.imageUrl.flatMap(URL.init(string:)), size: 48)

            VStack(alignment: .leading, spacing: 3) {
                Text(receipt.storeName ?? "Unknown store").font(.appBody.weight(.medium))
                HStack(spacing: 6) {
                    if let d = receipt.date {
                        Text(d.formatted(date: .abbreviated, time: .omitted))
                            .font(.appCaption1)
                            .foregroundStyle(DesignTokens.secondaryLabel)
                    }
                    if let domain = receipt.domain {
                        CategoryChip(domain: CategoryChip.Domain(rawValue: domain) ?? .unknown)
                    }
                    if receipt.isConfirmed == true {
                        Badge(text: "Confirmed", style: .success)
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
        .frame(width: 800, height: 600)
}
