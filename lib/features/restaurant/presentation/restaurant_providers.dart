import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/restaurant_models.dart';
import '../data/restaurant_repository.dart';

final restaurantRepositoryProvider = Provider<RestaurantRepository>((ref) {
  return RestaurantRepository(ref.watch(apiClientProvider));
});

/// Month picker for budget — YYYY-MM. Defaults to current month.
String _currentMonth() {
  final n = DateTime.now();
  return '${n.year.toString().padLeft(4, '0')}-'
      '${n.month.toString().padLeft(2, '0')}';
}

final restaurantPeriodProvider = StateProvider<int>((ref) => 6);
final restaurantBudgetMonthProvider =
    StateProvider<String>((ref) => _currentMonth());

class RestaurantBundle {
  RestaurantBundle({required this.summary, required this.budget});
  final RestaurantSummary summary;
  final BudgetStatus? budget;
}

final restaurantBundleProvider =
    FutureProvider.autoDispose<RestaurantBundle>((ref) async {
  final repo = ref.watch(restaurantRepositoryProvider);
  final months = ref.watch(restaurantPeriodProvider);
  final month = ref.watch(restaurantBudgetMonthProvider);

  final sumFut = repo.summary(months: months);
  final budFut = repo.budgetStatus(month: month);
  final summary = await sumFut;
  final budget = await budFut;
  return RestaurantBundle(summary: summary, budget: budget);
});
