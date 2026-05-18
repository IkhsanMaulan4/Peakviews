"""Main GUI - always-on-top window dengan tombol Next/Prev/Recalibrate/Export."""
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

from segments import SEGMENTS, SOURCES
from storage import PeakStore
from capture import capture_all, capture_all_with_debug
from debug_window import OcrDebugWindow
from calibration import load_calibration, run_calibration, run_edit_calibration

OUTPUT_DIR = Path(__file__).parent / "output"
POLL_INTERVAL = 0.3  # seconds


class PeakViewApp:
    def __init__(self, root: tk.Tk, regions: dict):
        self.root = root
        self.regions = regions
        self.active_sources = [s for s in SOURCES if s in regions]
        self.store = PeakStore()
        self.seg_index = 0
        self.live = {src: None for src in self.active_sources}
        self.debug_window: OcrDebugWindow | None = None
        self.status = tk.StringVar(value="Ready")
        self._stop = threading.Event()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        self.session_file = OUTPUT_DIR / f"peak_{stamp}.txt"

        root.title("Peak View")
        root.attributes("-topmost", True)
        root.geometry("420x360+1000+50")
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

        btn_frame2 = tk.Frame(self.root)
        btn_frame2.pack(**pad)
        tk.Button(btn_frame2, text="Recalibrate", width=11, command=self.recalibrate).grid(row=0, column=0, padx=2)
        tk.Button(btn_frame2, text="Edit Boxes", width=10, command=self.edit_boxes).grid(row=0, column=1, padx=2)
        tk.Button(btn_frame2, text="Export TXT", width=11, command=self.export).grid(row=0, column=2, padx=2)
        tk.Button(btn_frame2, text="Debug", width=7, command=self.toggle_debug).grid(row=0, column=3, padx=2)

        tk.Label(self.root, textvariable=self.status, fg="gray", font=("Arial", 8)).pack(side="bottom", pady=2)

    def _render(self):
        seg = SEGMENTS[self.seg_index]
        self.seg_label.config(text=f"[{self.seg_index + 1}/{len(SEGMENTS)}] {seg}")
        for src, lbl in self.live_labels.items():
            val = self.live.get(src)
            display = self._fmt(val) if val is not None else "--"
            lbl.config(text=f"{src}: {display}")
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
                seg = SEGMENTS[self.seg_index]
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

    def next_segment(self):
        if self.seg_index < len(SEGMENTS) - 1:
            self.seg_index += 1
            self.status.set(f"-> {SEGMENTS[self.seg_index]}")
            self._render()
            self._auto_save()
        else:
            self.status.set("Sudah segment terakhir")

    def prev_segment(self):
        if self.seg_index > 0:
            self.seg_index -= 1
            self.status.set(f"<- {SEGMENTS[self.seg_index]}")
            self._render()
            self._auto_save()
        else:
            self.status.set("Sudah segment pertama")

    def reset_current(self):
        seg = SEGMENTS[self.seg_index]
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
            self.active_sources = [s for s in SOURCES if s in new_regions]
            for widget in self.live_frame.winfo_children():
                widget.destroy()
            self.live_labels = {}
            self.live = {src: None for src in self.active_sources}
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

    def export(self):
        try:
            path = self.store.export_txt(OUTPUT_DIR)
            self.status.set(f"Saved: {path.name}")
        except Exception as e:
            self.status.set(f"Export err: {e}")

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
