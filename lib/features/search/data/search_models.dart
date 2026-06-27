library;

class SearchInventoryHit {
  const SearchInventoryHit({
    required this.id,
    required this.productId,
    required this.productName,
    this.brand,
    this.category,
    required this.quantity,
    this.unit,
    this.location,
    this.expiryDate,
  });

  final int id;
  final int productId;
  final String productName;
  final String? brand;
  final String? category;
  final double quantity;
  final String? unit;
  final String? location;
  final String? expiryDate;

  factory SearchInventoryHit.fromJson(Map<String, dynamic> j) =>
      SearchInventoryHit(
        id: (j['id'] as num).toInt(),
        productId: (j['product_id'] as num).toInt(),
        productName: (j['product_name'] as String?) ?? '',
        brand: j['brand'] as String?,
        category: j['category'] as String?,
        quantity: (j['quantity'] as num?)?.toDouble() ?? 0,
        unit: j['unit'] as String?,
        location: j['location'] as String?,
        expiryDate: j['expiry_date'] as String?,
      );
}

class SearchProductHit {
  const SearchProductHit({
    required this.id,
    required this.productName,
    this.brand,
    this.category,
    this.lastPurchaseDate,
    this.lastPurchasePrice,
  });

  final int id;
  final String productName;
  final String? brand;
  final String? category;
  final String? lastPurchaseDate;
  final double? lastPurchasePrice;

  factory SearchProductHit.fromJson(Map<String, dynamic> j) =>
      SearchProductHit(
        id: (j['id'] as num).toInt(),
        productName: (j['product_name'] as String?) ?? '',
        brand: j['brand'] as String?,
        category: j['category'] as String?,
        lastPurchaseDate: j['last_purchase_date'] as String?,
        lastPurchasePrice:
            (j['last_purchase_price'] as num?)?.toDouble(),
      );
}

class SearchReceiptMatchedItem {
  const SearchReceiptMatchedItem({required this.name, this.price});
  final String name;
  final double? price;

  factory SearchReceiptMatchedItem.fromJson(Map<String, dynamic> j) =>
      SearchReceiptMatchedItem(
        name: (j['name'] as String?) ?? '',
        price: (j['price'] as num?)?.toDouble(),
      );
}

class SearchReceiptHit {
  const SearchReceiptHit({
    required this.purchaseId,
    required this.store,
    this.date,
    this.total,
    required this.matchedItems,
  });

  final int purchaseId;
  final String store;
  final String? date;
  final double? total;
  final List<SearchReceiptMatchedItem> matchedItems;

  factory SearchReceiptHit.fromJson(Map<String, dynamic> j) =>
      SearchReceiptHit(
        purchaseId: (j['purchase_id'] as num).toInt(),
        store: (j['store'] as String?) ?? '',
        date: j['date'] as String?,
        total: (j['total'] as num?)?.toDouble(),
        matchedItems: (j['matched_items'] as List<dynamic>? ?? [])
            .map((e) =>
                SearchReceiptMatchedItem.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class SearchResult {
  const SearchResult({
    required this.query,
    required this.inventory,
    required this.products,
    required this.receipts,
  });

  final String query;
  final List<SearchInventoryHit> inventory;
  final List<SearchProductHit> products;
  final List<SearchReceiptHit> receipts;

  bool get isEmpty =>
      inventory.isEmpty && products.isEmpty && receipts.isEmpty;

  factory SearchResult.fromJson(Map<String, dynamic> j) {
    final results = j['results'] as Map<String, dynamic>? ?? {};
    return SearchResult(
      query: (j['query'] as String?) ?? '',
      inventory: (results['inventory'] as List<dynamic>? ?? [])
          .map((e) =>
              SearchInventoryHit.fromJson(e as Map<String, dynamic>))
          .toList(),
      products: (results['products'] as List<dynamic>? ?? [])
          .map((e) =>
              SearchProductHit.fromJson(e as Map<String, dynamic>))
          .toList(),
      receipts: (results['receipts'] as List<dynamic>? ?? [])
          .map((e) =>
              SearchReceiptHit.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}
