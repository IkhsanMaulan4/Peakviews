# Plan Implementasi: PeakView Local Web

Sumber: [web-integration-prd.md](web-integration-prd.md). Dokumen ini = *bagaimana*, PRD = *apa*.
Status: plan, belum ada kode. Tanggal: 2026-10-05.

## 1. Temuan dari kode saat ini (mempengaruhi desain)

| Temuan | Dampak |
|---|---|
| `seg_index` hanya atribut `PeakViewApp` ([main.py:35](../main.py)); dibaca thread OCR tanpa lock ([main.py:141](../main.py)) | Perlu objek state bersama + lock (PRD 3.5). |
| `self.live` ([main.py:140](../main.py)) = hasil OCR **mentah** | PRD 6 minta data yang sudah lolos anti-spike. Pakai nilai terakhir `SeriesCleaner._last` lewat accessor baru di `TimelineTracker`. |
| `PeakStore.peaks` dimutasi thread OCR; `edit_segments`/`edit_sources` mengganti dict-nya di thread GUI | Thread web wajib baca lewat snapshot ber-lock, bukan akses langsung. |
| Timeline hanya ditulis ke CSV tiap 5 dtk; parser ada di `report._read_timeline` | Grafik live: simpan ring buffer in-memory di `TimelineTracker` (hindari baca CSV tiap poll). |
| `generate_report(...)` di [main.py:355](../main.py) tercampur dialog Tkinter | Pisahkan pembuatan file dari dialog, web memanggil bagian murninya. |
| Tidak ada folder tes; `requirements.txt` tanpa pytest; python tidak ada di PATH shell tool | Tes dijalankan lewat `peakview-env`; pytest jadi dev-dependency terpisah (tidak masuk bundle). |
| `PeakView.spec` hanya `collect_all` rapidocr + openpyxl | Tambah `datas` untuk `web/` (+ Chart.js). |

## 2. Keputusan desain

1. **State bersama**: modul baru `session.py`, kelas `SessionState` (lock, `index`, `current_name()`, `set_index()`, `set_by_name()`, `next()`/`prev()`, `subscribe(callback)`). GUI dan web sama-sama memanggilnya. Tidak import tkinter.
2. **GUI sync**: setiap perubahan lewat `SessionState` memanggil subscriber; subscriber GUI membungkus `root.after(0, app._on_segment_changed)` (render + autosave). Tkinter tidak pernah disentuh dari thread server.
3. **Server**: `webserver.py`, `ThreadingHTTPServer` bind `("0.0.0.0", 0)`, thread daemon, `shutdown()` dipanggil di `_on_close`. Server hanya menerima *provider* (callable/objek read-only), tidak import `main`, jadi mudah dites.
4. **Token**: `secrets.token_urlsafe(16)`, dibandingkan `hmac.compare_digest`. Dikirim sebagai `?t=` saat load pertama; JS menyimpannya lalu memakai header `X-Token` untuk semua `/api/*`, dan menghapus token dari address bar. Salah/kosong: 403. Static asset (`/`, `/static/*`) tidak membocorkan data, jadi HTML boleh dilayani tanpa token tetapi seluruh `/api/*` wajib token.
5. **Endpoint** (hanya ini):
   - `GET /api/state`: segmen aktif + index + daftar segmen (dengan grup), viewer bersih per source, peak segmen aktif, status OCR per source, running flag.
   - `GET /api/timeline?since=<n>`: delta titik grafik + penanda ganti segmen.
   - `GET /api/summary`: tabel peak source x segmen (sama dengan tab Ringkasan).
   - `POST /api/segment` body `{"name": ...}` atau `{"action":"next"|"prev"}`: validasi nama ada di `SEGMENTS`, selain itu 400.
   - `GET /api/report.xlsx`: bangun lewat `report.generate_report`; `NoDataError` jadi 409.
6. **QR**: pakai `segno` (pure-python, tanpa dependency, kecil), render matriks ke `PhotoImage` Tkinter. Alternatif `qrcode` ditolak karena menarik lebih banyak.
7. **Chart.js**: simpan lokal di `web/vendor/chart.min.js` (versi dikunci, bukan CDN).
8. **IP LAN**: ambil lewat socket UDP `connect(("10.255.255.255", 1))` + `getsockname()`; fallback `127.0.0.1`.
9. **Pertanyaan terbuka PRD**: ikuti default PRD (start/stop dari laptop saja, web read-only kecuali ganti segmen). QR dalam dialog terpisah (`Toplevel`) supaya jendela utama 540x360 tidak berubah.

## 3. Struktur file

```
session.py            # SessionState (baru)
webserver.py          # server, routing, token (baru)
web_api.py            # builder JSON murni dari store/timeline/session (baru, mudah dites)
qr_dialog.py          # dialog URL + QR (baru)
web/index.html, app.js, style.css, vendor/chart.min.js
tests/                # test_session.py, test_web_api.py, test_webserver.py, test_timeline_history.py
main.py               # pakai SessionState, tombol "Go to web", cleanup
timeline.py           # + latest(src), + history ring buffer (thread-safe)
storage.py            # + snapshot() ber-lock
PeakView.spec         # datas web/, hiddenimports segno
requirements.txt      # + segno
requirements-dev.txt  # pytest, pytest-cov
```

## 4. Fase build (TDD per fase: RED, GREEN, REFACTOR)

