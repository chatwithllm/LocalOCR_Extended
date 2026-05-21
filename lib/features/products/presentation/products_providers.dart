import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/product_models.dart';
import '../data/product_repository.dart';

final productRepositoryProvider = Provider<ProductRepository>((ref) {
  return ProductRepository(ref.watch(apiClientProvider));
});

class ProductFilters {
  const ProductFilters({
    this.search = '',
    this.sort = 'name_asc',
    this.categoryFilters = const <String>{},
    this.addCardOpen = false,
  });
  final String search;
  final String sort;
  final Set<String> categoryFilters;
  final bool addCardOpen;

  ProductFilters copyWith({
    String? search,
    String? sort,
    Set<String>? categoryFilters,
    bool? addCardOpen,
  }) =>
      ProductFilters(
        search: search ?? this.search,
        sort: sort ?? this.sort,
        categoryFilters: categoryFilters ?? this.categoryFilters,
        addCardOpen: addCardOpen ?? this.addCardOpen,
      );
}

final productFiltersProvider =
    StateProvider<ProductFilters>((ref) => const ProductFilters());

/// Async raw catalog. Server-side search is used when filters.search has
/// >= 2 chars (mirrors index.html:25429-25432); otherwise list endpoint.
final productListProvider =
    FutureProvider.autoDispose<ProductList>((ref) async {
  final repo = ref.watch(productRepositoryProvider);
  final filters = ref.watch(productFiltersProvider);
  final q = filters.search.trim();
  if (q.length >= 2) return repo.search(q);
  return repo.list();
});
