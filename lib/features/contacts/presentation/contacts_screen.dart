// MARK: Contacts (Dining) — F-801..F-806

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/util/logger.dart';
import 'contacts_providers.dart';

class ContactsScreen extends ConsumerStatefulWidget {
  const ContactsScreen({super.key});
  @override
  ConsumerState<ContactsScreen> createState() => _ContactsScreenState();
}

class _ContactsScreenState extends ConsumerState<ContactsScreen> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _email.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(contactsListProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Contacts'),
        actions: [
          // F-801 refresh
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(contactsListProvider),
          ),
        ],
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _Err(
          msg: 'Could not load contacts:\n$e',
          retry: () => ref.invalidate(contactsListProvider),
        ),
        data: (contacts) {
          appLogger.i('loaded ${contacts.length} contacts');
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(contactsListProvider);
              await ref.read(contactsListProvider.future);
            },
            child: ListView(
              padding: const EdgeInsets.all(12),
              children: [
                _AddCard(
                  name: _name,
                  phone: _phone,
                  email: _email,
                  busy: _busy,
                  onSave: _save,
                ),
                const SizedBox(height: 12),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Saved Contacts',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        if (contacts.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 18),
                            child: Center(
                              child: Text('No saved contacts yet. Add one above.',
                                  style: TextStyle(color: Colors.grey)),
                            ),
                          )
                        else
                          for (final c in contacts)
                            ListTile(
                              key: Key('contact-${c.id}'),
                              dense: true,
                              contentPadding: EdgeInsets.zero,
                              leading: CircleAvatar(
                                child: Text(
                                  c.name.isNotEmpty
                                      ? c.name[0].toUpperCase()
                                      : '?',
                                ),
                              ),
                              title: Text(c.name),
                              subtitle: Text(
                                [c.phone, c.email]
                                    .where((s) => s != null && s.isNotEmpty)
                                    .join(' · '),
                              ),
                            ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      _toast('Name is required', isError: true);
      return;
    }
    setState(() => _busy = true);
    try {
      final c = await ref.read(contactsRepositoryProvider).create(
            name: name,
            phone: _phone.text.trim(),
            email: _email.text.trim(),
          );
      _name.clear();
      _phone.clear();
      _email.clear();
      ref.invalidate(contactsListProvider);
      _toast('${c.name} added');
    } catch (e) {
      _toast('Could not save: $e', isError: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toast(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
    ));
  }
}

class _AddCard extends StatelessWidget {
  const _AddCard({
    required this.name,
    required this.phone,
    required this.email,
    required this.busy,
    required this.onSave,
  });
  final TextEditingController name;
  final TextEditingController phone;
  final TextEditingController email;
  final bool busy;
  final Future<void> Function() onSave;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Add Contact',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            // F-802 name
            TextField(
              key: const Key('contact-name-input'),
              controller: name,
              decoration: const InputDecoration(
                labelText: 'Name *',
                hintText: 'e.g. Anjali',
              ),
            ),
            const SizedBox(height: 8),
            // F-803 phone
            TextField(
              key: const Key('contact-phone-input'),
              controller: phone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Phone',
                hintText: '+1 555 …',
              ),
            ),
            const SizedBox(height: 8),
            // F-804 email
            TextField(
              key: const Key('contact-email-input'),
              controller: email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Email',
                hintText: 'name@example.com',
              ),
            ),
            const SizedBox(height: 10),
            // F-805 add
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: busy ? null : onSave,
                child: busy
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Text('Add Contact'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Err extends StatelessWidget {
  const _Err({required this.msg, required this.retry});
  final String msg;
  final VoidCallback retry;
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48),
              const SizedBox(height: 12),
              Text(msg, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(onPressed: retry, child: const Text('Retry')),
            ],
          ),
        ),
      );
}
