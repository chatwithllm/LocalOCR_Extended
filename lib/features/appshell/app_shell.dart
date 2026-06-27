import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/theme/theme_provider.dart';
import '../../core/providers.dart';
import 'nav_destinations.dart';

/// Drawer-based app shell wrapping every authenticated route (plan §3).
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.child, required this.location});

  final Widget child;
  final String location;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final modules = session?.appConfig.modules;
    final width = MediaQuery.sizeOf(context).width;
    final wide = width >= 840;

    final destinations = drawerDestinations.where((d) {
      if (!d.isImplemented) return false;
      if (d.id == 'restaurant' && modules != null && !modules.restaurant) {
        return false;
      }
      return true;
    }).toList();

    final activeIndex = destinations.indexWhere(
        (d) => location.startsWith(d.path));

    final drawerBody = NavigationDrawer(
      selectedIndex: activeIndex >= 0 ? activeIndex : 0,
      onDestinationSelected: (i) {
        Navigator.of(context).pop();
        context.go(destinations[i].path);
      },
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(28, 16, 16, 10),
          child: Text(
            session?.appConfig.appName ?? 'LocalOCR Extended',
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
        for (final d in destinations)
          NavigationDrawerDestination(
            icon: Icon(d.icon),
            label: Text(d.label),
          ),
      ],
    );

    final title = (activeIndex >= 0 ? destinations[activeIndex].label : 'LocalOCR Extended');
    final screenActions = ref.watch(appShellActionsProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          ...screenActions,
          IconButton(
            tooltip: 'Switch theme',
            icon: const Icon(Icons.brightness_6_outlined),
            onPressed: () => ref.read(themeProvider.notifier).cycle(),
          ),
          IconButton(
            tooltip: 'Account',
            icon: const Icon(Icons.account_circle_outlined),
            onPressed: () => context.go('/settings'),
          ),
        ],
      ),
      drawer: wide ? null : drawerBody,
      body: wide
          ? Row(
              children: [
                NavigationRail(
                  selectedIndex: activeIndex >= 0 ? activeIndex : 0,
                  onDestinationSelected: (i) => context.go(destinations[i].path),
                  labelType: NavigationRailLabelType.selected,
                  destinations: [
                    for (final d in destinations)
                      NavigationRailDestination(
                        icon: Icon(d.icon),
                        label: Text(d.label),
                      ),
                  ],
                ),
                const VerticalDivider(width: 1, thickness: 1),
                Expanded(child: child),
              ],
            )
          : child,
    );
  }
}
