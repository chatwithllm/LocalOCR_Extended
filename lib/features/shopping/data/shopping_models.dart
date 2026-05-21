/// Shopping DTOs — mirror `_serialize_item()` + `_build_shopping_list_payload()`
/// at `src/backend/manage_shopping_list.py:216/478` (RULE 2).
library;

class ShoppingItem {
  ShoppingItem({
    required this.id,
    required this.productId,
    required this.name,
    required this.displayName,
    required this.category,
    required this.quantity,
    required this.unit,
    required this.sizeLabel,
    required this.status,
    required this.source,
    required this.note,
    required this.preferredStore,
    required this.manualEstimatedPrice,
    required this.actualPrice,
    required this.effectiveStore,
    required this.latestPrice,
    required this.snapshotImageUrl,
  });
  final int id;
  final int? productId;
  final String name;
  final String? displayName;
  final String? category;
  final double quantity;
  final String unit;
  final String? sizeLabel;
  final String status; // open | purchased | out_of_stock | …
  final String? source;
  final String? note;
  final String? preferredStore;
  final double? manualEstimatedPrice;
  final double? actualPrice;
  final String? effectiveStore;
  final double? latestPrice; // unit price
  final String? snapshotImageUrl;

  factory ShoppingItem.fromJson(Map<String, dynamic> j) {
    final lp = j['latest_price'];
    double? lpPrice;
    if (lp is Map) {
      final p = lp['price'];
      lpPrice = (p is num) ? p.toDouble() : null;
    }
    final snap = j['latest_snapshot'];
    String? snapUrl;
    if (snap is Map) snapUrl = snap['image_url'] as String?;
    return ShoppingItem(
      id: (j['id'] as num).toInt(),
      productId: (j['product_id'] as num?)?.toInt(),
      name: (j['name'] as String?) ?? '',
      displayName: j['product_display_name'] as String?,
      category: j['category'] as String?,
      quantity: (j['quantity'] as num?)?.toDouble() ?? 1,
      unit: (j['unit'] as String?) ?? 'each',
      sizeLabel: j['size_label'] as String?,
      status: (j['status'] as String?) ?? 'open',
      source: j['source'] as String?,
      note: j['note'] as String?,
      preferredStore: j['preferred_store'] as String?,
      manualEstimatedPrice: (j['manual_estimated_price'] as num?)?.toDouble(),
      actualPrice: (j['actual_price'] as num?)?.toDouble(),
      effectiveStore: j['effective_store'] as String?,
      latestPrice: lpPrice,
      snapshotImageUrl: snapUrl,
    );
  }

  /// Best display name for the row (product_display_name beats raw name).
  String get title => (displayName != null && displayName!.isNotEmpty)
      ? displayName!
      : name;

  double get estimatedLineTotal =>
      (latestPrice ?? manualEstimatedPrice ?? 0) * quantity;
}

class ShoppingSessionInfo {
  ShoppingSessionInfo({
    required this.id,
    required this.status,
    required this.startedAt,
  });
  final int? id;
  final String? status;
  final String? startedAt;

  factory ShoppingSessionInfo.fromJson(Map<String, dynamic> j) =>
      ShoppingSessionInfo(
        id: (j['id'] as num?)?.toInt(),
        status: j['status'] as String?,
        startedAt: j['started_at'] as String?,
      );
}

class ShoppingListPayload {
  ShoppingListPayload({
    required this.items,
    required this.count,
    required this.openCount,
    required this.purchasedCount,
    required this.estimatedTotalCost,
    required this.boughtEstimatedTotal,
    required this.actualTotal,
    required this.variance,
    required this.suggestedStores,
    required this.session,
  });
  final List<ShoppingItem> items;
  final int count;
  final int openCount;
  final int purchasedCount;
  final double estimatedTotalCost;
  final double boughtEstimatedTotal;
  final double actualTotal;
  final double variance;
  final List<String> suggestedStores;
  final ShoppingSessionInfo? session;

  factory ShoppingListPayload.fromJson(Map<String, dynamic> j) {
    final stores = <String>[];
    final raw = j['suggested_stores'];
    if (raw is List) {
      for (final s in raw) {
        if (s is Map && s['store'] is String) stores.add(s['store'] as String);
      }
    }
    return ShoppingListPayload(
      items: ((j['items'] as List?) ?? const [])
          .whereType<Map>()
          .map((m) => ShoppingItem.fromJson(m.cast<String, dynamic>()))
          .toList(),
      count: (j['count'] as num?)?.toInt() ?? 0,
      openCount: (j['open_count'] as num?)?.toInt() ?? 0,
      purchasedCount: (j['purchased_count'] as num?)?.toInt() ?? 0,
      estimatedTotalCost:
          (j['estimated_total_cost'] as num?)?.toDouble() ?? 0,
      boughtEstimatedTotal:
          (j['bought_estimated_total'] as num?)?.toDouble() ?? 0,
      actualTotal: (j['actual_total'] as num?)?.toDouble() ?? 0,
      variance: (j['variance'] as num?)?.toDouble() ?? 0,
      suggestedStores: stores,
      session: j['session'] is Map
          ? ShoppingSessionInfo.fromJson(
              (j['session'] as Map).cast<String, dynamic>())
          : null,
    );
  }
}

const shoppingCategoryOptions = <String>[
  'produce',
  'dairy',
  'meat',
  'frozen',
  'grains',
  'snacks',
  'beverages',
  'household',
  'other',
];
