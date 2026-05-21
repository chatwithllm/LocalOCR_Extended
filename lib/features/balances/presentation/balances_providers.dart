import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/balances_models.dart';
import '../data/balances_repository.dart';

final balancesRepositoryProvider = Provider<BalancesRepository>((ref) {
  return BalancesRepository(ref.watch(apiClientProvider));
});

final balancesListProvider =
    FutureProvider.autoDispose<List<BalanceRow>>((ref) async {
  final repo = ref.watch(balancesRepositoryProvider);
  return repo.list();
});
