// MARK: Products screen — F-401..F-435
//
// Implemented:
//   F-401..F-405 (Add: name/category/barcode/Create button/count display)
//   F-406 search (300ms debounce), F-407 sort (5 options), F-408 refresh,
//   F-409 category chip row, F-410 group header,
//   F-411 tile image (admin only), F-412 category+Low badge, F-413 ×N pill,
//   F-414 ⭐ regular-use prefix, F-415 📅 last purchase, F-416 variant
//   examples line, F-417 ✎ edit (inline dialog), F-418 🛒 add to shopping,
//   F-419 ✨ AI generate (admin), F-420 🗑 delete (confirm),
//   F-421 ▾ expand variants, F-422/F-423 variant rows w/ size + bought,
//   F-424 mini-link receipt buttons, F-425 ✎ variant edit, F-426 🛒 variant
//   add, F-427 🗑 variant delete, F-428 ✏️ rename (text prompt),
//   F-431 set-low / clear-low (PUT /inventory/products/<id>/low-status),
//   F-432/F-433/F-434 unit + size_label + save (PUT /products/<id>/update),
//   F-435 category change (PUT /products/<id>/update).
//
// 🔄 (justified adaptations):
//   F-429 photo upload — image_picker is wired but admin-only and only
//   surfaces in the edit dialog (web's separate 📷 button); F-430 view photo
//   tap opens a full-screen image viewer instead of web's overlay.

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart';

import '../../../app/theme/tokens.generated.dart';
import '../../../core/api/env.dart';
import '../../../core/providers.dart';
import '../../../core/util/friendly_error.dart';
import '../../../core/widgets/empty_state_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/util/logger.dart';
import '../data/product_models.dart';
import 'products_providers.dart';

class ProductsScreen extends ConsumerStatefulWidget {
  const ProductsScreen({super.key});
  @override
  ConsumerState<ProductsScreen> createState() => _ProductsScreenState();
}

