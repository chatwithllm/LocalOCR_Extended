/// Contacts repo — endpoints verified at
/// `src/backend/shared_dining_endpoints.py:95/105` (RULE 1).
library;

import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'contacts_models.dart';

class ContactsRepository {
  ContactsRepository(this._api);
  final ApiClient _api;

  /// GET /shared-dining/contacts → bare array (RULE 2).
  Future<List<DiningContact>> list() async {
    final raw = await _api.get<List<dynamic>>(Endpoints.sharedDiningContacts);
    return raw
        .whereType<Map>()
        .map((m) => DiningContact.fromJson(m.cast<String, dynamic>()))
        .toList();
  }

  /// POST /shared-dining/contacts body {name, phone?, email?}
  /// Returns `{id, name}` from backend.
  Future<DiningContact> create({
    required String name,
    String? phone,
    String? email,
  }) async {
    final r = await _api.post<Map<String, dynamic>>(
      Endpoints.sharedDiningContacts,
      body: {
        'name': name,
        if (phone != null && phone.isNotEmpty) 'phone': phone,
        if (email != null && email.isNotEmpty) 'email': email,
      },
    );
    return DiningContact(
      id: (r['id'] as num).toInt(),
      name: (r['name'] as String?) ?? name,
      phone: phone,
      email: email,
    );
  }
}
