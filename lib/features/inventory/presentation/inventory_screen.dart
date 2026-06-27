// MARK: Inventory screen — F-301..F-374 (focused MVP; see registry for 🔄 rows)
//
// Implemented in this build:
//   F-301 (hide/show Add card), F-302/F-303/F-304/F-306/F-308/F-311/F-312
//   (Add form: name / qty / location / threshold / category / shopping-on-add),
//   F-314 (search), F-315 (location filter), F-316 (group-by), F-317 (sort),
//   F-318 (show empty), F-321 (category chip row), F-322 (low badge),
//   F-330 (group header), F-334 (days-left), F-336 (qty pill), F-343 (name),
//   F-345/F-346 (Bought / Expires meta), F-349 (+3d defer), F-351 (cart),
//   F-352 (-1), F-353 (used-up), F-357 (swipe-right → -1),
//   F-358 (swipe-left → used-up), F-360 (tap row → expand details).
//
// Out of scope this round (per ANDROID_APP_PLAN sequencing — registered as ❌
// or 🔄 in FEATURE_PARITY_REGISTRY.md so follow-up agents can find them):
//   F-307/F-309/F-310/F-313 (extra add-card knobs + product creation),
//   F-319 recently-used-up modal, F-320 merge-duplicates, F-323 window note,
//   F-324..F-329 bulk-bar + undo, F-332/F-333/F-337..F-341 drag-slider
//   + tile image overlay, F-342 status pill cycle, F-344 ~est suffix,
//   F-347 medication link, F-348 ✎ inline edit, F-350/F-354 hold-alt actions,
//   F-355 AI generate snapshot, F-356 variant delete, F-359 long-press select,
//   F-361 right-click menu, F-362..F-368 edit sheet, F-369..F-374 restore tile.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/providers.dart' show appShellActionsProvider;
import '../../../core/util/friendly_error.dart';
import '../../../core/util/logger.dart';
import '../../../core/widgets/empty_state_view.dart';
import '../data/inventory_models.dart';
import 'inventory_providers.dart';

