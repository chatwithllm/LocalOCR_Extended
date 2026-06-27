// MARK: Balances — F-701..F-706
//
// Implemented:
//   F-701 refresh button
//   F-702 "Who Owes What" card title
//   F-703 per-contact row (name + direction + amount)
//   F-704 per-contact "Settle all" button → POST /contacts/<id>/settle-all
//
// 🔄:
//   F-705 expand → underlying debts list — web /shared-dining/balances does not
//         return per-debt rows; backend `get_all_balances` returns flat
//         {contact_id, name, net_amount}. Web doesn't render an expand UI
//         either. Deferred until backend exposes debt detail per contact.
//   F-706 per-debt settle — POST /shared-dining/debts/<id>/settle exists
//         (shared_dining_endpoints.py:62) but no UI lists debts. Will hydrate
//         once F-705 source is available.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/tokens.generated.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/providers.dart'
    show appShellActionsProvider, currencyFormatterProvider;
import '../../../core/util/logger.dart';
import '../data/balances_models.dart';
import 'balances_providers.dart';


class BalancesScreen extends ConsumerStatefulWidget {
  const BalancesScreen({super.key});
  @override
  ConsumerState<BalancesScreen> createState() => _BalancesScreenState();
}

class _BalancesScreenState extends ConsumerState<BalancesScreen> {
  late final List<Widget> _appBarActions;

  @override
  void initState() {
    super.initState();
    _appBarActions = [
      IconButton(
        tooltip: 'Refresh',
        icon: const Icon(Icons.refresh),
        onPressed: () => ref.invalidate(balancesListProvider),
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
    final async = ref.watch(balancesListProvider);
    return Scaffold(
      body: async.when(
        loading: () => const LoadingView(),
        error: (e, _) => _Err(
          msg: 'Could not load balances:\n$e',
          retry: () => ref.invalidate(balancesListProvider),
        ),
        data: (rows) {
          appLogger.i('loaded ${rows.length} balances');
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(balancesListProvider);
              await ref.read(balancesListProvider.future);
            },
            child: ListView(
              padding: const EdgeInsets.all(12),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // F-702 title
                        Text('Who Owes What',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        if (rows.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 24),
                            child: Center(
                              child: Text(
                                'No outstanding balances — all settled! 🎉',
                                style: TextStyle(color: Colors.grey),
                              ),
                            ),
                          )
                        else
                          for (final r in rows) _BalanceTile(row: r),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _BalanceTile extends ConsumerWidget {
  const _BalanceTile({required this.row});
  final BalanceRow row;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = Theme.of(context);
    final tokens = t.extension<AppTokens>()!;
    final money = ref.watch(currencyFormatterProvider);
    final dir = row.owesYou ? 'Owes you' : 'You owe';
    final color = row.owesYou ? tokens.success : tokens.error;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          // F-703 name + direction + amount
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(row.name,
                    style: t.textTheme.bodyLarge
                        ?.copyWith(fontWeight: FontWeight.w600)),
                Text(dir, style: t.textTheme.bodySmall),
              ],
            ),
          ),
          Text(
            money.format(row.netAmount.abs()),
            style: t.textTheme.titleMedium
                ?.copyWith(color: color, fontWeight: FontWeight.w700),
          ),
          const SizedBox(width: 8),
          // F-704 settle all
          OutlinedButton(
            key: Key('balances-settle-${row.contactId}'),
            onPressed: () => _settle(context, ref),
            child: const Text('Settle all'),
          ),
        ],
      ),
    );
  }

  Future<void> _settle(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Settle all?'),
            content: Text('Mark all balances with ${row.name} as settled?'),
            actions: [
              TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: const Text('Cancel')),
              FilledButton(
                  onPressed: () => Navigator.of(ctx).pop(true),
                  child: const Text('Settle')),
            ],
          ),
        ) ??
        false;
    if (!ok) return;
    try {
      final n =
          await ref.read(balancesRepositoryProvider).settleAll(row.contactId);
      ref.invalidate(balancesListProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Settled $n entr${n == 1 ? 'y' : 'ies'} ✅')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Settle failed: $e')));
      }
    }
  }
}

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
