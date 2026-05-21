import 'package:flutter/material.dart';

class NavDest {
  final String id;
  final String path;
  final String label;
  final IconData icon;
  const NavDest(this.id, this.path, this.label, this.icon);
}

/// Plan §3 routing table — every web `nav(...)` target.
const drawerDestinations = <NavDest>[
  NavDest('dashboard', '/dashboard', 'Dashboard', Icons.dashboard_outlined),
  NavDest('inventory', '/inventory', 'Inventory', Icons.kitchen_outlined),
  NavDest('products', '/products', 'Products', Icons.shopping_bag_outlined),
  NavDest('medicine', '/medicine', 'Medicine', Icons.medication_outlined),
  NavDest('upload', '/upload', 'Upload', Icons.add_a_photo_outlined),
  NavDest('receipts', '/receipts', 'Receipts', Icons.receipt_long_outlined),
  NavDest('shopping', '/shopping', 'Shopping', Icons.shopping_cart_outlined),
  NavDest('kitchen', '/kitchen', 'Kitchen', Icons.soup_kitchen_outlined),
  NavDest('restaurant', '/restaurant', 'Restaurant', Icons.restaurant_outlined),
  NavDest('balances', '/balances', 'Balances', Icons.account_balance_outlined),
  NavDest('contacts', '/contacts', 'Contacts', Icons.group_outlined),
  NavDest('expenses', '/expenses', 'Expenses', Icons.payments_outlined),
  NavDest('budget', '/budget', 'Budget', Icons.pie_chart_outline),
  NavDest('bills', '/bills', 'Bills', Icons.calendar_month_outlined),
  NavDest('accounts', '/accounts', 'Accounts', Icons.credit_card_outlined),
  NavDest('analytics', '/analytics', 'Analytics', Icons.insights_outlined),
  NavDest('contributions', '/contributions', 'Contributions',
      Icons.emoji_events_outlined),
  NavDest('features', '/features', 'Features', Icons.list_alt_outlined),
  NavDest('settings', '/settings', 'Settings', Icons.settings_outlined),
];
