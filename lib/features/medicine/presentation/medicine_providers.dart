import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/medicine_models.dart';
import '../data/medicine_repository.dart';

final medicineRepositoryProvider = Provider<MedicineRepository>((ref) {
  return MedicineRepository(ref.watch(apiClientProvider));
});

/// Filter chip key — `null` (all), `"household"`, `"user_<id>"`, `"member_<id>"`.
final medicineMemberFilterProvider = StateProvider<String?>((ref) => null);

/// Status filter — active | all | expired | finished
final medicineStatusFilterProvider = StateProvider<String>((ref) => 'active');

/// Cabinet bundle (medications + members + users), one fetch combines them.
class MedicineCabinet {
  MedicineCabinet({
    required this.medications,
    required this.members,
    required this.users,
  });
  final List<Medication> medications;
  final List<HouseholdMember> members;
  final List<MedicineUserChip> users;

  /// Combined people list — users first, then members (matches web order).
  List<MedicinePerson> get people => [
        for (final u in users)
          MedicinePerson(type: 'user', id: u.id, name: u.name, emoji: u.avatarEmoji ?? '👤'),
        for (final m in members)
          MedicinePerson(type: 'member', id: m.id, name: m.name, emoji: m.avatarEmoji ?? '👤'),
      ];
}

final medicineCabinetProvider = FutureProvider.autoDispose<MedicineCabinet>((ref) async {
  final repo = ref.watch(medicineRepositoryProvider);
  final status = ref.watch(medicineStatusFilterProvider);
  final filter = ref.watch(medicineMemberFilterProvider);

  String? memberId;
  String? userId;
  if (filter == 'household') {
    memberId = 'none';
  } else if (filter != null && filter.startsWith('user_')) {
    userId = filter.substring('user_'.length);
  } else if (filter != null && filter.startsWith('member_')) {
    memberId = filter.substring('member_'.length);
  }

  final medsFut = repo.list(status: status, memberId: memberId, userId: userId);
  final memsFut = repo.listMembers();
  // /auth/users may 403 for non-admins — tolerate failure.
  final usersFut = repo.listUsers().catchError((_) => <MedicineUserChip>[]);

  final meds = await medsFut;
  final mems = await memsFut;
  final users = await usersFut;
  return MedicineCabinet(
    medications: meds.medications,
    members: mems.members,
    users: users,
  );
});
