/// Dashboard response DTOs. Every key here was read from a
/// `return jsonify(...)` site in `src/backend/*.py` (RULE 1/RULE 2).
/// Plain Dart classes with manual `fromJson` (RULE 18 inversion — Dart has
/// no `convertFromSnakeCase`; declare explicit snake→camel mapping).
library;

/// Mirrors `/contributions/summary` payload (`manage_contributions.py:230`).
/// We only consume the `summary` sub-tree for leaderboard rendering on
/// Dashboard — other fields (rules, recent_events, opportunities, notes)
/// belong to the Contributions screen.
class ContributionsSummary {
  ContributionsSummary({
    required this.entries,
    required this.totalPoints,
  });
  final List<LeaderboardEntry> entries;
  final int totalPoints;

  factory ContributionsSummary.fromJson(Map<String, dynamic> json) {
    // summary key may be a list of leaderboard entries OR an object with
    // {"contributors": [...]}. We tolerate both shapes (RULE 2 — exact mirror;
    // see manage_contributions.py contribution_summary() body for the dict
    // it serializes).
    final raw = json['summary'];
    List<dynamic> list = const [];
    int total = 0;
    if (raw is List) {
      list = raw;
    } else if (raw is Map) {
      final cs = raw['contributors'];
      if (cs is List) list = cs;
      total = (raw['total_points'] as num?)?.toInt() ?? 0;
    }
    final entries = list
        .whereType<Map>()
        .map((m) => LeaderboardEntry.fromJson(m.cast<String, dynamic>()))
        .toList();
    if (total == 0) {
      total = entries.fold<int>(0, (a, e) => a + e.points);
    }
    return ContributionsSummary(entries: entries, totalPoints: total);
  }

  static ContributionsSummary empty =
      ContributionsSummary(entries: const [], totalPoints: 0);
}

class LeaderboardEntry {
  LeaderboardEntry({
    required this.userId,
    required this.name,
    required this.avatarEmoji,
    required this.points,
    required this.rank,
  });
  final int userId;
  final String name;
  final String? avatarEmoji;
  final int points;
  final int rank;

  factory LeaderboardEntry.fromJson(Map<String, dynamic> json) =>
      LeaderboardEntry(
        userId: (json['user_id'] as num?)?.toInt() ??
            (json['id'] as num?)?.toInt() ?? 0,
        name: (json['name'] as String?) ??
            (json['display_name'] as String?) ??
            'Unknown',
        avatarEmoji: json['avatar_emoji'] as String?,
        points: (json['points'] as num?)?.toInt() ??
            (json['score'] as num?)?.toInt() ?? 0,
        rank: (json['rank'] as num?)?.toInt() ?? 0,
      );
}

/// Mirrors `/analytics/spending-by-category` payload
/// (`calculate_spending_analytics.py:1575`).
class SpendingByCategory {
  SpendingByCategory({
    required this.month,
    required this.total,
    required this.categories,
  });
  final String month;
  final double total;
  final List<SpendingCategory> categories;

  factory SpendingByCategory.fromJson(Map<String, dynamic> json) =>
      SpendingByCategory(
        month: (json['month'] as String?) ?? '',
        total: (json['total'] as num?)?.toDouble() ?? 0,
        categories: ((json['categories'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) =>
                SpendingCategory.fromJson(m.cast<String, dynamic>()))
            .toList(),
      );

  static SpendingByCategory empty = SpendingByCategory(
    month: '',
    total: 0,
    categories: const [],
  );
}

class SpendingCategory {
  SpendingCategory({
    required this.category,
    required this.amount,
    required this.sharePct,
    required this.deltaPct,
  });
  final String category;
  final double amount;
  final int sharePct;
  final int? deltaPct;

