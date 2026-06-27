import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../app/theme/tokens.generated.dart';
import '../../../core/util/friendly_error.dart';
import '../../../core/widgets/empty_state_view.dart';
import '../data/search_models.dart';
import 'search_providers.dart';

class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});
  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _ctrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _onChanged(String v) {
    ref.read(searchQueryProvider.notifier).state = v;
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final tokens = t.extension<AppTokens>()!;
    final query = ref.watch(searchQueryProvider);
    final resultsAsync = ref.watch(searchResultsProvider);

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: TextField(
          controller: _ctrl,
          autofocus: true,
          onChanged: _onChanged,
          decoration: InputDecoration(
            hintText: 'Search inventory, products, receipts…',
            border: InputBorder.none,
            enabledBorder: InputBorder.none,
            focusedBorder: InputBorder.none,
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 4, vertical: 12),
            suffixIcon: query.isNotEmpty
                ? IconButton(
                    icon: const Icon(Icons.clear),
                    tooltip: 'Clear',
                    onPressed: () {
                      _ctrl.clear();
                      ref.read(searchQueryProvider.notifier).state = '';
                    },
                  )
                : null,
          ),
        ),
      ),
      body: Column(
        children: [
          // thin progress bar while loading
          if (resultsAsync.isLoading)
            const LinearProgressIndicator(minHeight: 2),
          Expanded(
            child: _buildBody(context, t, tokens, query, resultsAsync),
          ),
        ],
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    ThemeData t,
    AppTokens tokens,
    String query,
    AsyncValue<SearchResult?> resultsAsync,
  ) {
    if (query.trim().length < 2) {
      return const Center(
        child: Text('Type at least 2 characters to search'),
      );
    }

    return resultsAsync.when(
      loading: () => const SizedBox.shrink(),
      error: (e, _) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            friendlyError(e),
            textAlign: TextAlign.center,
            style: TextStyle(color: t.colorScheme.error),
          ),
        ),
      ),
      data: (result) {
        if (result == null || result.isEmpty) {
          return EmptyStateView(
            icon: Icons.search_off,
            message: 'No results for "$query"',
          );
        }
        return ListView(
          padding: const EdgeInsets.only(bottom: 24),
          children: [
            if (result.inventory.isNotEmpty) ...[
              _SectionHeader(
                  label: 'In Stock', count: result.inventory.length),
              ...result.inventory.map((h) => _InventoryTile(
                    hit: h,
                    tokens: tokens,
                    t: t,
                    onTap: () => context.go('/inventory'),
                  )),
            ],
            if (result.products.isNotEmpty) ...[
              _SectionHeader(
                  label: 'Products', count: result.products.length),
              ...result.products.map((h) => _ProductTile(
                    hit: h,
                    t: t,
                    onTap: () => context.go('/products'),
                  )),
            ],
            if (result.receipts.isNotEmpty) ...[
              _SectionHeader(
                  label: 'Receipts', count: result.receipts.length),
              ...result.receipts.map((h) => _ReceiptTile(
                    hit: h,
                    t: t,
                    onTap: () =>
                        context.go('/receipts/${h.purchaseId}'),
                  )),
            ],
          ],
        );
      },
    );
  }
}

