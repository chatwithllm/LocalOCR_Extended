// Medicine DTOs — mirror `_serialize_medication()` and `_serialize_member()`
// in `src/backend/manage_medications.py:58` and
// `src/backend/manage_household_members.py:24` verbatim (RULE 2).
//
// Endpoint shapes:
//   GET    /medications              -> {medications:[...], count:int}
//   POST   /medications              -> {medication:{...}}             201
//   GET    /medications/<id>         -> {medication:{...}}
//   PUT    /medications/<id>         -> {medication:{...}}
//   DELETE /medications/<id>         -> {deleted:true, id:int}
//   POST   /medications/<id>/photo   -> {medication:{...}}
//   POST   /medications/barcode-lookup -> {found:bool, fields:{...}}
//   GET    /household-members        -> {members:[...], count:int}
//   POST   /household-members        -> {member:{...}}                  201
//   PUT    /household-members/<id>   -> {member:{...}}
//   DELETE /household-members/<id>   -> {deleted:true, id:int}
library;

class Medication {
  Medication({
    required this.id,
    required this.name,
    required this.brand,
    required this.strength,
    required this.dosageForm,
    required this.activeIngredient,
    required this.ageGroup,
    required this.belongsTo,
    required this.memberId,
    required this.userId,
    required this.barcode,
    required this.productId,
    required this.manufactureDate,
    required this.expiryDate,
    required this.quantity,
    required this.unit,
    required this.lowThreshold,
    required this.rxNumber,
    required this.prescribingDoctor,
    required this.aiWarnings,
    required this.imagePath,
    required this.status,
    required this.notes,
    required this.createdAt,
    required this.updatedAt,
    required this.isExpired,
    required this.isLow,
  });

  final int id;
  final String name;
  final String? brand;
  final String? strength;
  final String? dosageForm;
  final String? activeIngredient;
  final String ageGroup; // both | adult | child
  final String belongsTo; // household | (user_id/member_id when populated)
  final int? memberId;
  final int? userId;
  final String? barcode;
  final int? productId;
  final String? manufactureDate; // YYYY-MM-DD
  final String? expiryDate; // YYYY-MM-DD
  final double? quantity;
  final String unit; // tablets/capsules/ml/oz/count/doses
  final double? lowThreshold;
  final String? rxNumber;
  final String? prescribingDoctor;
  final List<String> aiWarnings;
  final String? imagePath;
  final String status; // active | finished | expired
  final String? notes;
  final String? createdAt;
  final String? updatedAt;
  final bool isExpired;
  final bool isLow;

  factory Medication.fromJson(Map<String, dynamic> json) {
    final warnings = (json['ai_warnings'] as List?) ?? const [];
    return Medication(
      id: (json['id'] as num).toInt(),
      name: (json['name'] as String?) ?? '',
      brand: json['brand'] as String?,
      strength: json['strength'] as String?,
      dosageForm: json['dosage_form'] as String?,
      activeIngredient: json['active_ingredient'] as String?,
      ageGroup: (json['age_group'] as String?) ?? 'both',
      belongsTo: (json['belongs_to'] as String?) ?? 'household',
      memberId: (json['member_id'] as num?)?.toInt(),
      userId: (json['user_id'] as num?)?.toInt(),
      barcode: json['barcode'] as String?,
      productId: (json['product_id'] as num?)?.toInt(),
      manufactureDate: json['manufacture_date'] as String?,
      expiryDate: json['expiry_date'] as String?,
      quantity: (json['quantity'] as num?)?.toDouble(),
      unit: (json['unit'] as String?) ?? 'count',
      lowThreshold: (json['low_threshold'] as num?)?.toDouble(),
      rxNumber: json['rx_number'] as String?,
      prescribingDoctor: json['prescribing_doctor'] as String?,
      aiWarnings: warnings.whereType<String>().toList(),
      imagePath: json['image_path'] as String?,
      status: (json['status'] as String?) ?? 'active',
      notes: json['notes'] as String?,
      createdAt: json['created_at'] as String?,
      updatedAt: json['updated_at'] as String?,
      isExpired: (json['is_expired'] as bool?) ?? false,
      isLow: (json['is_low'] as bool?) ?? false,
    );
  }
}

class MedicationList {
  MedicationList({required this.medications, required this.count});
  final List<Medication> medications;
  final int count;

  factory MedicationList.fromJson(Map<String, dynamic> json) {
    final raw = (json['medications'] as List?) ?? const [];
    return MedicationList(
      medications: raw
          .whereType<Map>()
          .map((m) => Medication.fromJson(m.cast<String, dynamic>()))
          .toList(),
      count: (json['count'] as num?)?.toInt() ?? raw.length,
    );
  }
}