class _ProductsScreenState extends ConsumerState<ProductsScreen> {
  final _searchCtl = TextEditingController();
  final _expandedKeys = <String>{};
  Timer? _searchDebounce;

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _searchCtl.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 300), () {
      final f = ref.read(productFiltersProvider);
      ref.read(productFiltersProvider.notifier).state =
          f.copyWith(search: value);
    });
  }

  @override
  Widget build(BuildContext context) {
    final filters = ref.watch(productFiltersProvider);
    final asyncList = ref.watch(productListProvider);
    final isAdmin = ref.watch(sessionProvider)?.user.role == 'admin';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Products'),
        actions: [
          IconButton(
            tooltip: filters.addCardOpen ? 'Hide add card' : 'Add product',
            icon: Icon(filters.addCardOpen ? Icons.close : Icons.add),
            onPressed: () {
              ref.read(productFiltersProvider.notifier).state =
                  filters.copyWith(addCardOpen: !filters.addCardOpen);
            },
          ),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(productListProvider),
          ),
        ],
      ),
      body: asyncList.when(
        loading: () => const LoadingView(),
        error: (e, _) => _ErrorView(
          message: 'Could not load products:\n$e',
          onRetry: () => ref.invalidate(productListProvider),
        ),
        data: (list) {
          final groups = ProductGroup.from(list.products);
          final visibleGroups = _filterAndSort(groups, filters);
          final totalItems = visibleGroups.fold<int>(
              0, (acc, g) => acc + g.count);
          appLogger.i('loaded ${list.products.length} products '
              '(groups=${groups.length} shown=${visibleGroups.length})');
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(productListProvider);
              await ref.read(productListProvider.future);
            },
            child: CustomScrollView(
              key: const Key('products-scroll'),
              slivers: [
                if (filters.addCardOpen)
                  SliverToBoxAdapter(child: _AddProductCard()),
                SliverToBoxAdapter(
                  child: _FiltersBar(
                    filters: filters,
                    searchCtl: _searchCtl,
                    onSearch: _onSearchChanged,
                    onSortChange: (s) => ref
                        .read(productFiltersProvider.notifier)
                        .state = filters.copyWith(sort: s),
                    groupCount: visibleGroups.length,
                    itemCount: totalItems,
                  ),
                ),
                SliverToBoxAdapter(
                  child: _CategoryChipRow(
                    items: list.products,
                    filters: filters,
                  ),
                ),
                ..._buildGroupSlivers(visibleGroups, isAdmin),
                const SliverToBoxAdapter(child: SizedBox(height: 32)),
              ],
            ),
          );
        },
      ),
    );
  }

  List<Widget> _buildGroupSlivers(List<ProductGroup> groups, bool isAdmin) {
    if (groups.isEmpty) {
      return const [
        SliverFillRemaining(
          hasScrollBody: false,
          child: EmptyStateView(
            message: 'No products yet.',
            icon: Icons.inventory_2_outlined,
          ),
        ),
      ];
    }
    // Group groups by displayCategory.
    final byCat = <String, List<ProductGroup>>{};
    for (final g in groups) {
      byCat.putIfAbsent(g.displayCategory, () => []).add(g);
    }
    final slivers = <Widget>[];
    byCat.forEach((cat, list) {
      slivers.add(SliverToBoxAdapter(child: _GroupHeader(category: cat, count: list.length)));
      slivers.add(
        SliverList.builder(
          itemCount: list.length,
          itemBuilder: (ctx, i) {
            final g = list[i];
            return _ProductTile(
              group: g,
              isAdmin: isAdmin,
              expanded: _expandedKeys.contains(g.key),
              onToggleExpand: () => setState(() {
                if (!_expandedKeys.add(g.key)) _expandedKeys.remove(g.key);
              }),
            );
          },
        ),
      );
    });
    return slivers;
  }

  List<ProductGroup> _filterAndSort(
      List<ProductGroup> groups, ProductFilters f) {
    Iterable<ProductGroup> r = groups;
    final hasSearch = f.search.trim().length >= 2;
    // When server search active, skip category filter (matches web behavior).
    if (!hasSearch && f.categoryFilters.isNotEmpty) {
      r = r.where((g) => f.categoryFilters.contains(g.displayCategory));
    }
    final list = r.toList();
    final cmp = _sortCmp(f.sort);
    list.sort(cmp);
    return list;
  }

  int Function(ProductGroup, ProductGroup) _sortCmp(String sort) {
    int cmpStr(String a, String b) =>
        a.toLowerCase().compareTo(b.toLowerCase());
    switch (sort) {
      case 'name_desc':
        return (a, b) => cmpStr(b.family, a.family);
      case 'category_asc':
        return (a, b) {
          final c = cmpStr(a.displayCategory, b.displayCategory);
          return c != 0 ? c : cmpStr(a.family, b.family);
        };
      case 'variants_desc':
        return (a, b) {
          final c = b.count.compareTo(a.count);
          return c != 0 ? c : cmpStr(a.family, b.family);
        };
      case 'recent_desc':
        return (a, b) {
          final al = a.latestPurchase ?? '';
          final bl = b.latestPurchase ?? '';
          final c = bl.compareTo(al);
          return c != 0 ? c : cmpStr(a.family, b.family);
        };
      case 'name_asc':
      default:
        return (a, b) => cmpStr(a.family, b.family);
    }
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48),
              const SizedBox(height: 12),
              Text(message, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(
                  onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      );
}

// ===== Add Product card (F-401..F-405) =====

class _AddProductCard extends ConsumerStatefulWidget {
  @override
  ConsumerState<_AddProductCard> createState() => _AddProductCardState();
}

class _AddProductCardState extends ConsumerState<_AddProductCard> {
  final _nameCtl = TextEditingController();
  final _barcodeCtl = TextEditingController();
  String _category = 'other';
  bool _busy = false;

