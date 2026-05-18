# PyInstaller Portable Bundle — Design

**Date:** 2026-05-18
**Status:** Approved

## Problem

The app currently requires the target PC to have Python 3.12 installed, the project pip dependencies installed, and Tesseract OCR installed at a standard location. For an operator using it at an event on a different PC, this is too much setup. Users may also be confused about running `python main.py` from a terminal.

## Goals

- Distribute the app as a single zip the operator extracts and runs by double-clicking `PeakView.exe`.
- Zero install on the target PC: no Python, no pip, no Tesseract install. Everything bundled.
- Calibration data and output files travel with the bundle folder (portable mode), so the operator can copy the folder between PCs and keep their setup.
- Dev workflow on the source PC stays unchanged — `python main.py` from source must still work.

## Non-Goals

- Auto-update mechanism. New release = new zip sent manually.
- Code signing / SmartScreen suppression. Acceptable for now; revisit if SmartScreen becomes a blocker.
- Installer (.msi or Inno Setup). The folder + .exe is enough.
- macOS/Linux builds. Windows only.

## Architecture

Three pieces:

1. **Build inputs (in repo):** a PyInstaller spec file, a build script, and the vendored Tesseract binaries.
2. **Code changes (small):** a path helper so the running app finds the right data directory whether frozen or run from source.
3. **Distributed artifact:** the `dist/PeakView/` folder PyInstaller produces, zipped and shipped to operators.

### Build inputs

| File | Purpose |
|------|---------|
| `vendor/tesseract/` | Tesseract portable: `tesseract.exe`, supporting DLLs, and `tessdata/eng.traineddata` (~25–30 MB). Committed to git. Downloaded once by the developer from UB-Mannheim Tesseract releases; only English language data needed since the OCR pipeline never sets `-l`. |
| `PeakView.spec` | PyInstaller spec file. Entry point `main.py`, windowed (no console), hidden imports `mss`, `pytesseract`, `PIL.ImageTk`, `PIL._tkinter_finder`, datas `[('vendor/tesseract', 'tesseract')]` so the bundle ships `tesseract/` inside `_internal/`. Name `PeakView`. Uses PyInstaller 6.x default `contents_directory='_internal'` for a clean user-facing folder (only `PeakView.exe` + `_internal/` visible at the top level; user data files like `calibration.json` and `output/` sit alongside the .exe). |
| `build.bat` | Wrapper that runs `pyinstaller PeakView.spec --noconfirm --clean`, then copies `dist-README.txt` → `dist/PeakView/README.txt`. |
| `dist-README.txt` | Short operator-facing note shipped at the root of the bundle (committed in repo). Contents: "Extract to Documents or Desktop (not Program Files). Double-click PeakView.exe. If Windows SmartScreen blocks: More Info → Run anyway. If antivirus quarantines: whitelist PeakView.exe." |
| `.gitignore` | Add `build/`, `dist/`, `*.zip` so PyInstaller artifacts are not committed. |

### Code changes

A new tiny module `paths.py` centralizes the "where does the running app live" decision so it's not duplicated across `main.py`, `calibration.py`, and `capture.py`. It distinguishes two locations: the user-facing folder (where calibration / output live), and the bundled-resources folder (where PyInstaller put our tesseract files):

```python
"""Resolve runtime paths so the app works both as a PyInstaller bundle and from source."""
import sys
from pathlib import Path


def app_dir() -> Path:
    """User-facing app folder for calibration.json and output/.
    - Frozen (PyInstaller bundle): the folder containing PeakView.exe.
    - Source: the repo root (parent of this file).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _bundle_resources_dir() -> Path:
    """Where PyInstaller put our `datas` files at runtime.
    - --onedir frozen: _internal/ sibling of the .exe (set via sys._MEIPASS).
    - --onefile frozen: the temp-extraction dir (also sys._MEIPASS).
    - Source: repo root.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).parent


def bundled_tesseract() -> Path | None:
    """Return path to bundled tesseract.exe if present (frozen build), else None."""
    candidate = _bundle_resources_dir() / "tesseract" / "tesseract.exe"
    return candidate if candidate.exists() else None
```

Then three consumers update:

