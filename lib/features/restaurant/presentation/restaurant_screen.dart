// MARK: Restaurant — F-601..F-613
//
// Implemented:
//   F-601 visits stat
//   F-602 dining spend stat
//   F-603 average ticket stat
//   F-604 top restaurant stat
//   F-605 budget month picker
//   F-606 budget amount input
//   F-607 save budget button
//   F-608 budget progress bar
//   F-609 period select (3/6/12 months)
//   F-610 refresh button
//   F-611 receipt row tap → /receipts/<id>
//   F-612 top restaurants row tap → /receipts?store=<name>
//   F-613 top items row (display)

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/providers.dart';
import '../../../core/util/logger.dart';
import '../data/restaurant_models.dart';
import 'restaurant_providers.dart';

final _money = NumberFormat.simpleCurrency(name: 'USD');

class RestaurantScreen extends ConsumerWidget {
  const RestaurantScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bundleAsync = ref.watch(restaurantBundleProvider);
    final isAdmin = ref.watch(sessionProvider)?.user.role == 'admin';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Restaurant'),
        actions: [
          // F-610 refresh
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(restaurantBundleProvider),
          ),
        ],
      ),
      body: bundleAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _ErrorView(
          message: 'Could not load restaurant data:\n$e',
          onRetry: () => ref.invalidate(restaurantBundleProvider),
        ),
        data: (bundle) {
          appLogger.i(
              'loaded restaurant summary visits=${bundle.summary.visitCount} '
              'spend=${bundle.summary.totalSpend.toStringAsFixed(2)} '
              'top=${bundle.summary.topRestaurants.length} '
              'items=${bundle.summary.topItems.length} '
              'receipts=${bundle.summary.recentReceipts.length}');
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(restaurantBundleProvider);
              await ref.read(restaurantBundleProvider.future);
            },
            child: ListView(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
              children: [
                _Subtitle(),
                const SizedBox(height: 8),
                _StatsGrid(summary: bundle.summary),
                const SizedBox(height: 12),
                _BudgetCard(budget: bundle.budget, canEdit: isAdmin),
                const SizedBox(height: 12),
                _ReceiptsCard(summary: bundle.summary),
                const SizedBox(height: 12),
                _TopRestaurantsCard(summary: bundle.summary),
                const SizedBox(height: 12),
                _TopItemsCard(summary: bundle.summary),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _Subtitle extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(horizontal: 4, vertical: 4),
      child: Text(
        'Track dining-out receipts, repeat orders, and restaurant spend '
        'without touching grocery inventory.',
        style: TextStyle(color: Colors.grey),
      ),
    );
  }
}

