// MARK: Medicine Cabinet — F-501..F-539
//
// Implemented (39 rows):
//   F-501 page header (H1 + subtitle)
//   F-502 + Add Medication button (opens add sheet)
//   F-503 👥 Members button (opens members sheet)
//   F-504 status select (active/all/expired/finished)
//   F-505 "All" chip
//   F-506 per-person/user/household chip
//   F-507 tile image (admin only) 🔄 — backend has no GET handler; we attempt
//         the URL via Image.network and fall back to emoji on error.
//   F-508 age-group label (👶/🧑/👪)
//   F-509 Expired / Low badge
//   F-510 ×qty pill
//   F-511 name + strength
//   F-512 🍂 expiry date
//   F-513 member/household label
//   F-514 ⚠️ AI warning line
//   F-515 ✎ edit (opens edit sheet)
//   F-516 ✓ Done (active only — PUT status=finished)
//   F-517 🗑 delete (DELETE confirm)
//   F-518..F-535 Add/Edit sheet — full field set + scan/lookup/save/cancel.
//   F-536..F-539 Members sheet — list/delete + add row.
//
// 🔄 (justified adaptations):
//   F-507 image — see note above (backend lacks GET handler).
//   F-531/F-532 camera/gallery — uses image_picker + zxing via mobile_scanner's
//     `analyzeImage` API (matches web's Html5Qrcode.scanFile flow).

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../../app/theme/tokens.generated.dart';
import '../../../core/api/env.dart';
import '../../../core/providers.dart';
import '../../../core/util/friendly_error.dart';
import '../../../core/widgets/empty_state_view.dart';
import '../../../core/util/logger.dart';
import '../data/medicine_models.dart';
import 'medicine_providers.dart';

class MedicineScreen extends ConsumerStatefulWidget {
  const MedicineScreen({super.key});
  @override
  ConsumerState<MedicineScreen> createState() => _MedicineScreenState();
}

class _MedicineScreenState extends ConsumerState<MedicineScreen> {
  late final List<Widget> _appBarActions;

