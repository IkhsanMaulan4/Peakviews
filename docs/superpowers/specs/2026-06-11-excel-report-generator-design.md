# Excel Report Generator — Design Spec

**Tanggal:** 2026-06-11
**Status:** Disetujui (siap masuk implementation plan)
**Scope:** Level 1 — report dari data peak yang sudah ada (tanpa time-series)

## Tujuan

Menambah fitur ke peak-view: sekali klik tombol di app, hasilkan satu file
Excel (`.xlsx`) berisi laporan peak viewer per-segmen yang rapi dan siap
dipamerkan, langsung dari data peak yang sedang aktif. Ini melengkapi
peak-view menjadi sistem utuh: capture → analyze → report.

## Konteks Data

Data yang tersedia di `PeakStore.peaks` (lihat `storage.py`):

```
peaks[segmen][channel] = nilai_peak (int)
```

- Channel/source: dari `segments.SOURCES` (mis. BOG-YT, MPL-YT, MDL-YT, ...).
- Segmen: dari `segments.SEGMENTS` (mis. format BO3 dengan 31 segmen).
- **Tidak ada data time-series** — hanya nilai puncak final per (segmen, channel).
  Konsekuensi: report Level 1 tidak punya kurva penonton / rata-rata
  sepanjang waktu. Itu cakupan Level 2 di masa depan.

## Keputusan Desain (hasil brainstorm)

| Aspek | Keputusan |
|-------|-----------|
| Format output | Excel `.xlsx` |
| Library | `openpyxl` (pure Python, tidak butuh Excel terinstall, chart native, bundle mulus di PyInstaller) |
| Pemicu | Tombol "Generate Report" di UI app peak-view |
| Struktur file | 1 workbook, 2 tab: **Ringkasan** + **Detail** |
| Segmen kosong | Di-skip (segmen yang semua channel-nya 0 tidak ditampilkan) |
| Jenis chart | Bar chart saja (tidak ada pie) |

## Arsitektur

### Modul baru: `report.py`

Fungsi publik yang pure & testable — tidak tahu-menahu soal `PeakStore`
maupun Tkinter:

```python
def generate_report(
    peaks: dict[str, dict[str, int]],   # {segmen: {channel: nilai_peak}}
    sources: list[str],                 # urutan channel
    segments: list[str],                # urutan segmen
    out_path: Path,
) -> Path:
    ...
```

Semua logika ada di sini: skip segmen kosong, hitung ringkasan, format,
bikin chart, tulis file. Mengembalikan path file yang ditulis.

### Data flow

```
[main.py] tombol "Generate Report" diklik
   → ambil store.peaks + SOURCES + SEGMENTS
   → tentukan out_path = output/laporan_peak_<YYYY-MM-DD_HHMM>.xlsx
   → report.generate_report(...)
   → tampilkan konfirmasi sukses (+ opsional buka file); kalau gagal, messagebox error
```

### Perubahan pada file existing

- **`main.py`** — tambah 1 tombol "Generate Report" + handler. Handler
  mengambil `store.peaks`, `SOURCES`, `SEGMENTS`, tentukan out_path lewat
  helper path yang ada, panggil `report.generate_report`, lalu notif.
- **`requirements.txt`** — tambah `openpyxl`.
- **`PeakView.spec`** — pastikan `openpyxl` ter-bundle (verifikasi saat build;
  tambah hidden import bila perlu).
- **`storage.py`** — tidak diubah. Report membaca atribut publik `store.peaks`.

## Isi Report

### Tab 1: "Ringkasan"

1. **Judul + metadata** — "Laporan Peak Viewer", tanggal generate, jumlah
   segmen ber-data.
2. **Kotak highlight** — 4 angka kunci:
   - Peak tertinggi keseluruhan → nilai + "di segmen X, channel Y"
   - Segmen paling rame (berdasarkan TOTAL)
   - Channel paling rame (total seluruh segmen)
   - Rata-rata TOTAL peak antar segmen (hanya segmen ber-data)
3. **Perbandingan antar-channel** — tabel `Channel | Total Peak | Rata-rata`
   + bar chart total peak per channel.

### Tab 2: "Detail"

4. **Tabel detail** — kolom `Segmen | <tiap channel> | TOTAL`. Header bold +
   background warna, border tipis, freeze baris header, angka pakai pemisah
   ribuan. **Hanya segmen ber-data** (semua-channel-0 di-skip).
5. **Bar chart per-segmen** — batang TOTAL peak tiap segmen ber-data,
   diletakkan di bawah/samping tabel. Label segmen auto-fit/miring bila panjang.

### Formatting umum

Header bold + warna background, border tipis, kolom auto-width, angka dengan
pemisah ribuan (mis. `1.234`).

## Edge Cases

- **Semua segmen 0** (report diklik sebelum ada data) → jangan tulis file
  kosong/korup. Tampilkan notif "Belum ada data peak buat di-report." dan
  batalkan.
- **Hanya 1 channel / 1 segmen ber-data** → tabel & chart tetap valid, tidak crash.
- **Nama segmen panjang** → label chart auto-fit/dimiringkan agar terbaca.
- **File Excel lama sedang dibuka** → nama file pakai timestamp, jadi tidak
  menimpa file lama.

## Error Handling

Handler tombol membungkus seluruh proses dalam try/except. Bila gagal (mis.
disk penuh, file terkunci), app **tidak crash** — cukup munculkan messagebox
error. Konsisten dengan pola app saat ini.

## Testing

Catatan: python tidak ada di PATH untuk shell tools, jadi verifikasi lewat
menjalankan app langsung.

- **Happy path:** jalankan app → isi beberapa peak dummy via segmen → klik
  Generate Report → buka Excel, cek tab Ringkasan & Detail, angka cocok,
  chart terbentuk.
- **Skip kosong:** pastikan segmen yang 0 tidak muncul di tabel & chart.
- **Belum ada data:** klik saat semua 0 → muncul notif, tidak ada file korup.

## Di Luar Cakupan (Level 2, masa depan)

- Logging time-series angka penonton sepanjang siaran.
- Kurva penonton / retention curve, rata-rata penonton sepanjang waktu,
  deteksi momen lonjakan.
- Output PDF.