class InventoryScreen extends ConsumerStatefulWidget {
  const InventoryScreen({super.key});
  @override
  ConsumerState<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends ConsumerState<InventoryScreen> {
  final _searchCtl = TextEditingController();
  final _expandedIds = <int>{};
  late final List<Widget> _appBarActions;
  bool _showSwipeHint = false;

  @override
  void initState() {
    super.initState();
    _appBarActions = [
      IconButton(
        tooltip: 'Refresh',
        onPressed: () => ref.invalidate(inventoryListProvider),
        icon: const Icon(Icons.refresh),
      ),
    ];
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(appShellActionsProvider.notifier).state = _appBarActions;
    });
    _checkSwipeHint();
  }

  @override
  void dispose() {
    ref.read(appShellActionsProvider.notifier).state = const [];
    _searchCtl.dispose();
    super.dispose();
  }

  Future<void> _checkSwipeHint() async {
    final prefs = await SharedPreferences.getInstance();
    final shown = prefs.getBool('inventory_swipe_hint_shown') ?? false;
    if (!shown && mounted) setState(() => _showSwipeHint = true);
  }

  Future<void> _dismissSwipeHint() async {
    setState(() => _showSwipeHint = false);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('inventory_swipe_hint_shown', true);
  }

  @override
  Widget build(BuildContext context) {
    final filters = ref.watch(inventoryFiltersProvider);
    final asyncList = ref.watch(inventoryListProvider);
    return Scaffold(
      body: asyncList.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline, size: 48),
                const SizedBox(height: 12),
                Text('Could not load inventory:\n${friendlyError(e)}',
                    textAlign: TextAlign.center),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: () => ref.invalidate(inventoryListProvider),
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ),
        data: (list) {
          final filtered = _applyFilters(list.items, filters);
          final grouped = _group(filtered, filters);
          final lowCount =
              list.items.where((i) => i.isLow || i.manualLow).length;
          appLogger.i('loaded ${list.items.length} inventory items '
              '(low=$lowCount)');
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(inventoryListProvider);
              await ref.read(inventoryListProvider.future);
            },
            child: CustomScrollView(
              key: const Key('inventory-scroll'),
              slivers: [
                SliverToBoxAdapter(
                  child: _AddCard(open: filters.addCardOpen),
                ),
                SliverToBoxAdapter(
                  child: _FiltersBar(
                    filters: filters,
                    searchCtl: _searchCtl,
                    lowCount: lowCount,
                  ),
                ),
                SliverToBoxAdapter(
                  child: _CategoryChipRow(items: list.items, filters: filters),
                ),
                ..._buildSliverGroups(grouped),
                const SliverToBoxAdapter(child: SizedBox(height: 32)),
              ],
            ),
          );
        },
      ),
    );
  }

  List<Widget> _buildSliverGroups(List<_Group> grouped) {
    if (grouped.isEmpty) {
      return [
        const SliverFillRemaining(
          hasScrollBody: false,
          child: EmptyStateView(
            message: 'No inventory rows match these filters.',
            icon: Icons.search_off,
          ),
        ),
      ];
    }
    final slivers = <Widget>[];
    if (_showSwipeHint) {
      slivers.add(SliverToBoxAdapter(
        child: _SwipeHintBanner(onDismiss: _dismissSwipeHint),
      ));
    }
    for (final g in grouped) {
      slivers.add(SliverToBoxAdapter(child: _GroupHeader(group: g)));
      slivers.add(
        SliverList.builder(
          itemCount: g.items.length,
          itemBuilder: (ctx, i) {
            final item = g.items[i];
            return _InventoryTile(
              item: item,
              expanded: _expandedIds.contains(item.id),
              onToggleExpand: () => setState(() {
                if (!_expandedIds.add(item.id)) _expandedIds.remove(item.id);
              }),
            );
          },
        ),
      );
    }
    return slivers;
  }

  List<InventoryItem> _applyFilters(
      List<InventoryItem> items, InventoryFilters f) {
    final q = f.search.trim().toLowerCase();
    return items.where((item) {
      if (q.isNotEmpty &&
          !item.productName.toLowerCase().contains(q) &&
          !item.category.toLowerCase().contains(q)) {
        return false;
      }
      if (f.location != null && f.location!.isNotEmpty) {
        if (item.location.toLowerCase() != f.location!.toLowerCase()) {
          return false;
        }
      }
      if (!f.showEmpty && item.quantity == 0 && !item.manualLow) {
        return false;
      }
      if (f.categoryFilters.isNotEmpty &&
          !f.categoryFilters.contains(item.category)) {
        return false;
      }
      return true;
    }).toList()
      ..sort(_sortFn(f.sort));
  }

  int Function(InventoryItem, InventoryItem) _sortFn(String sort) {
    switch (sort) {
      case 'name':
        return (a, b) =>
            a.productName.toLowerCase().compareTo(b.productName.toLowerCase());
      case 'qty':
        return (a, b) => a.quantity.compareTo(b.quantity);
      case 'expiry':
      default:
        return (a, b) {
          final ad = a.daysLeft ?? 99999;
          final bd = b.daysLeft ?? 99999;
          return ad.compareTo(bd);
        };
    }
  }

  List<_Group> _group(List<InventoryItem> items, InventoryFilters f) {
    if (items.isEmpty) return const [];
    switch (f.groupBy) {
      case 'domain':
        return _groupByKey(items, (i) => _domainEmoji(i.category),
            (i) => i.category[0].toUpperCase() + i.category.substring(1));
      case 'location':
        return _groupByKey(items, (i) => '📍',
            (i) => i.location.isEmpty ? 'No location' : i.location);
      case 'low_first':
      default:
        final low = items.where((i) => i.isLow || i.manualLow).toList();
        final fresh = items.where((i) => !(i.isLow || i.manualLow)).toList();
        return [
          if (low.isNotEmpty) _Group('⚠️', 'Low stock', low),
          if (fresh.isNotEmpty) _Group('✅', 'Fresh', fresh),
        ];
    }
  }

  List<_Group> _groupByKey(
    List<InventoryItem> items,
    String Function(InventoryItem) emojiOf,
    String Function(InventoryItem) labelOf,
  ) {
    final map = <String, _Group>{};
    for (final it in items) {
      final label = labelOf(it);
      final key = label.toLowerCase();
      map.putIfAbsent(key, () => _Group(emojiOf(it), label, [])).items.add(it);
    }
    final list = map.values.toList();
    list.sort((a, b) => a.label.compareTo(b.label));
    return list;
  }

  String _domainEmoji(String cat) {
    switch (cat) {
      case 'produce':
        return '🥦';
      case 'dairy':
        return '🥛';
      case 'meat':
        return '🥩';
      case 'frozen':
        return '🧊';
      case 'grains':
        return '🌾';
      case 'snacks':
        return '🍪';
      case 'beverages':
        return '🥤';
      case 'household':
        return '🧴';
      default:
        return '📦';
    }
  }
}

