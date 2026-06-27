// MARK: Shopping — F-1001..F-1069 (MVP — heavy 🔄 on advanced sub-trees)
//
// Implemented (✅):
//   F-1004 session banner display
//   F-1005 open-count pill + status filter
//   F-1006 estimate total display
//   F-1007 purchased-count pill + status filter
//   F-1012..F-1018 manual add basic form (name/category/qty/price/note/store)
//   F-1030 current-list header
//   F-1031 aggregate total
//   F-1040 item name display
//   F-1049 −1 button
//   F-1050 mark-purchased / reopen toggle
//   F-1057 delete (More-menu equivalent — direct tile button)
//   F-1058 skipped/purchased detailed group (status filter)
//   F-1059 reopen-from-purchased
//
// 🔄 (deferred to Shopping polish wave, see status column for per-row reason):
//   F-1001/F-1019/F-1022/F-1026/F-1030 collapse-toggle infrastructure
//   F-1002/F-1027/F-1028/F-1029 recommendations (✨)
//   F-1003 helper banner (kitchen helper mode)
//   F-1008/F-1011 manual-add hide-toggle / photo preview
//   F-1009/F-1010/F-1065 identify-from-photo subsystem
//   F-1019..F-1025 quick-find subsystem (depends on /products?q= shopping flag)
//   F-1032..F-1034 sort chips
//   F-1035..F-1037 store grouping headers
//   F-1038/F-1039/F-1052/F-1053 product snapshot / thumb / photo subsystem
//   F-1041 full-name expander
//   F-1042..F-1047 per-item inline edit fields (Store/Unit/Size/Price/Update/Rename)
//   F-1048 actual-price reconciliation strip
//   F-1051..F-1056 More menu (low-status, out-of-stock, rename live in 🔄)
//   F-1060 swipe-to-delete on skipped row
//   F-1061..F-1064 long-press / swipe / context-menu / mobile expand
//   F-1066..F-1069 past trips section

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/providers.dart' show appShellActionsProvider;
import '../../../core/util/logger.dart';
import '../data/shopping_models.dart';
import 'shopping_providers.dart';

final _money = NumberFormat.simpleCurrency(name: 'USD');

class ShoppingScreen extends ConsumerStatefulWidget {
  const ShoppingScreen({super.key});
  @override
  ConsumerState<ShoppingScreen> createState() => _ShoppingScreenState();
}

class _ShoppingScreenState extends ConsumerState<ShoppingScreen> {
  late final List<Widget> _appBarActions;

