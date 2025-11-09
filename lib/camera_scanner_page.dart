import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

class CameraScannerPage extends StatefulWidget {
  const CameraScannerPage({super.key, required this.targetLabel});

  final String targetLabel;

  @override
  State<CameraScannerPage> createState() => _CameraScannerPageState();
}

class _CameraScannerPageState extends State<CameraScannerPage> {
  final MobileScannerController _controller = MobileScannerController();
  bool _isProcessing = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_isProcessing) return;

    for (final barcode in capture.barcodes) {
      final value = barcode.rawValue;
      if (value != null && value.trim().isNotEmpty) {
        _isProcessing = true;
        if (mounted) {
          Navigator.of(context).pop(value.trim());
        }
        break;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: Text('Сканування ${widget.targetLabel}')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                const Icon(Icons.info_outline, color: Colors.blueAccent),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Наведіть камеру на штрихкод ${widget.targetLabel}. Сканування відбудеться автоматично.',
                    style: theme.textTheme.bodyMedium,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Stack(
              children: [
                MobileScanner(controller: _controller, onDetect: _onDetect),
                Align(
                  alignment: Alignment.topCenter,
                  child: Container(
                    margin: const EdgeInsets.only(top: 24),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 8,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.45),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      'Скануємо ${widget.targetLabel}',
                      style: theme.textTheme.titleMedium?.copyWith(
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  IconButton(
                    icon: const Icon(Icons.flash_on_outlined),
                    tooltip: 'Увімкнути/вимкнути спалах',
                    onPressed: () => _controller.toggleTorch(),
                  ),
                  IconButton(
                    icon: const Icon(Icons.cameraswitch_outlined),
                    tooltip: 'Перемкнути камеру',
                    onPressed: () => _controller.switchCamera(),
                  ),
                  FilledButton.icon(
                    onPressed: () => Navigator.of(context).maybePop(),
                    icon: const Icon(Icons.close),
                    label: const Text('Закрити'),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
