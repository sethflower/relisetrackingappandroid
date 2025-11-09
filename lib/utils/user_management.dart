import 'dart:convert';

import 'package:http/http.dart' as http;

const String kApiHost = 'tracking-api-b4jb.onrender.com';

class ApiException implements Exception {
  ApiException(this.message, this.statusCode);

  final String message;
  final int statusCode;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

enum UserRole { admin, operator, viewer }

extension UserRoleX on UserRole {
  String get label {
    switch (this) {
      case UserRole.admin:
        return 'Адмін';
      case UserRole.operator:
        return 'Оператор';
      case UserRole.viewer:
        return 'Перегляд';
    }
  }

  String get description {
    switch (this) {
      case UserRole.admin:
        return 'Повний доступ до функцій та керування користувачами';
      case UserRole.operator:
        return 'Додавання записів та базовий функціонал';
      case UserRole.viewer:
        return 'Перегляд інформації без змін';
    }
  }

  int get level {
    switch (this) {
      case UserRole.admin:
        return 1;
      case UserRole.operator:
        return 0;
      case UserRole.viewer:
        return 2;
    }
  }
}

UserRole parseUserRole(String? value) {
  switch (value) {
    case 'admin':
      return UserRole.admin;
    case 'operator':
      return UserRole.operator;
    case 'viewer':
      return UserRole.viewer;
    default:
      return UserRole.viewer;
  }
}

class ManagedUser {
  const ManagedUser({
    required this.id,
    required this.surname,
    required this.role,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  final int id;
  final String surname;
  final UserRole role;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  ManagedUser copyWith({
    UserRole? role,
    bool? isActive,
  }) {
    return ManagedUser(
      id: id,
      surname: surname,
      role: role ?? this.role,
      isActive: isActive ?? this.isActive,
      createdAt: createdAt,
      updatedAt: DateTime.now(),
    );
  }

  factory ManagedUser.fromJson(Map<String, dynamic> json) {
    return ManagedUser(
      id: json['id'] is int
          ? json['id'] as int
          : int.tryParse(json['id']?.toString() ?? '') ?? 0,
      surname: json['surname']?.toString() ?? 'Невідомий користувач',
      role: parseUserRole(json['role']?.toString()),
      isActive: json['is_active'] == true,
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.now(),
      updatedAt: DateTime.tryParse(json['updated_at']?.toString() ?? '') ??
          DateTime.now(),
    );
  }
}

class PendingUser {
  const PendingUser({
    required this.id,
    required this.surname,
    required this.createdAt,
  });

  final int id;
  final String surname;
  final DateTime createdAt;

  factory PendingUser.fromJson(Map<String, dynamic> json) {
    return PendingUser(
      id: json['id'] is int
          ? json['id'] as int
          : int.tryParse(json['id']?.toString() ?? '') ?? 0,
      surname: json['surname']?.toString() ?? 'Невідомий користувач',
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.now(),
    );
  }
}

class UserApi {
  const UserApi._();

  static Uri _uri(String path, [Map<String, String>? query]) {
    return Uri.https(kApiHost, path, query);
  }

  static Map<String, String> _headers({String? token}) {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    };
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  static dynamic _decodeBody(http.Response response) {
    if (response.body.isEmpty) {
      return null;
    }
    try {
      return jsonDecode(response.body);
    } catch (_) {
      return null;
    }
  }

  static String _extractMessage(dynamic body, int statusCode) {
    if (body is Map<String, dynamic>) {
      final detail = body['detail'] ?? body['message'];
      if (detail is String && detail.isNotEmpty) {
        return detail;
      }
    }
    return 'Помилка сервера ($statusCode)';
  }

  static Never _throwError(http.Response response) {
    final body = _decodeBody(response);
    final message = _extractMessage(body, response.statusCode);
    throw ApiException(message, response.statusCode);
  }

  static Future<void> registerUser(String surname, String password) async {
    final response = await http.post(
      _uri('/register'),
      headers: _headers(),
      body: jsonEncode({
        'surname': surname.trim(),
        'password': password.trim(),
      }),
    );

    if (response.statusCode == 200) {
      return;
    }
    _throwError(response);
  }

  static Future<List<PendingUser>> fetchPendingUsers(String token) async {
    final response = await http.get(
      _uri('/admin/registration_requests'),
      headers: _headers(token: token),
    );

    if (response.statusCode == 200) {
      final body = _decodeBody(response);
      if (body is List) {
        return body
            .map((item) => PendingUser.fromJson(
                item is Map<String, dynamic>
                    ? item
                    : Map<String, dynamic>.from(
                        (item as Map).map(
                          (key, value) => MapEntry(key.toString(), value),
                        ),
                      )))
            .toList(growable: false);
      }
      return const [];
    }

    _throwError(response);
  }

  static Future<void> approvePendingUser({
    required String token,
    required int requestId,
    required UserRole role,
  }) async {
    final response = await http.post(
      _uri('/admin/registration_requests/$requestId/approve'),
      headers: _headers(token: token),
      body: jsonEncode({'role': role.name}),
    );

    if (response.statusCode == 200) {
      return;
    }

    _throwError(response);
  }

  static Future<void> rejectPendingUser({
    required String token,
    required int requestId,
  }) async {
    final response = await http.post(
      _uri('/admin/registration_requests/$requestId/reject'),
      headers: _headers(token: token),
    );

    if (response.statusCode == 200) {
      return;
    }

    _throwError(response);
  }

  static Future<List<ManagedUser>> fetchUsers(String token) async {
    final response = await http.get(
      _uri('/admin/users'),
      headers: _headers(token: token),
    );

    if (response.statusCode == 200) {
      final body = _decodeBody(response);
      if (body is List) {
        return body
            .map((item) => ManagedUser.fromJson(
                item is Map<String, dynamic>
                    ? item
                    : Map<String, dynamic>.from(
                        (item as Map).map(
                          (key, value) => MapEntry(key.toString(), value),
                        ),
                      )))
            .toList(growable: false);
      }
      return const [];
    }

    _throwError(response);
  }

  static Future<ManagedUser> updateUser({
    required String token,
    required int userId,
    UserRole? role,
    bool? isActive,
  }) async {
    final payload = <String, dynamic>{};
    if (role != null) {
      payload['role'] = role.name;
    }
    if (isActive != null) {
      payload['is_active'] = isActive;
    }

    if (payload.isEmpty) {
      throw ApiException('Немає даних для оновлення', 400);
    }

    final response = await http.patch(
      _uri('/admin/users/$userId'),
      headers: _headers(token: token),
      body: jsonEncode(payload),
    );

    if (response.statusCode == 200) {
      final body = _decodeBody(response);
      if (body is Map<String, dynamic>) {
        return ManagedUser.fromJson(body);
      }
      throw ApiException('Некоректна відповідь сервера', response.statusCode);
    }

    _throwError(response);
  }

  static Future<void> deleteUser({
    required String token,
    required int userId,
  }) async {
    final response = await http.delete(
      _uri('/admin/users/$userId'),
      headers: _headers(token: token),
    );

    if (response.statusCode == 200) {
      return;
    }

    _throwError(response);
  }

  static Future<Map<UserRole, String>> fetchRolePasswords(String token) async {
    final response = await http.get(
      _uri('/admin/role-passwords'),
      headers: _headers(token: token),
    );

    if (response.statusCode == 200) {
      final body = _decodeBody(response);
      if (body is Map) {
        final result = <UserRole, String>{};
        body.forEach((key, value) {
          final role = parseUserRole(key.toString());
          result[role] = value == null ? '' : value.toString();
        });
        return result;
      }
      return const {};
    }

    _throwError(response);
  }

  static Future<void> updateRolePassword({
    required String token,
    required UserRole role,
    required String password,
  }) async {
    final response = await http.post(
      _uri('/admin/role-passwords/${role.name}'),
      headers: _headers(token: token),
      body: jsonEncode({'password': password.trim()}),
    );

    if (response.statusCode == 200) {
      return;
    }

    _throwError(response);
  }
}