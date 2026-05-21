// Product DTOs — mirror `_serialize_product()` in
// `src/backend/manage_product_catalog.py:217` verbatim (RULE 2).
// RULE 18 inversion: Dart `ApiClient` has no `.convertFromSnakeCase`, so
// explicit snake_case keys are correct here.
library;

class ProductSnapshot {
  ProductSnapshot({
    required this.id,
    required this.imageUrl,
    required this.createdAt,
  });
  final int id;
  final String? imageUrl;
  final String? createdAt;

  factory ProductSnapshot.fromJson(Map<String, dynamic> json) =>
      ProductSnapshot(
        id: (json['id'] as num?)?.toInt() ?? 0,
        imageUrl: json['image_url'] as String?,
        createdAt: json['created_at'] as String?,
      );
}

class ProductPrice {
  ProductPrice({required this.price, required this.date, required this.store});
  final double? price;
  final String? date;
  final String? store;

  factory ProductPrice.fromJson(Map<String, dynamic> json) => ProductPrice(
        price: (json['price'] as num?)?.toDouble(),
        date: json['date'] as String?,
        store: json['store'] as String?,
      );
}

class ProductReceiptLink {
  ProductReceiptLink({
    required this.receiptId,
    required this.store,
    required this.date,
    required this.total,
  });
  final int receiptId;
  final String? store;
  final String? date;
  final double total;

  factory ProductReceiptLink.fromJson(Map<String, dynamic> json) =>
      ProductReceiptLink(
        receiptId: (json['receipt_id'] as num?)?.toInt() ?? 0,
        store: json['store'] as String?,
        date: json['date'] as String?,
        total: (json['total'] as num?)?.toDouble() ?? 0.0,
      );
}

class Product {
  Product({
    required this.id,
    required this.name,
    required this.rawName,
    required this.displayName,
    required this.brand,
    required this.size,
    required this.defaultUnit,
    required this.defaultSizeLabel,
    required this.category,
    required this.barcode,
    required this.createdAt,
    required this.recentReceipts,
    required this.lastPurchaseDate,
    required this.latestPrice,
    required this.latestSnapshot,
    required this.inventoryItemId,
    required this.inventoryQuantity,
    required this.inventoryThreshold,
    required this.manualLow,
    required this.isLow,
    required this.isRegularUse,
  });
  final int id;
  final String name;
  final String rawName;
  final String displayName;
  final String? brand;
  final String? size;
  final String defaultUnit;
  final String? defaultSizeLabel;
  final String category;
  final String? barcode;
  final String? createdAt;
  final List<ProductReceiptLink> recentReceipts;
  final String? lastPurchaseDate;
  /// Backend returns `{price, date, store}` dict (manage_product_catalog.py:173)
  /// — NOT a bare number. RULE 2 mirror verbatim.
  final ProductPrice? latestPrice;
  final ProductSnapshot? latestSnapshot;
  final int? inventoryItemId;
  final double? inventoryQuantity;
  final double? inventoryThreshold;
  final bool manualLow;
  final bool isLow;
  final bool isRegularUse;

  factory Product.fromJson(Map<String, dynamic> json) {
    final snap = (json['latest_snapshot'] as Map?)?.cast<String, dynamic>();
    final links = (json['recent_receipts'] as List?) ?? const [];
    return Product(
      id: (json['id'] as num).toInt(),
      name: (json['name'] as String?) ?? '',
      rawName: (json['raw_name'] as String?) ?? '',
      displayName: (json['display_name'] as String?) ?? '',
      brand: json['brand'] as String?,
      size: json['size'] as String?,
      defaultUnit: (json['default_unit'] as String?) ?? 'each',
      defaultSizeLabel: json['default_size_label'] as String?,
      category: (json['category'] as String?) ?? 'other',
      barcode: json['barcode'] as String?,
      createdAt: json['created_at'] as String?,
      recentReceipts: links
          .whereType<Map>()
          .map((m) => ProductReceiptLink.fromJson(m.cast<String, dynamic>()))
          .toList(),
      lastPurchaseDate: json['last_purchase_date'] as String?,
      latestPrice: (json['latest_price'] as Map?) == null
          ? null
          : ProductPrice.fromJson(
              (json['latest_price'] as Map).cast<String, dynamic>()),
      latestSnapshot: snap == null ? null : ProductSnapshot.fromJson(snap),
      inventoryItemId: (json['inventory_item_id'] as num?)?.toInt(),
      inventoryQuantity: (json['inventory_quantity'] as num?)?.toDouble(),
      inventoryThreshold: (json['inventory_threshold'] as num?)?.toDouble(),
      manualLow: (json['manual_low'] as bool?) ?? false,
      isLow: (json['is_low'] as bool?) ?? false,
      isRegularUse: (json['is_regular_use'] as bool?) ?? false,
    );
  }
}

class ProductList {
  ProductList({required this.products, required this.total});
  final List<Product> products;
  final int total;

  factory ProductList.fromJson(Map<String, dynamic> json) {
    final raw = (json['products'] as List?) ?? (json['results'] as List?) ?? const [];
    return ProductList(
      products: raw
          .whereType<Map>()
          .map((m) => Product.fromJson(m.cast<String, dynamic>()))
          .toList(),
      total: (json['total'] as num?)?.toInt() ?? raw.length,
    );
  }
}

/// Grouped by canonical family name (case-insensitive). Web reduces variants
/// (same family, different size/brand) into a single tile with N-count pill.
class ProductGroup {
  ProductGroup({
    required this.key,
    required this.family,
    required this.displayCategory,
    required this.items,
  });
  final String key;
  final String family;
  final String displayCategory;
  final List<Product> items;

  Product get primary => items.first;
  int get count => items.length;

  static List<ProductGroup> from(List<Product> items) {
    final map = <String, List<Product>>{};
    for (final p in items) {
      final fam = _familyOf(p);
      final key = fam.toLowerCase();
      map.putIfAbsent(key, () => []).add(p);
    }
    final out = <ProductGroup>[];
    map.forEach((key, list) {
      list.sort((a, b) => a.name.compareTo(b.name));
      final primary = list.first;
      out.add(ProductGroup(
        key: key,
        family: _familyOf(primary),
        displayCategory: primary.category,
        items: list,
      ));
    });
    return out;
  }

  static String _familyOf(Product p) {
    final name = p.displayName.isNotEmpty ? p.displayName : p.name;
    return name.trim();
  }

  String? get latestPurchase {
    String? best;
    for (final p in items) {
      final d = p.lastPurchaseDate;
      if (d == null) continue;
      if (best == null || d.compareTo(best) > 0) best = d;
    }
    return best;
  }

  List<String> get examples =>
      items.skip(1).take(2).map((p) => p.name).toList(growable: false);
}

const productSortOptions = <String, String>{
  'name_asc': 'Name ↑',
  'name_desc': 'Name ↓',
  'category_asc': 'Category',
  'variants_desc': 'Most variants',
  'recent_desc': 'Recent purchase',
};

const productCategoryOptions = <String>[
  'other',
  'produce',
  'dairy',
  'meat',
  'pantry',
  'beverage',
  'frozen',
  'bakery',
  'snack',
  'household',
  'health',
  'restaurant',
];
