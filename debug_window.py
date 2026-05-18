"""Live debug Toplevel that shows per-source binarized variants + vote tally + final value."""
import tkinter as tk
from collections import Counter
from PIL import Image, ImageTk

_DISPLAY_WIDTH = 200  # px wide for binarized variant display


class OcrDebugWindow(tk.Toplevel):
    """Always-on-top window. Call .update_debug(results) from the Tk main thread
    with the dict returned by capture.capture_all_with_debug.
    """

    def __init__(self, parent: tk.Misc, sources: list[str], on_close):
        super().__init__(parent)
        self.title("OCR Debug")
        self.attributes("-topmost", True)
        try:
            self.geometry("+50+50")
        except Exception:
            pass
        self._on_close = on_close
        self._photo_refs: dict[str, list[ImageTk.PhotoImage]] = {}
        self._headers: dict[str, tk.Label] = {}
        self._image_labels: dict[str, tuple[tk.Label, tk.Label]] = {}
        self._vote_labels: dict[str, tk.Label] = {}

        for src in sources:
            frame = tk.Frame(self, padx=8, pady=6)
            frame.pack(fill="x")
            header = tk.Label(
                frame, text=f"{src}    final: --",
                font=("Arial", 12, "bold"), anchor="w",
            )
            header.pack(fill="x")
            img_row = tk.Frame(frame)
            img_row.pack(anchor="w", pady=4)
            bin_lbl = tk.Label(img_row, text="[bin]", bd=1, relief="solid")
            bin_lbl.pack(side="left", padx=(0, 6))
            inv_lbl = tk.Label(img_row, text="[bin_inv]", bd=1, relief="solid")
            inv_lbl.pack(side="left")
            votes_lbl = tk.Label(
                frame, text="votes: --",
                font=("Consolas", 9), anchor="w", fg="dimgray",
            )
            votes_lbl.pack(fill="x")
            sep = tk.Frame(self, height=1, bg="gray70")
            sep.pack(fill="x")

            self._headers[src] = header
            self._image_labels[src] = (bin_lbl, inv_lbl)
            self._vote_labels[src] = votes_lbl
            self._photo_refs[src] = []

        self.protocol("WM_DELETE_WINDOW", self._handle_close)

    def _handle_close(self):
        try:
            self._on_close()
        finally:
            self.destroy()

    def update_debug(self, results: dict):
        """Refresh display from a capture_all_with_debug result. Safe on a
        destroyed window — silently no-ops on TclError.
        """
        try:
            for src, header in self._headers.items():
                payload = results.get(src)
                if payload is None:
                    continue
                value = payload.get("value")
                votes: Counter = payload.get("votes") or Counter()
                conf: dict = payload.get("conf") or {}
                bin_img = payload.get("bin")
                inv_img = payload.get("bin_inv")

                header.config(text=f"{src}    final: {self._fmt(value)}")
                self._vote_labels[src].config(text=self._fmt_votes(votes, conf))

                refs: list[ImageTk.PhotoImage] = []
                bin_lbl, inv_lbl = self._image_labels[src]
                for src_img, lbl, placeholder in (
                    (bin_img, bin_lbl, "[bin]"),
                    (inv_img, inv_lbl, "[bin_inv]"),
                ):
                    if src_img is None:
                        lbl.config(image="", text=placeholder)
                        continue
                    photo = ImageTk.PhotoImage(self._fit_width(src_img, _DISPLAY_WIDTH))
                    lbl.config(image=photo, text="")
                    refs.append(photo)
                self._photo_refs[src] = refs
        except tk.TclError:
            pass  # window was destroyed mid-update

    @staticmethod
    def _fit_width(img: Image.Image, target_w: int) -> Image.Image:
        if img.width == target_w:
            return img
        ratio = target_w / img.width
        new_size = (target_w, max(1, int(img.height * ratio)))
        return img.resize(new_size, Image.NEAREST)

    @staticmethod
    def _fmt(value):
        if value is None:
            return "--"
        return f"{value:,}"

    @staticmethod
    def _fmt_votes(votes: Counter, conf: dict | None = None) -> str:
        if not votes:
            return "votes: --"
        # Rank for display: vote count, then confidence, then value — mirrors
        # _ocr_image_core's tie-break so the winning candidate sorts first.
        items = sorted(
            votes.items(),
            key=lambda kv: (-kv[1], -(conf or {}).get(kv[0], 0.0), -kv[0]),
        )
        parts = []
        for v, c in items:
            if conf and v in conf:
                parts.append(f"{v:,}×{c} ({int(conf[v])})")
            else:
                parts.append(f"{v:,}×{c}")
        return "votes: " + ", ".join(parts)
