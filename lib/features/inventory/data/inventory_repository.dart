import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'inventory_models.dart';

/// Inventory repository — every endpoint here was grepped from
/// `src/backend/manage_inventory.py` (RULE 1 pre-flight). Registry
/// `PATCH /inventory/products/<id>/consume` and `PATCH /inventory/<id>/status`
/// labels were fabricated — real consume path is `PUT /inventory/<id>/consume`
/// and status cycling is `PUT /inventory/<id>/update` with
/// `consumed_pct_override` (web `_invSetOverride()` at index.html:23274).
class InventoryRepository {
  InventoryRepository(this._api);
  final ApiClient _api;

  Future<InventoryList> list({String? location, bool? lowStock}) async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.inventory,
      query: {
        if (location != null) 'location': location,
        if (lowStock == true) 'low_stock': 'true',
      },
    );
    return InventoryList.fromJson(data);
  }

  /// POST /inventory/add-item — accepts either product_id or product_name
  /// + category + quantity + location + threshold (manage_inventory.py:214).
  Future<void> addItem({
    int? productId,
    String? productName,
    String? category,
    double quantity = 1,
    String location = 'Pantry',
    double? threshold,
    String? size,
  }) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.inventoryAddItem,
      body: {
        if (productId != null) 'product_id': productId,
        if (productName != null && productName.isNotEmpty)
          'product_name': productName,
        if (category != null && category.isNotEmpty) 'category': category,
        'quantity': quantity,
        'location': location,
        if (threshold != null) 'threshold': threshold,
        if (size != null && size.isNotEmpty) 'size': size,
      },
    );
  }

  /// PUT /inventory/<id>/consume — decrements by `amount` (default 1).
  Future<void> consume(int itemId, {double amount = 1}) async {
    await _api.put<Map<String, dynamic>>(
      Endpoints.inventoryConsume(itemId),
      body: {'amount': amount},
    );
  }

  /// PUT /inventory/<id>/update — set quantity / location / threshold /
  /// consumed_pct_override (manage_inventory.py:362).
  Future<void> updateItem(
    int itemId, {
    double? quantity,
    String? location,
    double? threshold,
    double? consumedPctOverride,
  }) async {
    await _api.put<Map<String, dynamic>>(
      Endpoints.inventoryUpdate(itemId),
      body: {
        if (quantity != null) 'quantity': quantity,
        if (location != null) 'location': location,
        if (threshold != null) 'threshold': threshold,
        if (consumedPctOverride != null)
          'consumed_pct_override': consumedPctOverride,
      },
    );
  }

  /// PATCH /inventory/products/<productId> — flexible body:
  /// `defer_days`, `quantity` (0 = used-up = delete row), `location`,
  /// `expires_at`, `display_name`, `unit`, `size_label`
  /// (manage_inventory.py:639 → apply_manual_patch).
  Future<void> patchByProduct(
    int productId, {
    int? deferDays,
    double? quantity,
    String? location,
    String? expiresAt,
    String? displayName,
    String? unit,
    String? sizeLabel,
  }) async {
    await _api.patch<Map<String, dynamic>>(
      Endpoints.inventoryProduct(productId),
      body: {
        if (deferDays != null) 'defer_days': deferDays,
        if (quantity != null) 'quantity': quantity,
        if (location != null) 'location': location,
        if (expiresAt != null) 'expires_at': expiresAt,
        if (displayName != null) 'display_name': displayName,
        if (unit != null) 'unit': unit,
        if (sizeLabel != null) 'size_label': sizeLabel,
      },
    );
  }

  /// PUT /inventory/products/<productId>/low-status — mark/clear low.
  Future<void> setLowStatus(int productId, {required bool low}) async {
    await _api.put<Map<String, dynamic>>(
      Endpoints.inventoryProductLowStatus(productId),
      body: {'manual_low': low},
    );
  }

  /// Mark used-up via PATCH quantity=0 (apply_manual_patch deletes the row,
  /// preserving audit. Web's `invConsumeAll()` posts the same shape).
  Future<void> markUsedUp(int productId) async {
    await patchByProduct(productId, quantity: 0);
  }

  /// Defer expiry by N days (+3d / +7d buttons).
  Future<void> deferExpiry(int productId, int days) async {
    await patchByProduct(productId, deferDays: days);
  }

  /// POST /shopping-list/items — add product to shopping list.
  Future<void> addToShoppingList(InventoryItem item) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.shoppingListItems,
      body: {
        'product_id': item.productId,
        'name': item.productName,
        'source': 'inventory:${item.id}',
      },
    );
  }
}
