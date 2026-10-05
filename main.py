"""Main GUI - always-on-top window dengan tombol Next/Prev/Recalibrate/Export."""
import os
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox
from datetime import datetime
from pathlib import Path

from segments import (
    SEGMENTS, SOURCES,
    reload_sources, save_sources,
    reload_segments, save_segments,
)
from session import SessionState
from storage import PeakStore
from timeline import TimelineTracker, STATUS_WARN, STATUS_ERROR
from capture import capture_all, capture_all_with_debug
from debug_window import OcrDebugWindow
from calibration import load_calibration, run_calibration, run_edit_calibration, save_calibration
from source_editor import run_source_editor
from segment_editor import run_segment_editor
from paths import app_dir
from report import generate_report as build_report, NoDataError
from web_api import WebContext
from web_launcher import WebController
from qr_dialog import WebDialog

OUTPUT_DIR = app_dir() / "output"
POLL_INTERVAL = 0.3  # seconds


class PeakViewApp:
    def __init__(self, root: tk.Tk, regions: dict):
        self.root = root
        self.regions = regions
        self.active_sources = [s for s in SOURCES if s in regions]
        self.store = PeakStore()
        self.session = SessionState(SEGMENTS)
        self.session.subscribe(self._on_segment_changed_threadsafe)
        self.live = {src: None for src in self.active_sources}
        self.debug_window: OcrDebugWindow | None = None
        self.status = tk.StringVar(value="Ready")
        self._stop = threading.Event()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        self.session_file = OUTPUT_DIR / f"peak_{stamp}.txt"
        self.timeline = TimelineTracker(OUTPUT_DIR, stamp, self.active_sources)
        self.web_ctx = WebContext(
            session=self.session, store=self.store, timeline=self.timeline,
            segments=SEGMENTS, sources=self.active_sources,
            is_running=lambda: not self._stop.is_set(),
            report_builder=self.build_report_file,
        )
        self.web = WebController(self.web_ctx)
        self.web_dialog: WebDialog | None = None

        root.title("Peak View")
        root.attributes("-topmost", True)
        root.geometry("540x360+1000+50")
        root.resizable(False, False)

        self._build_ui()
        self._render()

        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 2}

        self.seg_label = tk.Label(
            self.root, text="", font=("Arial", 13, "bold"), fg="navy", wraplength=380
        )
        self.seg_label.pack(**pad)

        self.live_frame = tk.Frame(self.root)
        self.live_frame.pack(**pad)
        self.live_labels = {}
        for i, src in enumerate(self.active_sources):
            row = i // 2
            col = i % 2
            lbl = tk.Label(self.live_frame, text=f"{src}: --", font=("Consolas", 10), width=18, anchor="w")
            lbl.grid(row=row, column=col, padx=4, pady=2)
            self.live_labels[src] = lbl

        self.peak_label = tk.Label(self.root, text="", font=("Consolas", 9), fg="darkgreen", justify="left")
        self.peak_label.pack(**pad)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(**pad)
        tk.Button(btn_frame, text="< Prev", width=7, command=self.prev_segment).grid(row=0, column=0, padx=2)
        tk.Button(btn_frame, text="Next >", width=7, command=self.next_segment).grid(row=0, column=1, padx=2)
        tk.Button(btn_frame, text="Reset Current", width=12, fg="red", command=self.reset_current).grid(row=0, column=2, padx=2)
        tk.Button(btn_frame, text="Go to web", width=10, command=self.go_to_web).grid(row=0, column=3, padx=2)

        btn_frame2 = tk.Frame(self.root)
        btn_frame2.pack(**pad)
        tk.Button(btn_frame2, text="Recalibrate", width=10, command=self.recalibrate).grid(row=0, column=0, padx=2)
        tk.Button(btn_frame2, text="Edit Boxes", width=9, command=self.edit_boxes).grid(row=0, column=1, padx=2)
        tk.Button(btn_frame2, text="Sources", width=7, command=self.edit_sources).grid(row=0, column=2, padx=2)
        tk.Button(btn_frame2, text="Segments", width=8, command=self.edit_segments).grid(row=0, column=3, padx=2)
        tk.Button(btn_frame2, text="Export TXT", width=9, command=self.export).grid(row=0, column=4, padx=2)
        tk.Button(btn_frame2, text="Debug", width=6, command=self.toggle_debug).grid(row=0, column=5, padx=2)
        tk.Button(btn_frame2, text="Report", width=7, command=self.generate_report).grid(row=0, column=6, padx=2)

        tk.Label(self.root, textvariable=self.status, fg="gray", font=("Arial", 8)).pack(side="bottom", pady=2)

    def _render(self):
        index = self.session.index
        seg = SEGMENTS[index]
        self.seg_label.config(text=f"[{index + 1}/{len(SEGMENTS)}] {seg}")
        default_bg = self.root.cget("bg")
        for src, lbl in self.live_labels.items():
            val = self.live.get(src)
            display = self._fmt(val) if val is not None else "--"
            state = self.timeline.status(src)
            if state == STATUS_ERROR:
                colors = {"bg": "red", "fg": "white"}
            elif state == STATUS_WARN:
                colors = {"bg": "gold", "fg": "black"}
            else:
                colors = {"bg": default_bg, "fg": "black"}
            lbl.config(text=f"{src}: {display}", **colors)
        peaks = self.store.get_current(seg)
        lines = ["Peak:"]
        for s in self.active_sources:
            raw = peaks[s] or 0
            lines.append(f"  {s}: {raw:,}  ({self._fmt(raw)})")
        self.peak_label.config(text="\n".join(lines))

    @staticmethod
    def _fmt(n):
        if n is None or n == 0:
            return "0"
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    def _capture_loop(self):
        cycles_since_save = 0
        while not self._stop.is_set():
            try:
                dbg = self.debug_window  # snapshot once per cycle
                if dbg is not None:
                    debug_results = capture_all_with_debug(self.regions)
                    results = {k: r["value"] for k, r in debug_results.items()}
                    self.root.after(0, lambda r=debug_results, w=dbg: w.update_debug(r))
                else:
                    results = capture_all(self.regions)
                self.live = results
                seg = self.session.current_name()
                self.timeline.feed(seg, results)
                for label, val in results.items():
                    self.store.update(seg, label, val)
                self.root.after(0, self._render)
                cycles_since_save += 1
                if cycles_since_save >= 10:
                    cycles_since_save = 0
                    self.root.after(0, self._auto_save)
            except Exception as e:
                self.root.after(0, lambda msg=str(e): self.status.set(f"Capture err: {msg[:40]}"))
            self._stop.wait(POLL_INTERVAL)

    def _set_active_sources(self, sources):
        self.active_sources = sources
        self.web_ctx.sources = sources  # web thread reads this reference

    def go_to_web(self):
        try:
            self.web.ensure_started()
        except OSError as e:
            messagebox.showerror("Go to web", f"Server gagal start: {e}", parent=self.root)
            self.status.set("Web: gagal start")
            return
        webbrowser.open(self.web.local_url())
        if self.web_dialog is not None and self.web_dialog.winfo_exists():
            self.web_dialog.refresh()
            self.web_dialog.lift()
        else:
            self.web_dialog = WebDialog(self.root, self.web, on_stop=self._on_web_stopped)
        self.status.set("Web berjalan")

    def _on_web_stopped(self):
        self.web_dialog = None
        self.status.set("Web dihentikan")

    def next_segment(self):
        if not self.session.next():
            self.status.set("Sudah segment terakhir")

    def prev_segment(self):
        if not self.session.prev():
            self.status.set("Sudah segment pertama")

    def _on_segment_changed_threadsafe(self, index, name):
        # May fire from the web server thread: Tk must only be touched via after().
        try:
            self.root.after(0, lambda: self._on_segment_changed(name))
        except (tk.TclError, RuntimeError):
            pass  # window already closing

    def _on_segment_changed(self, name):
        self.status.set(f"-> {name}")
        self._render()
        self._auto_save()

    def reset_current(self):
        seg = self.session.current_name()
        self.store.reset_segment(seg)
        self.status.set(f"Peak '{seg}' di-reset ke 0")
        self._render()
        self._auto_save()

    def _auto_save(self):
        try:
            self.store.export_to_path(self.session_file)
        except Exception as e:
            self.status.set(f"Auto-save err: {e}")

    def recalibrate(self):
        self.status.set("Membuka calibration...")
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass
        new_regions = run_calibration(parent=self.root)
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
        except Exception:
            pass
        if new_regions:
            self.regions = new_regions
            self._set_active_sources([s for s in SOURCES if s in new_regions])
            for widget in self.live_frame.winfo_children():
                widget.destroy()
            self.live_labels = {}
            self.live = {src: None for src in self.active_sources}
            self.timeline.set_sources(self.active_sources)
            for i, src in enumerate(self.active_sources):
                row = i // 2
                col = i % 2
                lbl = tk.Label(self.live_frame, text=f"{src}: --", font=("Consolas", 10), width=18, anchor="w")
                lbl.grid(row=row, column=col, padx=4, pady=2)
                self.live_labels[src] = lbl
            self.status.set(f"Calibration disimpan ({len(self.active_sources)} source)")
            self._render()
        else:
            self.status.set("Calibration dibatalkan")

    def edit_boxes(self):
        if not self.regions:
            self.status.set("Belum ada calibration. Pakai Recalibrate dulu.")
            return
        self.status.set("Membuka editor box...")
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass
        new_regions = run_edit_calibration(self.regions, parent=self.root)
        try:
            self.root.attributes("-topmost", True)
            self.root.lift()
        except Exception:
            pass
        if new_regions:
            self.regions = new_regions
            self.status.set(f"Box disimpan ({len(self.regions)} source)")
            self._render()
        else:
            self.status.set("Edit dibatalkan")

    def edit_sources(self):
        result = run_source_editor(self.root, list(SOURCES))
        if result is None:
            self.status.set("Edit sources dibatalkan")
            return
        new_list, rename_map = result

        # Persist + refresh the in-place SOURCES so existing imports stay valid.
        save_sources(new_list)
        reload_sources()

        # Migrate calibration: renames carry regions to the new key, removes drop.
        inv = {new: old for old, new in rename_map.items()}
        new_regions = {}
        for src in new_list:
            old = inv.get(src, src)
            if old in self.regions:
                new_regions[src] = self.regions[old]
        save_calibration(new_regions)
        self.regions = new_regions

        # Reshape peak store (preserves recent/peak buffers across renames).
        self.store.reconfigure_sources(new_list, rename_map)

        # Rebuild live UI — same pattern as recalibrate.
        self._set_active_sources([s for s in new_list if s in new_regions])
        self.live = {src: None for src in self.active_sources}
        self.timeline.set_sources(self.active_sources)
        for widget in self.live_frame.winfo_children():
            widget.destroy()
        self.live_labels = {}
        for i, src in enumerate(self.active_sources):
            row = i // 2
            col = i % 2
            lbl = tk.Label(self.live_frame, text=f"{src}: --", font=("Consolas", 10), width=18, anchor="w")
            lbl.grid(row=row, column=col, padx=4, pady=2)
            self.live_labels[src] = lbl

        # Debug window holds stale source list — easiest to drop it.
        if self.debug_window is not None:
            try:
                self.debug_window.destroy()
            except Exception:
                pass
            self.debug_window = None

        self._render()
        uncalibrated = [s for s in new_list if s not in new_regions]
        if uncalibrated:
            self.status.set(f"Sources updated — calibrate: {', '.join(uncalibrated)}")
        else:
            self.status.set(f"Sources updated ({len(new_list)} sources)")

    def edit_segments(self):
        old_segments = list(SEGMENTS)
        current_seg = self.session.current_name()

        result = run_segment_editor(self.root, old_segments)
        if result is None:
            self.status.set("Edit segments dibatalkan")
            return
        new_list, rename_map = result

        kept_originals = set(new_list) | set(rename_map.keys())
        to_delete = [s for s in old_segments if s not in kept_originals]
        deleted_with_data = [
            s for s in to_delete
            if any(v > 0 for v in self.store.peaks.get(s, {}).values())
        ]

        if deleted_with_data:
            shown = deleted_with_data[:10]
            extra = len(deleted_with_data) - len(shown)
            lines = []
            for s in shown:
                peak_max = max(self.store.peaks[s].values())
                lines.append(f"• {s} ({self._fmt(peak_max)})")
            if extra > 0:
                lines.append(f"… dan {extra} lainnya")
            body = (
                "Segmen berikut akan dihapus beserta data peak-nya:\n\n"
                + "\n".join(lines)
                + "\n\nLanjut?"
            )
            if not messagebox.askyesno("Konfirmasi hapus", body, parent=self.root):
                self.status.set("Edit segments dibatalkan (data dipertahankan)")
                return

        # SessionState clamps its index on every read, so the capture/web
        # threads stay safe while SEGMENTS is swapped in place.
        new_current_seg = rename_map.get(current_seg, current_seg)

        save_segments(new_list)
        reload_segments()
        self.session.sync_to(new_current_seg)
        self.store.reconfigure_segments(new_list, rename_map)

        self._render()
        self._auto_save()
        added = len(new_list) - (len(old_segments) - len(to_delete))
        if added or to_delete:
            self.status.set(f"Segments updated ({len(new_list)} total)")
        else:
            self.status.set("Segments updated")

    def export(self):
        try:
            path = self.store.export_txt(OUTPUT_DIR)
            self.status.set(f"Saved: {path.name}")
        except Exception as e:
            self.status.set(f"Export err: {e}")

    def build_report_file(self):
        """Write the Excel report and return its path. Raises NoDataError. Thread-safe."""
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        out_path = OUTPUT_DIR / f"laporan_peak_{stamp}.xlsx"
        return build_report(self.store.snapshot(), list(SOURCES), list(SEGMENTS), out_path, self.timeline.path)

    def generate_report(self):
        try:
            path = self.build_report_file()
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

    def toggle_debug(self):
        if self.debug_window is not None:
            try:
                self.debug_window.destroy()
            except Exception:
                pass
            self.debug_window = None
            self.status.set("Debug window closed")
            return
        if not self.active_sources:
            self.status.set("No active sources to debug — calibrate first")
            return
        self.debug_window = OcrDebugWindow(
            self.root, self.active_sources, on_close=self._on_debug_close
        )
        self.status.set("Debug window opened")

    def _on_debug_close(self):
        self.debug_window = None
        self.status.set("Debug window closed")

    def _on_close(self):
        self._stop.set()
        self.web.stop()
        self.root.destroy()


def main():
    regions = load_calibration()
    if regions is None:
        print("Calibration belum ada. Menjalankan kalibrasi...")
        regions = run_calibration()
        if regions is None:
            print("Kalibrasi dibatalkan. Keluar.")
            return

    root = tk.Tk()
    PeakViewApp(root, regions)
    root.mainloop()


if __name__ == "__main__":
    main()
