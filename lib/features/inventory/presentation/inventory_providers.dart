import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/inventory_models.dart';
import '../data/inventory_repository.dart';

final inventoryRepositoryProvider = Provider<InventoryRepository>((ref) {
  return InventoryRepository(ref.watch(apiClientProvider));
});

/// Filter state — search query, location, group-by, sort.
class InventoryFilters {
  const InventoryFilters({
    this.search = '',
    this.location,
    this.groupBy = 'low_first',
    this.sort = 'expiry',
    this.showEmpty = false,
    this.categoryFilters = const <String>{},
    this.addCardOpen = false,
  });
  final String search;
  final String? location;
  final String groupBy;
  final String sort;
  final bool showEmpty;
  final Set<String> categoryFilters;
  final bool addCardOpen;

  InventoryFilters copyWith({
    String? search,
    Object? location = const _Unset(),
    String? groupBy,
    String? sort,
    bool? showEmpty,
    Set<String>? categoryFilters,
    bool? addCardOpen,
  }) =>
      InventoryFilters(
        search: search ?? this.search,
        location: location is _Unset ? this.location : location as String?,
        groupBy: groupBy ?? this.groupBy,
        sort: sort ?? this.sort,
        showEmpty: showEmpty ?? this.showEmpty,
        categoryFilters: categoryFilters ?? this.categoryFilters,
        addCardOpen: addCardOpen ?? this.addCardOpen,
      );
}

class _Unset {
  const _Unset();
}

final inventoryFiltersProvider =
    StateProvider<InventoryFilters>((ref) => const InventoryFilters());

/// Async raw list. Filters/grouping/sorting are applied in the screen body.
final inventoryListProvider =
    FutureProvider.autoDispose<InventoryList>((ref) async {
  final repo = ref.watch(inventoryRepositoryProvider);
  return repo.list();
});