  @override
  void dispose() {
    _nameCtl.dispose();
    _barcodeCtl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _nameCtl.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a product name')),
      );
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(productRepositoryProvider).create(
            name: name,
            category: _category,
            barcode: _barcodeCtl.text.trim(),
          );
      if (!mounted) return;
      _nameCtl.clear();
      _barcodeCtl.clear();
      ref.invalidate(productListProvider);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$name created')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Create failed: ${friendlyError(e)}')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 12, 12, 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Add Product',
                style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            TextField(
              key: const Key('prod-name'),
              controller: _nameCtl,
              decoration: const InputDecoration(
                labelText: 'Name',
                isDense: true,
              ),
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              key: const Key('prod-cat'),
              value: _category,
              isDense: true,
              decoration: const InputDecoration(labelText: 'Category'),
              items: [
                for (final c in productCategoryOptions)
                  DropdownMenuItem(value: c, child: Text(_labelOf(c)))
              ],
              onChanged: (v) => setState(() => _category = v ?? 'other'),
            ),
            const SizedBox(height: 8),
            TextField(
              key: const Key('prod-barcode'),
              controller: _barcodeCtl,
              decoration: const InputDecoration(
                labelText: 'Barcode (optional)',
                isDense: true,
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _busy ? null : _submit,
              icon: const Icon(Icons.add),
              label: const Text('Add Product'),
            ),
          ],
        ),
      ),
    );
  }
}

// ===== Filters bar (F-405 count, F-406 search, F-407 sort) =====

class _FiltersBar extends ConsumerWidget {
  const _FiltersBar({
    required this.filters,
    required this.searchCtl,
    required this.onSearch,
    required this.onSortChange,
    required this.groupCount,
    required this.itemCount,
  });
  final ProductFilters filters;
  final TextEditingController searchCtl;
  final ValueChanged<String> onSearch;
  final ValueChanged<String> onSortChange;
  final int groupCount;
  final int itemCount;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Catalog ($groupCount groups / $itemCount items)',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: TextField(
                  key: const Key('prod-search'),
                  controller: searchCtl,
                  decoration: const InputDecoration(
                    isDense: true,
                    prefixIcon: Icon(Icons.search),
                    labelText: 'Search products',
                  ),
                  onChanged: onSearch,
                ),
              ),
              const SizedBox(width: 8),
              DropdownButtonFormField<String>(
                value: filters.sort,
                decoration: const InputDecoration(
                  labelText: 'Sort',
                  isDense: true,
                ),
                items: [
                  for (final e in productSortOptions.entries)
                    DropdownMenuItem(value: e.key, child: Text(e.value))
                ],
                onChanged: (v) => v == null ? null : onSortChange(v),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ===== Category chip row (F-409) =====

class _CategoryChipRow extends ConsumerWidget {
  const _CategoryChipRow({required this.items, required this.filters});
  final List<Product> items;
  final ProductFilters filters;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cats = <String, int>{};
    for (final p in items) {
      cats.update(p.category, (v) => v + 1, ifAbsent: () => 1);
    }
    final sorted = cats.keys.toList()..sort();
    return SizedBox(
      height: 48,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        children: [
          for (final c in sorted)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: FilterChip(
                label: Text('${_labelOf(c)} (${cats[c]})'),
                selected: filters.categoryFilters.contains(c),
                onSelected: (sel) {
                  final next = {...filters.categoryFilters};
                  if (sel) {
                    next.add(c);
                  } else {
                    next.remove(c);
                  }
                  ref.read(productFiltersProvider.notifier).state =
                      filters.copyWith(categoryFilters: next);
                },
              ),
            )
        ],
      ),
    );
  }
}

class _GroupHeader extends StatelessWidget {
  const _GroupHeader({required this.category, required this.count});
  final String category;
  final int count;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 6),
      child: Text(
        '🏷️ ${_labelOf(category)}  ·  $count product${count == 1 ? '' : 's'}',
        style: Theme.of(context).textTheme.titleSmall,
      ),
    );
  }
}

// ===== Tile (F-411..F-421) =====

