import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/tokens.generated.dart';
import '../../../core/util/logger.dart';
import '../data/dashboard_models.dart';
import 'dashboard_providers.dart';

/// Dashboard screen (F-201..F-234). Plan §6.3.
///
/// RULE 13 decomposition — every registry row maps to a leaf widget below:
/// - DashboardHeader      → F-201
/// - _DemoHero            → F-202..F-206 (demo, only when not authenticated)
/// - _LeaderboardCard     → F-207..F-210
/// - _AttributionNudge    → F-211
/// - _StatTilesRow        → F-212..F-215
/// - _SpendingByCategory  → F-216..F-219
/// - _LowStockCard        → F-220..F-222 (sourced from /inventory `is_low`)
/// - _ReceiptsActivityCard → F-223..F-227
/// - _TopPicksCard        → F-228, F-229
/// - _ShoppingSummary     → F-230..F-233
/// - F-234 (Floor Obligations) → 🚫 hidden in web, not ported.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(dashboardStateProvider);
    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(dashboardStateProvider);
        await ref.read(dashboardStateProvider.future);
      },
      child: async.when(
        loading: () => const _LoadingView(),
        error: (e, _) => _ErrorView(error: e, ref: ref),
        data: (state) {
          appLogger.i('loaded ${state.cardsLoaded} dashboard cards');
          return _DashboardBody(state: state);
        },
      ),
    );
  }
}

class _LoadingView extends StatelessWidget {
  const _LoadingView();
  @override
  Widget build(BuildContext context) => const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: CircularProgressIndicator(),
        ),
      );
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.error, required this.ref});
  final Object error;
  final WidgetRef ref;
  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const SizedBox(height: 80),
        Icon(Icons.error_outline,
            size: 64, color: Theme.of(context).colorScheme.error),
        const SizedBox(height: 12),
        Text(
          'Dashboard failed to load',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 8),
        Text('$error',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: () => ref.invalidate(dashboardStateProvider),
          child: const Text('Retry'),
        ),
      ],
    );
  }
}

class _DashboardBody extends ConsumerWidget {
  const _DashboardBody({required this.state});
  final DashboardState state;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const _DashboardHeader(),
        const SizedBox(height: 16),
        _LeaderboardCard(leaderboard: state.leaderboard),
        const SizedBox(height: 12),
        _AttributionNudge(stats: state.attribution),
        const SizedBox(height: 12),
        _StatTilesRow(inv: state.inventory, prod: state.products),
        const SizedBox(height: 12),
        _SpendingByCategoryCard(spending: state.spending),
        const SizedBox(height: 12),
        _LowStockCard(low: state.inventory),
        const SizedBox(height: 12),
        _ReceiptsActivityCard(activity: state.activity),
        const SizedBox(height: 12),
        _TopPicksCard(recs: state.recommendations),
        const SizedBox(height: 12),
        _ShoppingSummaryCard(shopping: state.shopping),
        const SizedBox(height: 32),
      ],
    );
  }
}

// ---- F-201 Header ---------------------------------------------------------

class _DashboardHeader extends StatelessWidget {
  const _DashboardHeader();
  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Dashboard',
            key: const Key('dashboard-h1'),
            style: th.textTheme.headlineMedium),
        const SizedBox(height: 4),
        Text(
          'Your household system at a glance',
          style: th.textTheme.bodyMedium?.copyWith(
            color: th.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

// ---- F-207..F-210 Leaderboard --------------------------------------------

class _LeaderboardCard extends ConsumerWidget {
  const _LeaderboardCard({required this.leaderboard});
  final Leaderboard leaderboard;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final expanded = ref.watch(
        dashboardSectionExpandedProvider('leaderboard'));
    final entries = leaderboard.entries;
    final top3 = entries.take(3).toList();
    final rest = entries.skip(3).toList();
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(Icons.emoji_events_outlined,
                  color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Household contributions',
                  key: const Key('dashboard-leaderboard-title'),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              if (entries.length > 3)
                TextButton(
                  key: const Key('dashboard-leaderboard-toggle'),
                  onPressed: () => ref
                      .read(dashboardSectionExpandedProvider('leaderboard').notifier)
                      .state = !expanded,
                  child: Text(expanded ? 'Collapse' : 'Show full ranking'),
                ),
            ],
          ),
          const SizedBox(height: 8),
          if (entries.isEmpty)
            const _EmptyTile(label: 'No contributions yet'),
          // Collapsed preview F-208
          if (top3.isNotEmpty)
            InkWell(
              key: const Key('dashboard-leaderboard-preview'),
              onTap: () => ref
                  .read(dashboardSectionExpandedProvider('leaderboard').notifier)
                  .state = !expanded,
              child: Column(
                children: [
                  for (final e in top3) _LeaderboardRow(entry: e),
                ],
              ),
            ),
          if (expanded && rest.isNotEmpty)
            for (final e in rest) _LeaderboardRow(entry: e),
        ],
      ),
    );
  }
}

