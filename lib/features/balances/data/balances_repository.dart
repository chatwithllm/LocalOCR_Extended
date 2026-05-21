/// Balances repo — endpoints verified at
/// `src/backend/shared_dining_endpoints.py:75/82` (RULE 1).
library;

import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'balances_models.dart';

class BalancesRepository {
  BalancesRepository(this._api);
  final ApiClient _api;

  /// GET /shared-dining/balances → bare JSON array (RULE 2).
  Future<List<BalanceRow>> list() async {
    final raw = await _api.get<List<dynamic>>(Endpoints.sharedDiningBalances);
    return raw
        .whereType<Map>()
        .map((m) => BalanceRow.fromJson(m.cast<String, dynamic>()))
        .toList();
  }

  /// POST /shared-dining/contacts/<id>/settle-all → {settled:int}.
  Future<int> settleAll(int contactId) async {
    final r = await _api.post<Map<String, dynamic>>(
      Endpoints.sharedDiningContactSettleAll(contactId),
    );
    return (r['settled'] as num?)?.toInt() ?? 0;
  }
}
