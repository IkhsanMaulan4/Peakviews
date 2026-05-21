"""Modal dialog for renaming, adding, and removing segment labels."""
import tkinter as tk
from tkinter import messagebox


def run_segment_editor(parent, current_segments: list[str]) -> tuple[list[str], dict[str, str]] | None:
    """Open the segment editor. Returns (new_segments, rename_map) on Save, None on Cancel.
    rename_map maps original label -> new label for rows whose text was edited
    (used by callers to migrate peak state across renames).
    """
    dlg = tk.Toplevel(parent)
    dlg.title("Edit Segments")
    dlg.attributes("-topmost", True)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.geometry("440x520+1000+80")
    dlg.resizable(False, True)

    tk.Label(
        dlg, text="Rename, tambah, atau hapus segment:",
        anchor="w", font=("Arial", 10),
    ).pack(fill="x", padx=10, pady=(10, 4))

    # Scrollable list — segment count can exceed visible area.
    canvas_frame = tk.Frame(dlg)
    canvas_frame.pack(fill="both", expand=True, padx=10)
    canvas = tk.Canvas(canvas_frame, highlightthickness=0)
    scrollbar = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
    list_frame = tk.Frame(canvas)
    list_frame.bind(
        "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=list_frame, anchor="nw", width=400)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    rows: list[dict] = []  # [{"orig": str|None, "var": StringVar, "frame": Frame}]

    def add_row(orig: str | None = None):
        row_f = tk.Frame(list_frame)
        row_f.pack(fill="x", pady=2)
        var = tk.StringVar(value=orig or "")
        entry = tk.Entry(row_f, textvariable=var, font=("Consolas", 10))
        entry.pack(side="left", fill="x", expand=True)
        row_dict = {"orig": orig, "var": var, "frame": row_f}

        def remove():
            row_f.destroy()
            if row_dict in rows:
                rows.remove(row_dict)

        tk.Button(row_f, text="×", width=2, fg="red", command=remove).pack(side="right", padx=(4, 0))
        rows.append(row_dict)
        if orig is None:
            entry.focus_set()
            dlg.after_idle(lambda: canvas.yview_moveto(1.0))

    for seg in current_segments:
        add_row(seg)

    btn_row = tk.Frame(dlg)
    btn_row.pack(fill="x", padx=10, pady=6)
    tk.Button(btn_row, text="+ Add Segment", command=lambda: add_row(None)).pack(side="left")

    result: dict = {"data": None}

    def on_save():
        new_list: list[str] = []
        rename_map: dict[str, str] = {}
        seen: set[str] = set()
        for r in rows:
            name = r["var"].get().strip()
            if not name:
                messagebox.showerror("Invalid", "Segment name tidak boleh kosong.", parent=dlg)
                return
            if name in seen:
                messagebox.showerror("Invalid", f"Segment name duplikat: {name}", parent=dlg)
                return
            seen.add(name)
            new_list.append(name)
            if r["orig"] and r["orig"] != name:
                rename_map[r["orig"]] = name
        if not new_list:
            messagebox.showerror("Invalid", "Minimal 1 segment harus ada.", parent=dlg)
            return
        result["data"] = (new_list, rename_map)
        _cleanup_and_close()

    def on_cancel():
        _cleanup_and_close()

    def _cleanup_and_close():
        try:
            canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        dlg.destroy()

    save_row = tk.Frame(dlg)
    save_row.pack(fill="x", padx=10, pady=(0, 10))
    tk.Button(save_row, text="Save", width=10, fg="darkgreen", command=on_save).pack(side="right", padx=4)
    tk.Button(save_row, text="Cancel", width=10, command=on_cancel).pack(side="right")

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.wait_window()
    return result["data"]
