# PyInstaller Portable Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the app as a zero-install Windows bundle (`PeakView.exe` + sibling folders) so an operator on another PC can extract a zip, double-click, and run — no Python, pip, or Tesseract install required.

**Architecture:** PyInstaller `--onedir` build with vendored Tesseract portable. A new `paths.py` helper resolves data locations differently when frozen (next to the .exe, portable) vs source (next to the script). Bundled resources (tesseract) are looked up via `sys._MEIPASS`. Source-mode execution stays unchanged.

**Tech Stack:** PyInstaller 6.x, Tesseract OCR portable (UB-Mannheim Windows build), Python 3.12

**Testing convention:** Per project preference [[feedback-no-inline-python]], no inline python smoke tests. Verification steps ask the user to run `python main.py` (source mode) or `PeakView.exe` (frozen mode) from their own terminal/Explorer. Subagents executing this plan **must skip** running python/pyinstaller themselves and instead pause for user confirmation.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `paths.py` | Create | Centralizes `app_dir()`, `_bundle_resources_dir()`, `bundled_tesseract()` |
| `capture.py` | Modify | Try `bundled_tesseract()` before existing system-install lookup |
| `main.py` | Modify | `OUTPUT_DIR = app_dir() / "output"` |
| `calibration.py` | Modify | `CALIBRATION_FILE = app_dir() / "calibration.json"` |
| `vendor/tesseract/` | Create (binaries) | Portable Tesseract: tesseract.exe, DLLs, tessdata/eng.traineddata. Committed to git. |
| `PeakView.spec` | Create | PyInstaller spec: onedir, windowed, bundles vendor/tesseract |
| `build.bat` | Create | One-shot build wrapper |
| `dist-README.txt` | Create | Operator-facing note that ships at bundle root |
| `.gitignore` | Create | Ignore `build/`, `dist/`, `*.zip` |

---

### Task 1: Create `paths.py`

A small module shared across `main.py`, `calibration.py`, and `capture.py`. No existing code depends on it yet.

**Files:**
- Create: `paths.py`

- [ ] **Step 1: Create the file with this content**

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

- [ ] **Step 2: Commit**

```bash
git add paths.py
git commit -m "feat(paths): add app_dir + bundled_tesseract helpers for frozen-vs-source mode"
```

No user verification step — file isn't imported yet. Task 2 will hook it up and verify together.

---

### Task 2: Wire `paths.py` into capture.py, main.py, calibration.py

Three small edits in three files. After this task, source-mode execution must still work identically (calibration.json and output/ continue to live in the repo root because `app_dir()` returns the repo root when not frozen).

**Files:**
- Modify: `capture.py:11-20` (tesseract autodetect)
- Modify: `main.py:13` (OUTPUT_DIR)
- Modify: `calibration.py:8` (CALIBRATION_FILE)

- [ ] **Step 1: Update `capture.py` tesseract autodetect**

The current code (lines 11-20) is:

```python
# Auto-detect Tesseract path on Windows if not in PATH
if not shutil.which("tesseract"):
    for path in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ):
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break
```

Replace it with:

```python
# Auto-detect Tesseract path: prefer bundled (frozen build), else search system installs
_bundled = bundled_tesseract()
if _bundled is not None:
    pytesseract.pytesseract.tesseract_cmd = str(_bundled)
elif not shutil.which("tesseract"):
    for path in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ):
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break
```

Then add `from paths import bundled_tesseract` to the top imports block of `capture.py` (right after `from PIL import Image, ImageFilter, ImageOps`). Keep all the existing imports intact.

- [ ] **Step 2: Update `main.py` OUTPUT_DIR**

Current line 13:

```python
OUTPUT_DIR = Path(__file__).parent / "output"
```

Replace with:

```python
from paths import app_dir
OUTPUT_DIR = app_dir() / "output"
```