- **`capture.py:12-20`** — before the existing autodetect loop, check `bundled_tesseract()`. If it returns a path, set `pytesseract.pytesseract.tesseract_cmd` to it and skip the rest. Otherwise fall through to the existing system-install lookup. This means the dev PC keeps using the installed Tesseract while bundles use the vendored one.
- **`main.py:13`** — change `OUTPUT_DIR = Path(__file__).parent / "output"` to `OUTPUT_DIR = app_dir() / "output"`. The session_file logic at `main.py:28-29` already builds from `OUTPUT_DIR` so no other change needed.
- **`calibration.py:8`** — change `CALIBRATION_FILE = Path(__file__).parent / "calibration.json"` to `CALIBRATION_FILE = app_dir() / "calibration.json"`.

## Distributed Folder Layout

```
PeakView/
├── PeakView.exe              ← user double-clicks this
├── README.txt                ← short note: extract to Documents/Desktop, antivirus tip
├── _internal/                ← PyInstaller runtime (Python DLL, deps) + bundled tesseract/
│   └── tesseract/
│       ├── tesseract.exe
│       ├── (supporting DLLs)
│       └── tessdata/eng.traineddata
├── output/                   ← created on first run
└── calibration.json          ← created on first calibration
```

User-facing folder is clean: they see only `PeakView.exe`, `README.txt`, `_internal/`, plus their own data files as they accumulate.

User flow on the target PC:
1. Extract `PeakView.zip` to Desktop or Documents (anywhere writable — **not** Program Files, since calibration.json + output/ need write access).
2. Double-click `PeakView.exe`.
3. App launches. First time: prompts to calibrate (existing flow). After calibration, `calibration.json` is written next to the .exe. Output files accumulate in `output/`.

## Dev Workflow

On the dev PC, source-mode execution is unchanged:

```
python main.py
```

`app_dir()` returns the repo root (parent of `main.py`), `calibration.json` and `output/` stay where they are today, and `bundled_tesseract()` returns `None` so the existing system-Tesseract autodetect runs.

## Build & Distribute Workflow

Dev does this once per release:

```
pip install pyinstaller       # one-time
.\build.bat                   # produces dist/PeakView/
Compress-Archive dist/PeakView PeakView.zip
# send PeakView.zip to operator
```

Operator extracts and runs.

## Error Handling

- **Tesseract not found at runtime in bundle:** if `tesseract/tesseract.exe` is missing from the bundle (shouldn't happen, but defensive), capture falls through to the system-install autodetect and prints the same "not found" behavior the source path already has. The UI's status bar will surface OCR errors via the existing `_capture_loop` exception handler.
- **Write permission denied for `calibration.json` / `output/`:** Surfaces as a normal `OSError` through the existing `auto_save` and calibration save paths. We document "extract to a writable folder (Desktop / Documents)" in a short `README.txt` shipped at the root of the bundle.
- **Antivirus quarantine of `PeakView.exe`:** Possible PyInstaller false positive. Not handled in code — documented in `README.txt` as a known thing operators may need to whitelist.

## Testing

Per project preference [[feedback-no-inline-python]] — no inline python smoke tests. Verification is manual:

**On dev PC (source mode preserved):**
1. Run `python main.py`. Confirm app launches, calibration / live readings / debug window still work exactly as before. Confirms `app_dir()` returns repo root and existing Tesseract install is still used.

**On dev PC (built bundle):**
2. Run `.\build.bat`. Confirm `dist/PeakView/PeakView.exe` exists, sibling `tesseract/tesseract.exe` exists, `_internal/` exists.
3. Move `dist/PeakView/` to a fresh location (e.g., `C:\Users\<you>\Desktop\test-bundle\PeakView\`) so we don't accidentally read source-tree paths.
4. Double-click `PeakView.exe`. Confirm window appears, calibration prompts on first run, after calibration the `calibration.json` and `output/` appear inside the test-bundle's `PeakView/` folder (not in the repo).
5. Confirm OCR readings work (proves bundled Tesseract is being used).
6. Confirm Debug button opens debug window and shows variants.

**On target PC (clean):**
7. Copy `PeakView.zip` to a Windows PC with no Python or Tesseract installed.
8. Extract to Desktop. Double-click `PeakView.exe`. Confirm full flow works.

## Out of Scope (sengaja YAGNI)

- Auto-update / version check
- Code signing
- Bundling other Tesseract languages (`eng` only)
- Installer / Start Menu shortcut
- Cross-platform builds
