# myapp

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Lab: Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Cookbook: Useful Flutter samples](https://docs.flutter.dev/cookbook)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

## Updating the app icon

This project uses [`flutter_launcher_icons`](https://pub.dev/packages/flutter_launcher_icons)
to generate platform-specific launcher icons from a single source image.

1. Replace `assets/app_icon/app_icon.png` with your own square PNG (at least
   512×512 pixels). Keep the same file name so no configuration changes are
   required.
2. From the project root run:

   ```bash
   flutter pub get
   flutter pub run flutter_launcher_icons
   ```

The tool will update the Android and iOS launcher icon assets with your image.