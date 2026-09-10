# Changelog

All notable changes to PointYoink. Versions before 1.0.0 are pre-release
builds; 1.0.0 will be the first public GitHub release.

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