(Add the `from paths import app_dir` line right above the `OUTPUT_DIR = ...` line. Don't touch the existing imports block at the top — keep the diff minimal.)

- [ ] **Step 3: Update `calibration.py` CALIBRATION_FILE**

Current line 8:

```python
CALIBRATION_FILE = Path(__file__).parent / "calibration.json"
```

Replace with:

```python
from paths import app_dir
CALIBRATION_FILE = app_dir() / "calibration.json"
```

(Same convention: add the import directly above the constant. Keep `Path` import — it's still used elsewhere in the file via `Path(__file__).parent` references in other paths, if any; if not, no harm leaving it.)

- [ ] **Step 4: Ask user to verify source mode still works**

Tell user: "Three small edits done. Please run `python main.py` from your terminal. Verify:
1. App launches as before, status bar shows 'Ready'.
2. Live OCR readings appear in the labels (proves Tesseract is still found via the system-install autodetect path).
3. If you make a small recalibration, `calibration.json` is updated in the repo root (not somewhere weird).
4. After ~10 capture cycles, a `peak_*.txt` file appears in `output/` in the repo root.

Confirms `app_dir()` correctly returns the repo root in source mode."

Wait for user confirmation before committing.

- [ ] **Step 5: Commit**

```bash
git add capture.py main.py calibration.py
git commit -m "feat: route data paths through paths.app_dir for portable bundle support"
```

---

### Task 3: Vendor Tesseract binaries

Manual developer task — download Tesseract portable on the dev PC, copy the needed files into `vendor/tesseract/`, commit the binaries.

**Files:**
- Create: `vendor/tesseract/tesseract.exe`
- Create: `vendor/tesseract/*.dll` (multiple)
- Create: `vendor/tesseract/tessdata/eng.traineddata`

- [ ] **Step 1: Download Tesseract Windows installer**

If an executing agent is doing this task: pause and ask the user to perform this step on their dev PC, because it requires opening a browser and running an installer.

Tell user: "Go to https://github.com/UB-Mannheim/tesseract/wiki and download the latest 64-bit Windows installer (file like `tesseract-ocr-w64-setup-5.x.x.exe`). Run it, install to the default `C:\Program Files\Tesseract-OCR\` location. **When the installer asks which languages to add: only check English** (uncheck everything else) to keep our bundle small. Confirm when done."

Wait for user confirmation.

- [ ] **Step 2: Create `vendor/tesseract/` directory structure**

Run from repo root:

```bash
mkdir vendor
mkdir vendor\tesseract
mkdir vendor\tesseract\tessdata
```

- [ ] **Step 3: Copy required files from the install to the vendor folder**

Tell user: "From `C:\Program Files\Tesseract-OCR\`, copy these into `vendor/tesseract/` of the repo:

- `tesseract.exe`
- **All `.dll` files** in that folder (there will be 10-15 of them — `leptonica-*.dll`, `libgcc_*.dll`, `libgomp-*.dll`, `libjpeg-*.dll`, `libpng*.dll`, `libstdc++-*.dll`, `libtiff-*.dll`, `libwebp*.dll`, `zlib*.dll`, etc.). Easy approach: select all `.dll` files in Explorer with Ctrl+A then deselect non-DLL items, or just copy everything and delete non-DLL non-needed items.
- `tessdata/eng.traineddata` → copy into `vendor/tesseract/tessdata/eng.traineddata`

Do NOT copy: `doc/`, `java/`, `tessdata_*/`, other `.traineddata` files, ScrollView, training tools.

Confirm when done."

Wait for user confirmation.

- [ ] **Step 4: Verify the vendor folder structure**

Run from repo root:

```bash
dir vendor\tesseract\tesseract.exe
dir vendor\tesseract\*.dll
dir vendor\tesseract\tessdata\eng.traineddata
```

Expected: `tesseract.exe` exists, several DLL files listed, `eng.traineddata` exists (~15 MB).

If any are missing, ask user to re-do Step 3.

- [ ] **Step 5: Commit the vendored binaries**

These are binary files; just commit them directly (no git LFS needed at ~30 MB total).

```bash
git add vendor/
git commit -m "build: vendor Tesseract OCR portable (English-only) for bundle"
```

---

### Task 4: Add PyInstaller spec, build script, distribution README, gitignore

Static config files. No code logic.

**Files:**
- Create: `PeakView.spec`
- Create: `build.bat`
- Create: `dist-README.txt`
- Create: `.gitignore` (does not currently exist)

- [ ] **Step 1: Create `PeakView.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('vendor/tesseract', 'tesseract')],
    hiddenimports=['PIL._tkinter_finder'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PeakView',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PeakView',
)
```

- [ ] **Step 2: Create `build.bat`**

```bat
@echo off
setlocal

echo === PeakView build ===
pyinstaller PeakView.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo BUILD FAILED at pyinstaller step.
    exit /b 1
)

copy /Y dist-README.txt dist\PeakView\README.txt >nul
if errorlevel 1 (
    echo.
    echo README copy failed.
    exit /b 1
)

echo.
echo === Build complete ===
echo Output: dist\PeakView\
echo Zip for distribution:
echo   Compress-Archive dist\PeakView PeakView.zip
endlocal
```

- [ ] **Step 3: Create `dist-README.txt`**

```text
PeakView — viewer counter peak tracker
=======================================

QUICK START
-----------
1. Extract this folder to Documents or Desktop.
   DO NOT extract to "Program Files" or any read-only location —
   the app needs to write calibration.json and the output/ folder
   next to PeakView.exe.

2. Double-click PeakView.exe.

3. First run: a calibration overlay will appear. Drag a box over
   each viewer-counter number on your screen. Press S to skip a
   source you don't have. Press Enter to save.

4. Click Next/Prev to switch segments as the match progresses.
   Peak values for each segment are auto-saved to output/peak_*.txt.

TROUBLESHOOTING
---------------
- "Windows protected your PC" (SmartScreen): click "More info" →
  "Run anyway". The app is unsigned (no Microsoft certificate),
  not malicious.

- Antivirus quarantines PeakView.exe: this is a PyInstaller false
  positive. Whitelist PeakView.exe in your antivirus settings.

- App launches but Tesseract errors appear: make sure the
  "tesseract" folder inside _internal/ is present. If missing,
  re-extract the zip.
```

- [ ] **Step 4: Create `.gitignore`**

```
build/
dist/
*.zip
__pycache__/
*.pyc
```

(The `__pycache__/` and `*.pyc` entries are belt-and-suspenders — the project may already ignore them implicitly, but make it explicit.)

- [ ] **Step 5: Commit**

```bash
git add PeakView.spec build.bat dist-README.txt .gitignore
git commit -m "build: add PyInstaller spec, build.bat, dist README, and .gitignore"
```

---

### Task 5: Build the bundle and verify end-to-end

The hardware test. User runs the build and validates the produced bundle on their dev PC. After this task succeeds, the bundle is ready to zip + ship.

**Files:** No code changes. Manual verification only.

- [ ] **Step 1: Install PyInstaller in the dev environment (one-time)**

Tell user: "Run `pip install pyinstaller` in the same Python environment you use for `python main.py`. Confirm it installs without error and `pyinstaller --version` prints a version (should be 6.x)."

Wait for confirmation.

- [ ] **Step 2: Run the build**

Tell user: "From the repo root, run `.\build.bat`. Watch the output for any 'BUILD FAILED' message. On success it should print '=== Build complete ===' and tell you the output is at `dist\PeakView\`. This takes 30-90 seconds. Tell me when done."

Wait for confirmation.

- [ ] **Step 3: Verify the produced bundle structure**

Run from repo root:

```bash
dir dist\PeakView\PeakView.exe
dir dist\PeakView\README.txt
dir dist\PeakView\_internal\tesseract\tesseract.exe
dir dist\PeakView\_internal\tesseract\tessdata\eng.traineddata
```

Expected: all four exist.

If any are missing, troubleshoot:
- `PeakView.exe` missing → check pyinstaller output above for errors.
- `_internal/tesseract/...` missing → check `PeakView.spec` line `datas=[('vendor/tesseract', 'tesseract')]` and the `vendor/tesseract/` folder contents.
- `README.txt` missing → check `build.bat` step that copies `dist-README.txt`.

- [ ] **Step 4: Test the bundle in isolation (proves portable mode works)**

Tell user: "To make sure the .exe isn't accidentally reading source-tree files, copy the entire `dist\PeakView\` folder to a fresh location, e.g.:

```
xcopy /E /I dist\PeakView C:\Users\%USERNAME%\Desktop\peakview-test\
```

Then:
1. Open `C:\Users\<you>\Desktop\peakview-test\` in Explorer.
2. Double-click `PeakView.exe`.
3. The app should launch. It will prompt for calibration since the test folder has no `calibration.json` yet.
4. Do a quick calibration (drag one box, press S to skip the rest, press Enter).
5. Confirm `calibration.json` appears in `C:\Users\<you>\Desktop\peakview-test\` (NOT in the repo).
6. Wait ~10 seconds. Confirm `output/peak_*.txt` appears in the same test folder.
7. Click Debug — confirm the debug window opens and shows OCR variants (proves bundled Tesseract is working).
8. Close the app.

Tell me which steps passed and if any errored."

Wait for user confirmation.

- [ ] **Step 5: Optional — test on a clean target PC**

Tell user: "If you have a target PC handy (no Python, no Tesseract installed), zip the bundle and try it there:

```powershell
Compress-Archive dist\PeakView PeakView.zip
```

Copy `PeakView.zip` to the target PC, extract it, double-click `PeakView.exe`, do a quick calibration smoke test. If it works there, the bundle is verified end-to-end.

If you don't have a clean PC available now, that's fine — the dev-PC isolation test in Step 4 is the meaningful check; cross-PC test can be done later when you actually deploy."

- [ ] **Step 6: No commit needed**

This task is verification only. Nothing to commit.

---

## Distribution Workflow (for future releases)

Once Task 5 passes, every subsequent release is just:

```
.\build.bat
Compress-Archive dist\PeakView PeakView.zip
# Send PeakView.zip to operator
```

Operator extracts and double-clicks. Done.

## Known Limitations (out of scope)

- Bundle is unsigned → SmartScreen warning on first run (documented in `dist-README.txt`).
- Antivirus false positives possible (PyInstaller signature).
- No auto-update — new release = new zip sent manually.
- English Tesseract only — adding other languages = copy more `.traineddata` files into `vendor/tesseract/tessdata/` and rebuild.
- If user extracts to `Program Files`, write to `calibration.json` / `output/` will fail. Documented in `dist-README.txt`.