class _LeaderboardRow extends StatelessWidget {
  const _LeaderboardRow({required this.entry});
  final LeaderboardEntry entry;
  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    return Semantics(
      button: true,
      label:
          '${entry.name}, rank #${entry.rank}, ${entry.points} points. Tap to view contributions.',
      child: InkWell(
        onTap: () {
          // F-210 row tap → navigate to contributions screen for this user.
          GoRouter.of(context).go('/contributions');
        },
        child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
        child: Row(
          children: [
            Text(
              entry.rank > 0 ? '#${entry.rank}' : '·',
              style: th.textTheme.bodySmall?.copyWith(
                color: th.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(width: 8),
            CircleAvatar(
              backgroundColor: th.colorScheme.primaryContainer,
              child: Text(entry.avatarEmoji ??
                  (entry.name.isNotEmpty ? entry.name[0] : '?')),
            ),
            const SizedBox(width: 12),
            Expanded(
                child:
                    Text(entry.name, style: th.textTheme.bodyLarge)),
            Text('${entry.points} pts',
                style: th.textTheme.titleSmall?.copyWith(
                  color: th.colorScheme.primary,
                )),
          ],
        ),
      ),
    ),
  );
  }
}

// ---- F-211 Attribution nudge ---------------------------------------------

class _AttributionNudge extends StatelessWidget {
  const _AttributionNudge({required this.stats});
  final AttributionStats stats;
  @override
  Widget build(BuildContext context) {
    if (stats.untaggedCount == 0) return const SizedBox.shrink();
    final th = Theme.of(context);
    final word = stats.untaggedCount == 1 ? 'receipt' : 'receipts';
    return _Card(
      key: const Key('dashboard-attribution-nudge'),
      child: Row(
        children: [
          Icon(Icons.local_offer_outlined,
              color: th.colorScheme.tertiary),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              '${stats.untaggedCount} $word untagged',
              key: const Key('dashboard-attr-nudge-text'),
              style: th.textTheme.bodyMedium,
            ),
          ),
          TextButton(
            key: const Key('dashboard-attribution-tag-now'),
            onPressed: () => GoRouter.of(context).go('/receipts?untagged_only=1'),
            child: const Text('Tag now →'),
          ),
        ],
      ),
    );
  }
}

// ---- F-212..F-214 Stat tiles ---------------------------------------------

class _StatTilesRow extends StatelessWidget {
  const _StatTilesRow({required this.inv, required this.prod});
  final InventoryStats inv;
  final ProductsStats prod;
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _StatTile(
            key: const Key('stat-low-inline'),
            label: 'Low stock',
            value: '${inv.lowCount}',
            icon: Icons.warning_amber_outlined,
            onTap: () => GoRouter.of(context)
                .go('/inventory?group_by=low_first'),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _StatTile(
            key: const Key('stat-inv-inline'),
            label: 'Inventory',
            value: '${inv.itemCount}',
            icon: Icons.kitchen_outlined,
            onTap: () => GoRouter.of(context).go('/inventory'),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _StatTile(
            key: const Key('stat-products-inline'),
            label: 'Products',
            value: '${prod.total}',
            icon: Icons.inventory_2_outlined,
            onTap: () => GoRouter.of(context).go('/products'),
          ),
        ),
      ],
    );
  }
}

class _StatTile extends StatelessWidget {
  const _StatTile({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    required this.onTap,
  });
  final String label;
  final String value;
  final IconData icon;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    return _Card(
      padding: const EdgeInsets.all(12),
      onTap: onTap,
      semanticLabel: '$value $label — tap to view',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: th.colorScheme.primary),
          const SizedBox(height: 8),
          Text(value, style: th.textTheme.headlineSmall),
          Text(label,
              style: th.textTheme.bodySmall?.copyWith(
                color: th.colorScheme.onSurfaceVariant,
              )),
        ],
      ),
    );
  }
}

// ---- F-216..F-219 Spending by Category -----------------------------------

