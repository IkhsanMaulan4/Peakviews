# Excel Report Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tambah tombol "Report" di peak-view yang sekali klik menghasilkan satu file Excel (`.xlsx`) berisi laporan peak viewer (ringkasan + detail per-segmen + chart) dari data peak yang sedang aktif.

**Architecture:** Modul baru `report.py` berisi fungsi pure `generate_report(peaks, sources, segments, out_path)` yang tidak tahu-menahu soal `PeakStore`/Tkinter — menerima dict/list biasa dan menulis `.xlsx` pakai openpyxl. `main.py` memanggilnya dari handler tombol dengan `self.store.peaks`, `SOURCES`, `SEGMENTS`. Workbook punya 2 tab: "Ringkasan" (highlight + perbandingan channel + bar chart) dan "Detail" (tabel per-segmen + bar chart). Segmen yang semua channel-nya 0 di-skip.

**Tech Stack:** Python 3, openpyxl (pure-Python xlsx + chart, tidak butuh Excel terinstall), Tkinter (UI existing), PyInstaller (bundling).

> **Catatan lingkungan:** python tidak ada di PATH untuk shell tools. Verifikasi dilakukan dengan menjalankan harness/script lewat venv project (`peakview-env\Scripts\python.exe ...`) atau menjalankan app, BUKAN pytest. Tidak ada framework test di project ini dan plan ini sengaja tidak menambahnya (YAGNI).

---

## File Structure

- **Create `report.py`** — generator Excel. Berisi: konstanta style, `NoDataError`, helper (`_id`, `_nonempty_segments`, `_segment_total`), builder per-tab (`_build_summary`, `_build_detail`), dan entrypoint `generate_report`. Satu tanggung jawab: data peak → file `.xlsx`.
- **Create `verify_report.py`** (repo root, dev-only, TIDAK di-commit) — harness kecil: panggil `generate_report` dengan data dummy → tulis `sample_report.xlsx` untuk di-eyeball tanpa perlu kalibrasi/stream.
- **Modify `requirements.txt`** — tambah `openpyxl`.
- **Modify `main.py`** — import `generate_report`+`NoDataError`, tambah tombol "Report" + handler `generate_report` (method).
- **Modify `PeakView.spec`** — pastikan openpyxl ter-bundle.
- **Modify `.gitignore`** — abaikan `verify_report.py` dan `sample_report.xlsx`.

---

## Task 1: Tambah dependency openpyxl

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Tambahkan openpyxl ke requirements.txt**

Tambahkan baris berikut di akhir `requirements.txt`:

```
openpyxl>=3.1
```

Hasil akhir file:

```
mss>=9.0.1
rapidocr-onnxruntime>=1.2.3
Pillow>=10.0.0
numpy>=1.26
pyinstaller>=6.0
openpyxl>=3.1
```

- [ ] **Step 2: Install ke venv project**

Minta user menjalankan (lewat prompt dengan prefix `!`, atau terminal mereka):

```
peakview-env\Scripts\python.exe -m pip install "openpyxl>=3.1"
```

Expected: output diakhiri `Successfully installed openpyxl-... et-xmlfile-...` (atau "Requirement already satisfied").

- [ ] **Step 3: Verifikasi import**

Minta user menjalankan:

```
peakview-env\Scripts\python.exe -c "import openpyxl; print(openpyxl.__version__)"
```

Expected: mencetak nomor versi (mis. `3.1.5`), tanpa traceback.

- [ ] **Step 4: Commit**

