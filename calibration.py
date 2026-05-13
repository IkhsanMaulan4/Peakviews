"""Transparent overlay calibration: drag 4 boxes over live screen to mark viewer count positions."""
import json
import tkinter as tk
from pathlib import Path
import mss
from segments import SOURCES

CALIBRATION_FILE = Path(__file__).parent / "calibration.json"

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


if __name__ == "__main__":
    run_calibration()