class _SpendingByCategoryCard extends ConsumerWidget {
  const _SpendingByCategoryCard({required this.spending});
  final SpendingByCategory spending;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final expanded =
        ref.watch(dashboardSectionExpandedProvider('spending'));
    final showMore = ref.watch(dashboardSpendingMoreProvider);
    final cats = showMore
        ? spending.categories
        : spending.categories.take(6).toList();
    final th = Theme.of(context);
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            key: const Key('dashboard-spending-toggle'),
            onTap: () => ref
                .read(dashboardSectionExpandedProvider('spending').notifier)
                .state = !expanded,
            child: Row(
              children: [
                Icon(expanded ? Icons.expand_less : Icons.expand_more),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Spending by Category',
                      style: th.textTheme.titleMedium),
                ),
                Text(
                  '\$${spending.total.toStringAsFixed(2)}',
                  key: const Key('dashboard-spending-total'),
                  style: th.textTheme.titleMedium?.copyWith(
                    color: th.colorScheme.primary,
                  ),
                ),
              ],
            ),
          ),
          if (expanded) ...[
            const SizedBox(height: 8),
            if (cats.isEmpty) const _EmptyTile(label: 'No spending this month'),
            for (final c in cats) _SpendingRow(category: c),
            if (spending.categories.length > 6)
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  key: const Key('dashboard-spending-more'),
                  onPressed: () => ref
                      .read(dashboardSpendingMoreProvider.notifier)
                      .state = !showMore,
                  child: Text(showMore ? 'Show less' : 'Show more'),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _SpendingRow extends StatelessWidget {
  const _SpendingRow({required this.category});
  final SpendingCategory category;
  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    final tokens = th.extension<AppTokens>()!;
    return InkWell(
      onTap: () {
        // F-218 row tap → drill panel (analytics screen for now).
        GoRouter.of(context)
            .go('/analytics?category=${Uri.encodeComponent(category.category)}');
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
        child: Row(
          children: [
            Expanded(
              child: Text(category.category,
                  style: th.textTheme.bodyLarge),
            ),
            Text('\$${category.amount.toStringAsFixed(2)} · ${category.sharePct}%',
                style: th.textTheme.bodyMedium),
            if (category.deltaPct != null) ...[
              const SizedBox(width: 6),
              Text(
                '${category.deltaPct! >= 0 ? '+' : ''}${category.deltaPct}%',
                style: th.textTheme.bodySmall?.copyWith(
                  color: category.deltaPct! >= 0
                      ? tokens.error
                      : tokens.success,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ---- F-220..F-222 Low stock ----------------------------------------------

class _LowStockCard extends ConsumerWidget {
  const _LowStockCard({required this.low});
  final InventoryStats low;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final expanded =
        ref.watch(dashboardSectionExpandedProvider('low-stock'));
    final th = Theme.of(context);
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: () => ref
                .read(dashboardSectionExpandedProvider('low-stock').notifier)
                .state = !expanded,
            child: Row(
              children: [
                Text('⚠️  Low Stock', style: th.textTheme.titleMedium),
                const SizedBox(width: 8),
                Container(
                  key: const Key('dashboard-low-chip'),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: th.colorScheme.errorContainer,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text('${low.lowCount}',
                      style: th.textTheme.labelSmall?.copyWith(
                        color: th.colorScheme.onErrorContainer,
                      )),
                ),
                const Spacer(),
                Icon(expanded ? Icons.expand_less : Icons.expand_more),
              ],
            ),
          ),
          if (expanded) ...[
            const SizedBox(height: 8),
            if (low.lowCount == 0)
              const _EmptyTile(label: 'No items running low')
            else ...[
              for (final item in low.lowItems.take(5))
                _LowStockItemRow(item: item),
              if (low.lowCount > 5)
                InkWell(
                  onTap: () => GoRouter.of(context)
                      .go('/inventory?group_by=low_first'),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Text(
                      'Open Inventory to triage all ${low.lowCount} →',
                      style: th.textTheme.bodyMedium,
                    ),
                  ),
                ),
            ],
          ],
        ],
      ),
    );
  }
}

class _LowStockItemRow extends StatelessWidget {
  const _LowStockItemRow({required this.item});
  final InventoryLowItem item;
  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    return InkWell(
      onTap: () => GoRouter.of(context)
          .go('/inventory?group_by=low_first&item_id=${item.id}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
        child: Row(
          children: [
            Icon(Icons.warning_amber_outlined,
                size: 18, color: th.colorScheme.error),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.name, style: th.textTheme.bodyMedium),
                  if (item.location.isNotEmpty)
                    Text(item.location,
                        style: th.textTheme.bodySmall?.copyWith(
                          color: th.colorScheme.onSurfaceVariant,
                        )),
                ],
              ),
            ),
            Text(
              '${item.quantity == item.quantity.truncateToDouble() ? item.quantity.toInt() : item.quantity} ${item.unit}',
              style: th.textTheme.labelSmall?.copyWith(
                color: th.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---- F-223..F-227 Receipts activity --------------------------------------

class _ReceiptsActivityCard extends ConsumerWidget {
  const _ReceiptsActivityCard({required this.activity});
  final ReceiptsActivity activity;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final expanded =
        ref.watch(dashboardSectionExpandedProvider('activity'));
    final grain = ref.watch(receiptsActivityGrainProvider);
    final th = Theme.of(context);
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: () => ref
                .read(dashboardSectionExpandedProvider('activity').notifier)
                .state = !expanded,
            child: Row(
              children: [
                Icon(expanded ? Icons.expand_less : Icons.expand_more),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Receipts processed',
                      style: th.textTheme.titleMedium),
                ),
                Text('${activity.total}',
                    style: th.textTheme.titleMedium),
              ],
            ),
          ),
          if (expanded) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                for (final g in const ['day', 'week', 'month'])
                  ChoiceChip(
                    key: Key('activity-grain-$g'),
                    label: Text(g[0].toUpperCase() + g.substring(1)),
                    selected: grain == g,
                    onSelected: (_) => ref
                        .read(receiptsActivityGrainProvider.notifier)
                        .state = g,
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Builder(builder: (context) {
              final buckets = activity.buckets;
              final trend = buckets.length >= 2
                  ? (buckets.last.count >= buckets.first.count
                      ? 'increasing'
                      : 'decreasing')
                  : 'stable';
              return Semantics(
                label:
                    '${activity.total} receipts processed. Trend is $trend.',
                excludeSemantics: true,
                child: SizedBox(
                  height: 80,
                  child: _Sparkline(activity: activity),
                ),
              );
            }),
          ],
        ],
      ),
    );
  }
}

