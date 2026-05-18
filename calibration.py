"""Transparent overlay calibration: drag 4 boxes over live screen to mark viewer count positions."""
import json
import tkinter as tk
from pathlib import Path
import mss
from segments import SOURCES
from paths import app_dir

CALIBRATION_FILE = app_dir() / "calibration.json"

OVERLAY_ALPHA = 0.35  # 0=fully transparent, 1=opaque. Lower = see streams more clearly.

# Locked to laptop's native resolution so calibration always covers the full screen
# regardless of OS DPI scaling or detected monitor metrics.
TARGET_SCREEN_W = 1920
TARGET_SCREEN_H = 1080


def load_calibration():
    if not CALIBRATION_FILE.exists():
        return None
    try:
        data = json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
        active = {k: v for k, v in data.items() if k in SOURCES and v}
        if active:
            return active
    except Exception:
        pass
    return None


def save_calibration(regions: dict):
    CALIBRATION_FILE.write_text(json.dumps(regions, indent=2), encoding="utf-8")


def run_calibration(on_done=None, parent=None):
    """Open a transparent fullscreen overlay so the user can drag boxes over the live screen.

    If `parent` is given, opens as a modal Toplevel. Otherwise creates a standalone Tk root.
    """
    # Locked to 1920x1080 (laptop native). monitor_left/top still come from mss
    # so coords stay correct on multi-monitor setups.
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        monitor_left = monitor["left"]
        monitor_top = monitor["top"]
    screen_w = TARGET_SCREEN_W
    screen_h = TARGET_SCREEN_H

    standalone = parent is None
    if standalone:
        root = tk.Tk()
    else:
        root = tk.Toplevel(parent)
    root.title("Calibration")

    # Fullscreen transparent overlay — force 1920x1080 to match laptop native res
    screen_tk_w = TARGET_SCREEN_W
    screen_tk_h = TARGET_SCREEN_H
    root.geometry(f"{screen_tk_w}x{screen_tk_h}+0+0")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", OVERLAY_ALPHA)
    root.configure(bg="gray10")
    root.lift()
    root.update_idletasks()

    # Tk coords -> mss screen coords scaling (for high-DPI safety)
    scale_x = screen_w / screen_tk_w
    scale_y = screen_h / screen_tk_h

    canvas = tk.Canvas(
        root,
        width=screen_tk_w,
        height=screen_tk_h,
        cursor="cross",
        bg="gray10",
        highlightthickness=0,
    )
    canvas.pack()

    label_text = tk.StringVar()
    info = tk.Label(
        root,
        textvariable=label_text,
        bg="black",
        fg="yellow",
        font=("Arial", 16, "bold"),
        padx=16,
        pady=8,
    )
    info.place(x=20, y=20)

    state = {"index": 0, "start": None, "rect": None, "regions": {}, "skipped": []}

    def update_info():
        idx = state["index"]
        if idx < len(SOURCES):
            label_text.set(
                f"[{idx + 1}/{len(SOURCES)}] Drag box di angka viewer: {SOURCES[idx]}    "
                f"(S = skip, R = reset semua, Enter = simpan, Esc = batal)"
            )
        else:
            n = len(state["regions"])
            label_text.set(
                f"Selesai! {n}/{len(SOURCES)} source dikalibrasi. "
                f"Tekan ENTER untuk simpan, R untuk ulangi, Esc batal."
            )

    def on_press(event):
        if state["index"] >= len(SOURCES):
            return
        state["start"] = (event.x, event.y)
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="lime", width=4
        )

    def on_drag(event):
        if not state["start"] or state["index"] >= len(SOURCES):
            return
        x0, y0 = state["start"]
        canvas.coords(state["rect"], x0, y0, event.x, event.y)

    def on_release(event):
        if not state["start"] or state["index"] >= len(SOURCES):
            return
        x0, y0 = state["start"]
        x1, y1 = event.x, event.y
        lx, rx = min(x0, x1), max(x0, x1)
        ty, by = min(y0, y1), max(y0, y1)
        if (rx - lx) < 5 or (by - ty) < 5:
            canvas.delete(state["rect"])
            state["rect"] = None
            state["start"] = None
            return
        # Convert Tk canvas coords -> actual screen coords (mss space)
        region = [
            int(lx * scale_x) + monitor_left,
            int(ty * scale_y) + monitor_top,
            int((rx - lx) * scale_x),
            int((by - ty) * scale_y),
        ]
        label = SOURCES[state["index"]]
        state["regions"][label] = region
        # Permanent rectangle with bright color + label tag for visibility
        canvas.create_rectangle(lx, ty, rx, by, outline="cyan", width=3)
        canvas.create_text(
            lx + 4,
            ty - 12,
            text=label,
            anchor="w",
            fill="cyan",
            font=("Arial", 13, "bold"),
        )
        state["index"] += 1
        state["start"] = None
        state["rect"] = None
        update_info()

    def reset_all():
        canvas.delete("all")
        state["index"] = 0
        state["start"] = None
        state["rect"] = None
        state["regions"] = {}
        state["skipped"] = []
        update_info()

    def on_key(event):
        key = event.keysym.lower()
        if event.keysym == "Escape":
            root.destroy()
        elif key == "r":
            reset_all()
        elif key == "s" and state["index"] < len(SOURCES):
            label = SOURCES[state["index"]]
            state["skipped"].append(label)
            # Show skip marker stacked in top-left, below the info label
            canvas.create_rectangle(
                18,
                72 + len(state["skipped"]) * 22 - 4,
                240,
                72 + len(state["skipped"]) * 22 + 18,
                fill="black",
                outline="",
            )
            canvas.create_text(
                24,
                72 + len(state["skipped"]) * 22 + 6,
                text=f"[SKIP] {label}",
                anchor="w",
                fill="orange",
                font=("Arial", 12, "bold"),
            )
            state["index"] += 1
            state["start"] = None
            if state["rect"]:
                canvas.delete(state["rect"])
                state["rect"] = None
            update_info()
        elif event.keysym == "Return" and state["index"] >= len(SOURCES):
            if not state["regions"]:
                label_text.set("Minimal 1 source harus dikalibrasi! Tekan R untuk ulangi.")
                return
            save_calibration(state["regions"])
            root.destroy()
            if on_done:
                on_done(state["regions"])

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Key>", on_key)
    root.focus_force()

    update_info()
    if standalone:
        root.mainloop()
    else:
        root.grab_set()
        root.wait_window()
    return state["regions"] if state["index"] >= len(SOURCES) else None


