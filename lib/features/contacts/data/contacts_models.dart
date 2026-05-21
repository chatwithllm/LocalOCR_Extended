/// Dining Contacts DTOs — GET /shared-dining/contacts returns a BARE ARRAY
/// of `{id, name, phone, email}` (RULE 2 verified at
/// `src/backend/shared_dining_endpoints.py:99-102`).
library;

class DiningContact {
  DiningContact({
    required this.id,
    required this.name,
    required this.phone,
    required this.email,
  });
  final int id;
  final String name;
  final String? phone;
  final String? email;

  factory DiningContact.fromJson(Map<String, dynamic> j) => DiningContact(
        id: (j['id'] as num).toInt(),
        name: (j['name'] as String?) ?? '?',
        phone: j['phone'] as String?,
        email: j['email'] as String?,
      );
}
