import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../features/appshell/app_shell.dart';
import '../../features/auth/login_screen.dart';
import '../../features/balances/presentation/balances_screen.dart';
import '../../features/contacts/presentation/contacts_screen.dart';
import '../../features/dashboard/presentation/dashboard_screen.dart';
import '../../features/expenses/presentation/expenses_screen.dart';
import '../../features/inventory/presentation/inventory_screen.dart';
import '../../features/medicine/presentation/medicine_screen.dart';
import '../../features/products/presentation/products_screen.dart';
import '../../features/restaurant/presentation/restaurant_screen.dart';
import '../../features/search/presentation/search_screen.dart';
import '../../features/shared/placeholder_screen.dart';
import '../../features/shopping/presentation/shopping_screen.dart';

/// Plan §3 — single go_router with NavigationDrawer shell, auth redirect,
/// query-param sub-tabs, and deep-link support.
final routerProvider = Provider<GoRouter>((ref) {
  final navKey = GlobalKey<NavigatorState>();

  // Re-evaluate when session or unauthorized-signal changes.
  ref.listen(sessionProvider, (_, __) {});
  ref.listen(unauthorizedSignalProvider, (_, __) {});

  return GoRouter(
    navigatorKey: navKey,
    initialLocation: '/dashboard',
    debugLogDiagnostics: true,
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      final loggedIn = session != null;
      final path = state.matchedLocation;
      final atLogin = path == '/login';
      final isInvite = path.startsWith('/invite/');
      final isPairApprove = state.uri.queryParameters['pair_device'] != null;

      if (!loggedIn && !atLogin && !isInvite && !isPairApprove) {
        final next = Uri.encodeComponent(
            state.uri.toString().isEmpty ? '/dashboard' : state.uri.toString());
        return '/login?next=$next';
      }
      if (loggedIn && atLogin) {
        final next = state.uri.queryParameters['next'];
        return next != null && next.startsWith('/') ? next : '/dashboard';
      }
      // Restaurant gate
      if (loggedIn && path.startsWith('/restaurant')) {
        final mods = session.appConfig.modules;
        if (!mods.restaurant) return '/dashboard';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        name: 'login',
        builder: (context, state) {
          final qp = state.uri.queryParameters;
          return LoginScreen(
            nextPath: qp['next'],
            inviteToken: qp['invite'],
            pairDeviceToken: qp['pair_device'],
          );
        },
      ),
      GoRoute(
        path: '/invite/:token',
        name: 'invite',
        builder: (context, state) => LoginScreen(
          inviteToken: state.pathParameters['token'],
        ),
      ),
      GoRoute(
        path: '/search',
        name: 'search',
        builder: (_, __) => const SearchScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) => AppShell(
          location: state.matchedLocation,
          child: child,
        ),
        routes: [
          GoRoute(path: '/dashboard', builder: (_, __) =>
              const DashboardScreen()),
          GoRoute(path: '/inventory', builder: (_, __) =>
              const InventoryScreen()),
          GoRoute(path: '/products', builder: (_, __) => const ProductsScreen()),
          GoRoute(path: '/medicine', builder: (_, __) =>
              const MedicineScreen()),
          GoRoute(path: '/upload', builder: (_, __) =>
              const PlaceholderScreen(title: 'Upload')),
          GoRoute(
            path: '/receipts',
            builder: (_, __) =>
                const PlaceholderScreen(title: 'Receipts'),
            routes: [
              GoRoute(
                path: ':id',
                builder: (context, state) => PlaceholderScreen(
                  title: 'Receipt #${state.pathParameters['id']}',
                ),
              ),
            ],
          ),
          GoRoute(path: '/shopping', builder: (_, __) =>
              const ShoppingScreen()),
          GoRoute(path: '/kitchen', builder: (_, __) =>
              const PlaceholderScreen(title: 'Kitchen')),
          GoRoute(path: '/restaurant', builder: (_, __) =>
              const RestaurantScreen()),
          GoRoute(path: '/balances', builder: (_, __) =>
              const BalancesScreen()),
          GoRoute(path: '/contacts', builder: (_, __) =>
              const ContactsScreen()),
          GoRoute(path: '/expenses', builder: (_, __) =>
              const ExpensesScreen()),
          GoRoute(path: '/budget', builder: (_, __) =>
              const PlaceholderScreen(title: 'Budget')),
          GoRoute(path: '/bills', builder: (_, __) =>
              const PlaceholderScreen(title: 'Bills')),
          GoRoute(path: '/accounts', builder: (_, __) =>
              const PlaceholderScreen(title: 'Accounts')),
          GoRoute(path: '/analytics', builder: (_, __) =>
              const PlaceholderScreen(title: 'Analytics')),
          GoRoute(path: '/contributions', builder: (_, __) =>
              const PlaceholderScreen(title: 'Contributions')),
          GoRoute(path: '/features', builder: (_, __) =>
              const PlaceholderScreen(
                title: 'Features',
                note: 'Will render the web /features page in an in-app WebView',
              )),
          GoRoute(path: '/settings', builder: (_, __) =>
              const PlaceholderScreen(title: 'Settings')),
        ],
      ),
    ],
  );
});
