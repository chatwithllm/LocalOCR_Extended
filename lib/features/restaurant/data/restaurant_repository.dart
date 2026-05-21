/// Restaurant repo — every endpoint here was grepped from
/// `src/backend/calculate_spending_analytics.py:350` and
/// `src/backend/manage_household_budget.py:160/284` (RULE 1).
library;

import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'restaurant_models.dart';

class RestaurantRepository {
  RestaurantRepository(this._api);
  final ApiClient _api;

  /// GET /analytics/restaurant-summary?months=N
  Future<RestaurantSummary> summary({int months = 6}) async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.analyticsRestaurantSummary,
      query: {'months': months},
    );
    return RestaurantSummary.fromJson(data);
  }

  /// GET /budget/status?month=YYYY-MM&domain=restaurant
  /// Returns null on 404 (no budget set yet — backend currently 200s with
  /// budget_amount=0, but we tolerate either).
  Future<BudgetStatus?> budgetStatus({required String month}) async {
    try {
      final data = await _api.get<Map<String, dynamic>>(
        Endpoints.budgetStatus,
        query: {'month': month, 'domain': 'restaurant'},
      );
      return BudgetStatus.fromJson(data);
    } catch (_) {
      return null;
    }
  }

  /// POST /budget/set-monthly  body {month, domain:'restaurant', budget_amount}
  Future<void> setBudget({required String month, required double amount}) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.budgetSetMonthly,
      body: {
        'month': month,
        'domain': 'restaurant',
        'budget_amount': amount,
      },
    );
  }
}
