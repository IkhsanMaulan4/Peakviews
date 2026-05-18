# OCR Debug Window — Design

**Date:** 2026-05-18
**Status:** Approved

## Problem

OCR misreads the YouTube viewer counter during digit-roll animations, and the current pipeline is opaque: `capture_all` returns only the final voted integer. There is no way to inspect *why* a misread happened — was the crop wrong? Did binarization destroy the digit? Did vote tally pick the wrong candidate? The user needs a live view of what tesseract actually sees and how votes resolve.

## Goals

- Live debug window that updates every poll cycle (~0.3s) while open.
- Per source, show: the two binarized image variants (`bin`, `bin_inv`) that are fed to tesseract, the vote tally (Counter of candidate values), and the final selected value.
- Zero overhead when the debug window is closed — main capture path stays unchanged.
- Debug data shown in the window must be from the *same* capture call that updated the main GUI's live values (no drift between windows).

## Non-Goals

- Persisting debug data to disk (no auto-dump). Out of scope; user can screenshot if needed.
- Showing raw OCR text per PSM config or the raw (pre-binarization) crop. User declined these in scoping.
- Anomaly-triggered captures. Live always-on was chosen instead.

## Architecture

Three files touched, one new:

### `capture.py` (modified)

- Existing `capture_all(regions) -> {label: int|None}` is unchanged — callers that don't need debug pay zero overhead.
- New `capture_all_with_debug(regions) -> {label: {"value": int|None, "bin": PIL.Image, "bin_inv": PIL.Image, "votes": Counter}}` for the debug path.
- Internal refactor: `_ocr_image` is split so that the variant generation (`_preprocess`) and the voting loop are reusable. A new helper returns both the voted value and the artifacts (variants + votes Counter). The existing `_ocr_image` becomes a thin wrapper that discards artifacts. This guarantees debug and non-debug code paths execute identical logic — no risk of the debug view showing votes that diverge from what the main path used.

### `debug_window.py` (new)

`OcrDebugWindow(tk.Toplevel)`:
- Constructor takes parent root and the list of active sources, builds one `Frame` per source.
- Each source frame contains: header label (source name + final value, large font), two `Label` widgets side-by-side holding `PhotoImage` references for `bin` / `bin_inv`, and a vote-tally label.
- `update(results)` method called from main thread (`root.after`). For each source: converts PIL images to `PhotoImage` at fixed display width (~200px wide, preserve aspect), reassigns to the label, rebuilds vote string. **Image references are stored on `self` to prevent Tk garbage collection** (well-known Tk gotcha).
- `WM_DELETE_WINDOW` protocol calls a close callback supplied by `main.py` so the parent can null out its reference.
- Toplevel attrs: `-topmost True`, default geometry positions it to the left of the main window so both fit on screen.

### `main.py` (modified)

- New state: `self.debug_window: OcrDebugWindow | None = None`.
- New button "Debug" added to `btn_frame2`, command toggles open/close.
- `_capture_loop` branches on `self.debug_window` (snapshot reference at top of cycle for thread safety):
  - If active: call `capture_all_with_debug`, extract `value` for `self.live`, marshal full results to `dbg.update(results)` via `root.after`.
  - If None: call existing `capture_all` exactly as today.
- Close handler clears `self.debug_window = None`, next cycle reverts to the cheap path automatically.

## Data Flow

```
capture_loop (background thread, every POLL_INTERVAL=0.3s):
    dbg = self.debug_window  # snapshot
    if dbg is not None:
        results = capture_all_with_debug(self.regions)
        live = {k: r["value"] for k, r in results.items()}
        root.after(0, lambda r=results: dbg.update(r))
    else:
        live = capture_all(self.regions)
    self.live = live
    for label, val in live.items():
        self.store.update(seg, label, val)
    root.after(0, self._render)
```

Thread safety: capture loop runs in a background thread; debug window widget updates marshal through `root.after(0, ...)` to the Tk main loop. The `self.debug_window` reference is snapshotted once per cycle — if the user closes the window mid-cycle, the in-flight `dbg.update` call may still fire on a destroyed Toplevel, so `update` must guard with a `try/except tk.TclError` and silently no-op.

## UI Layout

```
┌─ OCR Debug ──────────────────────────┐
│ BOG-YT         final: 1,234          │
│ ┌──────────┐ ┌──────────┐            │
│ │ [bin]    │ │ [bin_inv]│            │
│ └──────────┘ └──────────┘            │
│ votes: 1234×3, 1334×1                │
│ ─────────────────────────            │
│ MPL-YT         final: --             │
│ ... (if other sources active)        │
└──────────────────────────────────────┘
```

- Header font: Arial 12 bold, "{source}    final: {formatted}".
- Image display width fixed at 200px to ensure roll-animation artifacts are visible.
- Vote tally: sorted by count desc, e.g. `votes: 1234×3, 1334×1`. If no votes, show `votes: —`.
- Separator (horizontal `Frame` height=1, bg=gray) between sources.

## Error Handling

- Capture-level exception during a debug cycle: caught by existing `_capture_loop` `try/except`. Debug window shows the last successful update; status bar already surfaces the error message.
- Per-source error inside `_ocr_image_core`: source's debug entry shows `value: None`, empty votes, but pipeline continues for other sources (matches current behavior).
- Image reference GC: prevented by storing `PhotoImage` instances on the window object across updates.
- Closing the window during an in-flight `after` callback: `update` wraps widget mutations in `try/except tk.TclError` and exits silently.

## Testing

Per user preference [[feedback-no-inline-python]] — no inline python smoke tests. Verify by running the app:

1. Launch `python main.py` — main window appears, OCR ticks as today.
2. Click "Debug" — Toplevel appears, shows BOG-YT (only active source per current calibration), bin/bin_inv images visible, vote tally updates every ~0.3s.
3. Observe a roll-animation event in the YouTube counter, confirm the debug window captures the bin variants from that moment and shows the vote dispersion.
4. Close debug window via X — main window unaffected, status bar still updating; verify capture path reverted by confirming no debug-related load (subjective, just no crash).
5. Re-open debug window — works again, no leaked Toplevel.
6. Trigger capture error path (e.g., shrink box to 0) — main GUI shows error in status bar, debug window does not crash.

## Open Risks

- **Refactor of `_ocr_image`**: must preserve current vote ranking (count desc → digit_evidence → value desc). Risk mitigated by keeping `_ocr_image` as the entry point and routing both debug and non-debug through the same core function.
- **Per-cycle PIL→PhotoImage cost**: minor (2 small images converted per source per cycle — 2 for current 1-source setup, 10 for max 5 sources). Acceptable at 0.3s cadence.
