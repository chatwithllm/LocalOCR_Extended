import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/contacts_models.dart';
import '../data/contacts_repository.dart';

final contactsRepositoryProvider = Provider<ContactsRepository>((ref) {
  return ContactsRepository(ref.watch(apiClientProvider));
});

final contactsListProvider =
    FutureProvider.autoDispose<List<DiningContact>>((ref) async {
  return ref.watch(contactsRepositoryProvider).list();
});
