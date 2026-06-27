import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/search_models.dart';
import '../data/search_repository.dart';

final searchRepositoryProvider = Provider<SearchRepository>((ref) {
  return SearchRepository(ref.watch(apiClientProvider));
});

final searchQueryProvider = StateProvider<String>((ref) => '');

final searchResultsProvider =
    FutureProvider.autoDispose<SearchResult?>((ref) async {
  final q = ref.watch(searchQueryProvider).trim();
  if (q.length < 2) return null;

  // 400ms debounce — wait for typing to settle before hitting the API.
  await Future<void>.delayed(const Duration(milliseconds: 400));

  // If the query changed while we were waiting, the previous future is
  // cancelled by autoDispose; just bail early here too.
  if (ref.read(searchQueryProvider).trim() != q) return null;

  final repo = ref.read(searchRepositoryProvider);
  return repo.search(q);
});
