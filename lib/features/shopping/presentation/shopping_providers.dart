import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/shopping_models.dart';
import '../data/shopping_repository.dart';

final shoppingRepositoryProvider = Provider<ShoppingRepository>((ref) {
  return ShoppingRepository(ref.watch(apiClientProvider));
});

/// View filter — open | purchased | all
final shoppingViewProvider = StateProvider<String>((ref) => 'open');

final shoppingListProvider =
    FutureProvider.autoDispose<ShoppingListPayload>((ref) async {
  final repo = ref.watch(shoppingRepositoryProvider);
  final view = ref.watch(shoppingViewProvider);
  // Backend treats empty string as "all".
  return repo.list(status: view == 'all' ? null : view);
});