  factory SpendingCategory.fromJson(Map<String, dynamic> json) =>
      SpendingCategory(
        category: (json['category'] as String?) ?? 'other',
        amount: (json['amount'] as num?)?.toDouble() ?? 0,
        sharePct: (json['share_pct'] as num?)?.toInt() ?? 0,
        deltaPct: (json['delta_pct'] as num?)?.toInt(),
      );
}

/// Mirrors `/analytics/receipts-activity` payload
/// (`calculate_spending_analytics.py:1760`).
class ReceiptsActivity {
  ReceiptsActivity({
    required this.grain,
    required this.count,
    required this.buckets,
    required this.total,
    required this.totalAmount,
  });
  final String grain;
  final int count;
  final List<ReceiptsActivityBucket> buckets;
  final int total;
  final double totalAmount;

  factory ReceiptsActivity.fromJson(Map<String, dynamic> json) =>
      ReceiptsActivity(
        grain: (json['grain'] as String?) ?? 'day',
        count: (json['count'] as num?)?.toInt() ?? 0,
        buckets: ((json['buckets'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) =>
                ReceiptsActivityBucket.fromJson(m.cast<String, dynamic>()))
            .toList(),
        total: (json['total'] as num?)?.toInt() ?? 0,
        totalAmount: (json['total_amount'] as num?)?.toDouble() ?? 0,
      );

  static ReceiptsActivity emptyFor(String grain) =>
      ReceiptsActivity(
        grain: grain,
        count: 0,
        buckets: const [],
        total: 0,
        totalAmount: 0,
      );
}

class ReceiptsActivityBucket {
  ReceiptsActivityBucket({
    required this.period,
    required this.count,
    required this.amount,
  });
  final String period;
  final int count;
  final double amount;

  factory ReceiptsActivityBucket.fromJson(Map<String, dynamic> json) =>
      ReceiptsActivityBucket(
        period: (json['period'] as String?) ?? '',
        count: (json['count'] as num?)?.toInt() ?? 0,
        amount: (json['amount'] as num?)?.toDouble() ?? 0,
      );
}

/// Mirrors `/recommendations` payload (`generate_recommendations.py:46`).
class RecommendationList {
  RecommendationList({required this.recommendations, required this.count});
  final List<Recommendation> recommendations;
  final int count;