class _Group {
  _Group(this.emoji, this.label, this.items);
  final String emoji;
  final String label;
  final List<InventoryItem> items;
}

// ---- F-330 group header ---------------------------------------------------

class _GroupHeader extends StatelessWidget {
  const _GroupHeader({required this.group});
  final _Group group;
  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    final expiring =
        group.items.where((i) => (i.daysLeft ?? 99) <= 3).length;
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 6),
      child: Row(
        children: [
          Text(group.emoji, style: const TextStyle(fontSize: 18)),
          const SizedBox(width: 8),
          Text(group.label,
              style: th.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
              )),
          const SizedBox(width: 8),
          Text('· ${group.items.length}',
              style: th.textTheme.bodyMedium?.copyWith(
                color: th.colorScheme.onSurfaceVariant,
              )),
          if (expiring > 0) ...[
            const SizedBox(width: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: th.colorScheme.errorContainer,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text('$expiring expiring soon',
                  style: th.textTheme.labelSmall?.copyWith(
                    color: th.colorScheme.onErrorContainer,
                  )),
            ),
          ],
        ],
      ),
    );
  }
}

// ---- F-301..F-312 Add card ------------------------------------------------

class _AddCard extends ConsumerStatefulWidget {
  const _AddCard({required this.open});
  final bool open;
  @override
  ConsumerState<_AddCard> createState() => _AddCardState();
}

class _AddCardState extends ConsumerState<_AddCard> {
  final _nameCtl = TextEditingController();
  final _qtyCtl = TextEditingController(text: '1');
  final _threshCtl = TextEditingController();
  String _location = 'Pantry';
  String _category = 'other';
  bool _alsoShopping = false;
  bool _saving = false;