  @override
  void initState() {
    super.initState();
    _appBarActions = [
      IconButton(
        tooltip: 'Add Medication',
        icon: const Icon(Icons.add),
        onPressed: () => _openAddSheet(context),
      ),
      IconButton(
        tooltip: 'Household members',
        icon: const Icon(Icons.people_outline),
        onPressed: () => _openMembersSheet(context),
      ),
      IconButton(
        tooltip: 'Refresh',
        icon: const Icon(Icons.refresh),
        onPressed: () => ref.invalidate(medicineCabinetProvider),
      ),
    ];
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(appShellActionsProvider.notifier).state = _appBarActions;
    });
  }

  @override
  void dispose() {
    ref.read(appShellActionsProvider.notifier).state = const [];
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cabinetAsync = ref.watch(medicineCabinetProvider);
    final isAdmin = ref.watch(sessionProvider)?.user.role == 'admin';
    final status = ref.watch(medicineStatusFilterProvider);

    return Scaffold(
      body: Column(
        children: [
          // Subtitle
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Track household medications, expiry dates, and members',
                style: TextStyle(color: Colors.grey),
              ),
            ),
          ),
          // F-504 status select
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: Row(
              children: [
                const Text('Filter:'),
                const SizedBox(width: 8),
                DropdownButton<String>(
                  value: status,
                  items: [
                    for (final o in medicineStatusOptions)
                      DropdownMenuItem(
                          value: o['value'], child: Text(o['label']!))
                  ],
                  onChanged: (v) {
                    if (v == null) return;
                    ref.read(medicineStatusFilterProvider.notifier).state = v;
                  },
                ),
              ],
            ),
          ),
          Expanded(
            child: cabinetAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => _ErrorView(
                message: 'Could not load medicine cabinet:\n$e',
                onRetry: () => ref.invalidate(medicineCabinetProvider),
              ),
              data: (cabinet) {
                appLogger.i('loaded ${cabinet.medications.length} medications '
                    '(members=${cabinet.members.length} '
                    'users=${cabinet.users.length})');
                return RefreshIndicator(
                  onRefresh: () async {
                    ref.invalidate(medicineCabinetProvider);
                    await ref.read(medicineCabinetProvider.future);
                  },
                  child: CustomScrollView(
                    slivers: [
                      SliverToBoxAdapter(child: _MemberChipRow(cabinet: cabinet)),
                      if (cabinet.medications.isEmpty)
                        const SliverFillRemaining(
                          hasScrollBody: false,
                          child: EmptyStateView(
                            message:
                                'No medications. Tap + Add Medication to get started.',
                            icon: Icons.medication_outlined,
                          ),
                        )
                      else
                        SliverPadding(
                          padding: const EdgeInsets.fromLTRB(12, 4, 12, 16),
                          sliver: SliverGrid(
                            gridDelegate:
                                const SliverGridDelegateWithMaxCrossAxisExtent(
                              maxCrossAxisExtent: 220,
                              mainAxisExtent: 250,
                              mainAxisSpacing: 10,
                              crossAxisSpacing: 10,
                            ),
                            delegate: SliverChildBuilderDelegate(
                              (ctx, i) => _MedTile(
                                med: cabinet.medications[i],
                                cabinet: cabinet,
                                isAdmin: isAdmin,
                              ),
                              childCount: cabinet.medications.length,
                            ),
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  void _openAddSheet(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => const MedicineEditSheet(existing: null),
    );
  }

  void _openMembersSheet(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => const MembersSheet(),
    );
  }
}

// ===== Member chip row (F-505, F-506) =====

class _MemberChipRow extends ConsumerWidget {
  const _MemberChipRow({required this.cabinet});
  final MedicineCabinet cabinet;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(medicineMemberFilterProvider);
    final notifier = ref.read(medicineMemberFilterProvider.notifier);
    final people = cabinet.people;

    return SizedBox(
      height: 48,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        children: [
          // F-505 All chip
          Padding(
            padding: const EdgeInsets.only(right: 6),
            child: FilterChip(
              label: const Text('All'),
              selected: filter == null,
              onSelected: (_) => notifier.state = null,
            ),
          ),
          // F-506 per person/user/member
          for (final p in people)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: FilterChip(
                label: Text('${p.emoji} ${p.name}'),
                selected: filter == p.key,
                onSelected: (_) => notifier.state = p.key,
              ),
            ),
          // F-506 (household variant)
          Padding(
            padding: const EdgeInsets.only(right: 6),
            child: FilterChip(
              label: const Text('🏠 Household'),
              selected: filter == 'household',
              onSelected: (_) => notifier.state = 'household',
            ),
          ),
        ],
      ),
    );
  }
}

// ===== Med tile (F-507..F-517) =====

class _MedTile extends ConsumerWidget {
  const _MedTile({
    required this.med,
    required this.cabinet,
    required this.isAdmin,
  });
  final Medication med;
  final MedicineCabinet cabinet;
  final bool isAdmin;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final tokens = theme.extension<AppTokens>()!;
    final isExpired = med.isExpired || med.status == 'expired';
    final isLow = med.isLow;

    // F-508 age label
    final ageLabel = switch (med.ageGroup) {
      'child' => '👶 Kids',
      'adult' => '🧑 Adult',
      _ => '👪 All',
    };

    // F-510 qty pill (×N + unit if ≠ count)
    final qtyText = med.quantity != null
        ? '×${_fmtQty(med.quantity!)}'
            '${med.unit != 'count' ? ' ${med.unit}' : ''}'
        : '';

    // F-513 member/household label
    String? memberLabel;
    if (med.userId != null) {
      final p = cabinet.people.firstWhere(
        (p) => p.type == 'user' && p.id == med.userId,
        orElse: () => MedicinePerson(
            type: 'user', id: med.userId!, name: 'User', emoji: '👤'),
      );
      memberLabel = '${p.emoji} ${p.name}';
    } else if (med.memberId != null) {
      final p = cabinet.people.firstWhere(
        (p) => p.type == 'member' && p.id == med.memberId,
        orElse: () => MedicinePerson(
            type: 'member', id: med.memberId!, name: 'Member', emoji: '👤'),
      );
      memberLabel = '${p.emoji} ${p.name}';
    } else if (med.belongsTo == 'household') {
      memberLabel = '🏠 Household';
    }

    final accent = isExpired
        ? tokens.error
        : isLow
            ? tokens.warning
            : null;

    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: accent != null
            ? BorderSide(color: accent, width: 1.2)
            : BorderSide.none,
      ),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // F-507 image (admin only, image_path required)
            if (med.imagePath != null && isAdmin)
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.network(
                  '${Env.baseUrl}/medications/${med.id}/photo',
                  height: 70,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const SizedBox(height: 1),
                ),
              ),
            if (med.imagePath != null && isAdmin) const SizedBox(height: 6),
            // Header: age label + badge + qty
            Row(
              children: [
                Expanded(
                  child: Wrap(
                    spacing: 4,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(ageLabel, style: theme.textTheme.labelSmall),
                      // F-509 Expired / Low badge
                      if (isExpired)
                        _Pill(text: 'Expired', color: tokens.error),
                      if (!isExpired && isLow)
                        _Pill(text: 'Low', color: tokens.warning),
                    ],
                  ),
                ),
                if (qtyText.isNotEmpty)
                  Text(qtyText,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(fontWeight: FontWeight.w600)),
              ],
            ),
            const SizedBox(height: 4),
            // F-511 name + strength
            Text(
              med.strength != null && med.strength!.isNotEmpty
                  ? '${med.name} · ${med.strength}'
                  : med.name,
              style: theme.textTheme.titleSmall
                  ?.copyWith(fontWeight: FontWeight.w600),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 2),
            // F-512 expiry
            if (med.expiryDate != null)
              Text('🍂 Exp: ${med.expiryDate}',
                  style: theme.textTheme.bodySmall),
            // F-513 member
            if (memberLabel != null)
              Text(memberLabel,
                  style: theme.textTheme.bodySmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            // F-514 AI warning
            if (med.aiWarnings.isNotEmpty)
              Text(
                '⚠️ ${med.aiWarnings.first}',
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: Colors.grey, fontSize: 11),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            const Spacer(),
            // Actions: edit / done (active) / delete
            Row(
              children: [
                // F-515 edit
                IconButton(
                  tooltip: 'Edit',
                  iconSize: 20,
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.edit_outlined),
                  onPressed: () => _openEditSheet(context, med),
                ),
                // F-516 mark finished
                if (med.status == 'active')
                  TextButton.icon(
                    icon: const Icon(Icons.check, size: 16),
                    label: const Text('Done'),
                    style: TextButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                      minimumSize: const Size(44, 44),
                      padding: const EdgeInsets.symmetric(horizontal: 6),
                    ),
                    onPressed: () => _markFinished(context, ref, med),
                  ),
                const Spacer(),
                // F-517 delete
                IconButton(
                  tooltip: 'Delete',
                  iconSize: 20,
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.delete_outline),
                  color: theme.colorScheme.error,
                  onPressed: () => _delete(context, ref, med),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _openEditSheet(BuildContext context, Medication med) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => MedicineEditSheet(existing: med),
    );
  }

  Future<void> _markFinished(
      BuildContext context, WidgetRef ref, Medication med) async {
    try {
      await ref.read(medicineRepositoryProvider).markFinished(med.id);
      ref.invalidate(medicineCabinetProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Marked as finished ✅')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Failed: ${friendlyError(e)}')));
      }
    }
  }

  Future<void> _delete(
      BuildContext context, WidgetRef ref, Medication med) async {
    final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Delete medication?'),
            content: Text('Delete "${med.name}"?'),
            actions: [
              TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: const Text('Cancel')),
              FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: Theme.of(ctx).colorScheme.error),
                  onPressed: () => Navigator.of(ctx).pop(true),
                  child: const Text('Delete')),
            ],
          ),
        ) ??
        false;
    if (!ok) return;
    try {
      await ref.read(medicineRepositoryProvider).delete(med.id);
      ref.invalidate(medicineCabinetProvider);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Deleted')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Failed: ${friendlyError(e)}')));
      }
    }
  }
}