// ── Section header ────────────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label, required this.count});
  final String label;
  final int count;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Row(
        children: [
          Text(label,
              style: t.textTheme.labelLarge
                  ?.copyWith(color: t.colorScheme.primary)),
          const SizedBox(width: 6),
          Container(
            padding:
                const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(
              color: t.colorScheme.primaryContainer,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              '$count',
              style: t.textTheme.labelSmall
                  ?.copyWith(color: t.colorScheme.onPrimaryContainer),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Inventory tile ────────────────────────────────────────────────────────────

class _InventoryTile extends StatelessWidget {
  const _InventoryTile(
      {required this.hit,
      required this.tokens,
      required this.t,
      required this.onTap});
  final SearchInventoryHit hit;
  final AppTokens tokens;
  final ThemeData t;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final qty =
        hit.quantity == hit.quantity.roundToDouble()
            ? hit.quantity.toInt().toString()
            : hit.quantity.toStringAsFixed(1);
    final sub = [
      '$qty${hit.unit != null ? ' ${hit.unit}' : ''}',
      if (hit.location != null) hit.location!,
    ].join(' · ');

    return ListTile(
      leading: const Icon(Icons.inventory_2_outlined),
      title: Text(hit.productName),
      subtitle: Text(sub),
      trailing: hit.expiryDate != null
          ? _ExpiryChip(date: hit.expiryDate!, tokens: tokens, t: t)
          : null,
      onTap: onTap,
    );
  }
}

class _ExpiryChip extends StatelessWidget {
  const _ExpiryChip(
      {required this.date, required this.tokens, required this.t});
  final String date;
  final AppTokens tokens;
  final ThemeData t;

  @override
  Widget build(BuildContext context) {
    final d = DateTime.tryParse(date);
    final label = d != null ? DateFormat.MMMd().format(d) : date;
    final soon = d != null &&
        d.difference(DateTime.now()).inDays <= 7;
    return Chip(
      label: Text(label,
          style: t.textTheme.labelSmall
              ?.copyWith(color: soon ? tokens.warning : null)),
      padding: EdgeInsets.zero,
      visualDensity: VisualDensity.compact,
      side: BorderSide.none,
      backgroundColor: soon
          ? tokens.warning.withValues(alpha: 0.15)
          : t.colorScheme.surfaceContainerHighest,
    );
  }
}

// ── Product tile ──────────────────────────────────────────────────────────────

class _ProductTile extends StatelessWidget {
  const _ProductTile(
      {required this.hit, required this.t, required this.onTap});
  final SearchProductHit hit;
  final ThemeData t;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final parts = <String>[];
    if (hit.lastPurchaseDate != null) {
      final d = DateTime.tryParse(hit.lastPurchaseDate!);
      parts.add(
          'Last bought ${d != null ? DateFormat.MMMd().format(d) : hit.lastPurchaseDate}');
    }
    if (hit.lastPurchasePrice != null) {
      parts.add('\$${hit.lastPurchasePrice!.toStringAsFixed(2)}');
    }

    return ListTile(
      leading: const Icon(Icons.local_grocery_store_outlined),
      title: Text(hit.productName),
      subtitle: parts.isNotEmpty ? Text(parts.join(' · ')) : null,
      trailing: hit.brand != null
          ? Text(hit.brand!,
              style: t.textTheme.bodySmall
                  ?.copyWith(color: t.colorScheme.onSurfaceVariant))
          : null,
      onTap: onTap,
    );
  }
}

// ── Receipt tile ──────────────────────────────────────────────────────────────

class _ReceiptTile extends StatelessWidget {
  const _ReceiptTile(
      {required this.hit, required this.t, required this.onTap});
  final SearchReceiptHit hit;
  final ThemeData t;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final date = hit.date != null
        ? () {
            final d = DateTime.tryParse(hit.date!);
            return d != null ? DateFormat.MMMd().format(d) : hit.date!;
          }()
        : null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ListTile(
          leading: const Icon(Icons.receipt_outlined),
          title: Text(hit.store),
          subtitle: date != null
              ? Text(
                  '$date${hit.total != null ? ' · \$${hit.total!.toStringAsFixed(2)}' : ''}')
              : null,
          onTap: onTap,
        ),
        if (hit.matchedItems.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(72, 0, 16, 8),
            child: Wrap(
              spacing: 6,
              runSpacing: 4,
              children: hit.matchedItems
                  .map((item) => Chip(
                        label: Text(
                          item.price != null
                              ? '${item.name} · \$${item.price!.toStringAsFixed(2)}'
                              : item.name,
                          style: t.textTheme.labelSmall,
                        ),
                        padding: EdgeInsets.zero,
                        visualDensity: VisualDensity.compact,
                        side: BorderSide.none,
                      ))
                  .toList(),
            ),
          ),
        const Divider(height: 1),
      ],
    );
  }
}
