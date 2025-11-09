import 'package:flutter/material.dart';

import 'utils/user_management.dart';

class AdminPanelScreen extends StatefulWidget {
  const AdminPanelScreen({super.key, required this.adminToken});

  final String adminToken;

  @override
  State<AdminPanelScreen> createState() => _AdminPanelScreenState();
}

class _AdminPanelScreenState extends State<AdminPanelScreen> {
  List<PendingUser> _pendingUsers = const [];
  List<ManagedUser> _registeredUsers = const [];
  Map<UserRole, String> _apiPasswords = const {};
  bool _isLoading = true;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final pending = await UserApi.fetchPendingUsers(widget.adminToken);
      final users = await UserApi.fetchUsers(widget.adminToken);
      final passwords = await UserApi.fetchRolePasswords(widget.adminToken);

      final normalizedPasswords = <UserRole, String>{
        for (final role in UserRole.values) role: passwords[role] ?? '',
      };

      if (!mounted) return;
      setState(() {
        _pendingUsers = pending;
        _registeredUsers = users;
        _apiPasswords = normalizedPasswords;
        _isLoading = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _errorMessage = error.message;
        _isLoading = false;
      });
      _showError(error.message);
    } catch (_) {
      if (!mounted) return;
      const fallback = 'Не вдалося завантажити дані. Спробуйте пізніше.';
      setState(() {
        _errorMessage = fallback;
        _isLoading = false;
      });
      _showError(fallback);
    }
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Future<void> _approveUser(PendingUser user, UserRole role) async {
    try {
      await UserApi.approvePendingUser(
        token: widget.adminToken,
        requestId: user.id,
        role: role,
      );
      await _loadData();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '${user.surname} отримав(ла) роль "${role.label}"',
          ),
        ),
      );
    } on ApiException catch (error) {
      _showError(error.message);
    } catch (_) {
      _showError('Не вдалося підтвердити користувача');
    }
  }

  Future<void> _rejectUser(PendingUser user) async {
    try {
      await UserApi.rejectPendingUser(
        token: widget.adminToken,
        requestId: user.id,
      );
      await _loadData();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Запит від ${user.surname} відхилено'),
        ),
      );
    } on ApiException catch (error) {
      _showError(error.message);
    } catch (_) {
      _showError('Не вдалося відхилити запит');
    }
  }

  Future<void> _changeRole(ManagedUser user, UserRole role) async {
    try {
      await UserApi.updateUser(
        token: widget.adminToken,
        userId: user.id,
        role: role,
      );
      await _loadData();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Роль користувача ${user.surname} змінена на "${role.label}"',
          ),
        ),
      );
    } on ApiException catch (error) {
      _showError(error.message);
    } catch (_) {
      _showError('Не вдалося змінити роль користувача');
    }
  }

  Future<void> _toggleUser(ManagedUser user, bool value) async {
    try {
      await UserApi.updateUser(
        token: widget.adminToken,
        userId: user.id,
        isActive: value,
      );
      await _loadData();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            value
                ? 'Доступ для ${user.surname} активовано'
                : 'Доступ для ${user.surname} призупинено',
          ),
        ),
      );
    } on ApiException catch (error) {
      _showError(error.message);
    } catch (_) {
      _showError('Не вдалося змінити статус користувача');
    }
  }

  Future<void> _editApiPassword(UserRole role) async {
    final controller = TextEditingController(text: _apiPasswords[role] ?? '');

    final result = await showDialog<String?>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text('API пароль для ролі "${role.label}"'),
          content: TextField(
            controller: controller,
            decoration: const InputDecoration(
              labelText: 'Системний пароль',
              helperText: 'Використовується для отримання токена у бекенді',
            ),
            obscureText: true,
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Скасувати'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, controller.text.trim()),
              child: const Text('Зберегти'),
            ),
          ],
        );
      },
    );

    if (result == null) return;

    try {
      await UserApi.updateRolePassword(
        token: widget.adminToken,
        role: role,
        password: result,
      );
      await _loadData();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Пароль для ролі "${role.label}" оновлено'),
        ),
      );
    } on ApiException catch (error) {
      _showError(error.message);
    } catch (_) {
      _showError('Не вдалося оновити пароль ролі');
    }
  }

  Future<void> _deleteUser(ManagedUser user) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Видалити користувача'),
        content: Text(
          'Обліковий запис ${user.surname} буде повністю видалено. Користувач зможе зареєструватися знову з новим паролем.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Скасувати'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red,
            ),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Видалити'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      await UserApi.deleteUser(
        token: widget.adminToken,
        userId: user.id,
      );
      await _loadData();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Користувача ${user.surname} видалено'),
        ),
      );
    } on ApiException catch (error) {
      _showError(error.message);
    } catch (_) {
      _showError('Не вдалося видалити користувача');
    }
  }

  Future<void> _revokeAccess(ManagedUser user) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Призупинити доступ'),
        content: Text(
          'Користувач ${user.surname} втратить можливість входу до системи. Продовжити?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Скасувати'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Призупинити'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    await _toggleUser(user, false);
  }

  Widget _buildPendingCard(PendingUser user) {
    UserRole selectedRole = UserRole.viewer;

    return StatefulBuilder(
      builder: (context, setInnerState) {
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        user.surname,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                    Text(
                      _formatDate(user.createdAt),
                      style: Theme.of(context)
                          .textTheme
                          .labelMedium
                          ?.copyWith(color: Colors.grey),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<UserRole>(
                  value: selectedRole,
                  decoration: const InputDecoration(
                    labelText: 'Роль користувача',
                  ),
                  items: UserRole.values
                      .map(
                        (role) => DropdownMenuItem<UserRole>(
                          value: role,
                          child: Text(role.label),
                        ),
                      )
                      .toList(),
                  onChanged: (role) {
                    if (role == null) return;
                    setInnerState(() => selectedRole = role);
                  },
                ),
                const SizedBox(height: 12),
                Text(selectedRole.description),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: () => _approveUser(user, selectedRole),
                        icon: const Icon(Icons.check),
                        label: const Text('Підтвердити'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _rejectUser(user),
                        icon: const Icon(Icons.close),
                        label: const Text('Відхилити'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildUserCard(ManagedUser user) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    user.surname,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Switch.adaptive(
                      value: user.isActive,
                      onChanged: (value) => _toggleUser(user, value),
                    ),
                    PopupMenuButton<_UserMenuAction>(
                      tooltip: 'Додаткові дії',
                      onSelected: (action) {
                        switch (action) {
                          case _UserMenuAction.revoke:
                            _revokeAccess(user);
                            break;
                          case _UserMenuAction.delete:
                            _deleteUser(user);
                            break;
                        }
                      },
                      itemBuilder: (context) => [
                        PopupMenuItem<_UserMenuAction>(
                          value: _UserMenuAction.revoke,
                          child: Row(
                            children: const [
                              Icon(Icons.block, size: 20),
                              SizedBox(width: 8),
                              Text('Призупинити доступ'),
                            ],
                          ),
                        ),
                        const PopupMenuDivider(),
                        PopupMenuItem<_UserMenuAction>(
                          value: _UserMenuAction.delete,
                          child: Row(
                            children: const [
                              Icon(Icons.delete_outline, size: 20),
                              SizedBox(width: 8),
                              Text('Видалити користувача'),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ],
            ),
            Text(
              'Створено: ${_formatDate(user.createdAt)}',
              style: Theme.of(context)
                  .textTheme
                  .labelMedium
                  ?.copyWith(color: Colors.grey),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<UserRole>(
              value: user.role,
              decoration: const InputDecoration(labelText: 'Поточна роль'),
              items: UserRole.values
                  .map(
                    (role) => DropdownMenuItem<UserRole>(
                      value: role,
                      child: Text(role.label),
                    ),
                  )
                  .toList(),
              onChanged: (role) {
                if (role == null || role == user.role) return;
                _changeRole(user, role);
              },
            ),
            const SizedBox(height: 8),
            Text(user.role.description),
            const SizedBox(height: 12),
            Row(
              children: [
                Chip(
                  avatar: Icon(
                    user.isActive ? Icons.check_circle : Icons.pause_circle,
                    color: user.isActive ? Colors.green : Colors.orange,
                  ),
                  label: Text(
                    user.isActive ? 'Доступ активний' : 'Доступ призупинено',
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime date) {
    return '${date.day.toString().padLeft(2, '0')}.${date.month.toString().padLeft(2, '0')}.${date.year}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Панель адміністратора'),
        actions: [
          IconButton(
            onPressed: _loadData,
            icon: const Icon(Icons.refresh),
            tooltip: 'Оновити',
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadData,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  if (_errorMessage != null) ...[
                    Card(
                      color: Colors.red.shade50,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(
                          children: [
                            const Icon(Icons.warning_amber, color: Colors.redAccent),
                            const SizedBox(width: 12),
                            Expanded(child: Text(_errorMessage!)),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  if (_pendingUsers.isNotEmpty) ...[
                    Text(
                      'Нові запити (${_pendingUsers.length})',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 12),
                    for (final user in _pendingUsers) _buildPendingCard(user),
                    const SizedBox(height: 24),
                  ] else ...[
                    Card(
                      color: Colors.green.shade50,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(
                          children: const [
                            Icon(Icons.check_circle, color: Colors.green),
                            SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                'Немає нових запитів на реєстрацію',
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                  ],
                  Text(
                    'Зареєстровані користувачі (${_registeredUsers.length})',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 12),
                  if (_registeredUsers.isEmpty)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(
                          children: const [
                            Icon(Icons.person_search_outlined),
                            SizedBox(width: 12),
                            Expanded(
                              child: Text('Користувачів ще не підтверджено'),
                            ),
                          ],
                        ),
                      ),
                    )
                  else
                    ..._registeredUsers.map(_buildUserCard),
                  const SizedBox(height: 24),
                  Text(
                    'Системні паролі API',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 12),
                  ...UserRole.values.map(
                    (role) => Card(
                      child: ListTile(
                        title: Text(role.label),
                        subtitle: Text(
                          'Поточний пароль: ${(_apiPasswords[role] ?? '').isEmpty ? 'не вказано' : '•••••••'}',
                        ),
                        trailing: const Icon(Icons.edit),
                        onTap: () => _editApiPassword(role),
                      ),
                    ),
                  ),
                  const SizedBox(height: 48),
                ],
              ),
            ),
    );
  }
}

enum _UserMenuAction { revoke, delete }