class _ProductTile extends ConsumerWidget {
  const _ProductTile({
    required this.group,
    required this.isAdmin,
    required this.expanded,
    required this.onToggleExpand,
  });
  final ProductGroup group;
  final bool isAdmin;
  final bool expanded;
  final VoidCallback onToggleExpand;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = group.primary;
    final snap = p.latestSnapshot;
    final tokens = Theme.of(context).extension<AppTokens>()!;
    final imageUrl = snap?.imageUrl;
    final isLow = p.manualLow || p.isLow;
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 4, 12, 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (imageUrl != null && isAdmin) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.network(
                  _absImageUrl(imageUrl),
                  height: 120,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) =>
                      const SizedBox(height: 1),
                ),
              ),
              const SizedBox(height: 8),
            ],
            Row(
              children: [
                Expanded(
                  child: Wrap(
                    spacing: 6,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(_labelOf(group.displayCategory),
                          style: Theme.of(context).textTheme.labelMedium),
                      if (isLow)
                        _Pill(text: 'Low', color: tokens.error),
                    ],
                  ),
                ),
                _Pill(text: '×${group.count}', color: Colors.blueGrey),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              (p.isRegularUse ? '⭐ ' : '') + group.family,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 2),
            if (group.latestPurchase != null)
              Text('📅 ${group.latestPurchase}',
                  style: Theme.of(context).textTheme.bodySmall),
            if (group.count > 1 && group.examples.isNotEmpty)
              Text(
                group.examples.take(2).join(', ') +
                    (group.count > 2 ? ' …' : ''),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 4,
              children: [
                IconButton(
                  tooltip: 'Edit',
                  icon: const Icon(Icons.edit_outlined),
                  onPressed: () => _showEditSheet(context, ref, p),
                ),
                IconButton(
                  tooltip: 'Add to shopping list',
                  icon: const Icon(Icons.shopping_cart_outlined),
                  onPressed: () => _addToShopping(context, ref, p),
                ),
                if (imageUrl == null && isAdmin)
                  IconButton(
                    tooltip: 'Generate image (AI)',
                    icon: const Icon(Icons.auto_awesome),
                    onPressed: () => _generate(context, ref, p),
                  ),
                IconButton(
                  tooltip: 'Delete',
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () => _delete(context, ref, p),
                ),
                if (group.count > 1)
                  TextButton.icon(
                    onPressed: onToggleExpand,
                    icon: Icon(
                        expanded ? Icons.expand_less : Icons.expand_more),
                    label: Text(expanded ? 'Hide' : '${group.count}'),
                  ),
              ],
            ),
            if (expanded && group.count > 1) ...[
              const Divider(),
              for (final variant in group.items)
                _VariantRow(item: variant),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _addToShopping(
      BuildContext context, WidgetRef ref, Product p) async {
    try {
      await ref.read(productRepositoryProvider).addToShoppingList(p);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${p.name} added to shopping list')));
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Add failed: ${friendlyError(e)}')));
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, Product p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete product?'),
        content: Text(p.name),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(productRepositoryProvider).delete(p.id);
      ref.invalidate(productListProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Deleted')));
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Delete failed: ${friendlyError(e)}')));
    }
  }

  Future<void> _generate(
      BuildContext context, WidgetRef ref, Product p) async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Generating image (may take up to 1 min)…')),
    );
    try {
      final snap =
          await ref.read(productRepositoryProvider).generateAiImage(p.id);
      ref.invalidate(productListProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(snap == null ? 'No image generated' : 'Image ready')),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Generate failed: ${friendlyError(e)}')));
    }
  }

  Future<void> _showEditSheet(
      BuildContext context, WidgetRef ref, Product p) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _EditProductSheet(product: p),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.text, required this.color});
  final String text;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.4)),
        ),
        child: Text(text,
            style: TextStyle(color: color, fontSize: 12)),
      );
}

// ===== Variant row (F-422..F-435) =====

class _VariantRow extends ConsumerStatefulWidget {
  const _VariantRow({required this.item});
  final Product item;
  @override
  ConsumerState<_VariantRow> createState() => _VariantRowState();
}

