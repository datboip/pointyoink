# Changelog

All notable changes to PointYoink. Versions before 1.0.0 are pre-release
builds; 1.0.0 will be the first public GitHub release.

## 0.4.0
- Export ZIP: a button that bundles the selected project(s) into a single .zip
  in your save folder (raw frames skipped), for archiving or moving to another
  machine or slicer.

## 0.3.2
- Fix a crash that stopped the project list from rendering whenever the scanner
  had projects on it (an undefined variable in the list renderer). This made the
  app look like it connected but found nothing.
- HiDPI: read the GNOME desktop scale (and a POINTYOINK_SCALE override) so the
  window is sized correctly on scaled displays, not just from reported DPI.

## 0.3.1
- Fix a tiny window on HiDPI laptops by auto-detecting the display scale, plus a
  manual UI scale setting under Settings.
- Window no longer opens larger than the screen.
- Smarter re-import: shows an "updated" badge and skips the already-imported
  prompt when a project has changed on the device.
- Themed confirmation dialogs and animated progress during format conversion.
- Debian package (.deb) for one-command install.

## 0.3.0
- Rounded UI built on CustomTkinter, with an app icon, splash screen, and cleaner spacing.
- Auto-connects when the scanner is in File Transfer mode.
- Optional STL / OBJ export of the meshes on import.
- Rename a project to a readable name. The original scanner ID is kept as the
  folder name and reference so nothing is lost.
- Remembers which projects you have already imported, across sessions, and
  asks before importing one again.
- Bigger About panel: supported devices, requirements, and an inline changelog.
- Preview and Files tabs, per-project size, and an import summary.
- Settings that persist, plus Cancel and Retry during import.
- Licensed MIT.

## 0.2.0
- Project list with thumbnails and the scanner's own scan renders.
- Models-only vs full import, imported badges, and a destination picker.

## 0.1.0
- First working build: mount the MIRACO over MTP, pick projects, and pull them.
- Models-only mode skips the raw depth frames for a large speed-up.
