/// Inventory DTOs — every key here mirrors `src/backend/manage_inventory.py:175`
/// (`list_inventory()` jsonify body). Plain Dart classes with manual `fromJson`
/// (RULE 2 + RULE 18 inversion — Dart has no `convertFromSnakeCase`).
library;

class InventoryItem {
  InventoryItem({
    required this.id,
    required this.productId,
    required this.productName,
    required this.rawName,
    required this.category,
    required this.location,
    required this.quantity,
    required this.unit,
    required this.sizeLabel,
    required this.threshold,
    required this.manualLow,
    required this.isLow,
    required this.isRegularUse,
    required this.expiresAt,
    required this.expiresAtSystem,
    required this.expiresSource,
    required this.lastPurchasedAt,
    required this.daysLeft,
    required this.status,
    required this.remainingPct,
    required this.snapshotImageUrl,
  });
  final int id;
  final int productId;
  final String productName;
  final String rawName;
  final String category;
  final String location;
  final double quantity;
  final String unit;
  final String? sizeLabel;
  final double? threshold;
  final bool manualLow;
  final bool isLow;
  final bool isRegularUse;
  final DateTime? expiresAt;
  final DateTime? expiresAtSystem;
  final String? expiresSource;
  final DateTime? lastPurchasedAt;
  final int? daysLeft;
  final String status;
  final double remainingPct;
  final String? snapshotImageUrl;

  factory InventoryItem.fromJson(Map<String, dynamic> json) {
    final snap = (json['latest_snapshot'] as Map?)?.cast<String, dynamic>();
    return InventoryItem(
      id: (json['id'] as num).toInt(),
      productId: (json['product_id'] as num).toInt(),
      productName: (json['product_name'] as String?) ??
          (json['raw_name'] as String?) ??
          'Unnamed',
      rawName: (json['raw_name'] as String?) ?? '',
      category: (json['category'] as String?) ?? 'other',
      location: (json['location'] as String?) ?? '',
      quantity: (json['quantity'] as num?)?.toDouble() ?? 0,
      unit: (json['unit'] as String?) ?? 'each',
      sizeLabel: json['size_label'] as String?,
      threshold: (json['threshold'] as num?)?.toDouble(),
      manualLow: (json['manual_low'] as bool?) ?? false,
      isLow: (json['is_low'] as bool?) ?? false,
      isRegularUse: (json['is_regular_use'] as bool?) ?? false,
      expiresAt: _parseDate(json['expires_at']),
      expiresAtSystem: _parseDate(json['expires_at_system']),
      expiresSource: json['expires_source'] as String?,
      lastPurchasedAt: _parseDate(json['last_purchased_at']),
      daysLeft: (json['days_left'] as num?)?.toInt(),
      status: (json['status'] as String?) ?? 'fresh',
      remainingPct: (json['remaining_pct'] as num?)?.toDouble() ?? 100.0,
      snapshotImageUrl: snap == null ? null : snap['image_url'] as String?,
    );
  }
}

DateTime? _parseDate(Object? v) {
  if (v is! String) return null;
  return DateTime.tryParse(v);
}

class InventoryList {
  InventoryList({
    required this.items,
    required this.count,
    required this.windowLabel,
    required this.windowStart,
  });
  final List<InventoryItem> items;
  final int count;
  final String windowLabel;
  final String windowStart;

  factory InventoryList.fromJson(Map<String, dynamic> json) => InventoryList(
        items: ((json['inventory'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => InventoryItem.fromJson(m.cast<String, dynamic>()))
            .toList(),
        count: (json['count'] as num?)?.toInt() ?? 0,
        windowLabel: (json['window_label'] as String?) ?? '',
        windowStart: (json['window_start'] as String?) ?? '',
      );

  static InventoryList empty = InventoryList(
    items: const [],
    count: 0,
    windowLabel: '',
    windowStart: '',
  );
}
