import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:intl/intl.dart';
import 'utils/access_utils.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<dynamic> _records = [];
  List<dynamic> _filteredRecords = [];
  bool _isLoading = false;
  Map<String, dynamic> _accessInfo = {};

  // --- фильтры ---
  final TextEditingController _boxidController = TextEditingController();
  final TextEditingController _ttnController = TextEditingController();
  final TextEditingController _userController = TextEditingController();
  DateTime? _selectedDate;
  TimeOfDay? _startTime;
  TimeOfDay? _endTime;

  @override
  void initState() {
    super.initState();
    _loadAccess();
    _fetchHistory();
  }

  Future<void> _loadAccess() async {
    final info = await getUserAccessInfo();
    setState(() => _accessInfo = info);
  }

  /// Форматує дату/час у локальну зону пристрою (Київ, якщо вона вибрана)
  String formatDate(String isoString) {
    try {
      final localDate = DateTime.parse(isoString).toLocal();
      return DateFormat('dd.MM.yyyy HH:mm:ss').format(localDate);
    } catch (_) {
      return isoString;
    }
  }

  /// загрузка истории
  Future<void> _fetchHistory() async {
    setState(() => _isLoading = true);
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('token');
    if (token == null) {
      if (mounted) Navigator.pushReplacementNamed(context, '/');
      return;
    }

    try {
      final uri = Uri.parse(
        'https://tracking-api-b4jb.onrender.com/get_history',
      );
      final response = await http.get(
        uri,
        headers: {'Authorization': 'Bearer $token'},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        data.sort((a, b) {
          final da = DateTime.tryParse(a['datetime'] ?? '') ?? DateTime(2000);
          final db = DateTime.tryParse(b['datetime'] ?? '') ?? DateTime(2000);
          return db.compareTo(da);
        });
        setState(() {
          _records = data;
        });
        _applyFilters(); // сразу применяем фильтры
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Помилка сервера: ${response.statusCode}')),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Помилка зв’язку з сервером: $e')));
    } finally {
      setState(() => _isLoading = false);
    }
  }

  /// применяем фильтры локально
  void _applyFilters() {
    List<dynamic> filtered = List.from(_records);

    if (_boxidController.text.isNotEmpty) {
      filtered = filtered
          .where(
            (r) => r['boxid'].toString().contains(_boxidController.text.trim()),
          )
          .toList();
    }

    if (_ttnController.text.isNotEmpty) {
      filtered = filtered
          .where(
            (r) => r['ttn'].toString().contains(_ttnController.text.trim()),
          )
          .toList();
    }

    if (_userController.text.isNotEmpty) {
      filtered = filtered
          .where(
            (r) => r['user_name'].toString().toLowerCase().contains(
              _userController.text.trim().toLowerCase(),
            ),
          )
          .toList();
    }

    if (_selectedDate != null) {
      filtered = filtered.where((r) {
        final dt = DateTime.tryParse(r['datetime'] ?? '');
        if (dt == null) return false;
        final localDt = dt.toLocal();
        return localDt.year == _selectedDate!.year &&
            localDt.month == _selectedDate!.month &&
            localDt.day == _selectedDate!.day;
      }).toList();
    }

    if (_startTime != null || _endTime != null) {
      filtered = filtered.where((r) {
        final dt = DateTime.tryParse(r['datetime'] ?? '');
        if (dt == null) return false;
        final localDt = dt.toLocal();
        final time = TimeOfDay.fromDateTime(localDt);

        bool afterStart = true;
        bool beforeEnd = true;

        if (_startTime != null) {
          afterStart =
              time.hour > _startTime!.hour ||
              (time.hour == _startTime!.hour &&
                  time.minute >= _startTime!.minute);
        }

        if (_endTime != null) {
          beforeEnd =
              time.hour < _endTime!.hour ||
              (time.hour == _endTime!.hour && time.minute <= _endTime!.minute);
        }

        return afterStart && beforeEnd;
      }).toList();
    }

    setState(() {
      _filteredRecords = filtered;
    });
  }

  /// выбор даты
  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate ?? now,
      firstDate: DateTime(2023),
      lastDate: now,
      locale: const Locale('uk', 'UA'),
    );
    if (picked != null) {
      setState(() => _selectedDate = picked);
      _applyFilters();
    }
  }

  /// выбор времени (24-часовой)
  Future<void> _pickTime(bool isStart) async {
    final now = TimeOfDay.now();
    final picked = await showTimePicker(
      context: context,
      initialTime: isStart ? (_startTime ?? now) : (_endTime ?? now),
      helpText: isStart ? 'Початковий час' : 'Кінцевий час',
      cancelText: 'Скасувати',
      confirmText: 'OK',
      builder: (context, child) {
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(alwaysUse24HourFormat: true),
          child: child!,
        );
      },
    );
    if (picked != null) {
      setState(() {
        if (isStart) {
          _startTime = picked;
        } else {
          _endTime = picked;
        }
      });
      _applyFilters();
    }
  }

  void _clearFilters() {
    _boxidController.clear();
    _ttnController.clear();
    _userController.clear();
    _selectedDate = null;
    _startTime = null;
    _endTime = null;
    _applyFilters();
  }

  Future<void> _clearHistory() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Очистити історію?'),
        content: const Text('Ця дія видалить усі записи історії. Ви впевнені?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Скасувати'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent),
            child: const Text('Так, видалити'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _isLoading = true);
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('token');

    try {
      final uri = Uri.parse(
        'https://tracking-api-b4jb.onrender.com/clear_tracking',
      );
      final response = await http.delete(
        uri,
        headers: {'Authorization': 'Bearer $token'},
      );
      if (response.statusCode == 200) {
        setState(() {
          _records.clear();
          _filteredRecords.clear();
        });
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Історію очищено ✅')));
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Не вдалося очистити: ${response.statusCode}'),
          ),
        );
      }
    } catch (_) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Помилка зв’язку з сервером')),
      );
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Історія сканувань'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _fetchHistory),
          if (_accessInfo['canClearHistory'] == true)
            IconButton(
              icon: const Icon(Icons.delete_forever, color: Colors.redAccent),
              tooltip: 'Очистити історію (адмін)',
              onPressed: _clearHistory,
            ),
        ],
      ),
      backgroundColor: const Color(0xFFF7F8FA),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _filterField(_boxidController, 'BoxID'),
                _filterField(_ttnController, 'TTN'),
                _filterField(_userController, 'Користувач'),
                ElevatedButton.icon(
                  onPressed: _pickDate,
                  icon: const Icon(Icons.date_range),
                  label: Text(
                    _selectedDate == null
                        ? 'Дата'
                        : DateFormat('dd.MM.yyyy').format(_selectedDate!),
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: () => _pickTime(true),
                  icon: const Icon(Icons.access_time),
                  label: Text(
                    _startTime == null
                        ? 'Початок'
                        : _startTime!.format(context),
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: () => _pickTime(false),
                  icon: const Icon(Icons.timelapse),
                  label: Text(
                    _endTime == null ? 'Кінець' : _endTime!.format(context),
                  ),
                ),
                TextButton.icon(
                  onPressed: _clearFilters,
                  icon: const Icon(Icons.clear),
                  label: const Text('Скинути'),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _filteredRecords.isEmpty
                ? const Center(child: Text('Історія порожня'))
                : ListView.builder(
                    itemCount: _filteredRecords.length,
                    itemBuilder: (context, index) {
                      final item = _filteredRecords[index];
                      final hasError =
                          item['note'] != null &&
                          item['note'].toString().isNotEmpty;
                      return Card(
                        margin: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 6,
                        ),
                        color: hasError
                            ? const Color(0xFFFFEBEE)
                            : Colors.white,
                        elevation: 2,
                        child: ListTile(
                          leading: const Icon(Icons.qr_code_2),
                          title: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  const Icon(
                                    Icons.inventory_2,
                                    color: Colors.blueGrey,
                                    size: 18,
                                  ),
                                  const SizedBox(width: 6),
                                  Text(
                                    'BoxID: ${item['boxid']}',
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Row(
                                children: [
                                  const Icon(
                                    Icons.local_shipping,
                                    color: Colors.teal,
                                    size: 18,
                                  ),
                                  const SizedBox(width: 6),
                                  Text('TTN: ${item['ttn']}'),
                                ],
                              ),
                            ],
                          ),
                          subtitle: Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('👤 ${item['user_name']}'),
                                Text('🕓 ${formatDate(item['datetime'])}'),
                                if (hasError)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 4),
                                    child: Text(
                                      item['note'],
                                      style: const TextStyle(
                                        color: Colors.redAccent,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _filterField(TextEditingController controller, String label) {
    return SizedBox(
      width: 150,
      child: TextField(
        controller: controller,
        onChanged: (_) => _applyFilters(),
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
          isDense: true,
        ),
      ),
    );
  }
}
