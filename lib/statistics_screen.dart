import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'utils/access_utils.dart';

class StatisticsScreen extends StatefulWidget {
  const StatisticsScreen({super.key});

  @override
  State<StatisticsScreen> createState() => _StatisticsScreenState();
}

class _StatisticsScreenState extends State<StatisticsScreen> {
  bool _isAdmin = false;
  bool _accessChecked = false;
  bool _isLoading = true;
  String? _errorMessage;
  DateTime? _lastUpdated;

  DateTime? _startDate;
  DateTime? _endDate;
  TimeOfDay? _startTime;
  TimeOfDay? _endTime;

  List<dynamic> _historyRecords = [];
  List<dynamic> _errorRecords = [];

  Map<String, int> _scanCounts = {};
  Map<String, int> _errorCounts = {};

  int _totalScans = 0;
  int _uniqueUsers = 0;
  int _totalErrors = 0;
  int _errorUsers = 0;
  String _topOperator = '—';
  int _topOperatorCount = 0;
  String _topErrorOperator = '—';
  int _topErrorOperatorCount = 0;

  List<_DailyView> _dailyRows = [];

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _startDate = DateTime(now.year, now.month, 1);
    _endDate = DateTime(now.year, now.month, now.day);
    _startTime = const TimeOfDay(hour: 0, minute: 0);
    _endTime = const TimeOfDay(hour: 23, minute: 59);
    _loadAccess();
  }

  Future<void> _loadAccess() async {
    final info = await getUserAccessInfo();
    if (!mounted) return;
    setState(() {
      _isAdmin = info['isAdmin'] == true;
      _accessChecked = true;
    });
    if (_isAdmin) {
      await _fetchData();
    } else {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Доступ до статистики дозволено лише адміністраторам';
      });
    }
  }

  Future<void> _fetchData() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('token');
    if (token == null) {
      if (!mounted) return;
      Navigator.pushNamedAndRemoveUntil(context, '/', (route) => false);
      return;
    }

    try {
      final headers = {'Authorization': 'Bearer $token'};
      final historyUri = Uri.parse(
        'https://tracking-api-b4jb.onrender.com/get_history',
      );
      final errorsUri = Uri.parse(
        'https://tracking-api-b4jb.onrender.com/get_errors',
      );

      final responses = await Future.wait([
        http.get(historyUri, headers: headers),
        http.get(errorsUri, headers: headers),
      ]);

      final historyResponse = responses[0];
      final errorsResponse = responses[1];

      if (historyResponse.statusCode == 200 &&
          errorsResponse.statusCode == 200) {
        final historyData = jsonDecode(historyResponse.body) as List<dynamic>;
        final errorsData = jsonDecode(errorsResponse.body) as List<dynamic>;

        historyData.sort((a, b) {
          final da = _parseDate(a['datetime']);
          final db = _parseDate(b['datetime']);
          return db.compareTo(da);
        });
        errorsData.sort((a, b) {
          final da = _parseDate(a['datetime']);
          final db = _parseDate(b['datetime']);
          return db.compareTo(da);
        });

        if (!mounted) return;
        setState(() {
          _historyRecords = historyData;
          _errorRecords = errorsData;
          _isLoading = false;
          _lastUpdated = DateTime.now();
        });
        _applyFilters();
      } else {
        throw Exception(
          'history ${historyResponse.statusCode}, errors ${errorsResponse.statusCode}',
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _errorMessage = 'Не вдалося завантажити дані: $e';
      });
    }
  }

  DateTime _parseDate(dynamic value) {
    if (value is String) {
      try {
        return DateTime.parse(value).toLocal();
      } catch (_) {
        return DateTime.fromMillisecondsSinceEpoch(0);
      }
    }
    return DateTime.fromMillisecondsSinceEpoch(0);
  }

  DateTime? _startDateTime() =>
      _combineDateTime(_startDate, _startTime, isStart: true);
  DateTime? _endDateTime() =>
      _combineDateTime(_endDate, _endTime, isStart: false);

  DateTime? _combineDateTime(
    DateTime? date,
    TimeOfDay? time, {
    required bool isStart,
  }) {
    if (date == null) return null;
    final baseTime =
        time ??
        (isStart
            ? const TimeOfDay(hour: 0, minute: 0)
            : const TimeOfDay(hour: 23, minute: 59));
    return DateTime(
      date.year,
      date.month,
      date.day,
      baseTime.hour,
      baseTime.minute,
    );
  }

  void _ensurePeriodOrder() {
    final start = _startDateTime();
    final end = _endDateTime();
    if (start != null && end != null && start.isAfter(end)) {
      final tmpDate = _startDate;
      final tmpTime = _startTime;
      _startDate = _endDate;
      _startTime = _endTime;
      _endDate = tmpDate;
      _endTime = tmpTime;
    }
  }

  Future<void> _pickDate({required bool isStart}) async {
    final now = DateTime.now();
    final initial = isStart ? (_startDate ?? now) : (_endDate ?? now);
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2023, 1, 1),
      lastDate: now,
      locale: const Locale('uk', 'UA'),
    );
    if (picked != null) {
      setState(() {
        if (isStart) {
          _startDate = DateTime(picked.year, picked.month, picked.day);
        } else {
          _endDate = DateTime(picked.year, picked.month, picked.day);
        }
      });
      _ensurePeriodOrder();
      _applyFilters();
    }
  }

  Future<void> _pickTime({required bool isStart}) async {
    final now = TimeOfDay.now();
    final initial = isStart ? (_startTime ?? now) : (_endTime ?? now);
    final picked = await showTimePicker(
      context: context,
      initialTime: initial,
      helpText: isStart ? 'Час початку' : 'Час завершення',
      cancelText: 'Скасувати',
      confirmText: 'OK',
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(alwaysUse24HourFormat: true),
        child: child!,
      ),
    );
    if (picked != null) {
      setState(() {
        if (isStart) {
          _startTime = picked;
        } else {
          _endTime = picked;
        }
      });
      _ensurePeriodOrder();
      _applyFilters();
    }
  }

  void _resetPeriod() {
    final now = DateTime.now();
    setState(() {
      _startDate = DateTime(now.year, now.month, 1);
      _endDate = DateTime(now.year, now.month, now.day);
      _startTime = const TimeOfDay(hour: 0, minute: 0);
      _endTime = const TimeOfDay(hour: 23, minute: 59);
    });
    _applyFilters();
  }

  void _applyFilters() {
    final start = _startDateTime();
    final end = _endDateTime();

    final scans = _filterRecords(_historyRecords, start, end);
    final errors = _filterRecords(_errorRecords, start, end);

    final scanCounts = _groupByUser(scans);
    final errorCounts = _groupByUser(errors);

    final topScan = _topEntry(scanCounts);
    final topError = _topEntry(errorCounts);

    final daily = _buildDailyRows(scans, errors);

    setState(() {
      _scanCounts = scanCounts;
      _errorCounts = errorCounts;
      _totalScans = scanCounts.values.fold(0, (a, b) => a + b);
      _uniqueUsers = scanCounts.keys.length;
      _totalErrors = errorCounts.values.fold(0, (a, b) => a + b);
      _errorUsers = errorCounts.keys.length;
      _topOperator = topScan.name;
      _topOperatorCount = topScan.count;
      _topErrorOperator = topError.name;
      _topErrorOperatorCount = topError.count;
      _dailyRows = daily;
    });
  }

  List<dynamic> _filterRecords(
    List<dynamic> records,
    DateTime? start,
    DateTime? end,
  ) {
    return records.where((record) {
      final dt = _parseDate(record['datetime']);
      if (start != null && dt.isBefore(start)) return false;
      if (end != null && dt.isAfter(end)) return false;
      return true;
    }).toList();
  }

  Map<String, int> _groupByUser(List<dynamic> records) {
    final counts = <String, int>{};
    for (final record in records) {
      final rawName =
          record['user_name'] ?? record['operator'] ?? 'Невідомий користувач';
      final name = rawName.toString().trim().isEmpty
          ? 'Невідомий користувач'
          : rawName.toString().trim();
      counts[name] = (counts[name] ?? 0) + 1;
    }
    return counts;
  }

  _TopEntry _topEntry(Map<String, int> counts) {
    if (counts.isEmpty) {
      return const _TopEntry(name: '—', count: 0);
    }
    final sorted = counts.entries.toList()
      ..sort((a, b) {
        final cmp = b.value.compareTo(a.value);
        if (cmp != 0) return cmp;
        return a.key.toLowerCase().compareTo(b.key.toLowerCase());
      });
    final first = sorted.first;
    return _TopEntry(name: first.key, count: first.value);
  }

  List<_DailyView> _buildDailyRows(List<dynamic> scans, List<dynamic> errors) {
    final map = <DateTime, _DailyStats>{};

    void ensure(DateTime day) {
      map.putIfAbsent(day, () => _DailyStats(day));
    }

    for (final record in scans) {
      final dt = _parseDate(record['datetime']);
      final day = DateTime(dt.year, dt.month, dt.day);
      ensure(day);
      final rawName =
          record['user_name'] ?? record['operator'] ?? 'Невідомий користувач';
      final name = rawName.toString().trim().isEmpty
          ? 'Невідомий користувач'
          : rawName.toString().trim();
      final stats = map[day]!;
      stats.scans += 1;
      stats.scanUsers[name] = (stats.scanUsers[name] ?? 0) + 1;
    }

    for (final record in errors) {
      final dt = _parseDate(record['datetime']);
      final day = DateTime(dt.year, dt.month, dt.day);
      ensure(day);
      final rawName =
          record['user_name'] ?? record['operator'] ?? 'Невідомий користувач';
      final name = rawName.toString().trim().isEmpty
          ? 'Невідомий користувач'
          : rawName.toString().trim();
      final stats = map[day]!;
      stats.errors += 1;
      stats.errorUsers[name] = (stats.errorUsers[name] ?? 0) + 1;
    }

    final formatter = DateFormat('dd.MM.yyyy');
    final rows = map.values.toList()..sort((a, b) => b.date.compareTo(a.date));

    return rows
        .map(
          (stats) => _DailyView(
            dateLabel: formatter.format(stats.date),
            scans: stats.scans,
            errors: stats.errors,
            topScan: _topEntry(stats.scanUsers).formatted,
            topError: _topEntry(stats.errorUsers).formatted,
          ),
        )
        .toList();
  }

  String _periodLabel() {
    final start = _startDateTime();
    final end = _endDateTime();
    final formatter = DateFormat('dd.MM.yyyy HH:mm');
    if (start != null && end != null) {
      return 'Період: ${formatter.format(start)} – ${formatter.format(end)}';
    }
    if (start != null) {
      return 'Починаючи з ${formatter.format(start)}';
    }
    if (end != null) {
      return 'До ${formatter.format(end)}';
    }
    return 'Період: усі дані';
  }

  String _formatTime(TimeOfDay? time) {
    if (time == null) return '—';
    final hours = time.hour.toString().padLeft(2, '0');
    final minutes = time.minute.toString().padLeft(2, '0');
    return '$hours:$minutes';
  }

  String _formatDate(DateTime? date) {
    if (date == null) return '—';
    return DateFormat('dd.MM.yyyy').format(date);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Статистика'),
        actions: [
          if (_isAdmin)
            IconButton(
              icon: const Icon(Icons.refresh),
              tooltip: 'Оновити',
              onPressed: _fetchData,
            ),
        ],
      ),
      backgroundColor: const Color(0xFFF7F8FA),
      body: !_accessChecked
          ? const Center(child: CircularProgressIndicator())
          : !_isAdmin
          ? _buildNoAccess()
          : _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _buildContent(),
    );
  }

  Widget _buildNoAccess() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: const [
            Icon(Icons.lock_outline, size: 72, color: Colors.redAccent),
            SizedBox(height: 16),
            Text(
              'У вас немає прав для перегляду статистики.\nЗверніться до адміністратора.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 18),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.error_outline,
                size: 72,
                color: Colors.redAccent,
              ),
              const SizedBox(height: 16),
              Text(
                _errorMessage!,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 18),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _fetchData,
                icon: const Icon(Icons.refresh),
                label: const Text('Спробувати знову'),
              ),
            ],
          ),
        ),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildFiltersCard(),
          const SizedBox(height: 16),
          _buildSummaryCards(),
          const SizedBox(height: 16),
          _buildLeaderboards(),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Widget _buildFiltersCard() {
    final theme = Theme.of(context);
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Період аналізу',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                if (_lastUpdated != null)
                  Text(
                    'Оновлено: ${DateFormat('dd.MM.yyyy HH:mm').format(_lastUpdated!)}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: Colors.grey[600],
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              _periodLabel(),
              style: theme.textTheme.bodyMedium?.copyWith(
                color: Colors.grey[700],
              ),
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                _FilterButton(
                  icon: Icons.calendar_today,
                  label: 'Початок: ${_formatDate(_startDate)}',
                  onTap: () => _pickDate(isStart: true),
                ),
                _FilterButton(
                  icon: Icons.calendar_month,
                  label: 'Завершення: ${_formatDate(_endDate)}',
                  onTap: () => _pickDate(isStart: false),
                ),
                _FilterButton(
                  icon: Icons.access_time,
                  label: 'Час початку: ${_formatTime(_startTime)}',
                  onTap: () => _pickTime(isStart: true),
                ),
                _FilterButton(
                  icon: Icons.timelapse,
                  label: 'Час завершення: ${_formatTime(_endTime)}',
                  onTap: () => _pickTime(isStart: false),
                ),
                TextButton.icon(
                  onPressed: _resetPeriod,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Скинути період'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryCards() {
    final metrics = [
      _MetricCardData(
        title: 'Всього сканувань',
        value: _totalScans.toString(),
        icon: Icons.qr_code_scanner,
        color: Colors.blueAccent,
        footer: 'Унікальних операторів: $_uniqueUsers',
      ),
      _MetricCardData(
        title: 'Всього помилок',
        value: _totalErrors.toString(),
        icon: Icons.error_outline,
        color: Colors.redAccent,
        footer: 'Операторів з помилками: $_errorUsers',
      ),
      _MetricCardData(
        title: 'Топ оператор',
        value: _topOperator,
        icon: Icons.workspace_premium,
        color: Colors.deepPurpleAccent,
        footer: _topOperatorCount > 0
            ? 'Сканувань: $_topOperatorCount'
            : 'Немає даних',
      ),
      _MetricCardData(
        title: 'Топ помилок',
        value: _topErrorOperator,
        icon: Icons.report_problem,
        color: Colors.orangeAccent,
        footer: _topErrorOperatorCount > 0
            ? 'Помилок: $_topErrorOperatorCount'
            : 'Немає даних',
      ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final maxWidth = constraints.maxWidth;
        final crossAxisCount = maxWidth > 1100
            ? 4
            : maxWidth > 820
            ? 3
            : maxWidth > 540
            ? 2
            : 1;
        final itemWidth =
            (maxWidth - 16 * (crossAxisCount - 1)) / crossAxisCount;
        return Wrap(
          spacing: 16,
          runSpacing: 16,
          children: metrics
              .map(
                (metric) => SizedBox(
                  width: math.max(itemWidth, 220),
                  child: _MetricCard(data: metric),
                ),
              )
              .toList(),
        );
      },
    );
  }

  Widget _buildLeaderboards() {
    return LayoutBuilder(
      builder: (context, constraints) {
        final maxWidth = constraints.maxWidth;
        final isWide = maxWidth > 900;
        final children = [
          Expanded(
            child: _LeaderboardCard(
              title: 'Активність операторів',
              data: _scanCounts,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: _LeaderboardCard(
              title: 'Оператори з помилками',
              data: _errorCounts,
              color: Colors.redAccent,
            ),
          ),
        ];
        if (isWide) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: children,
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _LeaderboardCard(title: 'Активність операторів', data: _scanCounts),
            const SizedBox(height: 16),
            _LeaderboardCard(
              title: 'Оператори з помилками',
              data: _errorCounts,
              color: Colors.redAccent,
            ),
          ],
        );
      },
    );
  }

  Widget _buildDailyTimeline() {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: const [
                Icon(Icons.timeline, color: Colors.blueAccent),
                SizedBox(width: 8),
                Text(
                  'Добова активність',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _dailyRows.isEmpty
                ? const Text('Немає даних для вибраного періоду')
                : ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: _dailyRows.length,
                    separatorBuilder: (_, __) => const Divider(),
                    itemBuilder: (context, index) {
                      final row = _dailyRows[index];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          row.dateLabel,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Сканувань: ${row.scans}'),
                            Text('Помилок: ${row.errors}'),
                            Text('Лідер дня: ${row.topScan}'),
                            Text('Помилки дня: ${row.topError}'),
                          ],
                        ),
                      );
                    },
                  ),
          ],
        ),
      ),
    );
  }
}