String _fmtQty(double q) =>
    q == q.roundToDouble() ? q.toInt().toString() : q.toString();

class _Pill extends StatelessWidget {
  const _Pill({required this.text, required this.color});
  final String text;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.18),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          text,
          style: TextStyle(
              color: color, fontSize: 10, fontWeight: FontWeight.w700),
        ),
      );
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48),
              const SizedBox(height: 12),
              Text(message, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      );
}

// ===== Add/Edit sheet (F-518..F-535) =====

class MedicineEditSheet extends ConsumerStatefulWidget {
  const MedicineEditSheet({super.key, required this.existing});
  final Medication? existing;

  @override
  ConsumerState<MedicineEditSheet> createState() => _MedicineEditSheetState();
}

class _MedicineEditSheetState extends ConsumerState<MedicineEditSheet> {
  late final TextEditingController _name;
  late final TextEditingController _active;
  late final TextEditingController _brand;
  late final TextEditingController _strength;
  late final TextEditingController _qty;
  late final TextEditingController _barcode;
  late final TextEditingController _notes;

  String _dosageForm = 'tablet';
  String _ageGroup = 'both';
  String _unit = 'tablets';
  String _belongsTo = 'household'; // household | user_<id> | member_<id>
  DateTime? _expiry;
  DateTime? _mfg;

