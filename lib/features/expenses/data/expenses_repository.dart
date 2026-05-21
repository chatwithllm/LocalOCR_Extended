/// Expenses repo — endpoints verified at
/// `src/backend/calculate_spending_analytics.py:191` and
/// `src/backend/manage_household_budget.py:160/284` (RULE 1).
library;

import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import '../../restaurant/data/restaurant_models.dart' show BudgetStatus;
import 'expenses_models.dart';

class ExpensesRepository {
  ExpensesRepository(this._api);
  final ApiClient _api;

  /// GET /analytics/expense-summary?months=N
  Future<ExpenseSummary> summary({int months = 6}) async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.analyticsExpenseSummary,
      query: {'months': months},
    );
    return ExpenseSummary.fromJson(data);
  }

  /// GET /budget/status?month=&domain=general_expense
  Future<BudgetStatus?> budgetStatus({required String month}) async {
    try {
      final data = await _api.get<Map<String, dynamic>>(
        Endpoints.budgetStatus,
        query: {'month': month, 'domain': 'general_expense'},
      );
      return BudgetStatus.fromJson(data);
    } catch (_) {
      return null;
    }
  }

  /// POST /budget/set-monthly body {month, domain:'general_expense', budget_amount}
  Future<void> setBudget({required String month, required double amount}) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.budgetSetMonthly,
      body: {
        'month': month,
        'domain': 'general_expense',
        'budget_amount': amount,
      },
    );
  }
}
