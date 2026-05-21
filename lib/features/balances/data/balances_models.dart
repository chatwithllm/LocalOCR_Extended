/// Balances DTOs — GET /shared-dining/balances returns a BARE ARRAY of
/// `{contact_id, name, net_amount}` rows (RULE 2 verified at
/// `src/backend/shared_dining_endpoints.py:82` → `get_all_balances`).
/// net_amount > 0 means contact owes you; < 0 means you owe.
library;

class BalanceRow {
  BalanceRow({
    required this.contactId,
    required this.name,
    required this.netAmount,
  });
  final int contactId;
  final String name;
  final double netAmount;

  bool get owesYou => netAmount > 0;

  factory BalanceRow.fromJson(Map<String, dynamic> j) => BalanceRow(
        contactId: (j['contact_id'] as num).toInt(),
        name: (j['name'] as String?) ?? '',
        netAmount: (j['net_amount'] as num?)?.toDouble() ?? 0,
      );
}