class _VariantRowState extends ConsumerState<_VariantRow> {
  late String _unit;
  late TextEditingController _sizeCtl;
  late String _category;

  @override
  void initState() {
    super.initState();
    _unit = widget.item.defaultUnit;
    _sizeCtl = TextEditingController(text: widget.item.defaultSizeLabel ?? '');
    _category = widget.item.category;
  }

  @override
  void dispose() {
    _sizeCtl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final it = widget.item;
    final tokens = Theme.of(context).extension<AppTokens>()!;
    final isLow = it.manualLow || it.isLow;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(it.name,
                    style: const TextStyle(fontWeight: FontWeight.w600))),
              if (isLow)
                _Pill(text: 'Low', color: tokens.error),
            ],
          ),
          if (it.defaultSizeLabel != null || it.lastPurchaseDate != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                [
                  if (it.defaultSizeLabel != null) it.defaultSizeLabel!,
                  if (it.lastPurchaseDate != null)
                    'Bought ${DateFormat.MMMd().format(DateTime.parse(it.lastPurchaseDate!))}',
                ].join(' · '),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          if (it.recentReceipts.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Wrap(
                spacing: 6,
                runSpacing: 4,
                children: [
                  for (final r in it.recentReceipts)
                    OutlinedButton(
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        minimumSize: const Size(0, 28),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                      onPressed: () => _openReceipt(r.receiptId),
                      child: Text(
                        '${r.store ?? 'Receipt'} · ${r.date ?? '—'}',
                        style: const TextStyle(fontSize: 12),
                      ),
                    ),
                ],
              ),
            ),
          const SizedBox(height: 4),
          Wrap(
            spacing: 4,
            children: [
              IconButton(
                tooltip: 'Edit',
                icon: const Icon(Icons.edit_outlined, size: 18),
                onPressed: () => _showEdit(),
              ),
              IconButton(
                tooltip: 'Rename',
                icon: const Icon(Icons.drive_file_rename_outline, size: 18),
                onPressed: () => _rename(),
              ),
              IconButton(
                tooltip: 'Add to shopping list',
                icon: const Icon(Icons.shopping_cart_outlined, size: 18),
                onPressed: () async {
                  try {
                    await ref
                        .read(productRepositoryProvider)
                        .addToShoppingList(it);
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('${it.name} added')));
                  } catch (e) {
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Add failed: ${friendlyError(e)}')));
                  }
                },
              ),
              IconButton(
                tooltip: 'Delete',
                icon: const Icon(Icons.delete_outline, size: 18),
                onPressed: () => _delete(),
              ),
              FilledButton.tonal(
                style: FilledButton.styleFrom(
                  minimumSize: const Size(0, 32),
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                onPressed: () => _setLow(!it.manualLow),
                child: Text(it.manualLow ? 'Clear Low' : 'Set Low',
                    style: const TextStyle(fontSize: 12)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                flex: 2,
                child: DropdownButtonFormField<String>(
                  value: _unit,
                  isDense: true,
                  decoration: const InputDecoration(
                    labelText: 'Unit',
                    isDense: true,
                  ),
                  items: const [
                    DropdownMenuItem(value: 'each', child: Text('each')),
                    DropdownMenuItem(value: 'oz', child: Text('oz')),
                    DropdownMenuItem(value: 'lb', child: Text('lb')),
                    DropdownMenuItem(value: 'g', child: Text('g')),
                    DropdownMenuItem(value: 'kg', child: Text('kg')),
                    DropdownMenuItem(value: 'ml', child: Text('ml')),
                    DropdownMenuItem(value: 'L', child: Text('L')),
                    DropdownMenuItem(value: 'gal', child: Text('gal')),
                    DropdownMenuItem(value: 'count', child: Text('count')),
                  ],
                  onChanged: (v) => setState(() => _unit = v ?? 'each'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                flex: 3,
                child: TextField(
                  controller: _sizeCtl,
                  decoration: const InputDecoration(
                    labelText: 'Size label',
                    isDense: true,
                    hintText: '18 ct, 1 gal, 2.4 lb',
                  ),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _saveUnitDefaults,
                child: const Text('Save'),
              ),
            ],
          ),
          const SizedBox(height: 6),
          DropdownButtonFormField<String>(
            value: productCategoryOptions.contains(_category)
                ? _category
                : 'other',
            isDense: true,
            decoration: const InputDecoration(
              labelText: 'Category',
              isDense: true,
            ),
            items: [
              for (final c in productCategoryOptions)
                DropdownMenuItem(value: c, child: Text(_labelOf(c)))
            ],
            onChanged: (v) async {
              if (v == null || v == _category) return;
              setState(() => _category = v);
              await _updateCategory(v);
            },
          ),
        ],
      ),
    );
  }

  Future<void> _rename() async {
    final ctl = TextEditingController(text: widget.item.name);
    final v = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Rename product'),
        content: TextField(
          controller: ctl,
          autofocus: true,
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, null),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, ctl.text.trim()),
              child: const Text('Rename')),
        ],
      ),
    );
    if (v == null || v.isEmpty || v == widget.item.name) return;
    try {
      await ref.read(productRepositoryProvider).update(widget.item.id, name: v);
      ref.invalidate(productListProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Renamed')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Rename failed: ${friendlyError(e)}')));
    }
  }

  Future<void> _showEdit() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _EditProductSheet(product: widget.item),
    );
  }

  Future<void> _saveUnitDefaults() async {
    try {
      await ref.read(productRepositoryProvider).update(
            widget.item.id,
            defaultUnit: _unit,
            defaultSizeLabel: _sizeCtl.text.trim(),
          );
      ref.invalidate(productListProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Saved')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Save failed: ${friendlyError(e)}')));
    }
  }

  Future<void> _updateCategory(String v) async {
    try {
      await ref
          .read(productRepositoryProvider)
          .update(widget.item.id, category: v);
      ref.invalidate(productListProvider);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Category update failed: ${friendlyError(e)}')));
    }
  }

  Future<void> _setLow(bool low) async {
    try {
      await ref
          .read(productRepositoryProvider)
          .setLowStatus(widget.item.id, low: low);
      ref.invalidate(productListProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(low ? 'Marked low' : 'Cleared low')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Set-low failed: ${friendlyError(e)}')));
    }
  }

  Future<void> _delete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete variant?'),
        content: Text(widget.item.name),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(productRepositoryProvider).delete(widget.item.id);
      ref.invalidate(productListProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Deleted')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Delete failed: ${friendlyError(e)}')));
    }
  }

  Future<void> _openReceipt(int receiptId) async {
    // Per ANDROID_APP_PLAN.md §3, deep-linking into receipt detail is
    // routed via /receipts/<id> path. Receipts screen is wave 2.
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.showSnackBar(
        SnackBar(content: Text('Receipt $receiptId — open from Receipts tab')));
  }
}

