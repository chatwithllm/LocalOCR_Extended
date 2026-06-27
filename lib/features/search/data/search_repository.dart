library;

import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'search_models.dart';

class SearchRepository {
  SearchRepository(this._api);
  final ApiClient _api;

  Future<SearchResult> search(String q) async {
    final raw = await _api.get<Map<String, dynamic>>(
      Endpoints.search,
      query: {'q': q},
    );
    return SearchResult.fromJson(raw);
  }
}