  @override
  void dispose() {
    _nameCtl.dispose();
    _qtyCtl.dispose();
    _threshCtl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    final f = ref.watch(inventoryFiltersProvider);
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 12, 12, 0),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('Add Item',
                      style: th.textTheme.titleMedium),
                ),
                TextButton(
                  key: const Key('inv-add-card-toggle'),
                  onPressed: () => ref
                      .read(inventoryFiltersProvider.notifier)
                      .state = f.copyWith(addCardOpen: !widget.open),
                  child: Text(widget.open ? 'Hide' : 'Show'),
                ),
              ],
            ),
            if (widget.open) ...[
              TextField(
                key: const Key('inv-name'),
                controller: _nameCtl,
                decoration: const InputDecoration(
                  labelText: 'Product name',
                  prefixIcon: Icon(Icons.label_outline),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      key: const Key('inv-qty'),
                      controller: _qtyCtl,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      decoration: const InputDecoration(
                        labelText: 'Quantity',
                        prefixIcon: Icon(Icons.numbers),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      key: const Key('inv-loc'),
                      initialValue: _location,
                      items: const [
                        DropdownMenuItem(
                            value: 'Pantry', child: Text('Pantry')),
                        DropdownMenuItem(
                            value: 'Fridge', child: Text('Fridge')),
                        DropdownMenuItem(
                            value: 'Freezer', child: Text('Freezer')),
                        DropdownMenuItem(
                            value: 'Cabinet', child: Text('Cabinet')),
                        DropdownMenuItem(
                            value: 'Bathroom', child: Text('Bathroom')),
                        DropdownMenuItem(
                            value: 'Laundry', child: Text('Laundry')),
                      ],
                      onChanged: (v) => setState(() => _location = v ?? 'Pantry'),
                      decoration: const InputDecoration(
                        labelText: 'Location',
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      key: const Key('inv-cat'),
                      initialValue: _category,
                      items: const [
                        DropdownMenuItem(value: 'produce', child: Text('Produce')),
                        DropdownMenuItem(value: 'dairy', child: Text('Dairy')),
                        DropdownMenuItem(value: 'meat', child: Text('Meat')),
                        DropdownMenuItem(value: 'frozen', child: Text('Frozen')),
                        DropdownMenuItem(value: 'grains', child: Text('Grains')),
                        DropdownMenuItem(value: 'snacks', child: Text('Snacks')),
                        DropdownMenuItem(value: 'beverages', child: Text('Beverages')),
                        DropdownMenuItem(value: 'household', child: Text('Household')),
                        DropdownMenuItem(value: 'other', child: Text('Other')),
                      ],
                      onChanged: (v) => setState(() => _category = v ?? 'other'),
                      decoration: const InputDecoration(labelText: 'Category'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      key: const Key('inv-thresh'),
                      controller: _threshCtl,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      decoration: const InputDecoration(
                        labelText: 'Low threshold',
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              CheckboxListTile(
                key: const Key('inv-add-to-shopping'),
                contentPadding: EdgeInsets.zero,
                title: const Text('Also add to shopping list'),
                controlAffinity: ListTileControlAffinity.leading,
                value: _alsoShopping,
                onChanged: (v) => setState(() => _alsoShopping = v ?? false),
              ),
              const SizedBox(height: 4),
              FilledButton.icon(
                key: const Key('inv-add-btn'),
                onPressed: _saving ? null : _submit,
                icon: const Icon(Icons.add),
                label: Text(_saving ? 'Adding…' : 'Add to inventory'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final name = _nameCtl.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a product name first')),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final repo = ref.read(inventoryRepositoryProvider);
      await repo.addItem(
        productName: name,
        category: _category,
        quantity: double.tryParse(_qtyCtl.text) ?? 1,
        location: _location,
        threshold: double.tryParse(_threshCtl.text),
      );
      if (_alsoShopping) {
        // Quick add to shopping using the same name — backend treats name-only
        // adds as fuzzy lookups (manage_shopping_list.py:items_create).
        await ref.read(inventoryRepositoryProvider).addToShoppingList(
              InventoryItem(
                id: 0,
                productId: 0,
                productName: name,
                rawName: name,
                category: _category,
                location: _location,
                quantity: 1,
                unit: 'each',
                sizeLabel: null,
                threshold: null,
                manualLow: false,
                isLow: false,
                isRegularUse: false,
                expiresAt: null,
                expiresAtSystem: null,
                expiresSource: null,
                lastPurchasedAt: null,
                daysLeft: null,
                status: 'fresh',
                remainingPct: 100,
                snapshotImageUrl: null,
              ),
            );
      }
      _nameCtl.clear();
      _qtyCtl.text = '1';
      _threshCtl.clear();
      ref.invalidate(inventoryListProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Added "$name" to inventory')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Add failed: ${friendlyError(e)}')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

// ---- F-314..F-318 Filters bar --------------------------------------------

class _FiltersBar extends ConsumerWidget {
  const _FiltersBar({
    required this.filters,
    required this.searchCtl,
    required this.lowCount,
  });
  final InventoryFilters filters;
  final TextEditingController searchCtl;
  final int lowCount;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier = ref.read(inventoryFiltersProvider.notifier);
    final th = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            key: const Key('inventory-search'),
            controller: searchCtl,
            onChanged: (v) =>
                notifier.state = filters.copyWith(search: v),
            decoration: InputDecoration(
              labelText: 'Search inventory',
              prefixIcon: const Icon(Icons.search),
              border: const OutlineInputBorder(),
              isDense: true,
              suffixIcon: searchCtl.text.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.clear),
                      onPressed: () {
                        searchCtl.clear();
                        notifier.state = filters.copyWith(search: '');
                      },
                    ),
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              DropdownButtonFormField<String?>(
                key: const Key('inventory-location-filter'),
                value: filters.location,
                decoration: const InputDecoration(
                  labelText: 'Location',
                  isDense: true,
                ),
                items: const [
                  DropdownMenuItem(value: null, child: Text('All')),
                  DropdownMenuItem(value: 'Pantry', child: Text('Pantry')),
                  DropdownMenuItem(value: 'Fridge', child: Text('Fridge')),
                  DropdownMenuItem(value: 'Freezer', child: Text('Freezer')),
                  DropdownMenuItem(value: 'Cabinet', child: Text('Cabinet')),
                  DropdownMenuItem(value: 'Bathroom', child: Text('Bathroom')),
                ],
                onChanged: (v) =>
                    notifier.state = filters.copyWith(location: v),
              ),
              DropdownButtonFormField<String>(
                key: const Key('inventory-group-by'),
                value: filters.groupBy,
                decoration: const InputDecoration(
                  labelText: 'Group by',
                  isDense: true,
                ),
                items: const [
                  DropdownMenuItem(value: 'low_first', child: Text('Low first')),
                  DropdownMenuItem(value: 'domain', child: Text('Category')),
                  DropdownMenuItem(value: 'location', child: Text('Location')),
                ],
                onChanged: (v) =>
                    notifier.state = filters.copyWith(groupBy: v ?? 'low_first'),
              ),
              DropdownButtonFormField<String>(
                key: const Key('inventory-sort'),
                value: filters.sort,
                decoration: const InputDecoration(
                  labelText: 'Sort',
                  isDense: true,
                ),
                items: const [
                  DropdownMenuItem(value: 'expiry', child: Text('Expiry')),
                  DropdownMenuItem(value: 'name', child: Text('Name')),
                  DropdownMenuItem(value: 'qty', child: Text('Qty')),
                ],
                onChanged: (v) =>
                    notifier.state = filters.copyWith(sort: v ?? 'expiry'),
              ),
              FilterChip(
                key: const Key('inventory-show-empty'),
                label: const Text('Show empty'),
                selected: filters.showEmpty,
                onSelected: (v) =>
                    notifier.state = filters.copyWith(showEmpty: v),
              ),
              if (lowCount > 0)
                Container(
                  key: const Key('inv-low-badge'),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: th.colorScheme.errorContainer,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text('$lowCount running low',
                      style: th.textTheme.labelSmall?.copyWith(
                        color: th.colorScheme.onErrorContainer,
                      )),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

// ---- F-321 Category chip row ---------------------------------------------

class _CategoryChipRow extends ConsumerWidget {
  const _CategoryChipRow({required this.items, required this.filters});
  final List<InventoryItem> items;
  final InventoryFilters filters;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cats = <String>{for (final i in items) i.category}.toList()..sort();
    if (cats.isEmpty) return const SizedBox.shrink();
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      child: Row(
        key: const Key('inv-category-chips'),
        children: [
          for (final c in cats)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: FilterChip(
                label: Text(c[0].toUpperCase() + c.substring(1)),
                selected: filters.categoryFilters.contains(c),
                onSelected: (sel) {
                  final next = {...filters.categoryFilters};
                  if (sel) {
                    next.add(c);
                  } else {
                    next.remove(c);
                  }
                  ref.read(inventoryFiltersProvider.notifier).state =
                      filters.copyWith(categoryFilters: next);
                },
              ),
            ),
        ],
      ),
    );
  }
}

// ---- Tile -----------------------------------------------------------------

class _InventoryTile extends ConsumerWidget {
  const _InventoryTile({
    required this.item,
    required this.expanded,
    required this.onToggleExpand,
  });
  final InventoryItem item;
  final bool expanded;
  final VoidCallback onToggleExpand;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final th = Theme.of(context);
    final repo = ref.read(inventoryRepositoryProvider);

    return Dismissible(
      key: Key('inv-tile-${item.id}'),
      background: Container(
        color: th.colorScheme.secondaryContainer,
        alignment: Alignment.centerLeft,
        padding: const EdgeInsets.only(left: 24),
        child: const Icon(Icons.remove_circle_outline),
      ),
      secondaryBackground: Container(
        color: th.colorScheme.errorContainer,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        child: const Icon(Icons.check_circle_outline),
      ),
      confirmDismiss: (dir) async {
        if (dir == DismissDirection.startToEnd) {
          // F-357 swipe-right → -1
          await _wrap(context, () => repo.consume(item.id),
              'Decremented ${item.productName}');
          ref.invalidate(inventoryListProvider);
        } else if (dir == DismissDirection.endToStart) {
          // F-358 swipe-left → used up
          await _wrap(context, () => repo.markUsedUp(item.productId),
              'Marked ${item.productName} used up');
          ref.invalidate(inventoryListProvider);
        }
        // We re-fetch the list on every gesture, so always reject the dismiss
        // and let the new list rebuild the tile rather than tearing it out.
        return false;
      },
      child: InkWell(
        onTap: onToggleExpand,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  if (item.isLow || item.manualLow)
                    Padding(
                      padding: const EdgeInsets.only(right: 6),
                      child: Icon(Icons.warning_amber_outlined,
                          color: th.colorScheme.error, size: 18),
                    ),
                  Expanded(
                    child: Text(
                      item.productName,
                      style: th.textTheme.bodyLarge?.copyWith(
                        fontWeight: FontWeight.w500,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: th.colorScheme.surfaceContainerHigh,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '${_fmtQty(item.quantity)} ${item.unit}',
                      style: th.textTheme.labelSmall,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              DefaultTextStyle.merge(
                style: th.textTheme.bodySmall?.copyWith(
                  color: th.colorScheme.onSurfaceVariant,
                ) ??
                    const TextStyle(),
                child: Wrap(
                  spacing: 12,
                  runSpacing: 2,
                  children: [
                    if (item.location.isNotEmpty)
                      Row(mainAxisSize: MainAxisSize.min, children: [
                        const Icon(Icons.place_outlined, size: 14),
                        const SizedBox(width: 2),
                        Text(item.location),
                      ]),
                    if (item.daysLeft != null)
                      Row(mainAxisSize: MainAxisSize.min, children: [
                        const Icon(Icons.event_busy_outlined, size: 14),
                        const SizedBox(width: 2),
                        Text(_daysLabel(item.daysLeft!)),
                      ]),
                    if (item.lastPurchasedAt != null)
                      Row(mainAxisSize: MainAxisSize.min, children: [
                        const Icon(Icons.shopping_bag_outlined, size: 14),
                        const SizedBox(width: 2),
                        Text('Bought ${_shortDate(item.lastPurchasedAt!)}'),
                      ]),
                  ],
                ),
              ),
              if (expanded) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    OutlinedButton.icon(
                      key: Key('inv-defer-${item.id}'),
                      onPressed: () async {
                        await _wrap(context,
                            () => repo.deferExpiry(item.productId, 3),
                            'Deferred ${item.productName} +3d');
                        ref.invalidate(inventoryListProvider);
                      },
                      icon: const Icon(Icons.fast_forward, size: 16),
                      label: const Text('+3d'),
                    ),
                    const SizedBox(width: 6),
                    OutlinedButton.icon(
                      key: Key('inv-cart-${item.id}'),
                      onPressed: () async {
                        await _wrap(
                            context,
                            () => repo.addToShoppingList(item),
                            'Added ${item.productName} to shopping list');
                      },
                      icon: const Icon(Icons.add_shopping_cart, size: 16),
                      label: const Text('Add'),
                    ),
                    const Spacer(),
                    IconButton(
                      key: Key('inv-minus-${item.id}'),
                      tooltip: '-1',
                      onPressed: () async {
                        await _wrap(context, () => repo.consume(item.id),
                            'Decremented ${item.productName}');
                        ref.invalidate(inventoryListProvider);
                      },
                      icon: const Icon(Icons.remove_circle_outline),
                    ),
                    IconButton(
                      key: Key('inv-used-${item.id}'),
                      tooltip: 'Used up',
                      onPressed: () async {
                        await _wrap(
                            context,
                            () => repo.markUsedUp(item.productId),
                            'Marked ${item.productName} used up');
                        ref.invalidate(inventoryListProvider);
                      },
                      icon: const Icon(Icons.check_circle_outline),
                    ),
                  ],
                ),
              ],
              const Divider(height: 16),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _wrap(
      BuildContext context, Future<void> Function() fn, String onOk) async {
    try {
      await fn();
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(onOk)));
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Action failed: ${friendlyError(e)}')),
        );
      }
    }
  }

  String _fmtQty(double q) =>
      q == q.truncateToDouble() ? q.toInt().toString() : q.toStringAsFixed(1);

  String _daysLabel(int d) {
    if (d < 0) return 'EXPIRED ${-d}d ago';
    if (d == 0) return 'expires today';
    return '${d}d left';
  }

  String _shortDate(DateTime d) =>
      '${d.month.toString().padLeft(2, '0')}/${d.day.toString().padLeft(2, '0')}';
}

class _SwipeHintBanner extends StatefulWidget {
  const _SwipeHintBanner({required this.onDismiss});
  final VoidCallback onDismiss;

  @override
  State<_SwipeHintBanner> createState() => _SwipeHintBannerState();
}

class _SwipeHintBannerState extends State<_SwipeHintBanner>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _slide = Tween<Offset>(begin: Offset.zero, end: const Offset(0.15, 0))
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
    _ctrl.repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      child: Row(
        children: [
          SlideTransition(
            position: _slide,
            child: const Icon(Icons.swipe),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Swipe right to decrement · left to mark used up',
              style: th.textTheme.bodySmall
                  ?.copyWith(color: th.colorScheme.onSurfaceVariant),
            ),
          ),
          IconButton(
            tooltip: 'Dismiss',
            icon: const Icon(Icons.close, size: 16),
            onPressed: widget.onDismiss,
          ),
        ],
      ),
    );
  }
}