/// POST /medications/barcode-lookup -> {found, fields:{...}}.
/// `fields` is a flat map of medication columns (name/brand/strength/etc.)
class BarcodeLookupResult {
  BarcodeLookupResult({required this.found, required this.fields});
  final bool found;
  final Map<String, dynamic> fields;

  factory BarcodeLookupResult.fromJson(Map<String, dynamic> json) =>
      BarcodeLookupResult(
        found: (json['found'] as bool?) ?? false,
        fields: ((json['fields'] as Map?) ?? const {}).cast<String, dynamic>(),
      );
}

class HouseholdMember {
  HouseholdMember({
    required this.id,
    required this.name,
    required this.ageGroup,
    required this.avatarEmoji,
    required this.createdAt,
    required this.updatedAt,
  });
  final int id;
  final String name;
  final String ageGroup; // adult | child
  final String? avatarEmoji;
  final String? createdAt;
  final String? updatedAt;

  factory HouseholdMember.fromJson(Map<String, dynamic> json) =>
      HouseholdMember(
        id: (json['id'] as num).toInt(),
        name: (json['name'] as String?) ?? '',
        ageGroup: (json['age_group'] as String?) ?? 'adult',
        avatarEmoji: json['avatar_emoji'] as String?,
        createdAt: json['created_at'] as String?,
        updatedAt: json['updated_at'] as String?,
      );
}

class HouseholdMemberList {
  HouseholdMemberList({required this.members, required this.count});
  final List<HouseholdMember> members;
  final int count;

  factory HouseholdMemberList.fromJson(Map<String, dynamic> json) {
    final raw = (json['members'] as List?) ?? const [];
    return HouseholdMemberList(
      members: raw
          .whereType<Map>()
          .map((m) => HouseholdMember.fromJson(m.cast<String, dynamic>()))
          .toList(),
      count: (json['count'] as num?)?.toInt() ?? raw.length,
    );
  }
}

/// Combined "people" model for member chips + Belongs-To select.
/// type = 'user' | 'member'. id is the user/member primary key.
/// Encoded as `<type>_<id>` for filter chip keys (matches web `user_<id>` /
/// `member_<id>` convention at index.html:26073/26074).
class MedicinePerson {
  MedicinePerson({
    required this.type,
    required this.id,
    required this.name,
    required this.emoji,
  });
  final String type;
  final int id;
  final String name;
  final String emoji;

  String get key => '${type}_$id';
}

/// Auth `/auth/users` shape — a subset of fields used by Medicine for chips.
/// Mirrors the user list at `src/backend/manage_authentication.py:list_users`.
class MedicineUserChip {
  MedicineUserChip({required this.id, required this.name, required this.avatarEmoji});
  final int id;
  final String name;
  final String? avatarEmoji;

  factory MedicineUserChip.fromJson(Map<String, dynamic> json) =>
      MedicineUserChip(
        id: (json['id'] as num).toInt(),
        name: (json['name'] as String?) ??
            (json['display_name'] as String?) ??
            (json['email'] as String?) ??
            'User',
        avatarEmoji: json['avatar_emoji'] as String?,
      );
}

const medicineDosageFormOptions = <Map<String, String>>[
  {'value': 'tablet', 'label': 'Tablet'},
  {'value': 'capsule', 'label': 'Capsule'},
  {'value': 'liquid', 'label': 'Liquid/Syrup'},
  {'value': 'cream', 'label': 'Cream/Gel/Ointment'},
  {'value': 'spray', 'label': 'Spray'},
  {'value': 'patch', 'label': 'Patch'},
  {'value': 'other', 'label': 'Other'},
];

const medicineAgeGroupOptions = <Map<String, String>>[
  {'value': 'both', 'label': '👪 Everyone (Adult & Kids)'},
  {'value': 'adult', 'label': '🧑 Adults only'},
  {'value': 'child', 'label': '👶 Kids only'},
];

const medicineUnitOptions = <Map<String, String>>[
  {'value': 'tablets', 'label': 'Tablets'},
  {'value': 'capsules', 'label': 'Capsules'},
  {'value': 'ml', 'label': 'ml'},
  {'value': 'oz', 'label': 'oz'},
  {'value': 'count', 'label': 'Count'},
  {'value': 'doses', 'label': 'Doses'},
];

const medicineStatusOptions = <Map<String, String>>[
  {'value': 'active', 'label': 'Active'},
  {'value': 'all', 'label': 'All'},
  {'value': 'expired', 'label': 'Expired'},
  {'value': 'finished', 'label': 'Finished'},
];

const memberAgeGroupOptions = <Map<String, String>>[
  {'value': 'adult', 'label': 'Adult'},
  {'value': 'child', 'label': 'Child'},
];