class _StatsGrid extends ConsumerWidget {
  const _StatsGrid({required this.summary});
  final RestaurantSummary summary;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final period = ref.watch(restaurantPeriodProvider);
    final topStore = summary.topRestaurants.isNotEmpty
        ? summary.topRestaurants.first
        : null;
    return Column(
      children: [
        // F-609 period select
        Row(
          children: [
            const Text('Window:'),
            const SizedBox(width: 8),
            DropdownButton<int>(
              key: const Key('restaurant-period'),
              value: period,
              items: [
                for (final o in restaurantPeriodOptions)
                  DropdownMenuItem(
                      value: int.parse(o['value']!),
                      child: Text(o['label']!))
              ],
              onChanged: (v) {
                if (v == null) return;
                ref.read(restaurantPeriodProvider.notifier).state = v;
              },
            ),
          ],
        ),
        const SizedBox(height: 6),
        // F-601 .. F-604 stats
        GridView.count(
          crossAxisCount: 2,
          mainAxisSpacing: 8,
          crossAxisSpacing: 8,
          childAspectRatio: 1.6,
          physics: const NeverScrollableScrollPhysics(),
          shrinkWrap: true,
          children: [
            _StatCard(
              key: const Key('restaurant-visit-count'),
              label: 'Visits',
              value: '${summary.visitCount}',
              sub: summary.refundCount > 0
                  ? '${summary.refundCount} refund${summary.refundCount == 1 ? '' : 's'} in window'
                  : 'restaurant purchases',
            ),
            _StatCard(
              key: const Key('restaurant-total-spend'),
              label: 'Dining Spend',
              value: _money.format(summary.totalSpend),
              sub: 'current window',
            ),
            _StatCard(
              key: const Key('restaurant-average-ticket'),
              label: 'Average Ticket',
              value: _money.format(summary.averageTicket),
              sub: 'per visit',
            ),
            _StatCard(
              key: const Key('restaurant-top-store'),
              label: 'Top Restaurant',
              value: topStore?.store ?? '—',
              sub: topStore == null
                  ? 'No visits yet'
                  : '${topStore.visits} visit${topStore.visits == 1 ? '' : 's'}'
                      '${topStore.refunds > 0 ? ' · ${topStore.refunds} refund${topStore.refunds == 1 ? '' : 's'}' : ''}'
                      ' · Net ${_money.format(topStore.total)}',
            ),
          ],
        ),
      ],
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    super.key,
    required this.label,
    required this.value,
    required this.sub,
  });
  final String label;
  final String value;
  final String sub;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label,
                style: t.textTheme.labelSmall
                    ?.copyWith(color: Colors.grey)),
            const SizedBox(height: 4),
            Flexible(
              child: Text(
                value,
                style: t.textTheme.titleLarge
                    ?.copyWith(fontWeight: FontWeight.w700),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(height: 4),
            Text(sub,
                style: t.textTheme.bodySmall
                    ?.copyWith(color: Colors.grey, fontSize: 11),
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }
}

// ===== Budget card (F-605, F-606, F-607, F-608) =====

class _BudgetCard extends ConsumerStatefulWidget {
  const _BudgetCard({required this.budget, required this.canEdit});
  final BudgetStatus? budget;
  final bool canEdit;
  @override
  ConsumerState<_BudgetCard> createState() => _BudgetCardState();
}

class _BudgetCardState extends ConsumerState<_BudgetCard> {
  late TextEditingController _amount;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _amount = TextEditingController(
        text: widget.budget?.budgetAmount.toString() ?? '');
  }

  @override
  void didUpdateWidget(covariant _BudgetCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    final b = widget.budget?.budgetAmount;
    if (b != null && _amount.text.isEmpty) {
      _amount.text = b == 0 ? '' : b.toString();
    }
  }

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final month = ref.watch(restaurantBudgetMonthProvider);
    final b = widget.budget;
    final pct = (b?.percentage ?? 0).clamp(0, 100).toDouble();
    final color = pct >= 90
        ? Theme.of(context).colorScheme.error
        : pct >= 70
            ? const Color(0xFFFFB74D)
            : const Color(0xFF66BB6A);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Dining Budget',
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                // F-605 month picker
                TextButton.icon(
                  key: const Key('restaurant-budget-month'),
                  icon: const Icon(Icons.calendar_month_outlined),
                  label: Text(month),
                  onPressed: _busy ? null : _pickMonth,
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (widget.canEdit)
              Row(
                children: [
                  // F-606 amount input
                  Expanded(
                    child: TextField(
                      key: const Key('restaurant-budget-amount'),
                      controller: _amount,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true),
                      decoration: const InputDecoration(
                        labelText: 'Monthly budget',
                        prefixText: '\$ ',
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  // F-607 save
                  FilledButton(
                    onPressed: _busy ? null : _save,
                    child: _busy
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : const Text('Save'),
                  ),
                ],
              )
            else if (b == null || b.budgetAmount == 0)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text('No restaurant budget set for this month yet.',
                    style: TextStyle(color: Colors.grey)),
              ),
            const SizedBox(height: 10),
            // F-608 progress bar + meta
            if (b != null && b.budgetAmount > 0) ...[
              Row(
                children: [
                  Text(_money.format(b.spent),
                      style: Theme.of(context)
                          .textTheme
                          .titleLarge
                          ?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(width: 6),
                  Text('of ${_money.format(b.budgetAmount)}',
                      style: const TextStyle(color: Colors.grey)),
                ],
              ),
              const SizedBox(height: 6),
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: (pct / 100).clamp(0, 1).toDouble(),
                  backgroundColor: Colors.grey.shade300,
                  minHeight: 8,
                  valueColor: AlwaysStoppedAnimation(color),
                ),
              ),
              const SizedBox(height: 6),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${pct.toStringAsFixed(0)}% used · '
                      '${b.purchaseCount} visit${b.purchaseCount == 1 ? '' : 's'}'
                      '${b.refundCount > 0 ? ' · ${b.refundCount} refund${b.refundCount == 1 ? '' : 's'}' : ''}',
                      style: const TextStyle(color: Colors.grey, fontSize: 12),
                    ),
                  ),
                  Text(
                    b.remaining >= 0
                        ? '${_money.format(b.remaining)} left'
                        : '${_money.format(b.remaining.abs())} over',
                    style: TextStyle(
                        color: b.remaining >= 0
                            ? Colors.grey
                            : Theme.of(context).colorScheme.error,
                        fontSize: 12,
                        fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _pickMonth() async {
    final parts = ref.read(restaurantBudgetMonthProvider).split('-');
    final initial = DateTime(int.parse(parts[0]), int.parse(parts[1]), 1);
    final picked = await showDatePicker(
      context: context,
      firstDate: DateTime(2020),
      lastDate: DateTime(DateTime.now().year + 5),
      initialDate: initial,
    );
    if (picked == null) return;
    final m = '${picked.year.toString().padLeft(4, '0')}-'
        '${picked.month.toString().padLeft(2, '0')}';
    ref.read(restaurantBudgetMonthProvider.notifier).state = m;
    _amount.clear();
    ref.invalidate(restaurantBundleProvider);
  }

  Future<void> _save() async {
    final raw = _amount.text.trim();
    final amt = double.tryParse(raw);
    if (amt == null) {
      _toast('Enter a valid number', isError: true);
      return;
    }
    setState(() => _busy = true);
    try {
      await ref.read(restaurantRepositoryProvider).setBudget(
            month: ref.read(restaurantBudgetMonthProvider),
            amount: amt,
          );
      ref.invalidate(restaurantBundleProvider);
      _toast('Restaurant budget saved ✅');
    } catch (e) {
      _toast('Could not save: $e', isError: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toast(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
    ));
  }
}

// ===== Receipts card (F-611) =====

class _ReceiptsCard extends StatelessWidget {
  const _ReceiptsCard({required this.summary});
  final RestaurantSummary summary;

  @override
  Widget build(BuildContext context) {
    final receipts = summary.recentReceipts.take(8).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Restaurant Receipts',
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                TextButton(
                  onPressed: () =>
                      GoRouter.of(context).go('/receipts?type=restaurant'),
                  child: const Text('Open All'),
                ),
              ],
            ),
            const SizedBox(height: 6),
            if (receipts.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 18),
                child: Center(
                  child: Text('No restaurant receipts yet.',
                      style: TextStyle(color: Colors.grey)),
                ),
              )
            else
              for (final r in receipts)
                ListTile(
                  key: Key('restaurant-receipt-${r.purchaseId}'),
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(r.store, maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: Text(
                      '${r.date ?? '—'}${r.transactionType == 'refund' ? ' · refund' : ''}'),
                  trailing: Text(
                    _money.format(r.total),
                    style: TextStyle(
                      color: r.transactionType == 'refund'
                          ? Theme.of(context).colorScheme.error
                          : null,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  onTap: () => GoRouter.of(context).go('/receipts/${r.purchaseId}'),
                ),
          ],
        ),
      ),
    );
  }
}