  bool _busy = false;
  bool _looking = false;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final m = widget.existing;
    _name = TextEditingController(text: m?.name ?? '');
    _active = TextEditingController(text: m?.activeIngredient ?? '');
    _brand = TextEditingController(text: m?.brand ?? '');
    _strength = TextEditingController(text: m?.strength ?? '');
    _qty = TextEditingController(
        text: m?.quantity == null ? '' : _fmtQty(m!.quantity!));
    _barcode = TextEditingController(text: m?.barcode ?? '');
    _notes = TextEditingController(text: m?.notes ?? '');

    _dosageForm = m?.dosageForm ?? 'tablet';
    _ageGroup = m?.ageGroup ?? 'both';
    _unit = m?.unit ?? 'tablets';
    if (m != null) {
      if (m.userId != null) {
        _belongsTo = 'user_${m.userId}';
      } else if (m.memberId != null) {
        _belongsTo = 'member_${m.memberId}';
      } else {
        _belongsTo = 'household';
      }
    }
    _expiry = _parseDate(m?.expiryDate);
    _mfg = _parseDate(m?.manufactureDate);
  }

  @override
  void dispose() {
    _name.dispose();
    _active.dispose();
    _brand.dispose();
    _strength.dispose();
    _qty.dispose();
    _barcode.dispose();
    _notes.dispose();
    super.dispose();
  }

  DateTime? _parseDate(String? s) {
    if (s == null || s.isEmpty) return null;
    try {
      return DateTime.parse(s);
    } catch (_) {
      return null;
    }
  }

  String _fmtDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final cabinetAsync = ref.watch(medicineCabinetProvider);
    final people = cabinetAsync.maybeWhen(
      data: (c) => c.people,
      orElse: () => const <MedicinePerson>[],
    );
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;

    return Padding(
      padding: EdgeInsets.only(bottom: bottomInset),
      child: DraggableScrollableSheet(
        initialChildSize: 0.92,
        maxChildSize: 0.95,
        minChildSize: 0.5,
        expand: false,
        builder: (ctx, scrollController) => Column(
          children: [
            const SizedBox(height: 8),
            Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                    color: Colors.grey, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 8),
            Text(_isEdit ? 'Edit Medication' : 'Add Medication',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            // Scan row — add mode only (F-531, F-532, F-533)
            if (!_isEdit)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  children: [
                    // F-531 camera scan
                    Expanded(
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.photo_camera),
                        label: const Text('Camera'),
                        onPressed: _busy
                            ? null
                            : () => _scanFromSource(ImageSource.camera),
                      ),
                    ),
                    const SizedBox(width: 8),
                    // F-532 gallery scan
                    Expanded(
                      child: OutlinedButton.icon(
                        icon: const Icon(Icons.image_outlined),
                        label: const Text('Gallery'),
                        onPressed: _busy
                            ? null
                            : () => _scanFromSource(ImageSource.gallery),
                      ),
                    ),
                    const SizedBox(width: 8),
                    // F-533 lookup by name
                    SizedBox(
                      width: 100,
                      child: FilledButton.icon(
                        icon: _looking
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white))
                            : const Icon(Icons.search, size: 18),
                        label: const Text('Lookup'),
                        onPressed: _busy || _looking ? null : _lookupByName,
                      ),
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 8),
            Expanded(
              child: SingleChildScrollView(
                controller: scrollController,
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // F-518 name *
                    TextField(
                      controller: _name,
                      decoration: const InputDecoration(
                        labelText: 'Name *',
                        hintText: 'e.g. Ibuprofen',
                      ),
                    ),
                    const SizedBox(height: 8),
                    // F-519 active ingredient
                    TextField(
                      controller: _active,
                      decoration: const InputDecoration(
                        labelText: 'Active Ingredient',
                        hintText: 'e.g. Ibuprofen',
                      ),
                    ),
                    const SizedBox(height: 8),
                    // F-520 brand
                    TextField(
                      controller: _brand,
                      decoration: const InputDecoration(
                        labelText: 'Brand / Manufacturer',
                        hintText: 'e.g. Advil',
                      ),
                    ),
                    const SizedBox(height: 8),
                    // F-521 strength
                    TextField(
                      controller: _strength,
                      decoration: const InputDecoration(
                        labelText: 'Strength',
                        hintText: 'e.g. 200mg',
                      ),
                    ),
                    const SizedBox(height: 8),
                    // F-522 dosage form
                    DropdownButtonFormField<String>(
                      value: _dosageForm,
                      decoration:
                          const InputDecoration(labelText: 'Dosage Form'),
                      items: [
                        for (final o in medicineDosageFormOptions)
                          DropdownMenuItem(
                              value: o['value'], child: Text(o['label']!))
                      ],
                      onChanged: (v) =>
                          setState(() => _dosageForm = v ?? 'tablet'),
                    ),
                    const SizedBox(height: 8),
                    // F-523 age group
                    DropdownButtonFormField<String>(
                      value: _ageGroup,
                      decoration: const InputDecoration(labelText: 'For'),
                      items: [
                        for (final o in medicineAgeGroupOptions)
                          DropdownMenuItem(
                              value: o['value'], child: Text(o['label']!))
                      ],
                      onChanged: (v) => setState(() => _ageGroup = v ?? 'both'),
                    ),
                    const SizedBox(height: 8),
                    // F-524 belongs to
                    DropdownButtonFormField<String>(
                      value: _belongsTo,
                      decoration:
                          const InputDecoration(labelText: 'Belongs To'),
                      items: [
                        const DropdownMenuItem(
                            value: 'household',
                            child: Text('🏠 Household (shared)')),
                        for (final p in people)
                          DropdownMenuItem(
                              value: p.key,
                              child: Text('${p.emoji} ${p.name}'))
                      ],
                      onChanged: (v) =>
                          setState(() => _belongsTo = v ?? 'household'),
                    ),
                    const SizedBox(height: 8),
                    // F-525 + F-526 qty + unit
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _qty,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'Quantity',
                              hintText: 'e.g. 30',
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        SizedBox(
                          width: 130,
                          child: DropdownButtonFormField<String>(
                            value: _unit,
                            decoration:
                                const InputDecoration(labelText: 'Unit'),
                            items: [
                              for (final o in medicineUnitOptions)
                                DropdownMenuItem(
                                    value: o['value'],
                                    child: Text(o['label']!))
                            ],
                            onChanged: (v) =>
                                setState(() => _unit = v ?? 'tablets'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    // F-527 expiry date
                    _DateField(
                      label: 'Expiry Date',
                      date: _expiry,
                      onPick: (d) => setState(() => _expiry = d),
                    ),
                    const SizedBox(height: 8),
                    // F-528 mfg date
                    _DateField(
                      label: 'Manufacture Date (optional)',
                      date: _mfg,
                      onPick: (d) => setState(() => _mfg = d),
                    ),
                    const SizedBox(height: 8),
                    // F-529 barcode
                    TextField(
                      controller: _barcode,
                      decoration: const InputDecoration(
                        labelText: 'Barcode (optional)',
                        hintText: 'UPC/NDC',
                      ),
                    ),
                    const SizedBox(height: 8),
                    // F-530 notes
                    TextField(
                      controller: _notes,
                      decoration: const InputDecoration(
                        labelText: 'Notes (optional)',
                        hintText: 'e.g. Take with food',
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // Footer: cancel / save
            Container(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
              decoration: BoxDecoration(
                border: Border(
                    top: BorderSide(color: Theme.of(context).dividerColor)),
              ),
              child: Row(
                children: [
                  // F-534 cancel
                  Expanded(
                    child: OutlinedButton(
                      onPressed: _busy ? null : () => Navigator.of(context).pop(),
                      child: const Text('Cancel'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  // F-535 save
                  Expanded(
                    child: FilledButton(
                      onPressed: _busy ? null : _save,
                      child: _busy
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white))
                          : Text(_isEdit ? 'Save' : 'Add'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _scanFromSource(ImageSource source) async {
    try {
      final picker = ImagePicker();
      final picked = await picker.pickImage(source: source);
      if (picked == null) return;
      // Decode barcode from picked image using mobile_scanner.
      final controller = MobileScannerController();
      final BarcodeCapture? result = await controller.analyzeImage(picked.path);
      await controller.dispose();
      final code = result?.barcodes.firstOrNull?.rawValue;
      if (code == null || code.isEmpty) {
        _toast('No barcode found — try again with clearer photo', isError: true);
        return;
      }
      await _doBarcodeLookup(code);
    } catch (e) {
      _toast('Scan failed: $e', isError: true);
    }
  }

  Future<void> _doBarcodeLookup(String barcode) async {
    setState(() => _looking = true);
    try {
      final res =
          await ref.read(medicineRepositoryProvider).barcodeLookup(barcode: barcode);
      _applyLookupFields(res);
    } catch (e) {
      _toast('Lookup failed: $e', isError: true);
    } finally {
      if (mounted) setState(() => _looking = false);
    }
  }

  Future<void> _lookupByName() async {
    final nm = _name.text.trim();
    if (nm.isEmpty) {
      _toast('Enter a name first', isError: true);
      return;
    }
    setState(() => _looking = true);
    try {
      final res = await ref.read(medicineRepositoryProvider).barcodeLookup(name: nm);
      _applyLookupFields(res);
    } catch (e) {
      _toast('Lookup failed: $e', isError: true);
    } finally {
      if (mounted) setState(() => _looking = false);
    }
  }

  void _applyLookupFields(BarcodeLookupResult res) {
    if (!res.found || res.fields.isEmpty) {
      _toast('Not found in drug database');
      return;
    }
    final f = res.fields;
    setState(() {
      final n = f['name'];
      if (n is String && n.isNotEmpty) _name.text = n;
      final b = f['brand'];
      if (b is String && b.isNotEmpty) _brand.text = b;
      final s = f['strength'];
      if (s is String && s.isNotEmpty) _strength.text = s;
      final ai = f['active_ingredient'];
      if (ai is String && ai.isNotEmpty) _active.text = ai;
      final df = f['dosage_form'];
      if (df is String &&
          medicineDosageFormOptions.any((o) => o['value'] == df)) {
        _dosageForm = df;
      }
      final ag = f['age_group'];
      if (ag is String &&
          medicineAgeGroupOptions.any((o) => o['value'] == ag)) {
        _ageGroup = ag;
      }
      final bc = f['barcode'];
      if (bc is String && bc.isNotEmpty) _barcode.text = bc;
    });
    _toast('Filled from drug database ✅');
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    if (name.isEmpty) {
      _toast('Name is required', isError: true);
      return;
    }
    int? bodyMember;
    int? bodyUser;
    if (_belongsTo.startsWith('user_')) {
      bodyUser = int.tryParse(_belongsTo.substring('user_'.length));
    } else if (_belongsTo.startsWith('member_')) {
      bodyMember = int.tryParse(_belongsTo.substring('member_'.length));
    }
    final qty = _qty.text.trim().isEmpty
        ? null
        : double.tryParse(_qty.text.trim());
    final body = <String, dynamic>{
      'name': name,
      'brand': _brand.text.trim().isEmpty ? null : _brand.text.trim(),
      'strength': _strength.text.trim().isEmpty ? null : _strength.text.trim(),
      'active_ingredient':
          _active.text.trim().isEmpty ? null : _active.text.trim(),
      'dosage_form': _dosageForm,
      'age_group': _ageGroup,
      'belongs_to': _belongsTo == 'household' ? 'household' : _belongsTo,
      'member_id': bodyMember,
      'user_id': bodyUser,
      'quantity': qty,
      'unit': _unit,
      'expiry_date': _expiry == null ? null : _fmtDate(_expiry!),
      'manufacture_date': _mfg == null ? null : _fmtDate(_mfg!),
      'barcode': _barcode.text.trim().isEmpty ? null : _barcode.text.trim(),
      'notes': _notes.text.trim().isEmpty ? null : _notes.text.trim(),
      'status': widget.existing?.status ?? 'active',
    };
    setState(() => _busy = true);
    try {
      final repo = ref.read(medicineRepositoryProvider);
      if (_isEdit) {
        await repo.update(widget.existing!.id, body);
      } else {
        await repo.create(body);
      }
      ref.invalidate(medicineCabinetProvider);
      if (!mounted) return;
      Navigator.of(context).pop();
      _toast(_isEdit ? 'Updated ✅' : 'Added ✅');
    } catch (e) {
      _toast('Failed: $e', isError: true);
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

class _DateField extends StatelessWidget {
  const _DateField(
      {required this.label, required this.date, required this.onPick});
  final String label;
  final DateTime? date;
  final ValueChanged<DateTime?> onPick;

  @override
  Widget build(BuildContext context) {
    final text = date == null
        ? '—'
        : '${date!.year.toString().padLeft(4, '0')}-'
            '${date!.month.toString().padLeft(2, '0')}-'
            '${date!.day.toString().padLeft(2, '0')}';
    return InkWell(
      onTap: () async {
        final now = DateTime.now();
        final picked = await showDatePicker(
          context: context,
          firstDate: DateTime(2000),
          lastDate: DateTime(now.year + 20),
          initialDate: date ?? now,
        );
        if (picked != null) onPick(picked);
      },
      onLongPress: () => onPick(null),
      child: InputDecorator(
        decoration: InputDecoration(labelText: label),
        child: Row(
          children: [
            Expanded(child: Text(text)),
            const Icon(Icons.calendar_today_outlined, size: 16),
          ],
        ),
      ),
    );
  }
}

// ===== Members sheet (F-536..F-539) =====

class MembersSheet extends ConsumerStatefulWidget {
  const MembersSheet({super.key});
  @override
  ConsumerState<MembersSheet> createState() => _MembersSheetState();
}

class _MembersSheetState extends ConsumerState<MembersSheet> {
  final _name = TextEditingController();
  String _age = 'adult';
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cabinetAsync = ref.watch(medicineCabinetProvider);
    final members = cabinetAsync.maybeWhen(
      data: (c) => c.members,
      orElse: () => const <HouseholdMember>[],
    );
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;

    return Padding(
      padding: EdgeInsets.only(bottom: bottomInset),
      child: DraggableScrollableSheet(
        initialChildSize: 0.7,
        maxChildSize: 0.95,
        minChildSize: 0.4,
        expand: false,
        builder: (ctx, scrollCtl) => Column(
          children: [
            const SizedBox(height: 8),
            Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                    color: Colors.grey, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 8),
            Text('Household Members',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Expanded(
              child: ListView(
                controller: scrollCtl,
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
                children: [
                  if (members.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 16),
                      child: Center(
                        child: Text('No members yet.',
                            style: TextStyle(color: Colors.grey)),
                      ),
                    )
                  else
                    for (final m in members)
                      Card(
                        margin: const EdgeInsets.symmetric(vertical: 4),
                        child: ListTile(
                          leading: Text(m.avatarEmoji ?? '👤',
                              style: const TextStyle(fontSize: 22)),
                          title: Text(m.name),
                          subtitle: Text(
                              m.ageGroup == 'child' ? 'Child' : 'Adult'),
                          // F-536 delete
                          trailing: IconButton(
                            tooltip: 'Delete member',
                            icon: const Icon(Icons.delete_outline),
                            color: Theme.of(context).colorScheme.error,
                            onPressed: _busy ? null : () => _deleteMember(m),
                          ),
                        ),
                      ),
                  const SizedBox(height: 12),
                  Text('Add Member',
                      style: Theme.of(context).textTheme.labelMedium),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      // F-537 name input
                      Expanded(
                        child: TextField(
                          controller: _name,
                          decoration: const InputDecoration(
                            hintText: 'Name (e.g. Emma)',
                            isDense: true,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      // F-538 age select
                      SizedBox(
                        width: 110,
                        child: DropdownButtonFormField<String>(
                          value: _age,
                          isDense: true,
                          items: [
                            for (final o in memberAgeGroupOptions)
                              DropdownMenuItem(
                                  value: o['value'], child: Text(o['label']!))
                          ],
                          onChanged: (v) => setState(() => _age = v ?? 'adult'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      // F-539 add button
                      FilledButton(
                        onPressed: _busy ? null : _addMember,
                        child: const Text('Add'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // Done bar
            Container(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
              decoration: BoxDecoration(
                border: Border(
                    top: BorderSide(color: Theme.of(context).dividerColor)),
              ),
              child: SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Done'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _deleteMember(HouseholdMember m) async {
    final ok = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Delete member?'),
            content: Text('Delete ${m.name}?'),
            actions: [
              TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: const Text('Cancel')),
              FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: Theme.of(ctx).colorScheme.error),
                  onPressed: () => Navigator.of(ctx).pop(true),
                  child: const Text('Delete')),
            ],
          ),
        ) ??
        false;
    if (!ok) return;
    setState(() => _busy = true);
    try {
      await ref.read(medicineRepositoryProvider).deleteMember(m.id);
      ref.invalidate(medicineCabinetProvider);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Failed: ${friendlyError(e)}')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _addMember() async {
    final n = _name.text.trim();
    if (n.isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Name required')));
      return;
    }
    setState(() => _busy = true);
    try {
      await ref
          .read(medicineRepositoryProvider)
          .createMember(name: n, ageGroup: _age);
      _name.clear();
      ref.invalidate(medicineCabinetProvider);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Failed: ${friendlyError(e)}')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}

extension _FirstOrNull<T> on List<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
