import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';

import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'product_models.dart';

/// Product catalog repository — every endpoint here was grepped from
/// `src/backend/manage_product_catalog.py` + `manage_product_snapshots.py` +
/// `manage_inventory.py` (RULE 1).
///
/// Registry call-outs:
/// - F-431 set-low: `PUT /inventory/products/<id>/low-status` (NOT `/products/...`)
/// - F-432-F-435 unit/size/category: single `PUT /products/<id>/update` body
///   (no `/unit-defaults` or `/category` endpoint exists).
/// - F-419 AI gen: POST `/api/admin/image-backfill/run` + poll job, then
///   refetch `/products/<id>` for new `latest_snapshot.image_url`.
class ProductRepository {
  ProductRepository(this._api);
  final ApiClient _api;

  Future<ProductList> list({String? category, int page = 1, int perPage = 200}) async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.products,
      query: {
        if (category != null) 'category': category,
        'page': '$page',
        'per_page': '$perPage',
      },
    );
    return ProductList.fromJson(data);
  }

  /// GET /products/search?q=... — server requires q.length >= 2.
  Future<ProductList> search(String q) async {
    if (q.trim().length < 2) return ProductList(products: const [], total: 0);
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.productsSearch,
      query: {'q': q.trim()},
    );
    return ProductList.fromJson(data);
  }

  Future<Map<String, dynamic>> create({
    required String name,
    required String category,
    String? barcode,
  }) async {
    return await _api.post<Map<String, dynamic>>(
      Endpoints.productsCreate,
      body: {
        'name': name,
        'category': category,
        if (barcode != null && barcode.isNotEmpty) 'barcode': barcode,
      },
    );
  }

  Future<Map<String, dynamic>> update(
    int id, {
    String? name,
    String? category,
    String? defaultUnit,
    String? defaultSizeLabel,
    bool? isRegularUse,
  }) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (category != null) body['category'] = category;
    if (defaultUnit != null) body['default_unit'] = defaultUnit;
    if (defaultSizeLabel != null) body['default_size_label'] = defaultSizeLabel;
    if (isRegularUse != null) body['is_regular_use'] = isRegularUse;
    return await _api.put<Map<String, dynamic>>(
      Endpoints.productUpdate(id),
      body: body,
    );
  }

  Future<void> delete(int id) async {
    await _api.delete<Map<String, dynamic>>(Endpoints.product(id));
  }

  Future<Product?> fetchOne(int id) async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.product(id));
    final inner = (data['product'] as Map?)?.cast<String, dynamic>();
    if (inner == null) return null;
    return Product.fromJson(inner);
  }

  /// F-431 — note: PUT on inventory blueprint, not products.
  Future<void> setLowStatus(int productId, {required bool low}) async {
    await _api.put<Map<String, dynamic>>(
      Endpoints.inventoryProductLowStatus(productId),
      body: {'manual_low': low},
    );
  }

  /// F-418/F-426 — push to shopping list.
  Future<void> addToShoppingList(Product product) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.shoppingListItems,
      body: {
        'product_id': product.id,
        'name': product.name,
        'category': product.category,
        'quantity': 1,
        'source': 'product',
      },
    );
  }

  /// F-411 / F-429 / F-430 — product snapshots.
  Future<List<ProductSnapshot>> listSnapshots(int productId) async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.productSnapshots,
      query: {'product_id': '$productId'},
    );
    final raw = (data['snapshots'] as List?) ?? const [];
    return raw
        .whereType<Map>()
        .map((m) => ProductSnapshot.fromJson(m.cast<String, dynamic>()))
        .toList();
  }

  Future<ProductSnapshot?> uploadSnapshot({
    required int productId,
    required File image,
    String sourceContext = 'manual',
    String status = 'linked',
  }) async {
    final dio = _api.dio;
    final form = FormData.fromMap({
      'product_id': '$productId',
      'source_context': sourceContext,
      'status': status,
      'image': await MultipartFile.fromFile(
        image.path,
        filename: image.uri.pathSegments.last,
      ),
    });
    final r = await dio.post<Map<String, dynamic>>(
      Endpoints.productSnapshotsUpload,
      data: form,
    );
    final data = r.data ?? const {};
    final snap = (data['snapshot'] as Map?)?.cast<String, dynamic>();
    if (snap == null) return null;
    return ProductSnapshot.fromJson(snap);
  }

  Future<void> deleteSnapshot(int snapshotId) async {
    await _api.delete<Map<String, dynamic>>(
      Endpoints.productSnapshot(snapshotId),
    );
  }

  Future<void> promoteSnapshot(int snapshotId) async {
    await _api.post<Map<String, dynamic>>(
      Endpoints.productSnapshotPromote(snapshotId),
    );
  }

  /// F-419 — start backfill, poll the job, return the new snapshot if any.
  Future<ProductSnapshot?> generateAiImage(int productId,
      {Duration pollEvery = const Duration(seconds: 2),
      int maxPolls = 30}) async {
    final start = await _api.post<Map<String, dynamic>>(
      Endpoints.apiAdminImageBackfillRun,
      body: {
        'product_ids': [productId],
        'provider': 'auto',
      },
    );
    final jobId = (start['job_id'] ?? start['id'])?.toString();
    if (jobId == null) return null;
    for (var i = 0; i < maxPolls; i++) {
      await Future<void>.delayed(pollEvery);
      final job = await _api.get<Map<String, dynamic>>(
        Endpoints.apiAdminImageBackfillJob(jobId),
      );
      final status = job['status']?.toString();
      if (status == 'done' || status == 'error') {
        final items = (job['items'] as List?) ?? const [];
        final hit = items.whereType<Map>().firstWhere(
              (m) => (m['id'] as num?)?.toInt() == productId,
              orElse: () => const {},
            );
        if (hit['result'] != 'fetched') return null;
        final p = await fetchOne(productId);
        return p?.latestSnapshot;
      }
    }
    return null;
  }

}