Tiap fase berakhir dengan `verification-loop` dan commit kecil (conventional commits). Tidak ada fase yang mematahkan GUI yang sudah jalan.

**Fase 0: Setup tes** (`ecc:python-testing`)
- Buat `tests/`, `requirements-dev.txt`, pastikan `peakview-env\Scripts\python -m pytest` jalan.
- Selesai bila: satu tes dummy hijau.

**Fase 1: State bersama** (`ecc:tdd-workflow`, `ecc:python-patterns`)
- Tes dulu: next/prev di batas, `set_by_name` nama tidak valid, subscriber terpanggil, aman dari banyak thread, sinkron saat `SEGMENTS` diedit (index di-clamp).
- Implement `session.py`; refactor `main.py`: ganti `self.seg_index` dengan `SessionState`, `edit_segments` memperbarui lewat state.
- Selesai bila: GUI berperilaku sama persis (cek manual Prev/Next/Segments editor).

**Fase 2: Akses data thread-safe** (`ecc:tdd-workflow`)
- `PeakStore.snapshot()` ber-lock; `TimelineTracker.latest(src)` dan history ring buffer (titik + penanda segmen), `status()` sudah ada.
- Selesai bila: tes concurrency (thread tulis + thread baca) hijau.

**Fase 3: Web API murni + server** (`ecc:tdd-workflow`, `ecc:security-review`, `ecc:api-design`)
- Tes dulu: 403 tanpa/salah token di semua `/api/*`, nama segmen invalid 400, body besar/JSON rusak ditolak, port `0` memberi port berbeda untuk dua instance, `shutdown()` menghentikan thread, tidak ada endpoint selain daftar di 2.5.
- Implement `web_api.py` + `webserver.py` (header respon `Cache-Control: no-store`, batasi ukuran body, path traversal aman untuk static).
- Selesai bila: `curl` ke server lokal dengan dan tanpa token sesuai harapan.

**Fase 4: Halaman web, tab Kontrol dulu** (`ecc:frontend-design`, `ecc:frontend-patterns`)
- Segmen aktif besar, Prev/Next, daftar segmen berkelompok, viewer + indikator health, polling 1.5 dtk, tombol minimal 48px, uji di viewport 375px.
- Lalu tab Dashboard: kartu source, grafik timeline (warna sama dengan report Excel, garis vertikal ganti segmen), tabel peak, panel health, tombol Download Excel.
- Selesai bila: dicek di browser pane (mobile + desktop) tanpa error console.

**Fase 5: Integrasi GUI** (`ecc:python-patterns`)
- Tombol **Go to web** di [main.py:90](../main.py): start server sekali (idempotent), buka browser default, tampilkan dialog URL + QR. Klik ulang hanya membuka URL yang sama.
- `_on_close`: hentikan server bersih sebelum `root.destroy()`.
- Selesai bila: kriteria sukses PRD no. 1-3 lolos manual.

**Fase 6: Download Excel** (`ecc:tdd-workflow`)
- Ekstrak pembuatan file dari dialog di `generate_report`; endpoint stream file; tes `NoDataError` jadi 409.

**Fase 7: Packaging & dokumen** (`ecc:build-fix` bila build gagal, `ecc:update-docs`)
- `PeakView.spec`: `datas` untuk `web/`, resolve lewat helper di `paths.py` (mode frozen pakai `sys._MEIPASS`, bukan `app_dir()`, karena aset bundle bukan folder exe).
- Update README + `dist-README.txt` (firewall: pilih **Private**; fallback hotspot).
- Selesai bila: `PeakView.exe` dari `build.bat` menampilkan web lengkap di mesin tanpa Python.

**Fase 8: Review akhir** (`ecc:python-review`, `ecc:security-review`, `ecc:code-review`)
- Selesaikan semua CRITICAL/HIGH, coverage modul baru >= 80%.

## 5. Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Race GUI/OCR/server | Satu `SessionState` ber-lock, snapshot ber-lock, tes concurrency, Tkinter hanya via `root.after`. |
| `SEGMENTS`/`SOURCES` diedit saat request berjalan | Handler memakai salinan (`list(SEGMENTS)`) dari satu snapshot per request; clamp index di `SessionState`. |
| Token bocor via URL/log | Hapus dari address bar setelah load, jangan log query string, token berubah tiap start. |
| Firewall memblok HP | Dokumentasi Private + fallback hotspot; opsi bind `127.0.0.1` saja. |
| Aset web tak ikut bundle | Fase 7 uji `.exe` nyata; helper path khusus bundle. |
| Chart berat di HP | Tab Dashboard tidak memuat Chart.js sampai dibuka; batasi jumlah titik (downsample). |

## 6. Urutan commit yang disarankan

1. `test: add pytest scaffolding`
2. `refactor: extract SessionState for active segment`
3. `feat(timeline): expose latest values and in-memory history`
4. `feat(web): token-protected local API server`
5. `feat(web): control tab`
6. `feat(web): dashboard tab`
7. `feat(gui): Go to web button with QR dialog`
8. `feat(web): download Excel report`
9. `build: bundle web assets; docs: web usage`

## 7. Yang perlu keputusan sebelum mulai

- Setuju memakai `segno` (satu dependency kecil baru)? PRD bilang "tanpa dependency baru" untuk server, QR dikecualikan.
- Fase 1 mengubah `main.py` cukup dalam (semua pemakaian `seg_index`). Setuju dikerjakan sebagai refactor terpisah dulu?
