import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../../restaurant/data/restaurant_models.dart' show BudgetStatus;
import '../data/expenses_models.dart';
import '../data/expenses_repository.dart';

final expensesRepositoryProvider = Provider<ExpensesRepository>((ref) {
  return ExpensesRepository(ref.watch(apiClientProvider));
});

String _currentMonth() {
  final n = DateTime.now();
  return '${n.year.toString().padLeft(4, '0')}-${n.month.toString().padLeft(2, '0')}';
}

final expensesPeriodProvider = StateProvider<int>((ref) => 6);
final expensesBudgetMonthProvider =
    StateProvider<String>((ref) => _currentMonth());

class ExpensesBundle {
  ExpensesBundle({required this.summary, required this.budget});
  final ExpenseSummary summary;
  final BudgetStatus? budget;
}

final expensesBundleProvider =
    FutureProvider.autoDispose<ExpensesBundle>((ref) async {
  final repo = ref.watch(expensesRepositoryProvider);
  final months = ref.watch(expensesPeriodProvider);
  final month = ref.watch(expensesBudgetMonthProvider);
  final sumFut = repo.summary(months: months);
  final budFut = repo.budgetStatus(month: month);
  return ExpensesBundle(summary: await sumFut, budget: await budFut);
});