HANDLE_SIZE = 7
MIN_BOX = 20
HANDLE_NAMES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


def _handle_positions(lx, ty, rx, by):
    mx = (lx + rx) / 2
    my = (ty + by) / 2
    return {
        "nw": (lx, ty), "n": (mx, ty), "ne": (rx, ty),
        "e": (rx, my), "se": (rx, by), "s": (mx, by),
        "sw": (lx, by), "w": (lx, my),
    }


def run_edit_calibration(regions: dict, on_done=None, parent=None):
    """Open transparent overlay with existing boxes for resize / single-box redraw.

    Returns the new regions dict if saved (Enter), otherwise None.
    """
    if not regions:
        return None

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        monitor_left = monitor["left"]
        monitor_top = monitor["top"]
    screen_w = TARGET_SCREEN_W
    screen_h = TARGET_SCREEN_H

    standalone = parent is None
    if standalone:
        root = tk.Tk()
    else:
        root = tk.Toplevel(parent)
    root.title("Edit Calibration")

    screen_tk_w = TARGET_SCREEN_W
    screen_tk_h = TARGET_SCREEN_H
    root.geometry(f"{screen_tk_w}x{screen_tk_h}+0+0")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", OVERLAY_ALPHA)
    root.configure(bg="gray10")
    root.lift()
    root.update_idletasks()

    scale_x = screen_w / screen_tk_w
    scale_y = screen_h / screen_tk_h

    canvas = tk.Canvas(
        root, width=screen_tk_w, height=screen_tk_h,
        bg="gray10", highlightthickness=0,
    )
    canvas.pack()

    label_text = tk.StringVar()
    info = tk.Label(
        root, textvariable=label_text, bg="black", fg="yellow",
        font=("Arial", 14, "bold"), padx=12, pady=6,
    )
    info.place(x=20, y=20)

    # screen-coord region [sx, sy, sw, sh] -> canvas-coord rect [lx, ty, rx, by]
    boxes = {}
    for label, reg in regions.items():
        sx, sy, sw, sh = reg
        lx = (sx - monitor_left) / scale_x
        ty = (sy - monitor_top) / scale_y
        rx = lx + sw / scale_x
        by = ty + sh / scale_y
        boxes[label] = [lx, ty, rx, by]

    state = {
        "selected": None,
        "drag_handle": None,
        "drag_start": None,
        "drag_start_box": None,
        "redraw_target": None,
        "saved": None,
    }

    def update_info():
        if state["redraw_target"]:
            label_text.set(
                f"REDRAW [{state['redraw_target']}]: drag kotak baru. (Esc batal redraw)"
            )
        elif state["selected"]:
            label_text.set(
                f"Selected: {state['selected']}  |  Drag handle kuning untuk resize,  "
                f"R = redraw,  klik kotak lain untuk pilih,  Enter = simpan,  Esc = batal"
            )
        else:
            label_text.set(
                "Klik kotak untuk pilih.  Enter = simpan,  Esc = batal"
            )

    def redraw_canvas():
        canvas.delete("all")
        for label, (lx, ty, rx, by) in boxes.items():
            if label == state["redraw_target"]:
                continue
            is_sel = label == state["selected"]
            outline = "yellow" if is_sel else "cyan"
            width = 4 if is_sel else 2
            canvas.create_rectangle(lx, ty, rx, by, outline=outline, width=width)
            canvas.create_text(
                lx + 4, ty - 12, text=label, anchor="w",
                fill=outline, font=("Arial", 13, "bold"),
            )
        sel = state["selected"]
        if sel and sel in boxes and not state["redraw_target"]:
            lx, ty, rx, by = boxes[sel]
            for _, (hx, hy) in _handle_positions(lx, ty, rx, by).items():
                canvas.create_rectangle(
                    hx - HANDLE_SIZE, hy - HANDLE_SIZE,
                    hx + HANDLE_SIZE, hy + HANDLE_SIZE,
                    fill="yellow", outline="black", width=1,
                )
        update_info()

    def find_handle_at(x, y):
        sel = state["selected"]
        if not sel or sel not in boxes:
            return None
        lx, ty, rx, by = boxes[sel]
        for name, (hx, hy) in _handle_positions(lx, ty, rx, by).items():
            if abs(x - hx) <= HANDLE_SIZE and abs(y - hy) <= HANDLE_SIZE:
                return name
        return None

    def find_box_at(x, y):
        for label, (lx, ty, rx, by) in boxes.items():
            lo_x, hi_x = min(lx, rx), max(lx, rx)
            lo_y, hi_y = min(ty, by), max(ty, by)
            if lo_x <= x <= hi_x and lo_y <= y <= hi_y:
                return label
        return None

    def on_press(event):
        if state["redraw_target"]:
            state["drag_start"] = (event.x, event.y)
            return
        handle = find_handle_at(event.x, event.y)
        if handle:
            state["drag_handle"] = handle
            state["drag_start"] = (event.x, event.y)
            state["drag_start_box"] = list(boxes[state["selected"]])
            return
        label = find_box_at(event.x, event.y)
        if label != state["selected"]:
            state["selected"] = label
            redraw_canvas()

    def on_drag(event):
        if state["redraw_target"] and state["drag_start"]:
            x0, y0 = state["drag_start"]
            canvas.delete("temp_rect")
            canvas.create_rectangle(
                x0, y0, event.x, event.y,
                outline="lime", width=3, tags="temp_rect",
            )
            return
        if state["drag_handle"] and state["drag_start"]:
            sel = state["selected"]
            lx0, ty0, rx0, by0 = state["drag_start_box"]
            dx = event.x - state["drag_start"][0]
            dy = event.y - state["drag_start"][1]
            h = state["drag_handle"]
            lx, ty, rx, by = lx0, ty0, rx0, by0
            if "w" in h:
                lx = lx0 + dx
            if "e" in h:
                rx = rx0 + dx
            if "n" in h:
                ty = ty0 + dy
            if "s" in h:
                by = by0 + dy
            if rx - lx < MIN_BOX:
                if "w" in h:
                    lx = rx - MIN_BOX
                else:
                    rx = lx + MIN_BOX
            if by - ty < MIN_BOX:
                if "n" in h:
                    ty = by - MIN_BOX
                else:
                    by = ty + MIN_BOX
            boxes[sel] = [lx, ty, rx, by]
            redraw_canvas()

    def on_release(event):
        if state["redraw_target"] and state["drag_start"]:
            x0, y0 = state["drag_start"]
            x1, y1 = event.x, event.y
            canvas.delete("temp_rect")
            if abs(x1 - x0) >= 5 and abs(y1 - y0) >= 5:
                lx, rx = min(x0, x1), max(x0, x1)
                ty, by = min(y0, y1), max(y0, y1)
                boxes[state["redraw_target"]] = [lx, ty, rx, by]
                state["selected"] = state["redraw_target"]
                state["redraw_target"] = None
                state["drag_start"] = None
                redraw_canvas()
            else:
                state["drag_start"] = None
            return
        state["drag_handle"] = None
        state["drag_start"] = None
        state["drag_start_box"] = None

    def commit_save():
        new_regions = {}
        for label, (lx, ty, rx, by) in boxes.items():
            lx, rx = min(lx, rx), max(lx, rx)
            ty, by = min(ty, by), max(ty, by)
            new_regions[label] = [
                int(lx * scale_x) + monitor_left,
                int(ty * scale_y) + monitor_top,
                int((rx - lx) * scale_x),
                int((by - ty) * scale_y),
            ]
        save_calibration(new_regions)
        state["saved"] = new_regions
        root.destroy()
        if on_done:
            on_done(new_regions)

    def on_key(event):
        key = event.keysym.lower()
        if event.keysym == "Escape":
            if state["redraw_target"]:
                state["redraw_target"] = None
                state["drag_start"] = None
                canvas.delete("temp_rect")
                redraw_canvas()
            else:
                root.destroy()
        elif key == "r" and state["selected"] and not state["redraw_target"]:
            state["redraw_target"] = state["selected"]
            redraw_canvas()
        elif event.keysym == "Return":
            commit_save()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Key>", on_key)
    root.focus_force()

    redraw_canvas()
    if standalone:
        root.mainloop()
    else:
        root.grab_set()
        root.wait_window()
    return state["saved"]


if __name__ == "__main__":
    run_calibration()
