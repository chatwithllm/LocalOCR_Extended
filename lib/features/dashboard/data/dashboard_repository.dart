import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'dashboard_models.dart';

/// Dashboard repository — fans out 8 GETs concurrently for the initial mount.
/// Each card failure is captured per-endpoint so siblings keep rendering
/// (plan §6.3 edge case: "individual card switches to error tile").
class DashboardRepository {
  DashboardRepository(this._api);
  final ApiClient _api;

  /// Returns a fully populated [DashboardState] with `cardsLoaded` reflecting
  /// how many of the cards returned without throwing.
  Future<DashboardState> loadAll({String activityGrain = 'day'}) async {
    Future<T> guard<T>(Future<T> Function() fn, T fallback) async {
      try {
        return await fn();
      } catch (_) {
        return fallback;
      }
    }

    final results = await Future.wait<Object>([
      guard(_leaderboard, Leaderboard.empty),
      guard(_attribution, AttributionStats.empty),
      guard(_inventory, InventoryStats.empty),
      guard(_products, ProductsStats.empty),
      guard(_spending, SpendingByCategory.empty),
      guard(() => _activity(activityGrain),
          ReceiptsActivity.emptyFor(activityGrain)),
      guard(_recommendations, RecommendationList.empty),
      guard(_shopping, ShoppingSummary.empty),
    ]);

    final leaderboard = results[0] as Leaderboard;
    final attribution = results[1] as AttributionStats;
    final inv = results[2] as InventoryStats;
    final prod = results[3] as ProductsStats;
    final spending = results[4] as SpendingByCategory;
    final activity = results[5] as ReceiptsActivity;
    final recs = results[6] as RecommendationList;
    final shop = results[7] as ShoppingSummary;

    int loaded = 0;
    if (leaderboard.entries.isNotEmpty) loaded++;
    if (attribution.taggedCount + attribution.untaggedCount > 0) loaded++;
    if (inv.itemCount > 0) loaded++;
    if (prod.total > 0) loaded++;
    if (spending.total > 0 || spending.categories.isNotEmpty) loaded++;
    if (activity.buckets.isNotEmpty) loaded++;
    if (recs.recommendations.isNotEmpty) loaded++;
    if (shop.openCount > 0 || shop.preview.isNotEmpty) loaded++;

    return DashboardState(
      leaderboard: leaderboard,
      attribution: attribution,
      inventory: inv,
      products: prod,
      spending: spending,
      activity: activity,
      recommendations: recs,
      shopping: shop,
      cardsLoaded: loaded,
    );
  }

  Future<Leaderboard> _leaderboard() async {
    // Web reads leaderboard from /auth/me data.leaderboard (index.html:14664).
    // /contributions/summary is for the Contributions screen drill-down.
    final data = await _api.get<Map<String, dynamic>>(Endpoints.authMe);
    final lb = (data['leaderboard'] as Map?)?.cast<String, dynamic>();
    if (lb == null) return Leaderboard.empty;
    return Leaderboard.fromJson(lb);
  }

  Future<AttributionStats> _attribution() async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.receiptsAttributionStats,
    );
    return AttributionStats.fromJson(data);
  }

  Future<InventoryStats> _inventory() async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.inventory);
    return InventoryStats.fromJson(data);
  }

  Future<ProductsStats> _products() async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.products,
      query: const {'per_page': 1, 'page': 1},
    );
    return ProductsStats.fromJson(data);
  }

  Future<SpendingByCategory> _spending() async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.analyticsSpendingByCategory,
    );
    return SpendingByCategory.fromJson(data);
  }

  Future<ReceiptsActivity> activity(String grain) => _activity(grain);

  Future<ReceiptsActivity> _activity(String grain) async {
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.analyticsReceiptsActivity,
      query: {'grain': grain},
    );
    return ReceiptsActivity.fromJson(data);
  }

  Future<RecommendationList> _recommendations() async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.recommendations);
    return RecommendationList.fromJson(data);
  }

  Future<ShoppingSummary> _shopping() async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.shoppingList);
    return ShoppingSummary.fromJson(data);
  }

  /// Add a recommendation to the shopping list (F-229).
  Future<void> addRecommendationToList(Recommendation rec) async {
    final body = <String, dynamic>{
      if (rec.productId != null) 'product_id': rec.productId,
      'name': rec.title,
      'source': 'recommendation:${rec.id}',
    };
    await _api.post<Map<String, dynamic>>(Endpoints.shoppingListItems, body: body);
  }
}
