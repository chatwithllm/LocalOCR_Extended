/// Restaurant DTOs — mirror `_get_restaurant_summary()` body at
/// `src/backend/calculate_spending_analytics.py:450-462` and
/// `get_budget_status()` body at
/// `src/backend/manage_household_budget.py:332-343` verbatim (RULE 2).
library;

class TopRestaurant {
  TopRestaurant({
    required this.store,
    required this.visits,
    required this.refunds,
    required this.total,
    required this.purchaseTotal,
    required this.refundTotal,
    required this.averageTicket,
    required this.latestDate,
  });
  final String store;
  final int visits;
  final int refunds;
  final double total;
  final double purchaseTotal;
  final double refundTotal;
  final double averageTicket;
  final String? latestDate;

  factory TopRestaurant.fromJson(Map<String, dynamic> j) => TopRestaurant(
        store: (j['store'] as String?) ?? 'Unknown',
        visits: (j['visits'] as num?)?.toInt() ?? 0,
        refunds: (j['refunds'] as num?)?.toInt() ?? 0,
        total: (j['total'] as num?)?.toDouble() ?? 0,
        purchaseTotal: (j['purchase_total'] as num?)?.toDouble() ?? 0,
        refundTotal: (j['refund_total'] as num?)?.toDouble() ?? 0,
        averageTicket: (j['average_ticket'] as num?)?.toDouble() ?? 0,
        latestDate: j['latest_date'] as String?,
      );
}

class TopItem {
  TopItem({
    required this.name,
    required this.quantity,
    required this.total,
    required this.averagePrice,
    required this.category,
  });
  final String name;
  final double quantity;
  final double total;
  final double averagePrice;
  final String? category;

  factory TopItem.fromJson(Map<String, dynamic> j) => TopItem(
        name: (j['name'] as String?) ?? '',
        quantity: (j['quantity'] as num?)?.toDouble() ?? 0,
        total: (j['total'] as num?)?.toDouble() ?? 0,
        averagePrice: (j['average_price'] as num?)?.toDouble() ?? 0,
        category: j['category'] as String?,
      );
}

class RecentRestaurantReceipt {
  RecentRestaurantReceipt({
    required this.purchaseId,
    required this.store,
    required this.date,
    required this.total,
    required this.transactionType,
  });
  final int purchaseId;
  final String store;
  final String? date;
  final double total;
  final String transactionType; // purchase | refund

  factory RecentRestaurantReceipt.fromJson(Map<String, dynamic> j) =>
      RecentRestaurantReceipt(
        purchaseId: (j['purchase_id'] as num).toInt(),
        store: (j['store'] as String?) ?? 'Unknown',
        date: j['date'] as String?,
        total: (j['total'] as num?)?.toDouble() ?? 0,
        transactionType: (j['transaction_type'] as String?) ?? 'purchase',
      );
}

class RestaurantSummary {
  RestaurantSummary({
    required this.monthsBack,
    required this.visitCount,
    required this.receiptCount,
    required this.refundCount,
    required this.totalSpend,
    required this.purchaseTotal,
    required this.refundTotal,
    required this.averageTicket,
    required this.topRestaurants,
    required this.topItems,
    required this.recentReceipts,
  });
  final int monthsBack;
  final int visitCount;
  final int receiptCount;
  final int refundCount;
  final double totalSpend;
  final double purchaseTotal;
  final double refundTotal;
  final double averageTicket;
  final List<TopRestaurant> topRestaurants;
  final List<TopItem> topItems;
  final List<RecentRestaurantReceipt> recentReceipts;

  factory RestaurantSummary.fromJson(Map<String, dynamic> j) =>
      RestaurantSummary(
        monthsBack: (j['months_back'] as num?)?.toInt() ?? 6,
        visitCount: (j['visit_count'] as num?)?.toInt() ?? 0,
        receiptCount: (j['receipt_count'] as num?)?.toInt() ?? 0,
        refundCount: (j['refund_count'] as num?)?.toInt() ?? 0,
        totalSpend: (j['total_spend'] as num?)?.toDouble() ?? 0,
        purchaseTotal: (j['purchase_total'] as num?)?.toDouble() ?? 0,
        refundTotal: (j['refund_total'] as num?)?.toDouble() ?? 0,
        averageTicket: (j['average_ticket'] as num?)?.toDouble() ?? 0,
        topRestaurants: ((j['top_restaurants'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => TopRestaurant.fromJson(m.cast<String, dynamic>()))
            .toList(),
        topItems: ((j['top_items'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) => TopItem.fromJson(m.cast<String, dynamic>()))
            .toList(),
        recentReceipts: ((j['recent_receipts'] as List?) ?? const [])
            .whereType<Map>()
            .map((m) =>
                RecentRestaurantReceipt.fromJson(m.cast<String, dynamic>()))
            .toList(),
      );
}

/// GET /budget/status?month=&domain= envelope (verified against
/// `manage_household_budget.py:332-343`).
class BudgetStatus {
  BudgetStatus({
    required this.month,
    required this.domain,
    required this.budgetCategory,
    required this.budgetAmount,
    required this.spent,
    required this.remaining,
    required this.percentage,
    required this.alertTriggered,
    required this.purchaseCount,
    required this.refundCount,
    required this.receiptCount,
  });
  final String month;
  final String? domain;
  final String? budgetCategory;
  final double budgetAmount;
  final double spent;
  final double remaining;
  final double percentage;
  final bool alertTriggered;
  final int purchaseCount;
  final int refundCount;
  final int receiptCount;

  factory BudgetStatus.fromJson(Map<String, dynamic> j) => BudgetStatus(
        month: (j['month'] as String?) ?? '',
        domain: j['domain'] as String?,
        budgetCategory: j['budget_category'] as String?,
        budgetAmount: (j['budget_amount'] as num?)?.toDouble() ?? 0,
        spent: (j['spent'] as num?)?.toDouble() ?? 0,
        remaining: (j['remaining'] as num?)?.toDouble() ?? 0,
        percentage: (j['percentage'] as num?)?.toDouble() ?? 0,
        alertTriggered: (j['alert_triggered'] as bool?) ?? false,
        purchaseCount: (j['purchase_count'] as num?)?.toInt() ?? 0,
        refundCount: (j['refund_count'] as num?)?.toInt() ?? 0,
        receiptCount: (j['receipt_count'] as num?)?.toInt() ?? 0,
      );
}

const restaurantPeriodOptions = <Map<String, String>>[
  {'value': '3', 'label': '3 months'},
  {'value': '6', 'label': '6 months'},
  {'value': '12', 'label': '12 months'},
];