class _FilterButton extends StatelessWidget {
  const _FilterButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return FilledButton.tonalIcon(
      onPressed: onTap,
      icon: Icon(icon),
      label: Text(label, textAlign: TextAlign.left),
    );
  }
}

class _MetricCardData {
  const _MetricCardData({
    required this.title,
    required this.value,
    required this.icon,
    required this.color,
    this.footer,
  });

  final String title;
  final String value;
  final IconData icon;
  final Color color;
  final String? footer;
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.data});

  final _MetricCardData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  decoration: BoxDecoration(
                    color: data.color.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  padding: const EdgeInsets.all(12),
                  child: Icon(data.icon, color: data.color, size: 28),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    data.title,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            Text(
              data.value,
              style: theme.textTheme.displaySmall?.copyWith(
                color: data.color,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (data.footer != null) ...[
              const SizedBox(height: 8),
              Text(
                data.footer!,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: Colors.grey[700],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _LeaderboardCard extends StatelessWidget {
  const _LeaderboardCard({required this.title, required this.data, this.color});

  final String title;
  final Map<String, int> data;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final entries = data.entries.toList()
      ..sort((a, b) {
        final cmp = b.value.compareTo(a.value);
        if (cmp != 0) return cmp;
        return a.key.toLowerCase().compareTo(b.key.toLowerCase());
      });

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.leaderboard, color: color ?? Colors.blueAccent),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            entries.isEmpty
                ? const Text('Немає даних для відображення')
                : ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: entries.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final entry = entries[index];
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: CircleAvatar(
                          backgroundColor: (color ?? Colors.blueAccent)
                              .withOpacity(0.12),
                          child: Text(
                            '${index + 1}',
                            style: TextStyle(color: color ?? Colors.blueAccent),
                          ),
                        ),
                        title: Text(
                          entry.key,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        trailing: Text(
                          entry.value.toString(),
                          style: const TextStyle(fontSize: 16),
                        ),
                      );
                    },
                  ),
          ],
        ),
      ),
    );
  }
}

class _DailyView {
  const _DailyView({
    required this.dateLabel,
    required this.scans,
    required this.errors,
    required this.topScan,
    required this.topError,
  });

  final String dateLabel;
  final int scans;
  final int errors;
  final String topScan;
  final String topError;
}

class _DailyStats {
  _DailyStats(this.date);

  final DateTime date;
  int scans = 0;
  int errors = 0;
  final Map<String, int> scanUsers = {};
  final Map<String, int> errorUsers = {};
}

class _TopEntry {
  const _TopEntry({required this.name, required this.count});

  final String name;
  final int count;

  String get formatted => count > 0 ? '$name ($count)' : '—';
}
