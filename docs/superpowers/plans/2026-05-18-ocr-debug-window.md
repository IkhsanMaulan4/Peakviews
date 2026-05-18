# OCR Debug Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live always-on debug Toplevel that exposes binarized image variants, vote tally, and final value per OCR source — making YouTube viewer-counter roll-animation misreads inspectable.

**Architecture:** Split `_ocr_image` into a reusable core that returns artifacts (value, votes, variants). Add `capture_all_with_debug` alongside the existing `capture_all` so the cheap path keeps zero overhead. New `debug_window.py` defines `OcrDebugWindow(Toplevel)`. `main.py` toggles the window via a new button and branches the capture loop based on whether the window is open.

**Tech Stack:** Python 3.12, tkinter (stdlib), PIL/Pillow, pytesseract, mss

**Testing convention:** Per project preference, no inline python smoke tests — `python` isn't on PATH in the shell tools used during execution. Each task's verification step asks the user to run `python main.py` from their own terminal and confirm behavior. The executing agent should pause and wait for the user's confirmation before committing.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `capture.py` | Modify | Refactor `_ocr_image` to expose `_ocr_image_core`; add `capture_all_with_debug` |
| `debug_window.py` | Create | `OcrDebugWindow(Toplevel)` — UI and `update_debug` method |
| `main.py` | Modify | New Debug button, `self.debug_window` state, branched capture loop |

---

### Task 1: Refactor `_ocr_image` to expose a reusable core

Pure refactor. The existing `_ocr_image` becomes a thin wrapper around `_ocr_image_core` which additionally returns the variants and votes. Behavior must be identical for existing callers.

**Files:**
- Modify: `capture.py:129-154` (the `_ocr_image` function)

- [ ] **Step 1: Replace `_ocr_image` with a core helper + wrapper**

In `capture.py`, replace lines 129-154 with:

```python
def _ocr_image_core(img: Image.Image):
    """Run OCR with multiple preprocessings + PSM modes, vote across readings.
    Returns (final_value, votes_counter, variants_list).
    Variants are kept so debug callers can show what tesseract actually saw.
    """
    variants = list(_preprocess(img))
    votes: Counter = Counter()
    digit_evidence: dict[int, int] = {}
    for _, variant in variants:
        for config in OCR_CONFIGS:
            try:
                text = pytesseract.image_to_string(variant, config=config)
            except Exception:
                continue
            digits_in_text = sum(1 for c in text if c.isdigit())
            for val in _extract_numbers(text):
                votes[val] += 1
                if digits_in_text > digit_evidence.get(val, 0):
                    digit_evidence[val] = digits_in_text

    if not votes:
        return None, votes, variants
    ranked = sorted(
        votes.items(),
        key=lambda kv: (kv[1], digit_evidence.get(kv[0], 0), kv[0]),
        reverse=True,
    )
    return ranked[0][0], votes, variants


def _ocr_image(img: Image.Image):
    """Thin wrapper for callers that only need the voted value."""
    value, _, _ = _ocr_image_core(img)
    return value
```

- [ ] **Step 2: Ask user to verify app still works identically**

Tell user: "Refactor done. Please run `python main.py` from your terminal and confirm OCR readings still appear in the live labels exactly as before. This is a pure refactor — behavior should be unchanged."

Wait for user confirmation before proceeding.

- [ ] **Step 3: Commit**

```bash
git add capture.py
git commit -m "refactor(capture): split _ocr_image into reusable core helper"
```

---

### Task 2: Add `capture_all_with_debug`

Adds a parallel capture function that returns the variants + votes alongside the voted value. Existing `capture_all` is untouched.

**Files:**
- Modify: `capture.py` (append after the existing `capture_all` function, around line 189)

- [ ] **Step 1: Append the new function**

Add at the end of `capture.py`:

```python
def capture_all_with_debug(regions: dict) -> dict:
    """Like capture_all, but also returns the binarized variants and vote
    tally per source so a debug UI can inspect what tesseract saw and how
    the vote resolved. Slower than capture_all (carries PIL images back to
    caller); only use when a debug window is open.

    regions: {label: [x,y,w,h]} ->
        {label: {"value": int|None,
                 "bin": PIL.Image | None,
                 "bin_inv": PIL.Image | None,
                 "votes": Counter}}
    """
    if not regions:
        return {}

    with mss.mss() as sct:
        grabs = {label: _grab(sct, region) for label, region in regions.items()}

    def ocr_one(item):
        label, img = item
        try:
            value, votes, variants = _ocr_image_core(img)
        except Exception:
            return label, {"value": None, "bin": None, "bin_inv": None, "votes": Counter()}
        variant_map = {name: im for name, im in variants}
        return label, {
            "value": value,
            "bin": variant_map.get("bin"),
            "bin_inv": variant_map.get("bin_inv"),
            "votes": votes,
        }

    result = {}
    with ThreadPoolExecutor(max_workers=min(len(grabs), 5)) as ex:
        for label, payload in ex.map(ocr_one, grabs.items()):
            result[label] = payload
    return result
```

- [ ] **Step 2: Ask user to verify import is clean**

Tell user: "New unused function added. Please run `python main.py` and confirm app still starts — no import errors. Function isn't wired up yet."