  @override
  void initState() {
    super.initState();
    _appBarActions = [
      IconButton(
        tooltip: 'Refresh',
        icon: const Icon(Icons.refresh),
        onPressed: () => ref.invalidate(shoppingListProvider),
      ),
    ];
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(appShellActionsProvider.notifier).state = _appBarActions;
    });
  }

  @override
  void dispose() {
    ref.read(appShellActionsProvider.notifier).state = const [];
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final listAsync = ref.watch(shoppingListProvider);
    return Scaffold(
      body: listAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _Err(
          msg: 'Could not load shopping list:\n$e',
          retry: () => ref.invalidate(shoppingListProvider),
        ),
        data: (payload) {
          appLogger.i('loaded ${payload.items.length} shopping items '
              '(open=${payload.openCount} purchased=${payload.purchasedCount} '
              'session=${payload.session?.id}/${payload.session?.status})');
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(shoppingListProvider);
              await ref.read(shoppingListProvider.future);
            },
            child: ListView(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
              children: [
                if (payload.session != null)
                  _SessionBanner(session: payload.session!),
                const SizedBox(height: 8),
                _SummaryPills(),
                const SizedBox(height: 8),
                _AddCard(),
                const SizedBox(height: 8),
                _CurrentListCard(payload: payload),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _SessionBanner extends StatelessWidget {
  const _SessionBanner({required this.session});
  final ShoppingSessionInfo session;
  @override
  Widget build(BuildContext context) {
    final label = switch (session.status) {
      'ready_to_bill' => 'Trip ready to bill',
      'closed' => 'Trip closed',
      _ => 'Active trip',
    };
    return Card(
      color: Theme.of(context).colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Row(
          children: [
            const Icon(Icons.shopping_cart_outlined, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '$label · session #${session.id ?? '—'}',
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
            if (session.startedAt != null)
              Text(session.startedAt!.substring(0, 10),
                  style: const TextStyle(fontSize: 11, color: Colors.grey)),
          ],
        ),
      ),
    );
  }
}

class _SummaryPills extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final view = ref.watch(shoppingViewProvider);
    final payload = ref.watch(shoppingListProvider).valueOrNull;
    return SizedBox(
      height: 42,
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: [
          // F-1005 open pill
          _Pill(
            label: 'Open ${payload?.openCount ?? 0}',
            selected: view == 'open',
            onTap: () =>
                ref.read(shoppingViewProvider.notifier).state = 'open',
          ),
          // F-1006 estimate total
          _Pill(
            label: 'Est ${_money.format(payload?.estimatedTotalCost ?? 0)}',
            selected: false,
            onTap: null,
          ),
          // F-1007 purchased pill
          _Pill(
            label: 'Purchased ${payload?.purchasedCount ?? 0}',
            selected: view == 'purchased',
            onTap: () =>
                ref.read(shoppingViewProvider.notifier).state = 'purchased',
          ),
          _Pill(
            label: 'All',
            selected: view == 'all',
            onTap: () =>
                ref.read(shoppingViewProvider.notifier).state = 'all',
          ),
        ],
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback? onTap;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: ChoiceChip(
        label: Text(label),
        selected: selected,
        onSelected: onTap == null ? null : (_) => onTap!(),
      ),
    );
  }
}

// ===== Add card (F-1012..F-1018) =====

class _AddCard extends ConsumerStatefulWidget {
  @override
  ConsumerState<_AddCard> createState() => _AddCardState();
}

class _AddCardState extends ConsumerState<_AddCard> {
  final _name = TextEditingController();
  final _qty = TextEditingController(text: '1');
  final _price = TextEditingController();
  final _note = TextEditingController();
  final _store = TextEditingController();
  String _cat = 'other';
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _qty.dispose();
    _price.dispose();
    _note.dispose();
    _store.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Add Item', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            TextField(
              key: const Key('shop-name'),
              controller: _name,
              decoration: const InputDecoration(
                labelText: 'Name *',
                hintText: 'e.g. milk',
                isDense: true,
              ),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  flex: 2,
                  child: DropdownButtonFormField<String>(
                    key: const Key('shop-cat'),
                    value: _cat,
                    isDense: true,
                    decoration: const InputDecoration(
                      labelText: 'Category',
                      isDense: true,
                    ),
                    items: [
                      for (final c in shoppingCategoryOptions)
                        DropdownMenuItem(value: c, child: Text(c)),
                    ],
                    onChanged: (v) => setState(() => _cat = v ?? 'other'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    key: const Key('shop-qty'),
                    controller: _qty,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                        labelText: 'Qty', isDense: true),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    key: const Key('shop-manual-price'),
                    controller: _price,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                        labelText: 'Est \$', isDense: true),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    key: const Key('shop-manual-store'),
                    controller: _store,
                    decoration: const InputDecoration(
                        labelText: 'Preferred store', isDense: true),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    key: const Key('shop-note'),
                    controller: _note,
                    decoration: const InputDecoration(
                        labelText: 'Note', isDense: true),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                icon: const Icon(Icons.add_shopping_cart),
                label: const Text('Add to Shopping List'),
                onPressed: _busy ? null : _save,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      _toast('Name is required', isError: true);
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(shoppingRepositoryProvider).create(
            name: name,
            category: _cat,
            quantity: double.tryParse(_qty.text.trim()) ?? 1,
            preferredStore: _store.text.trim(),
            manualEstimatedPrice: double.tryParse(_price.text.trim()),
            note: _note.text.trim(),
          );
      _name.clear();
      _price.clear();
      _note.clear();
      ref.invalidate(shoppingListProvider);
      _toast('$name added ✅');
    } catch (e) {
      _toast('Could not add: $e', isError: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toast(String m, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(m),
      backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
    ));
  }
}

// ===== List (F-1030..F-1060) =====

class _CurrentListCard extends ConsumerWidget {
  const _CurrentListCard({required this.payload});
  final ShoppingListPayload payload;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Current List',
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                Text(_money.format(payload.estimatedTotalCost),
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ],
            ),
            const SizedBox(height: 4),
            if (payload.items.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 18),
                child: Center(
                  child: Text('Nothing to shop for. Add an item above.',
                      style: TextStyle(color: Colors.grey)),
                ),
              )
            else
              for (final it in payload.items) _ShoppingTile(item: it),
          ],
        ),
      ),
    );
  }
}