// ===== Top restaurants card (F-612) =====

class _TopRestaurantsCard extends StatelessWidget {
  const _TopRestaurantsCard({required this.summary});
  final RestaurantSummary summary;

  @override
  Widget build(BuildContext context) {
    final tops = summary.topRestaurants.take(8).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Top Restaurants',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            if (tops.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 18),
                child: Center(
                  child: Text('No restaurant history yet.',
                      style: TextStyle(color: Colors.grey)),
                ),
              )
            else
              for (final t in tops)
                ListTile(
                  key: Key('restaurant-top-${t.store}'),
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(t.store,
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: Text(
                    '${t.visits} visit${t.visits == 1 ? '' : 's'}'
                    '${t.refunds > 0 ? ' · ${t.refunds} refund${t.refunds == 1 ? '' : 's'}' : ''}'
                    '${t.visits > 0 ? ' · Avg ${_money.format(t.averageTicket)}' : ''}',
                  ),
                  trailing: Text(_money.format(t.total),
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  onTap: () => GoRouter.of(context)
                      .go('/receipts?store=${Uri.encodeQueryComponent(t.store)}'),
                ),
          ],
        ),
      ),
    );
  }
}

// ===== Top items card (F-613) =====

class _TopItemsCard extends StatelessWidget {
  const _TopItemsCard({required this.summary});
  final RestaurantSummary summary;

  @override
  Widget build(BuildContext context) {
    final items = summary.topItems.take(10).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Top Ordered Items',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            if (items.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 18),
                child: Center(
                  child: Text('No restaurant line items yet.',
                      style: TextStyle(color: Colors.grey)),
                ),
              )
            else
              for (final it in items)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(it.name,
                            maxLines: 1, overflow: TextOverflow.ellipsis),
                      ),
                      SizedBox(
                          width: 50,
                          child: Text('×${_fmt(it.quantity)}',
                              textAlign: TextAlign.end)),
                      SizedBox(
                          width: 80,
                          child: Text(_money.format(it.total),
                              textAlign: TextAlign.end,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600))),
                      SizedBox(
                          width: 70,
                          child: Text(_money.format(it.averagePrice),
                              textAlign: TextAlign.end,
                              style: const TextStyle(color: Colors.grey))),
                    ],
                  ),
                ),
          ],
        ),
      ),
    );
  }
}

String _fmt(double q) =>
    q == q.roundToDouble() ? q.toInt().toString() : q.toStringAsFixed(2);

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
              FilledButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      );
}
