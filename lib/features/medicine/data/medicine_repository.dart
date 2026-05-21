// Medicine repository — every endpoint here was grepped from
// `src/backend/manage_medications.py` + `src/backend/manage_household_members.py`
// + `src/backend/manage_authentication.py` (RULE 1).
//
// Registry call-outs:
// - F-507 photo image: backend has NO `GET /medications/<id>/photo` handler
//   (only POST upload at line 278). We attempt the URL via NetworkImage in the
//   tile widget and fall back to an emoji placeholder on error — see
//   medicine_screen.dart `_buildTileImage()`. Marked 🔄 on registry.
// - F-531/F-532 camera/gallery scan: web uses Html5Qrcode#scanFile to decode
//   the picked image client-side, then calls `/medications/barcode-lookup`.
//   Android picks a code via mobile_scanner or falls back to the device
//   barcode reader (image_picker + ML Kit handled elsewhere); here we expose
//   only the lookup endpoint and let the screen choose the input flow.
library;

import 'dart:io';

import 'package:dio/dio.dart';

import '../../../core/api/api_client.dart';
import '../../../core/api/endpoints.dart';
import 'medicine_models.dart';

class MedicineRepository {
  MedicineRepository(this._api);
  final ApiClient _api;

  /// GET /medications?status=...&member_id=...&user_id=...&age_group=...
  /// status: active | all | expired | finished
  /// member_id: "none" maps to household (no user, no member)
  Future<MedicationList> list({
    String status = 'active',
    String? memberId,
    String? userId,
    String? ageGroup,
  }) async {
    final query = <String, dynamic>{'status': status};
    if (memberId != null) query['member_id'] = memberId;
    if (userId != null) query['user_id'] = userId;
    if (ageGroup != null) query['age_group'] = ageGroup;
    final data = await _api.get<Map<String, dynamic>>(
      Endpoints.medications,
      query: query,
    );
    return MedicationList.fromJson(data);
  }

  Future<Medication> fetchOne(int id) async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.medication(id));
    final m = (data['medication'] as Map).cast<String, dynamic>();
    return Medication.fromJson(m);
  }

  Future<Medication> create(Map<String, dynamic> body) async {
    final data = await _api.post<Map<String, dynamic>>(
      Endpoints.medications,
      body: body,
    );
    final m = (data['medication'] as Map).cast<String, dynamic>();
    return Medication.fromJson(m);
  }

  Future<Medication> update(int id, Map<String, dynamic> body) async {
    final data = await _api.put<Map<String, dynamic>>(
      Endpoints.medication(id),
      body: body,
    );
    final m = (data['medication'] as Map).cast<String, dynamic>();
    return Medication.fromJson(m);
  }

  Future<void> delete(int id) async {
    await _api.delete<Map<String, dynamic>>(Endpoints.medication(id));
  }

  /// F-516 — set status=finished.
  Future<Medication> markFinished(int id) => update(id, {'status': 'finished'});

  /// F-531/F-532/F-533 — barcode or name lookup.
  Future<BarcodeLookupResult> barcodeLookup({String? barcode, String? name}) async {
    final body = <String, dynamic>{
      if (barcode != null && barcode.isNotEmpty) 'barcode': barcode,
      if (name != null && name.isNotEmpty) 'name': name,
    };
    final data = await _api.post<Map<String, dynamic>>(
      Endpoints.medicationsBarcodeLookup,
      body: body,
    );
    return BarcodeLookupResult.fromJson(data);
  }

  /// POST /medications/<id>/photo (multipart `image`).
  /// Returns updated Medication with new image_path.
  Future<Medication> uploadPhoto({required int medicationId, required File image}) async {
    final form = FormData.fromMap({
      'image': await MultipartFile.fromFile(
        image.path,
        filename: image.uri.pathSegments.last,
      ),
    });
    final r = await _api.dio.post<Map<String, dynamic>>(
      Endpoints.medicationPhoto(medicationId),
      data: form,
    );
    final m = ((r.data ?? const {})['medication'] as Map).cast<String, dynamic>();
    return Medication.fromJson(m);
  }

  // ---- household members ----

  Future<HouseholdMemberList> listMembers() async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.householdMembers);
    return HouseholdMemberList.fromJson(data);
  }

  Future<HouseholdMember> createMember({required String name, String ageGroup = 'adult', String? avatarEmoji}) async {
    final data = await _api.post<Map<String, dynamic>>(
      Endpoints.householdMembers,
      body: {
        'name': name,
        'age_group': ageGroup,
        if (avatarEmoji != null) 'avatar_emoji': avatarEmoji,
      },
    );
    final m = (data['member'] as Map).cast<String, dynamic>();
    return HouseholdMember.fromJson(m);
  }

  Future<HouseholdMember> updateMember(int id, Map<String, dynamic> body) async {
    final data = await _api.put<Map<String, dynamic>>(
      Endpoints.householdMember(id),
      body: body,
    );
    final m = (data['member'] as Map).cast<String, dynamic>();
    return HouseholdMember.fromJson(m);
  }

  Future<void> deleteMember(int id) async {
    await _api.delete<Map<String, dynamic>>(Endpoints.householdMember(id));
  }

  // ---- users (subset for chips) ----

  /// GET /auth/users -> {users:[...]} (filtered). Used to populate "people"
  /// chips alongside household members (matches index.html:26071).
  Future<List<MedicineUserChip>> listUsers() async {
    final data = await _api.get<Map<String, dynamic>>(Endpoints.authUsers);
    final raw = (data['users'] as List?) ?? const [];
    return raw
        .whereType<Map>()
        .map((m) => MedicineUserChip.fromJson(m.cast<String, dynamic>()))
        .toList();
  }
}
