# Peak View Detector

Deteksi peak viewer dari 4 live stream (BOG-YT, BOG-TT, MPL ID-YT, MPL ID-TT) lewat OCR screenshot, dengan segmentasi manual via tombol Next/Prev.

## Setup

### 1. Install Tesseract OCR (Windows)
Download installer: https://github.com/UB-Mannheim/tesseract/wiki
Default install path biasanya `C:\Program Files\Tesseract-OCR\tesseract.exe`. Pastikan path ini masuk ke PATH environment variable, atau set manual di `capture.py`:

```python
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

### 2. Install Python dependencies
```powershell
pip install -r requirements.txt
```

### 3. Jalankan
```powershell
python main.py
```

## Cara Pakai

1. **Setup tampilan layar**: buka 4 tab live stream, tile/split jadi 2x2 grid agar angka viewer keempatnya kelihatan.
2. **Jalankan `python main.py`** - kalau pertama kali, window fullscreen muncul untuk kalibrasi.
3. **Kalibrasi**: drag kotak satu per satu di angka viewer:
   - Kotak 1: BOG-YouTube
   - Kotak 2: BOG-Tiktok
   - Kotak 3: MPL ID-YouTube
   - Kotak 4: MPL ID-Tiktok

   Tekan **S** untuk skip source (kalau cuma butuh 1-3 source aja), **R** untuk reset semua, **Enter** untuk simpan, **Esc** untuk batal.

   Source yang di-skip tidak akan di-OCR & tidak muncul di GUI, tapi tetap ada kolomnya di file export (isi 0) supaya match spreadsheet utama.
4. **Window kecil** muncul di pojok (always-on-top):
   - Segment aktif di atas (mulai dari "Waiting Screen")
   - Live values 4 sumber update tiap 1 detik
   - Peak yang tercatat ditampilkan
5. **Tekan `Next >`** saat segment berganti. Peak segment sebelumnya tersimpan.
   - `< Prev` untuk koreksi kalau salah pencet.
   - `Reset Current` untuk clear peak segment yang lagi aktif (kalau ke-pollute karena salah pencet Next).
6. **Auto-save**: file `output/peak_YYYY-MM-DD_HHMM.txt` otomatis di-update setiap kali pencet Next/Prev/Reset, plus tiap ~10 detik selama segment berjalan. Aman dari crash.
7. **Akhir event** tinggal buka file auto-save itu, atau pencet `Export TXT (save as)` untuk simpan snapshot dengan timestamp baru.
   - Format tab-separated, langsung paste ke Google Sheet/Excel.

### Koreksi salah pencet Next

Misal pas di "Waiting Screen" tidak sengaja pencet Next:
1. Pencet `< Prev` untuk balik ke Waiting Screen
2. Nanti pas event sampai TVC beneran, navigate ke TVC, **pencet `Reset Current`** untuk clear data yang tadi nyasar
3. Lanjut normal

## File Output

```
Segmen          BOG-YT  BOG-TT  MPL-YT  MPL-TT  TOTAL
Waiting Screen  1234    567     890     123     2814
TVC             2100    890     ...
```

## Catatan

- Kalau angka viewer salah ke-OCR (misal "1.2K" malah jadi 12), recalibrate dan pastikan kotak benar-benar pas dengan angka (jangan ada ikon mata atau teks lain di dalam kotak).
- Format yang didukung: angka biasa (`1234`, `1,234`), suffix K/M (`1.2K`, `1.5M`), suffix `jt` (`2 jt`).
- Segment list (31 segment) untuk format BO3. Kalau perlu BO5/BO7, edit `segments.py` range loop.