```
git add requirements.txt
git commit -m "build(report): add openpyxl dependency

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Buat report.py (helper + entrypoint, belum ada isi tab)

**Files:**
- Create: `report.py`

- [ ] **Step 1: Tulis kerangka report.py dengan konstanta, error, helper, dan entrypoint**

Buat file `report.py`:

```python
"""Generate an Excel (.xlsx) peak-viewer report from PeakStore data.

Pure module: menerima dict/list biasa, tidak tahu-menahu soal PeakStore maupun
Tkinter, jadi bisa diuji standalone. Pakai openpyxl (tidak butuh Excel terinstall).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# --- Styling constants ---
HEADER_FILL = PatternFill("solid", fgColor="DDDDDD")
HIGHLIGHT_FILL = PatternFill("solid", fgColor="FFF2CC")
HEADER_FONT = Font(bold=True)
TITLE_FONT = Font(bold=True, size=14)
_THIN = Side(style="thin", color="999999")
BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
NUM_FMT = "#,##0"  # Excel merender pemisah ribuan sesuai locale sistem.


class NoDataError(Exception):
    """Diraise saat tidak ada data peak > 0 yang bisa dilaporkan."""


def _id(n: int) -> str:
    """Format int dengan pemisah ribuan gaya Indonesia (mis. 1234 -> '1.234')."""
    return f"{n:,}".replace(",", ".")


def _nonempty_segments(peaks: dict, sources: list, segments: list) -> list:
    """Segmen (urut sesuai `segments`) yang minimal satu channel-nya peak > 0."""
    result = []
    for seg in segments:
        row = peaks.get(seg, {})
        if any((row.get(src) or 0) > 0 for src in sources):
            result.append(seg)
    return result


def _segment_total(peaks: dict, sources: list, seg: str) -> int:
    """Jumlah peak semua channel untuk satu segmen."""
    row = peaks.get(seg, {})
    return sum((row.get(src) or 0) for src in sources)


def generate_report(peaks: dict, sources: list, segments: list, out_path) -> Path:
    """Tulis laporan Excel ke out_path. Raise NoDataError bila semua segmen 0."""
    out_path = Path(out_path)
    active_segments = _nonempty_segments(peaks, sources, segments)
    if not active_segments:
        raise NoDataError("Belum ada data peak buat di-report.")

    wb = Workbook()
    ws_sum = wb.active
    ws_sum.title = "Ringkasan"
    ws_detail = wb.create_sheet("Detail")

    _build_summary(ws_sum, peaks, sources, active_segments)
    _build_detail(ws_detail, peaks, sources, active_segments)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def _build_summary(ws, peaks, sources, active_segments):
    raise NotImplementedError  # diisi di Task 3


def _build_detail(ws, peaks, sources, active_segments):
    raise NotImplementedError  # diisi di Task 4
```

- [ ] **Step 2: Verifikasi file bisa di-import**

Minta user menjalankan dari repo root:

```
peakview-env\Scripts\python.exe -c "import report; print('ok', report.NoDataError)"
```

Expected: `ok <class 'report.NoDataError'>`, tanpa traceback (membuktikan import openpyxl + sintaks modul benar).

- [ ] **Step 3: Commit**

```
git add report.py
git commit -m "feat(report): scaffold report module with helpers and entrypoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Isi tab "Ringkasan" (highlight + perbandingan channel + chart)

**Files:**
- Modify: `report.py`

- [ ] **Step 1: Ganti stub `_build_summary` dengan implementasi**

Ganti fungsi `_build_summary` di `report.py` (yang masih `raise NotImplementedError`) menjadi:

```python
def _build_summary(ws, peaks, sources, active_segments):
    # --- Judul + metadata ---
    ws["A1"] = "Laporan Peak Viewer"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Digenerate: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A3"] = f"Jumlah segmen ber-data: {len(active_segments)}"

    # --- Hitung angka kunci ---
    best_val, best_seg, best_src = 0, "-", "-"
    for seg in active_segments:
        row = peaks.get(seg, {})
        for src in sources:
            v = row.get(src) or 0
            if v > best_val:
                best_val, best_seg, best_src = v, seg, src

    seg_totals = {seg: _segment_total(peaks, sources, seg) for seg in active_segments}
    busiest_seg = max(seg_totals, key=seg_totals.get)

    channel_totals = {
        src: sum((peaks.get(seg, {}).get(src) or 0) for seg in active_segments)
        for src in sources
    }
    busiest_channel = max(channel_totals, key=channel_totals.get)
    n_seg = len(active_segments)
    avg_total = round(sum(seg_totals.values()) / n_seg)

    # --- Kotak highlight ---
    highlights = [
        ("Peak tertinggi keseluruhan", f"{_id(best_val)} (segmen {best_seg}, {best_src})"),
        ("Segmen paling rame", f"{busiest_seg} ({_id(seg_totals[busiest_seg])})"),
        ("Channel paling rame", f"{busiest_channel} ({_id(channel_totals[busiest_channel])})"),
        ("Rata-rata TOTAL peak antar segmen", _id(avg_total)),
    ]
    hl_title_row = 5
    ws.cell(row=hl_title_row, column=1, value="HIGHLIGHT").font = HEADER_FONT
    for i, (label, val) in enumerate(highlights, start=hl_title_row + 1):
        lc = ws.cell(row=i, column=1, value=label)
        lc.font = HEADER_FONT
        lc.fill = HIGHLIGHT_FILL
        lc.border = BORDER
        vc = ws.cell(row=i, column=2, value=val)
        vc.fill = HIGHLIGHT_FILL
        vc.border = BORDER

    # --- Tabel perbandingan channel ---
    tbl_title_row = hl_title_row + len(highlights) + 3
    ws.cell(row=tbl_title_row, column=1, value="Perbandingan Channel").font = HEADER_FONT
    hdr = tbl_title_row + 1
    for col, name in enumerate(["Channel", "Total Peak", "Rata-rata"], start=1):
        c = ws.cell(row=hdr, column=col, value=name)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.border = BORDER
        c.alignment = Alignment(horizontal="center")
    for i, src in enumerate(sources, start=1):
        r = hdr + i
        ws.cell(row=r, column=1, value=src).border = BORDER
        tc = ws.cell(row=r, column=2, value=channel_totals[src])
        tc.number_format = NUM_FMT
        tc.border = BORDER
        ac = ws.cell(row=r, column=3, value=round(channel_totals[src] / n_seg))
        ac.number_format = NUM_FMT
        ac.border = BORDER
    last = hdr + len(sources)

    # --- Lebar kolom ---
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 14

    # --- Bar chart: total peak per channel ---
    chart = BarChart()
    chart.type = "col"
    chart.title = "Total Peak per Channel"
    chart.y_axis.title = "Total Peak"
    chart.x_axis.title = "Channel"
    data = Reference(ws, min_col=2, min_row=hdr, max_row=last)
    cats = Reference(ws, min_col=1, min_row=hdr + 1, max_row=last)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.legend = None
    chart.height = 8
    chart.width = 14
    ws.add_chart(chart, "E5")
```

- [ ] **Step 2: (sementara) Buat harness verifikasi `verify_report.py`**

Buat file `verify_report.py` di repo root (dev-only, akan di-gitignore di Task 7):

```python
"""Dev-only: generate sample_report.xlsx dengan data dummy untuk eyeball layout.
Jalankan dari repo root:  peakview-env\\Scripts\\python.exe verify_report.py
Lalu buka sample_report.xlsx di Excel.
"""
from report import generate_report

SOURCES = ["BOG-YT", "MPL-YT", "MDL-YT"]
SEGMENTS = [
    "Waiting Screen", "TVC",
    "Match 1 - Game #1 In Game", "Match 1 - Game #2 In Game",
    "Match 2 - Game #1 In Game",
]
PEAKS = {
    "Waiting Screen": {"BOG-YT": 1200, "MPL-YT": 800, "MDL-YT": 0},
    "TVC": {"BOG-YT": 0, "MPL-YT": 0, "MDL-YT": 0},  # semua 0 -> harus di-skip
    "Match 1 - Game #1 In Game": {"BOG-YT": 15400, "MPL-YT": 9800, "MDL-YT": 4300},
    "Match 1 - Game #2 In Game": {"BOG-YT": 18700, "MPL-YT": 11200, "MDL-YT": 5100},
    "Match 2 - Game #1 In Game": {"BOG-YT": 22300, "MPL-YT": 13900, "MDL-YT": 6800},
}

path = generate_report(PEAKS, SOURCES, SEGMENTS, "sample_report.xlsx")
print(f"Wrote: {path}")
```

- [ ] **Step 3: Jalankan harness (akan error di tab Detail — itu wajar)**

Minta user menjalankan:

```
peakview-env\Scripts\python.exe verify_report.py
```

Expected: `NotImplementedError` dari `_build_detail` (tab Ringkasan sudah jalan, Detail belum diisi). Ini konfirmasi `_build_summary` tidak crash. **Jangan commit dulu** sampai Task 4 selesai.

---

## Task 4: Isi tab "Detail" (tabel per-segmen + chart)

**Files:**
- Modify: `report.py`

- [ ] **Step 1: Ganti stub `_build_detail` dengan implementasi**

Ganti fungsi `_build_detail` di `report.py` menjadi:

```python
def _build_detail(ws, peaks, sources, active_segments):
    # --- Header ---
    headers = ["Segmen"] + list(sources) + ["TOTAL"]
    for col, name in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col, value=name)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.border = BORDER
        c.alignment = Alignment(horizontal="center")

    total_col = len(sources) + 2  # kolom TOTAL

    # --- Baris data ---
    for r, seg in enumerate(active_segments, start=2):
        row = peaks.get(seg, {})
        ws.cell(row=r, column=1, value=seg).border = BORDER
        for c_idx, src in enumerate(sources, start=2):
            cell = ws.cell(row=r, column=c_idx, value=(row.get(src) or 0))
            cell.number_format = NUM_FMT
            cell.border = BORDER
        tc = ws.cell(row=r, column=total_col,
                     value=_segment_total(peaks, sources, seg))
        tc.number_format = NUM_FMT
        tc.font = HEADER_FONT
        tc.border = BORDER

    last_row = 1 + len(active_segments)

    # --- Lebar kolom + freeze header ---
    ws.column_dimensions["A"].width = 34
    for c_idx in range(2, total_col + 1):
        ws.column_dimensions[get_column_letter(c_idx)].width = 12
    ws.freeze_panes = "A2"

    # --- Bar chart: TOTAL peak per segmen ---
    chart = BarChart()
    chart.type = "col"
    chart.title = "Total Peak per Segmen"
    chart.y_axis.title = "Peak Viewer"
    chart.x_axis.title = "Segmen"
    data = Reference(ws, min_col=total_col, min_row=1, max_row=last_row)
    cats = Reference(ws, min_col=1, min_row=2, max_row=last_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    chart.legend = None
    chart.height = 10
    chart.width = max(15, len(active_segments) * 1.3)
    anchor = get_column_letter(total_col + 2)
    ws.add_chart(chart, f"{anchor}2")
```

- [ ] **Step 2: Jalankan harness sampai sukses**

Minta user menjalankan:

```
peakview-env\Scripts\python.exe verify_report.py
```

Expected: `Wrote: sample_report.xlsx`, tanpa traceback.

- [ ] **Step 3: Eyeball hasil Excel**

Minta user buka `sample_report.xlsx` dan konfirmasi:
- Ada 2 tab: **Ringkasan** & **Detail**.
- Tab Ringkasan: judul + metadata, kotak highlight (4 angka), tabel perbandingan channel, bar chart per channel.
- Tab Detail: tabel `Segmen | BOG-YT | MPL-YT | MDL-YT | TOTAL`, header berwarna + freeze, bar chart per segmen.
- **Segmen "TVC" (semua 0) TIDAK muncul** di tabel maupun chart.
- Angka pakai pemisah ribuan.

Kalau ada yang salah layout/angka, perbaiki `report.py` dan ulangi Step 2-3.

- [ ] **Step 4: Commit (hanya report.py)**

```
git add report.py
git commit -m "feat(report): build Ringkasan and Detail tabs with charts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Wire tombol "Report" ke main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Tambah import os dan import report**

Di `main.py`, tambahkan `import os` di blok import atas (setelah `import time`):

```python
import os
import threading
import time
```

Lalu tambahkan import report tepat setelah baris `from paths import app_dir` (baris ~20):

```python
from report import generate_report as build_report, NoDataError
```

(Alias `build_report` dipakai agar tidak bentrok dengan nama method `generate_report`.)

- [ ] **Step 2: Tambah tombol "Report" di btn_frame2**

Di `_build_ui`, setelah baris tombol "Debug" (`...column=5...`), tambahkan:

```python
        tk.Button(btn_frame2, text="Report", width=7, command=self.generate_report).grid(row=0, column=6, padx=2)
```

- [ ] **Step 3: Tambah method handler `generate_report`**

Tambahkan method berikut ke class `PeakViewApp` (mis. tepat setelah method `export`):

```python
    def generate_report(self):
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        out_path = OUTPUT_DIR / f"laporan_peak_{stamp}.xlsx"
        try:
            path = build_report(self.store.peaks, SOURCES, SEGMENTS, out_path)
        except NoDataError:
            messagebox.showinfo("Report", "Belum ada data peak buat di-report.", parent=self.root)
            self.status.set("Report: belum ada data")
            return
        except Exception as e:
            messagebox.showerror("Report gagal", str(e), parent=self.root)
            self.status.set(f"Report err: {e}")
            return
        self.status.set(f"Report: {path.name}")
        if messagebox.askyesno("Report selesai", f"Tersimpan:\n{path}\n\nBuka sekarang?", parent=self.root):
            try:
                os.startfile(path)
            except Exception:
                pass
```

- [ ] **Step 4: Verifikasi end-to-end di app**

Minta user menjalankan app (`run.bat` atau `peakview-env\Scripts\python.exe main.py`) lalu:
1. Klik **Report** sebelum ada data peak → harus muncul info "Belum ada data peak buat di-report." (tidak ada file korup).
2. Biarkan beberapa segmen ter-record (atau pindah segmen dengan stream jalan) → klik **Report** → muncul dialog "Tersimpan ... Buka sekarang?" → klik Yes → Excel kebuka dengan tab Ringkasan & Detail terisi benar.

Kalau gagal, perbaiki `main.py` dan ulangi.

- [ ] **Step 5: Commit**

```
git add main.py
git commit -m "feat(report): add Report button to main window

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Pastikan openpyxl ter-bundle di PyInstaller

**Files:**
- Modify: `PeakView.spec`

- [ ] **Step 1: Tambah collect_submodules untuk openpyxl**

Di `PeakView.spec`, ubah baris import hooks:

```python
from PyInstaller.utils.hooks import collect_all
```

menjadi:

```python
from PyInstaller.utils.hooks import collect_all, collect_submodules
```

Lalu, tepat setelah blok `_rapidocr_* = collect_all("rapidocr_onnxruntime")`, tambahkan:

```python
# openpyxl + et_xmlfile dipakai oleh report.py; sebagian sub-module di-import
# secara lazy sehingga scanner pyinstaller bisa melewatkannya.
_openpyxl_hidden = collect_submodules("openpyxl") + ["et_xmlfile"]
```

Lalu ubah `hiddenimports` di `Analysis(...)` dari:

```python
    hiddenimports=['PIL._tkinter_finder', 'PIL.ImageTk', *_rapidocr_hidden],
```

menjadi:

```python
    hiddenimports=['PIL._tkinter_finder', 'PIL.ImageTk', *_rapidocr_hidden, *_openpyxl_hidden],
```

- [ ] **Step 2: Build executable**

Minta user menjalankan `build.bat`.

Expected: build selesai tanpa error, menghasilkan `dist/PeakView/PeakView.exe`.

- [ ] **Step 3: Verifikasi tombol Report di executable**

Minta user jalankan `dist/PeakView/PeakView.exe`, isi sedikit data, klik **Report**. Expected: Excel ter-generate (membuktikan openpyxl ikut ter-bundle, bukan cuma jalan di source mode).

- [ ] **Step 4: Commit**

```
git add PeakView.spec
git commit -m "build(report): bundle openpyxl in PyInstaller spec

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Bersihkan artefak dev

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Gitignore artefak verifikasi**

Tambahkan ke `.gitignore`:

```
verify_report.py
sample_report.xlsx
```

- [ ] **Step 2: Commit**

```
git add .gitignore
git commit -m "chore(report): gitignore report verification artifacts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Catatan untuk reviewer

- `report.py` murni: tidak meng-import `storage`, `segments`, atau Tkinter. Itu disengaja agar bisa diverifikasi standalone lewat `verify_report.py` dan agar Level 2 (time-series) nanti tinggal menambah fungsi di modul yang sama.
- `main.py` mengirim `self.store.peaks` (di-key oleh seluruh SEGMENTS × SOURCES), `SOURCES`, dan `SEGMENTS` global. Filtering segmen kosong terjadi di dalam `report.py`, bukan di `main.py`.
- `os.startfile` Windows-only; konsisten dengan target platform app (Windows).
