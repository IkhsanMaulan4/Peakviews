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