  factory RecommendationList.fromJson(Map<String, dynamic> json) =>
      RecommendationList(
        recommendations: ((json['recommendations'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => Recommendation.fromJson(m.cast<String, dynamic>()))
            .toList(),
        count: (json['count'] as num?)?.toInt() ?? 0,
      );

  static RecommendationList empty =
      RecommendationList(recommendations: const [], count: 0);
}

class Recommendation {
  Recommendation({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.productId,
    required this.kind,
    required this.confidence,
    required this.onShoppingList,
  });
  final String id;
  final String title;
  final String subtitle;
  final int? productId;
  final String kind;
  final double confidence;
  final bool onShoppingList;

  factory Recommendation.fromJson(Map<String, dynamic> json) =>
      Recommendation(
        id: (json['id'] as Object?)?.toString() ?? '',
        title: (json['title'] as String?) ??
            (json['name'] as String?) ??
            (json['product_name'] as String?) ??
            'Recommendation',
        subtitle: (json['subtitle'] as String?) ??
            (json['reason'] as String?) ??
            (json['description'] as String?) ??
            '',
        productId: (json['product_id'] as num?)?.toInt(),
        kind: (json['kind'] as String?) ??
            (json['type'] as String?) ??
            'general',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        onShoppingList: (json['on_shopping_list'] as bool?) ?? false,
      );
}

/// Mirrors `/inventory` payload (`manage_inventory.py:142`). We only consume
/// the `count` field on Dashboard; full items belong to Inventory screen.
class InventoryStats {
  InventoryStats({required this.itemCount, required this.lowCount});
  final int itemCount;
  final int lowCount;

  factory InventoryStats.fromJson(Map<String, dynamic> json) {
    final items = (json['items'] as List?) ?? const [];
    final low = items
        .whereType<Map>()
        .where((m) => (m['is_low'] as bool?) ?? false)
        .length;
    return InventoryStats(
      itemCount: (json['count'] as num?)?.toInt() ?? items.length,
      lowCount: low,
    );
  }

  static InventoryStats empty = InventoryStats(itemCount: 0, lowCount: 0);
}

/// Mirrors `/products` payload (`manage_product_catalog.py:260`). We only
/// consume the `total` field on Dashboard.
class ProductsStats {
  ProductsStats({required this.total});
  final int total;

  factory ProductsStats.fromJson(Map<String, dynamic> json) =>
      ProductsStats(total: (json['total'] as num?)?.toInt() ?? 0);

  static ProductsStats empty = ProductsStats(total: 0);
}

/// Subset of `/shopping-list` payload (`manage_shopping_list.py:496` →
/// `_build_shopping_list_payload`). Dashboard cares about open count +
/// estimated total + a small preview of the first few open items.
class ShoppingSummary {
  ShoppingSummary({
    required this.openCount,
    required this.estimatedTotal,
    required this.preview,
  });
  final int openCount;
  final double estimatedTotal;
  final List<ShoppingPreviewItem> preview;

  factory ShoppingSummary.fromJson(Map<String, dynamic> json) {
    final items = ((json['items'] as List?) ?? const [])
        .whereType<Map>()
        .map((m) => m.cast<String, dynamic>())
        .toList();
    final open = items.where((m) => m['status'] == 'open').toList();
    final preview = open
        .take(5)
        .map((m) => ShoppingPreviewItem.fromJson(m))
        .toList();
    final est = (json['total_estimated_cost'] as num?)?.toDouble() ?? 0;
    return ShoppingSummary(
      openCount: open.length,
      estimatedTotal: est,
      preview: preview,
    );
  }

  static ShoppingSummary empty =
      ShoppingSummary(openCount: 0, estimatedTotal: 0, preview: const []);
}

class ShoppingPreviewItem {
  ShoppingPreviewItem({
    required this.id,
    required this.name,
    required this.quantity,
    required this.unit,
  });
  final int id;
  final String name;
  final double quantity;
  final String? unit;

  factory ShoppingPreviewItem.fromJson(Map<String, dynamic> json) =>
      ShoppingPreviewItem(
        id: (json['id'] as num?)?.toInt() ?? 0,
        name: (json['name'] as String?) ?? '',
        quantity: (json['quantity'] as num?)?.toDouble() ?? 0,
        unit: json['unit'] as String?,
      );
}

/// Aggregate state owned by the Dashboard. `null` fields mean the
/// corresponding endpoint has not yet returned (loading or error).
class DashboardState {
  DashboardState({
    required this.leaderboard,
    required this.inventory,
    required this.products,
    required this.spending,
    required this.activity,
    required this.recommendations,
    required this.shopping,
    required this.cardsLoaded,
  });
  final ContributionsSummary leaderboard;
  final InventoryStats inventory;
  final ProductsStats products;
  final SpendingByCategory spending;
  final ReceiptsActivity activity;
  final RecommendationList recommendations;
  final ShoppingSummary shopping;

  /// Number of card payloads that returned without throwing.
  final int cardsLoaded;

  static DashboardState empty = DashboardState(
    leaderboard: ContributionsSummary.empty,
    inventory: InventoryStats.empty,
    products: ProductsStats.empty,
    spending: SpendingByCategory.empty,
    activity: ReceiptsActivity.emptyFor('day'),
    recommendations: RecommendationList.empty,
    shopping: ShoppingSummary.empty,
    cardsLoaded: 0,
  );

  DashboardState copyWith({
    ContributionsSummary? leaderboard,
    InventoryStats? inventory,
    ProductsStats? products,
    SpendingByCategory? spending,
    ReceiptsActivity? activity,
    RecommendationList? recommendations,
    ShoppingSummary? shopping,
    int? cardsLoaded,
  }) =>
      DashboardState(
        leaderboard: leaderboard ?? this.leaderboard,
        inventory: inventory ?? this.inventory,
        products: products ?? this.products,
        spending: spending ?? this.spending,
        activity: activity ?? this.activity,
        recommendations: recommendations ?? this.recommendations,
        shopping: shopping ?? this.shopping,
        cardsLoaded: cardsLoaded ?? this.cardsLoaded,
      );
}
