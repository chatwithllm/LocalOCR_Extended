import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/dashboard_models.dart';
import '../data/dashboard_repository.dart';

final dashboardRepositoryProvider = Provider<DashboardRepository>((ref) {
  return DashboardRepository(ref.watch(apiClientProvider));
});

/// Receipts-activity grain selection (F-224/F-225/F-226). Persists across
/// re-builds via `StateProvider`; not durable across cold launches.
final receiptsActivityGrainProvider =
    StateProvider<String>((ref) => 'day');

/// Async dashboard state. Re-fetches when the grain changes.
final dashboardStateProvider =
    FutureProvider.autoDispose<DashboardState>((ref) async {
  final repo = ref.watch(dashboardRepositoryProvider);
  final grain = ref.watch(receiptsActivityGrainProvider);
  return repo.loadAll(activityGrain: grain);
});

/// Per-section collapsed flags (F-209 leaderboard, F-216 spending,
/// F-221 low-stock, F-223 activity, F-228 top picks, F-230 shopping).
final dashboardSectionExpandedProvider =
    StateProvider.family<bool, String>((ref, _) => true);

final dashboardShoppingPreviewExpandedProvider =
    StateProvider<bool>((ref) => false);

final dashboardSpendingMoreProvider = StateProvider<bool>((ref) => false);
