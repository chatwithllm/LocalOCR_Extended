/// Shopping repo — endpoints verified at
/// `src/backend/manage_shopping_list.py:496/609/756/846` (RULE 1).
library;

import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'shopping_models.dart';

class ShoppingRepository {
  ShoppingRepository(this._api);
  final ApiClient _api;

  /// GET /shopping-list?status=  → full payload (current session).
  Future<ShoppingListPayload> list({String? status}) async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.shoppingList,
      query: {if (status != null && status.isNotEmpty) 'status': status},
    );
    return ShoppingListPayload.fromJson(data);
  }

  /// POST /shopping-list/items body {name, category?, quantity?, …}.
  Future<ShoppingItem> create({
    required String name,
    String? category,
    double? quantity,
    String? unit,
    String? preferredStore,
    double? manualEstimatedPrice,
    String? note,
  }) async {
    final body = <String, dynamic>{
      'name': name,
      if (category != null) 'category': category,
      if (quantity != null) 'quantity': quantity,
      if (unit != null) 'unit': unit,
      if (preferredStore != null && preferredStore.isNotEmpty)
        'preferred_store': preferredStore,
      if (manualEstimatedPrice != null)
        'manual_estimated_price': manualEstimatedPrice,
      if (note != null && note.isNotEmpty) 'note': note,
    };
    final data = await _api.post<Map<String, dynamic>>(
      Endpoints.shoppingListItems,
      body: body,
    );
    return ShoppingItem.fromJson((data['item'] as Map).cast<String, dynamic>());
  }

  /// PUT /shopping-list/items/<id> body {…fields…}.
  Future<ShoppingItem> update(int id, Map<String, dynamic> body) async {
    final data = await _api.put<Map<String, dynamic>>(
      Endpoints.shoppingListItem(id),
      body: body,
    );
    return ShoppingItem.fromJson((data['item'] as Map).cast<String, dynamic>());
  }

  Future<void> delete(int id) async {
    await _api.delete<Map<String, dynamic>>(Endpoints.shoppingListItem(id));
  }

  Future<ShoppingItem> markPurchased(int id) =>
      update(id, {'status': 'purchased'});
  Future<ShoppingItem> reopen(int id) => update(id, {'status': 'open'});
  Future<ShoppingItem> setQuantity(int id, double q) =>
      update(id, {'quantity': q});
}