class _ShoppingTile extends ConsumerWidget {
  const _ShoppingTile({required this.item});
  final ShoppingItem item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final isPurchased = item.status == 'purchased';
    final priceStr = item.latestPrice != null
        ? '${_money.format(item.latestPrice)} ea'
        : item.manualEstimatedPrice != null
            ? '~${_money.format(item.manualEstimatedPrice)} ea'
            : '';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          if (item.snapshotImageUrl != null)
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: SizedBox(
                width: 36,
                height: 36,
                child: Image.network(
                  item.snapshotImageUrl!.startsWith('http')
                      ? item.snapshotImageUrl!
                      : '${const String.fromEnvironment('BASE_URL')}${item.snapshotImageUrl}',
                  fit: BoxFit.cover,
                  errorBuilder: (_, _, _) =>
                      const Icon(Icons.shopping_basket_outlined, size: 28),
                ),
              ),
            )
          else
            const SizedBox(
              width: 36,
              height: 36,
              child: Icon(Icons.shopping_basket_outlined, size: 28),
            ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.title,
                  style: t.textTheme.bodyLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                      decoration: isPurchased
                          ? TextDecoration.lineThrough
                          : null,
                      color: isPurchased ? Colors.grey : null),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  '×${_fmt(item.quantity)} ${item.unit}'
                  '${priceStr.isNotEmpty ? ' · $priceStr' : ''}'
                  '${item.effectiveStore != null ? ' · ${item.effectiveStore}' : ''}',
                  style: t.textTheme.bodySmall?.copyWith(color: Colors.grey),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          // F-1049 −1
          if (!isPurchased)
            IconButton(
              tooltip: 'Decrease quantity',
              iconSize: 18,
              visualDensity: VisualDensity.compact,
              icon: const Icon(Icons.remove_circle_outline),
              onPressed: () => _decrement(context, ref),
            ),
          // F-1050 Bought / Reopen
          IconButton(
            tooltip: isPurchased ? 'Reopen' : 'Mark bought',
            iconSize: 18,
            visualDensity: VisualDensity.compact,
            icon: Icon(isPurchased
                ? Icons.replay_circle_filled_outlined
                : Icons.check_circle_outline),
            color: isPurchased ? null : const Color(0xFF66BB6A),
            onPressed: () => _toggle(context, ref),
          ),
          // F-1057 delete
          IconButton(
            tooltip: 'Delete',
            iconSize: 18,
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.delete_outline),
            color: t.colorScheme.error,
            onPressed: () => _deleteWithUndo(context, ref),
          ),
        ],
      ),
    );
  }

  Future<void> _decrement(BuildContext context, WidgetRef ref) async {
    final newQty = (item.quantity - 1);
    if (newQty <= 0) {
      await _deleteWithUndo(context, ref);
      return;
    }
    try {
      await ref.read(shoppingRepositoryProvider).setQuantity(item.id, newQty);
      ref.invalidate(shoppingListProvider);
    } catch (e) {
      _toast(context, 'Could not update: $e', isError: true);
    }
  }

  Future<void> _toggle(BuildContext context, WidgetRef ref) async {
    try {
      if (item.status == 'purchased') {
        await ref.read(shoppingRepositoryProvider).reopen(item.id);
      } else {
        await ref.read(shoppingRepositoryProvider).markPurchased(item.id);
      }
      ref.invalidate(shoppingListProvider);
    } catch (e) {
      _toast(context, 'Could not update: $e', isError: true);
    }
  }

  Future<void> _deleteWithUndo(BuildContext context, WidgetRef ref) async {
    final repo = ref.read(shoppingRepositoryProvider);
    final deleted = item; // capture before any async gap
    try {
      await repo.delete(deleted.id);
      ref.invalidate(shoppingListProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('"${deleted.title}" removed'),
          action: SnackBarAction(
            label: 'Undo',
            onPressed: () async {
              try {
                await repo.create(
                  name: deleted.title,
                  category: deleted.category,
                  quantity: deleted.quantity,
                  unit: deleted.unit,
                  preferredStore: deleted.effectiveStore,
                  manualEstimatedPrice: deleted.manualEstimatedPrice,
                );
                ref.invalidate(shoppingListProvider);
              } catch (_) {}
            },
          ),
          duration: const Duration(seconds: 5),
        ),
      );
    } catch (e) {
      _toast(context, 'Could not delete: $e', isError: true);
    }
  }

  void _toast(BuildContext context, String m, {bool isError = false}) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(m),
      backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
    ));
  }
}

String _fmt(double q) =>
    q == q.roundToDouble() ? q.toInt().toString() : q.toStringAsFixed(2);

class _Err extends StatelessWidget {
  const _Err({required this.msg, required this.retry});
  final String msg;
  final VoidCallback retry;
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48),
              const SizedBox(height: 12),
              Text(msg, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(onPressed: retry, child: const Text('Retry')),
            ],
          ),
        ),
      );
}