class _Sparkline extends StatelessWidget {
  const _Sparkline({required this.activity});
  final ReceiptsActivity activity;
  @override
  Widget build(BuildContext context) {
    if (activity.buckets.isEmpty) {
      return Center(
        child: Text(
          'No receipts in this window',
          style: Theme.of(context).textTheme.bodySmall,
        ),
      );
    }
    final maxV = activity.buckets
        .map((b) => b.count)
        .fold<int>(0, (a, b) => a > b ? a : b);
    return CustomPaint(
      painter: _SparkPainter(
        values: activity.buckets.map((b) => b.count.toDouble()).toList(),
        maxValue: (maxV == 0 ? 1 : maxV).toDouble(),
        color: Theme.of(context).colorScheme.primary,
      ),
      child: const SizedBox.expand(),
    );
  }
}

class _SparkPainter extends CustomPainter {
  _SparkPainter({
    required this.values,
    required this.maxValue,
    required this.color,
  });
  final List<double> values;
  final double maxValue;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty) return;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    final path = Path();
    final dx = values.length > 1 ? size.width / (values.length - 1) : 0;
    for (int i = 0; i < values.length; i++) {
      final x = i * dx.toDouble();
      final y = size.height - (values[i] / maxValue) * size.height;
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _SparkPainter old) =>
      old.values != values || old.maxValue != maxValue || old.color != color;
}

// ---- F-228..F-229 Top picks ----------------------------------------------

class _TopPicksCard extends ConsumerStatefulWidget {
  const _TopPicksCard({required this.recs});
  final RecommendationList recs;
  @override
  ConsumerState<_TopPicksCard> createState() => _TopPicksCardState();
}

class _TopPicksCardState extends ConsumerState<_TopPicksCard> {
  final Set<String> _adding = <String>{};

