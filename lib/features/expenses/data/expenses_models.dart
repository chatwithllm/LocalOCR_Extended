/// Expenses DTOs — mirror `get_general_expense_summary()` jsonify body at
/// `src/backend/calculate_spending_analytics.py:332-347` (RULE 2). Reuses the
/// same shape family as restaurant-summary plus a `category_breakdown` array.
library;

class ExpenseMerchant {
  ExpenseMerchant({
    required this.store,
    required this.visits,
    required this.refunds,
    required this.total,
    required this.averageTicket,
  });
  final String store;
  final int visits;
  final int refunds;
  final double total;
  final double averageTicket;

  factory ExpenseMerchant.fromJson(Map<String, dynamic> j) => ExpenseMerchant(
        store: (j['store'] as String?) ?? 'Unknown',
        visits: (j['visits'] as num?)?.toInt() ?? 0,
        refunds: (j['refunds'] as num?)?.toInt() ?? 0,
        total: (j['total'] as num?)?.toDouble() ?? 0,
        averageTicket: (j['average_ticket'] as num?)?.toDouble() ?? 0,
      );
}

class ExpenseItem {
  ExpenseItem({
    required this.name,
    required this.quantity,
    required this.total,
    required this.averagePrice,
  });
  final String name;
  final double quantity;
  final double total;
  final double averagePrice;

  factory ExpenseItem.fromJson(Map<String, dynamic> j) => ExpenseItem(
        name: (j['name'] as String?) ?? '',
        quantity: (j['quantity'] as num?)?.toDouble() ?? 0,
        total: (j['total'] as num?)?.toDouble() ?? 0,
        averagePrice: (j['average_price'] as num?)?.toDouble() ?? 0,
      );
}

class ExpenseCategory {
  ExpenseCategory({
    required this.category,
    required this.total,
    required this.count,
  });
  final String category;
  final double total;
  final int count;

  factory ExpenseCategory.fromJson(Map<String, dynamic> j) => ExpenseCategory(
        category: (j['category'] as String?) ?? 'other',
        total: (j['total'] as num?)?.toDouble() ?? 0,
        count: (j['count'] as num?)?.toInt() ?? 0,
      );
}

class ExpenseRecentReceipt {
  ExpenseRecentReceipt({
    required this.purchaseId,
    required this.store,
    required this.date,
    required this.total,
    required this.transactionType,
    required this.itemCount,
  });
  final int purchaseId;
  final String store;
  final String? date;
  final double total;
  final String transactionType;
  final int itemCount;

  factory ExpenseRecentReceipt.fromJson(Map<String, dynamic> j) =>
      ExpenseRecentReceipt(
        purchaseId: (j['purchase_id'] as num).toInt(),
        store: (j['store'] as String?) ?? 'Unknown',
        date: j['date'] as String?,
        total: (j['total'] as num?)?.toDouble() ?? 0,
        transactionType: (j['transaction_type'] as String?) ?? 'purchase',
        itemCount: (j['item_count'] as num?)?.toInt() ?? 0,
      );
}

class ExpenseSummary {
  ExpenseSummary({
    required this.monthsBack,
    required this.receiptCount,
    required this.purchaseCount,
    required this.refundCount,
    required this.totalSpend,
    required this.averageTicket,
    required this.topMerchants,
    required this.topItems,
    required this.categoryBreakdown,
    required this.recentReceipts,
  });
  final int monthsBack;
  final int receiptCount;
  final int purchaseCount;
  final int refundCount;
  final double totalSpend;
  final double averageTicket;
  final List<ExpenseMerchant> topMerchants;
  final List<ExpenseItem> topItems;
  final List<ExpenseCategory> categoryBreakdown;
  final List<ExpenseRecentReceipt> recentReceipts;

  factory ExpenseSummary.fromJson(Map<String, dynamic> j) => ExpenseSummary(
        monthsBack: (j['months_back'] as num?)?.toInt() ?? 6,
        receiptCount: (j['receipt_count'] as num?)?.toInt() ?? 0,
        purchaseCount: (j['purchase_count'] as num?)?.toInt() ?? 0,
        refundCount: (j['refund_count'] as num?)?.toInt() ?? 0,
        totalSpend: (j['total_spend'] as num?)?.toDouble() ?? 0,
        averageTicket: (j['average_ticket'] as num?)?.toDouble() ?? 0,
        topMerchants: ((j['top_merchants'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => ExpenseMerchant.fromJson(m.cast<String, dynamic>()))
            .toList(),
        topItems: ((j['top_items'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => ExpenseItem.fromJson(m.cast<String, dynamic>()))
            .toList(),
        categoryBreakdown: ((j['category_breakdown'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => ExpenseCategory.fromJson(m.cast<String, dynamic>()))
            .toList(),
        recentReceipts: ((j['recent_receipts'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => ExpenseRecentReceipt.fromJson(m.cast<String, dynamic>()))
            .toList(),
      );
}
