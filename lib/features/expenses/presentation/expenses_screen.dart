// MARK: Expenses — F-901..F-916
//
// Implemented:
//   F-901 receipts count   F-902 total spend   F-903 avg ticket
//   F-904 top merchant     F-905 budget month  F-906 budget amount
//   F-907 save budget      F-908 budget status F-909 period select
//   F-910 refresh          F-911 receipt row tap → /receipts/<id>
//   F-913 top merchants tap → /receipts?store=<name>
//   F-914 top items (display — web has no row tap, mirrors Restaurant F-613)
//   F-915 category breakdown bar
//
// 🔄:
//   F-912 selected receipt detail — Receipts wave hydrates inline detail;
//         Android navigates to /receipts/<id> route instead (placeholder
//         until Receipts wave). Verb still tap.
//   F-916 mobile reposition — N/A on native (single-column layout).

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/providers.dart';
import '../../../core/util/logger.dart';
import '../../restaurant/data/restaurant_models.dart' show BudgetStatus;
import '../data/expenses_models.dart';
import 'expenses_providers.dart';

final _money = NumberFormat.simpleCurrency(name: 'USD');

class ExpensesScreen extends ConsumerWidget {
  const ExpensesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bundleAsync = ref.watch(expensesBundleProvider);
    final isAdmin = ref.watch(sessionProvider)?.user.role == 'admin';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Expenses'),
        actions: [
          // F-910 refresh
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(expensesBundleProvider),
          ),
        ],
      ),
      body: bundleAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _Err(
          msg: 'Could not load expenses:\n$e',
          retry: () => ref.invalidate(expensesBundleProvider),
        ),
        data: (bundle) {
          appLogger.i(
              'loaded expenses summary purchases=${bundle.summary.purchaseCount} '
              'spend=${bundle.summary.totalSpend.toStringAsFixed(2)} '
              'merchants=${bundle.summary.topMerchants.length} '
              'items=${bundle.summary.topItems.length} '
              'cats=${bundle.summary.categoryBreakdown.length} '
              'receipts=${bundle.summary.recentReceipts.length}');
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(expensesBundleProvider);
              await ref.read(expensesBundleProvider.future);
            },
            child: ListView(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
              children: [
                _StatsGrid(summary: bundle.summary),
                const SizedBox(height: 12),
                _BudgetCard(budget: bundle.budget, canEdit: isAdmin),
                const SizedBox(height: 12),
                _ReceiptsCard(summary: bundle.summary),
                const SizedBox(height: 12),
                _TopMerchantsCard(summary: bundle.summary),
                const SizedBox(height: 12),
                _CategoryBreakdownCard(summary: bundle.summary),
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

class _StatsGrid extends ConsumerWidget {
  const _StatsGrid({required this.summary});
  final ExpenseSummary summary;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final period = ref.watch(expensesPeriodProvider);
    final top = summary.topMerchants.isNotEmpty ? summary.topMerchants.first : null;
    return Column(
      children: [
        Row(
          children: [
            // F-909 period select
            Expanded(
              child: DropdownButtonFormField<int>(
                key: const Key('expense-period'),
                value: period,
                decoration: const InputDecoration(
                  labelText: 'Window',
                  isDense: true,
                ),
                items: const [
                  DropdownMenuItem(value: 3, child: Text('3 months')),
                  DropdownMenuItem(value: 6, child: Text('6 months')),
                  DropdownMenuItem(value: 12, child: Text('12 months')),
                ],
                onChanged: (v) {
                  if (v == null) return;
                  ref.read(expensesPeriodProvider.notifier).state = v;
                },
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        GridView.count(
          crossAxisCount: 2,
          mainAxisSpacing: 8,
          crossAxisSpacing: 8,
          childAspectRatio: 1.6,
          physics: const NeverScrollableScrollPhysics(),
          shrinkWrap: true,
          children: [
            _StatCard(
              key: const Key('expense-receipt-count'),
              label: 'Expense Receipts',
              value: '${summary.purchaseCount}',
              sub: summary.refundCount > 0
                  ? '${summary.refundCount} refund${summary.refundCount == 1 ? '' : 's'} in window'
                  : 'purchase receipts',
            ),
            _StatCard(
              key: const Key('expense-total-spend'),
              label: 'Total Spend',
              value: _money.format(summary.totalSpend),
              sub: 'current window',
            ),
            _StatCard(
              key: const Key('expense-average-ticket'),
              label: 'Average Ticket',
              value: _money.format(summary.averageTicket),
              sub: 'per receipt',
            ),
            _StatCard(
              key: const Key('expense-top-store'),
              label: 'Top Merchant',
              value: top?.store ?? '—',
              sub: top == null
                  ? 'No expenses yet'
                  : '${top.visits} receipt${top.visits == 1 ? '' : 's'}'
                      '${top.refunds > 0 ? ' · ${top.refunds} refund${top.refunds == 1 ? '' : 's'}' : ''}'
                      ' · Net ${_money.format(top.total)}',
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
                style: t.textTheme.labelSmall?.copyWith(color: Colors.grey)),
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
    final month = ref.watch(expensesBudgetMonthProvider);
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
                Text('Expense Budget',
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                // F-905 month picker
                TextButton.icon(
                  key: const Key('expense-budget-month'),
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
                  // F-906 amount input
                  Expanded(
                    child: TextField(
                      key: const Key('expense-budget-amount'),
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
                  // F-907 save
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
                child: Text('No expense budget set for this month yet.',
                    style: TextStyle(color: Colors.grey)),
              ),
            const SizedBox(height: 10),
            // F-908 progress
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
                      '${b.purchaseCount} receipt${b.purchaseCount == 1 ? '' : 's'}'
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
    final parts = ref.read(expensesBudgetMonthProvider).split('-');
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
    ref.read(expensesBudgetMonthProvider.notifier).state = m;
    _amount.clear();
    ref.invalidate(expensesBundleProvider);
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
      await ref.read(expensesRepositoryProvider).setBudget(
            month: ref.read(expensesBudgetMonthProvider),
            amount: amt,
          );
      ref.invalidate(expensesBundleProvider);
      _toast('Expense budget saved ✅');
    } catch (e) {
      _toast('Could not save: $e', isError: true);
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

class _ReceiptsCard extends StatelessWidget {
  const _ReceiptsCard({required this.summary});
  final ExpenseSummary summary;
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
                Text('Expense Receipts',
                    style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                TextButton(
                  onPressed: () => GoRouter.of(context)
                      .go('/receipts?type=general_expense'),
                  child: const Text('Open All'),
                ),
              ],
            ),
            const SizedBox(height: 6),
            if (receipts.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 18),
                child: Center(
                  child: Text('No expense receipts yet.',
                      style: TextStyle(color: Colors.grey)),
                ),
              )
            else
              for (final r in receipts)
                ListTile(
                  key: Key('expense-receipt-${r.purchaseId}'),
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(r.store,
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: Text(
                      '${r.date ?? '—'}'
                      '${r.itemCount > 0 ? ' · ${r.itemCount} item${r.itemCount == 1 ? '' : 's'}' : ''}'
                      '${r.transactionType == 'refund' ? ' · refund' : ''}'),
                  trailing: Text(
                    _money.format(r.total),
                    style: TextStyle(
                      color: r.transactionType == 'refund'
                          ? Theme.of(context).colorScheme.error
                          : null,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  // F-911 + F-912: tap → /receipts/<id>
                  onTap: () =>
                      GoRouter.of(context).go('/receipts/${r.purchaseId}'),
                ),
          ],
        ),
      ),
    );
  }
}

class _TopMerchantsCard extends StatelessWidget {
  const _TopMerchantsCard({required this.summary});
  final ExpenseSummary summary;
  @override
  Widget build(BuildContext context) {
    final tops = summary.topMerchants.take(8).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Top Merchants',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            if (tops.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 18),
                child: Center(
                  child: Text('No merchant history yet.',
                      style: TextStyle(color: Colors.grey)),
                ),
              )
            else
              for (final m in tops)
                ListTile(
                  key: Key('expense-merchant-${m.store}'),
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(m.store,
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: Text(
                    '${m.visits} receipt${m.visits == 1 ? '' : 's'}'
                    '${m.refunds > 0 ? ' · ${m.refunds} refund${m.refunds == 1 ? '' : 's'}' : ''}'
                    '${m.visits > 0 ? ' · Avg ${_money.format(m.averageTicket)}' : ''}',
                  ),
                  trailing: Text(_money.format(m.total),
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  // F-913 tap → /receipts?store=
                  onTap: () => GoRouter.of(context)
                      .go('/receipts?store=${Uri.encodeQueryComponent(m.store)}'),
                ),
          ],
        ),
      ),
    );
  }
}

class _CategoryBreakdownCard extends StatelessWidget {
  const _CategoryBreakdownCard({required this.summary});
  final ExpenseSummary summary;
  @override
  Widget build(BuildContext context) {
    final cats = summary.categoryBreakdown;
    if (cats.isEmpty) return const SizedBox.shrink();
    final total = cats.fold<double>(0, (s, c) => s + c.total.abs());
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Expense Categories',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            // F-915 category breakdown bar
            for (final c in cats)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(_fmtCategory(c.category),
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600)),
                        ),
                        Text(
                            '${c.count} line${c.count == 1 ? '' : 's'} · '
                            '${_money.format(c.total)}',
                            style: const TextStyle(color: Colors.grey, fontSize: 12)),
                      ],
                    ),
                    const SizedBox(height: 4),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: total > 0 ? (c.total.abs() / total) : 0,
                        backgroundColor: Colors.grey.shade300,
                        minHeight: 6,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _fmtCategory(String c) {
    if (c.isEmpty) return 'Other';
    return c[0].toUpperCase() + c.substring(1);
  }
}

class _TopItemsCard extends StatelessWidget {
  const _TopItemsCard({required this.summary});
  final ExpenseSummary summary;
  @override
  Widget build(BuildContext context) {
    final items = summary.topItems.take(10).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Top Reference Items',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            if (items.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 18),
                child: Center(
                  child: Text('No saved expense line items yet.',
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
                              maxLines: 1, overflow: TextOverflow.ellipsis)),
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