  @override
  Widget build(BuildContext context) {
    final expanded =
        ref.watch(dashboardSectionExpandedProvider('recs'));
    final th = Theme.of(context);
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: () => ref
                .read(dashboardSectionExpandedProvider('recs').notifier)
                .state = !expanded,
            child: Row(
              children: [
                Icon(expanded ? Icons.expand_less : Icons.expand_more),
                const SizedBox(width: 8),
                Expanded(
                  child:
                      Text('Top picks', style: th.textTheme.titleMedium),
                ),
                Text('${widget.recs.count}',
                    style: th.textTheme.titleMedium),
              ],
            ),
          ),
          if (expanded) ...[
            const SizedBox(height: 8),
            if (widget.recs.recommendations.isEmpty)
              const _EmptyTile(label: 'No recommendations yet'),
            for (final r in widget.recs.recommendations.take(5))
              _RecRow(
                rec: r,
                busy: _adding.contains(r.id),
                onAdd: () async {
                  final messenger = ScaffoldMessenger.of(context);
                  setState(() => _adding.add(r.id));
                  try {
                    await ref
                        .read(dashboardRepositoryProvider)
                        .addRecommendationToList(r);
                    messenger.showSnackBar(
                      SnackBar(content: Text('Added "${r.title}"')),
                    );
                  } catch (e) {
                    messenger.showSnackBar(
                      SnackBar(content: Text('Add failed: $e')),
                    );
                  } finally {
                    if (mounted) setState(() => _adding.remove(r.id));
                  }
                },
              ),
          ],
        ],
      ),
    );
  }
}

class _RecRow extends StatelessWidget {
  const _RecRow({required this.rec, required this.busy, required this.onAdd});
  final Recommendation rec;
  final bool busy;
  final VoidCallback onAdd;
  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(rec.title, style: th.textTheme.bodyLarge),
                if (rec.subtitle.isNotEmpty)
                  Text(rec.subtitle,
                      style: th.textTheme.bodySmall?.copyWith(
                        color: th.colorScheme.onSurfaceVariant,
                      )),
              ],
            ),
          ),
          if (rec.onShoppingList)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Icon(Icons.check_circle,
                  color: th.colorScheme.primary, size: 18),
            ),
          IconButton(
            key: Key('rec-add-${rec.id}'),
            tooltip: 'Add to shopping list',
            onPressed: busy ? null : onAdd,
            icon: busy
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.add_shopping_cart),
          ),
        ],
      ),
    );
  }
}

// ---- F-230..F-233 Shopping summary ---------------------------------------

class _ShoppingSummaryCard extends ConsumerWidget {
  const _ShoppingSummaryCard({required this.shopping});
  final ShoppingSummary shopping;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final showPreview =
        ref.watch(dashboardShoppingPreviewExpandedProvider);
    final th = Theme.of(context);
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: () => GoRouter.of(context).go('/shopping'),
            child: Row(
              children: [
                Icon(Icons.shopping_cart_outlined,
                    color: th.colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Shopping list',
                    key: const Key('dashboard-shopping-title'),
                    style: th.textTheme.titleMedium,
                  ),
                ),
                Container(
                  key: const Key('dash-shopping-header-count'),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: th.colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text('${shopping.openCount}',
                      style: th.textTheme.labelSmall?.copyWith(
                        color: th.colorScheme.onPrimaryContainer,
                      )),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Text('Est. \$${shopping.estimatedTotal.toStringAsFixed(2)}',
                  style: th.textTheme.bodyMedium),
              const Spacer(),
              TextButton(
                key: const Key('dashboard-shopping-preview-toggle'),
                onPressed: () => ref
                    .read(dashboardShoppingPreviewExpandedProvider.notifier)
                    .state = !showPreview,
                child: Text(showPreview ? 'Hide preview' : 'Estimate'),
              ),
            ],
          ),
          if (showPreview) ...[
            if (shopping.preview.isEmpty)
              const _EmptyTile(label: 'List is empty')
            else
              for (final p in shopping.preview)
                ListTile(
                  dense: true,
                  visualDensity: VisualDensity.compact,
                  contentPadding: EdgeInsets.zero,
                  title: Text(p.name),
                  subtitle: Text('${p.quantity}${p.unit != null ? ' ${p.unit}' : ''}'),
                  onTap: () =>
                      GoRouter.of(context).go('/shopping?item_id=${p.id}'),
                ),
          ],
        ],
      ),
    );
  }
}

// ---- shared bits ---------------------------------------------------------

class _Card extends StatelessWidget {
  const _Card({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.onTap,
    this.semanticLabel,
  });
  final Widget child;
  final EdgeInsets padding;
  final VoidCallback? onTap;
  final String? semanticLabel;
  @override
  Widget build(BuildContext context) {
    final th = Theme.of(context);
    return Semantics(
      button: onTap != null,
      label: semanticLabel,
      child: Material(
        color: th.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
  }
}

class _EmptyTile extends StatelessWidget {
  const _EmptyTile({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Text(label,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                )),
      );
}
