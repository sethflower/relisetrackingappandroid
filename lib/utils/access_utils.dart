import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'user_management.dart';

/// Возвращает информацию о доступе:
/// уровень, подпись, цвет и права (очистка истории и ошибок)
Future<Map<String, dynamic>> getUserAccessInfo() async {
  final prefs = await SharedPreferences.getInstance();
  final storedRole = prefs.getString('user_role');
  final level = prefs.getInt('access_level');

  UserRole role = storedRole != null
      ? parseUserRole(storedRole)
      : level == UserRole.admin.level
          ? UserRole.admin
          : level == UserRole.operator.level
              ? UserRole.operator
              : UserRole.viewer;

  String label = '👁 Перегляд';
  Color color = Colors.grey;
  bool canClearHistory = false;
  bool canClearErrors = false;
  bool isAdmin = false;

  switch (role) {
    case UserRole.admin:
      label = '🔑 Адмін';
      color = Colors.redAccent;
      canClearHistory = true;
      canClearErrors = true;
      isAdmin = true;
      break;
    case UserRole.operator:
      label = '🧰 Оператор';
      color = Colors.blueAccent;
      break;
    case UserRole.viewer:
      label = '👁 Перегляд';
      color = Colors.grey;
      break;
  }

  canClearHistory = role == UserRole.admin;
  canClearErrors = role == UserRole.admin || role == UserRole.operator;

  return {
    'label': label,
    'color': color,
    'level': level ?? role.level,
    'canClearHistory': canClearHistory,
    'canClearErrors': canClearErrors,
    'isAdmin': isAdmin,
  };
}
