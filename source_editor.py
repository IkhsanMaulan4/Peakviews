"""Modal dialog for renaming, adding, and removing source labels."""
import tkinter as tk
from tkinter import messagebox


def run_source_editor(parent, current_sources: list[str]) -> tuple[list[str], dict[str, str]] | None:
    """Open the source editor. Returns (new_sources, rename_map) on Save, None on Cancel.
    rename_map maps original label -> new label for rows whose text was edited
    (used by callers to migrate calibration regions and peak state).
    """
    dlg = tk.Toplevel(parent)
    dlg.title("Edit Sources")
    dlg.attributes("-topmost", True)
    dlg.transient(parent)
    dlg.grab_set()
    dlg.geometry("380x360+1050+120")
    dlg.resizable(False, True)

    tk.Label(
        dlg, text="Rename, tambah, atau hapus source label:",
        anchor="w", font=("Arial", 10),
    ).pack(fill="x", padx=10, pady=(10, 4))

    list_frame = tk.Frame(dlg)
    list_frame.pack(fill="both", expand=True, padx=10)

    rows: list[dict] = []  # [{"orig": str|None, "var": StringVar, "frame": Frame}]

    def add_row(orig: str | None = None):
        row_f = tk.Frame(list_frame)
        row_f.pack(fill="x", pady=2)
        var = tk.StringVar(value=orig or "")
        entry = tk.Entry(row_f, textvariable=var, font=("Consolas", 11))
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

    for src in current_sources:
        add_row(src)

    btn_row = tk.Frame(dlg)
    btn_row.pack(fill="x", padx=10, pady=6)
    tk.Button(btn_row, text="+ Add Source", command=lambda: add_row(None)).pack(side="left")

    result: dict = {"data": None}

    def on_save():
        new_list: list[str] = []
        rename_map: dict[str, str] = {}
        seen: set[str] = set()
        for r in rows:
            name = r["var"].get().strip()
            if not name:
                messagebox.showerror("Invalid", "Source name tidak boleh kosong.", parent=dlg)
                return
            if name in seen:
                messagebox.showerror("Invalid", f"Source name duplikat: {name}", parent=dlg)
                return
            seen.add(name)
            new_list.append(name)
            if r["orig"] and r["orig"] != name:
                rename_map[r["orig"]] = name
        if not new_list:
            messagebox.showerror("Invalid", "Minimal 1 source harus ada.", parent=dlg)
            return
        result["data"] = (new_list, rename_map)
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    save_row = tk.Frame(dlg)
    save_row.pack(fill="x", padx=10, pady=(0, 10))
    tk.Button(save_row, text="Save", width=10, fg="darkgreen", command=on_save).pack(side="right", padx=4)
    tk.Button(save_row, text="Cancel", width=10, command=on_cancel).pack(side="right")

    dlg.protocol("WM_DELETE_WINDOW", on_cancel)
    dlg.wait_window()
    return result["data"]
