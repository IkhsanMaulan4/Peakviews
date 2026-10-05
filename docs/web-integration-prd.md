# PRD: PeakView Local Web (Go to Web)

Status: hasil brainstorm, belum ada implementasi. Tanggal: 2026-10-05.

## 1. Masalah & Tujuan

PeakView (Tkinter + PyInstaller, OCR viewer count YouTube per source) hanya bisa dikontrol dari GUI di laptop. Saat acara berlangsung, operator sering jauh dari laptop dan perlu:

1. Mengganti segmen aktif (Waiting Screen, TVC, Match 1 - Game #1 In Game, dst) dari HP.
2. Memantau viewer per source tanpa harus menatap window Tkinter.

Tujuan: tambah tombol **Go to web** di GUI yang menjalankan web server lokal. Web bisa dibuka di laptop (dashboard) maupun HP (kontrol segmen) tanpa server eksternal dan tanpa dependency baru.

## 2. Non-Goals (sengaja tidak dibuat di versi pertama)

- Edit sources, kalibrasi, atau segment editor lewat web (tetap di GUI).
- Hapus data / reset dari web.
- Start/stop pengambilan data dari HP (tetap di laptop, supaya tidak kepencet mati). Boleh dievaluasi ulang nanti.
- Login/akun. Cukup token per sesi.
- Akses dari luar jaringan lokal / internet.

## 3. Fitur

### 3.1 Tombol "Go to web" di GUI
- Menjalankan server HTTP kecil di thread daemon di proses PeakView yang sama.
- Membuka browser default ke halaman web.
- Kalau server sudah jalan, tombol hanya membuka ulang URL yang sama (tidak start server kedua).
- Menampilkan **URL + QR code** (untuk HP) di GUI atau dialog kecil.

### 3.2 Port otomatis
- Bind ke port `0` supaya OS memilih port bebas; baca port aktual dari `server.server_address[1]`.
- Beda mesin tidak pernah bentrok port. Bentrok hanya bisa terjadi di mesin yang sama, dan port otomatis menghindarinya.

### 3.3 Akses dari HP
- Server bind ke `0.0.0.0` agar HP di WiFi yang sama bisa konek (`http://<IP-laptop>:<port>`).
- Windows Firewall akan memunculkan prompt saat pertama jalan: pilih **Private** saja, jangan Public.
- WiFi kantor sudah dites tanpa client isolation (kendala awal ternyata server tidak sengaja ditutup). Fallback kalau suatu saat diblok: hotspot HP/laptop.

### 3.4 Halaman web (satu halaman responsif, dua tab)
HP otomatis masuk tab Kontrol, laptop tab Dashboard.

**Tab Kontrol (prioritas HP, tombol besar, satu tangan):**
- Segmen aktif ditampilkan besar di atas.
- Tombol **Prev / Next** untuk geser segmen berurutan (aksi paling sering).
- Daftar semua segmen yang bisa di-tap, dikelompokkan (Intro / Match 1 / 2 / 3), yang aktif di-highlight.
- Viewer saat ini per source (kecil) dengan indikator OCR health hijau/kuning/merah (selaras tombol warning di GUI).
- Status running/stopped (read-only).

**Tab Dashboard (laptop):**
- Kartu per source: viewer sekarang dan peak segmen aktif.
- Grafik timeline live, satu garis per source (warna sama seperti report Excel), penanda vertikal tiap ganti segmen.
- Tabel peak per segmen (source x segmen), setara tab Ringkasan di report.
- Tombol **Download Excel** yang memanggil `generate_report` yang sudah ada.
- Panel OCR health per source.

### 3.5 Ganti segmen dari HP
- Endpoint menulis segmen aktif; GUI Tkinter ikut update, dan sebaliknya (GUI ganti, web ikut).
- Perlu **state segmen aktif bersama** (dilindungi lock) yang dipakai GUI dan thread server.
- Update ke widget Tkinter dari thread server wajib lewat `root.after(...)` (Tkinter tidak thread-safe).

## 4. Keamanan

- **Token acak per sesi**, dibuat setiap PeakView dijalankan, dimasukkan ke URL/QR (`?t=...`). Request tanpa token valid ditolak (403), termasuk untuk endpoint data.
- Hanya endpoint yang perlu yang diekspos: ganti segmen, baca status/data, download report.
- Tidak ada endpoint untuk edit sources, kalibrasi, atau hapus data.
- Server hanya hidup selama PeakView berjalan. Pertimbangkan opsi bind `127.0.0.1` saja kalau akses HP tidak dibutuhkan.
- Validasi input: nama segmen dari request harus ada di daftar `SEGMENTS`, tolak selain itu.

## 5. Pendekatan Teknis

- `http.server` bawaan Python (`ThreadingHTTPServer`) + satu halaman HTML/JS. Tanpa dependency baru, ukuran exe tetap kecil.
- Grafik: Chart.js disimpan sebagai file lokal di bundle (bukan CDN, supaya jalan tanpa internet). Perlu ditambahkan ke `PeakView.spec` sebagai data file.
- Live update: polling JSON tiap 1-2 detik (`/api/state`) cukup untuk versi pertama; SSE/WebSocket tidak perlu.
- QR code: library kecil (`qrcode`) atau generate sederhana; pilih yang paling ringan untuk dibundle.
- Sumber data: pakai ulang `storage.py` (PeakStore), `timeline.py`, `segments.py`, `report.py`. Jangan menduplikasi logika.
- Titik integrasi di kode saat ini: `main.py` (GUI Tkinter, memegang state segmen aktif), `segments.py` (`SEGMENTS`, `SOURCES`, file `segments.json`/`sources.json`), `paths.py` (`app_dir()`).

Modul baru yang disarankan: `webserver.py` (server + routing + token) dan folder `web/` (HTML/JS/CSS + Chart.js).

## 6. Risiko & Hal yang Perlu Dites

- Race condition antara thread server dan thread GUI/OCR (segmen aktif, data peak). Wajib pakai lock dan `root.after`.
- Firewall/jaringan: prompt Private vs Public; tes dari HP di jaringan kantor yang sebenarnya.
- Server mati bila proses PeakView ditutup (perilaku yang diinginkan); pastikan thread berhenti bersih saat GUI ditutup.
- Build PyInstaller: file `web/` dan Chart.js harus ikut ter-bundle dan terbaca lewat `paths.py` saat mode frozen.
- Keterbacaan di HP: tombol besar, tidak perlu zoom.
- Catatan proyek: digit-tick animation OCR adalah sumber misread utama, jadi tampilan viewer live perlu memakai data yang sudah lewat anti-spike, bukan raw OCR.

## 7. Kriteria Sukses

1. Klik **Go to web** membuka dashboard di laptop; klik lagi tidak membuat server kedua.
2. HP scan QR, buka tab Kontrol, ganti segmen, dan segmen di GUI Tkinter berubah dalam 2 detik; sebaliknya juga berlaku.
3. Request tanpa token ditolak.
4. Dua instance di mesin berbeda (atau port yang sudah dipakai) tidak saling bentrok.
5. Grafik timeline live dan tabel peak sesuai dengan isi report Excel untuk sesi yang sama.
6. Build `PeakView.exe` membundel semua aset web dan berjalan tanpa Python terpasang.

## 8. Pertanyaan Terbuka

- Perlu tombol start/stop dari HP, atau cukup dari laptop? (default: cukup dari laptop)
- Halaman HP perlu lebih dari ganti segmen, misal peak terakhir per source?
- Web boleh mengedit data atau read-only? (default: read-only kecuali ganti segmen)
- QR ditampilkan di jendela GUI utama atau dialog terpisah?

## 9. Urutan Pengerjaan yang Disarankan

1. State segmen aktif bersama + lock di `main.py`/`segments.py` (refactor kecil, tanpa fitur baru).
2. `webserver.py`: server, port otomatis, token, endpoint `/api/state` dan `/api/segment`.
3. Halaman web: tab Kontrol dulu (nilai paling tinggi), lalu Dashboard.
4. Tombol **Go to web** + QR di GUI.
5. Download Excel dari web.
6. Update `PeakView.spec`, README, dan tes di HP lewat jaringan kantor.
