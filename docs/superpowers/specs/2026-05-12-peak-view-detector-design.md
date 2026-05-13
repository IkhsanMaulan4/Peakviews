# Peak View Detector - Design Spec

**Date:** 2026-05-12
**Goal:** Desktop app yang mendeteksi peak viewer dari 4 live stream (BOG-YouTube, BOG-TikTok, MPL ID-YouTube, MPL ID-TikTok) lewat OCR screenshot, dengan segmentasi manual via tombol Next/Previous.

## Stack

- Python 3.10+
- `mss` - screenshot region (fast, cross-platform)
- `pytesseract` + Tesseract OCR engine (Windows install: UB Mannheim build)
- `Pillow` - image preprocessing
- `Tkinter` - GUI (built-in, no extra install)

## File Structure

```
peak-view/
  main.py              # GUI + main thread (always-on-top window)
  capture.py           # screenshot 4 regions + OCR + normalize K/M/jt
  calibration.py       # window: full-screen screenshot + click-drag 4 box
  segments.py          # daftar 31 segment hardcoded (BO3)
  storage.py           # peak in-memory dict + export ke .txt
  calibration.json     # tersimpan setelah kalibrasi: {label: [x,y,w,h]}
  output/peak_YYYY-MM-DD_HHMM.txt
  requirements.txt
  README.md
```

## Components

### 1. `segments.py`
Daftar 31 segment terurut (list of string):
- Waiting Screen, TVC, Opening Caster, Trivia
- Match 1 - Game #1 Pre Game / In Game / Post Game
- Match 1 - Game #2 Pre/In/Post Game
- Match 1 - Game #3 Pre/In/Post Game
- Match 2 - Game #1 Pre/In/Post Game (9 segmen)
- Match 3 - Game #1 Pre/In/Post Game (9 segmen)

### 2. `calibration.py`
- Saat dijalankan: ambil fullscreen screenshot pakai `mss`, tampilkan di window Tkinter Canvas
- User drag 4 kotak berurutan, label otomatis: BOG-YT, BOG-TT, MPL-YT, MPL-TT
- Save ke `calibration.json` format `{"BOG-YT":[x,y,w,h], ...}`
- Tombol "Reset" untuk ulangi drag

### 3. `capture.py`
- `capture_all(regions)` -> `dict[label, int|None]`
  - Untuk tiap region: `mss.grab(region)` -> PIL Image -> grayscale -> threshold (Otsu) -> `pytesseract.image_to_string` dengan `--psm 7 -c tessedit_char_whitelist=0123456789KMkmjt.,`
  - Normalisasi: `"1.2K"` -> 1200, `"1,234"` -> 1234, `"1.5M"` -> 1500000, `"2 jt"` -> 2000000
  - Return `None` kalau parse gagal (jangan rusak peak)

### 4. `storage.py`
- In-memory `dict[segment_name, dict[label, int]]` (peak per segment per sumber)
- `update_peak(segment, label, value)` - update kalau value > current peak
- `export_txt(path)` - tulis TSV (tab-separated) sesuai urutan segment, format:
  ```
  Segmen	BOG-YT	BOG-TT	MPL-YT	MPL-TT
  Waiting Screen	1234	567	890	123
  TVC	...
  ```
  (Header optional, default include. Bisa paste langsung ke Google Sheet/Excel.)

### 5. `main.py`
- Window kecil always-on-top (`-topmost`), pojok kanan atas, ~350x200px
- Cek `calibration.json`, kalau tidak ada -> jalankan calibration dulu
- Background thread tiap 1 detik: `capture_all` -> update peak segment aktif
- Display:
  - Segment aktif (besar): `[5/31] Waiting Screen`
  - 4 baris live peak: `BOG-YT: 1.2K  BOG-TT: 567  ...`
- Tombol: `[< Prev]` `[Next >]` `[Recalibrate]` `[Export TXT]`
- Next/Prev: pindah index segment, peak tidak di-reset (tetap simpan max kalau visit lagi)

## Error Handling

- OCR gagal -> log warn, skip frame (jangan update peak)
- Tesseract tidak terinstall -> error message di startup dengan link download
- Region calibration salah / kosong -> tampil `--` di GUI, peak tidak update
- File output write gagal -> fallback ke clipboard

## Testing Strategy

- Unit test `capture.normalize_number()` untuk berbagai format input
- Unit test `storage.update_peak()` (peak hanya naik, tidak turun)
- Manual test: buka 4 tab YT/TikTok live, kalibrasi, observe 5 menit, verify peak masuk akal & export TXT bisa di-paste

## Out of Scope

- Auto-detect viewer count region (template matching)
- Multi-monitor calibration
- Editable segment list via GUI
- Realtime grafik / history
- API integration (YouTube Data API, dst)