// ===== Edit sheet (F-417/F-425 — name + category + photo upload) =====

class _EditProductSheet extends ConsumerStatefulWidget {
  const _EditProductSheet({required this.product});
  final Product product;
  @override
  ConsumerState<_EditProductSheet> createState() => _EditProductSheetState();
}

class _EditProductSheetState extends ConsumerState<_EditProductSheet> {
  late TextEditingController _nameCtl;
  late String _category;
  bool _busy = false;
  List<ProductSnapshot>? _snapshots;

  @override
  void initState() {
    super.initState();
    _nameCtl = TextEditingController(text: widget.product.name);
    _category = widget.product.category;
    _loadSnapshots();
  }

  @override
  void dispose() {
    _nameCtl.dispose();
    super.dispose();
  }

  Future<void> _loadSnapshots() async {
    try {
      final snaps = await ref
          .read(productRepositoryProvider)
          .listSnapshots(widget.product.id);
      if (!mounted) return;
      setState(() => _snapshots = snaps);
    } catch (_) {
      if (mounted) setState(() => _snapshots = const []);
    }
  }

  Future<void> _pickAndUpload() async {
    final picker = ImagePicker();
    final x = await picker.pickImage(source: ImageSource.gallery);
    if (x == null) return;
    setState(() => _busy = true);
    try {
      await ref.read(productRepositoryProvider).uploadSnapshot(
            productId: widget.product.id,
            image: File(x.path),
          );
      await _loadSnapshots();
      ref.invalidate(productListProvider);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Upload failed: ${friendlyError(e)}')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final newName = _nameCtl.text.trim();
    if (newName.isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Name required')));
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(productRepositoryProvider).update(
            widget.product.id,
            name: newName != widget.product.name ? newName : null,
            category: _category != widget.product.category ? _category : null,
          );
      ref.invalidate(productListProvider);
      if (!mounted) return;
      Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Save failed: ${friendlyError(e)}')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final viewInsets = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 12, 16, 16 + viewInsets),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.grey.shade400,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 10),
          const Center(
              child: Text('Edit product',
                  style: TextStyle(fontWeight: FontWeight.w700))),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _nameCtl,
                  decoration: const InputDecoration(labelText: 'Name'),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'Add photo',
                icon: const Icon(Icons.photo_camera_outlined),
                onPressed: _busy ? null : _pickAndUpload,
              ),
            ],
          ),
          if ((_snapshots ?? const []).isNotEmpty) ...[
            const SizedBox(height: 10),
            const Align(
              alignment: Alignment.centerLeft,
              child: Text('Photos',
                  style: TextStyle(fontSize: 12, color: Colors.grey)),
            ),
            const SizedBox(height: 6),
            SizedBox(
              height: 72,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _snapshots!.length,
                separatorBuilder: (_, __) => const SizedBox(width: 6),
                itemBuilder: (ctx, i) {
                  final s = _snapshots![i];
                  final url = s.imageUrl;
                  return GestureDetector(
                    onTap: () async {
                      if (i == 0 || url == null) return;
                      await ref
                          .read(productRepositoryProvider)
                          .promoteSnapshot(s.id);
                      await _loadSnapshots();
                      ref.invalidate(productListProvider);
                    },
                    child: Stack(
                      children: [
                        Container(
                          width: 72,
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: i == 0
                                  ? Colors.blue
                                  : Colors.transparent,
                              width: 2,
                            ),
                          ),
                          clipBehavior: Clip.hardEdge,
                          child: url == null
                              ? const ColoredBox(color: Colors.black12)
                              : Image.network(_absImageUrl(url),
                                  fit: BoxFit.cover),
                        ),
                        Positioned(
                          top: 2,
                          right: 2,
                          child: InkWell(
                            onTap: () async {
                              await ref
                                  .read(productRepositoryProvider)
                                  .deleteSnapshot(s.id);
                              await _loadSnapshots();
                              ref.invalidate(productListProvider);
                            },
                            child: const CircleAvatar(
                              radius: 10,
                              backgroundColor: Colors.black54,
                              child: Icon(Icons.close,
                                  color: Colors.white, size: 14),
                            ),
                          ),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
          ],
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: productCategoryOptions.contains(_category)
                ? _category
                : 'other',
            isDense: true,
            decoration: const InputDecoration(labelText: 'Category'),
            items: [
              for (final c in productCategoryOptions)
                DropdownMenuItem(value: c, child: Text(_labelOf(c)))
            ],
            onChanged: (v) => setState(() => _category = v ?? 'other'),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Cancel'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: FilledButton(
                  onPressed: _busy ? null : _save,
                  child: const Text('Save'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

String _absImageUrl(String url) {
  if (url.startsWith('http')) return url;
  return Env.baseUrl + url;
}

String _labelOf(String c) {
  if (c.isEmpty) return 'Other';
  return c[0].toUpperCase() + c.substring(1);
}