Wait for user confirmation before proceeding.

- [ ] **Step 3: Commit**

```bash
git add capture.py
git commit -m "feat(capture): add capture_all_with_debug exposing variants and vote tally"
```

---

### Task 3: Create `debug_window.py`

New file containing the `OcrDebugWindow` Toplevel. Built once per open with frames for each active source; `update_debug(results)` mutates labels/images in place.

**Files:**
- Create: `debug_window.py`

- [ ] **Step 1: Create the file**

Full file content:

```python
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
                bin_img = payload.get("bin")
                inv_img = payload.get("bin_inv")

                header.config(text=f"{src}    final: {self._fmt(value)}")
                self._vote_labels[src].config(text=self._fmt_votes(votes))

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
    def _fmt_votes(votes: Counter) -> str:
        if not votes:
            return "votes: --"
        items = sorted(votes.items(), key=lambda kv: (-kv[1], -kv[0]))
        return "votes: " + ", ".join(f"{v:,}×{c}" for v, c in items)
```

- [ ] **Step 2: Commit**

(No app-run verification step — nothing imports the module yet. Syntax errors will surface in Task 4's integration test.)

```bash
git add debug_window.py
git commit -m "feat(debug): add OcrDebugWindow Toplevel for live OCR inspection"
```

---

### Task 4: Wire Debug button + branched capture loop in `main.py`

Hooks the new module into the app: import, state, button, toggle methods, and the capture-loop branch.

**Files:**
- Modify: `main.py:1-12` (imports)
- Modify: `main.py:17-42` (`__init__` — add `self.debug_window`)
- Modify: `main.py:71-77` (`_build_ui` — add Debug button)
- Modify: `main.py:103-119` (`_capture_loop` — branch)
- Modify: `main.py:204-212` (add `toggle_debug` + `_on_debug_close` methods before `_on_close`)

- [ ] **Step 1: Update imports**

Change line 10 of `main.py`:

```python
from capture import capture_all
```

to:

```python
from capture import capture_all, capture_all_with_debug
from debug_window import OcrDebugWindow
```

- [ ] **Step 2: Add `self.debug_window` state**

In `__init__`, after the existing `self.live = {src: None for src in self.active_sources}` line (around line 24), add:

```python
        self.debug_window: OcrDebugWindow | None = None
```

- [ ] **Step 3: Add Debug button to `btn_frame2`**

In `_build_ui` (lines 71-75), replace:

```python
        btn_frame2 = tk.Frame(self.root)
        btn_frame2.pack(**pad)
        tk.Button(btn_frame2, text="Recalibrate", width=11, command=self.recalibrate).grid(row=0, column=0, padx=2)
        tk.Button(btn_frame2, text="Edit Boxes", width=10, command=self.edit_boxes).grid(row=0, column=1, padx=2)
        tk.Button(btn_frame2, text="Export TXT", width=11, command=self.export).grid(row=0, column=2, padx=2)
```

with:

```python
        btn_frame2 = tk.Frame(self.root)
        btn_frame2.pack(**pad)
        tk.Button(btn_frame2, text="Recalibrate", width=11, command=self.recalibrate).grid(row=0, column=0, padx=2)
        tk.Button(btn_frame2, text="Edit Boxes", width=10, command=self.edit_boxes).grid(row=0, column=1, padx=2)
        tk.Button(btn_frame2, text="Export TXT", width=11, command=self.export).grid(row=0, column=2, padx=2)
        tk.Button(btn_frame2, text="Debug", width=7, command=self.toggle_debug).grid(row=0, column=3, padx=2)
```

- [ ] **Step 4: Branch the capture loop**

Replace `_capture_loop` (lines 103-119) with:

```python
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
```

- [ ] **Step 5: Add toggle + close methods**

Insert these methods into the `PeakViewApp` class. Place them after the `export` method (around line 209) and before `_on_close`:

```python
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
```

- [ ] **Step 6: Ask user to verify integration**

Tell user: "Integration done. Please run `python main.py` and verify:

1. Main window appears with a new 'Debug' button next to 'Export TXT'.
2. Click Debug — a Toplevel titled 'OCR Debug' appears, shows the BOG-YT entry with bin/bin_inv image previews side-by-side and a vote tally line.
3. Numbers update every ~0.3s — the binarized images visibly refresh, votes change as digits roll.
4. Close the debug window via the X button — main window keeps ticking, status bar shows 'Debug window closed'.
5. Click Debug again — window re-appears cleanly, no errors.
6. Click Debug while window is open — closes via toggle, status bar shows 'Debug window closed'.

Bonus: catch a YouTube counter roll animation while debug is open — note whether vote tally shows dispersion (e.g., `votes: 1234×2, 1334×2`) at that moment."

Wait for user confirmation before committing.

- [ ] **Step 7: Commit**

```bash
git add main.py
git commit -m "feat(main): add Debug button + live OCR debug window integration"
```

---

## Known Limitations (out of scope)

- Debug window captures `active_sources` at construction. If the user recalibrates while the debug window is open, the window will continue showing stale source list. Workaround: close and reopen the debug window after recalibration.
- Debug images use NEAREST resize (no smoothing) so individual binarized pixels are visible. This is intentional — smoothed display would obscure exactly the artifacts being debugged.
