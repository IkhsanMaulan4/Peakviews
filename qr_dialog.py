"""Small dialog showing the web URL + QR code for phones."""
import tkinter as tk
import webbrowser

from PIL import ImageTk

from web_launcher import WebController, qr_image

QR_SCALE = 5


class WebDialog(tk.Toplevel):
    def __init__(self, root: tk.Tk, controller: WebController, on_stop):
        super().__init__(root)
        self._controller = controller
        self._on_stop = on_stop
        self._photo = None
        self._lan_var = tk.BooleanVar(value=controller.lan)

        self.title("PeakView Web")
        self.attributes("-topmost", True)
        self.resizable(False, False)

        self._qr_label = tk.Label(self, bd=1, relief="solid")
        self._qr_label.pack(padx=14, pady=(14, 6))

        self._url_var = tk.StringVar()
        entry = tk.Entry(self, textvariable=self._url_var, width=48, state="readonly", justify="center")
        entry.pack(padx=14, pady=4)

        tk.Checkbutton(
            self, text="Akses dari HP (WiFi yang sama)", variable=self._lan_var, command=self._toggle_lan
        ).pack(pady=2)
        tk.Label(
            self,
            text="Firewall Windows: pilih 'Private'. Jangan bagikan URL/QR ke orang lain.",
            fg="gray", font=("Arial", 8), wraplength=360,
        ).pack(padx=14)

        row = tk.Frame(self)
        row.pack(pady=10)
        tk.Button(row, text="Buka di browser", command=self._open).grid(row=0, column=0, padx=4)
        tk.Button(row, text="Salin URL", command=self._copy).grid(row=0, column=1, padx=4)
        tk.Button(row, text="Stop server", fg="red", command=self._stop).grid(row=0, column=2, padx=4)

        self.refresh()

    def refresh(self) -> None:
        url = self._controller.share_url()
        if url is None:
            return
        self._url_var.set(url)
        self._photo = ImageTk.PhotoImage(qr_image(url, scale=QR_SCALE))
        self._qr_label.config(image=self._photo)

    def _toggle_lan(self) -> None:
        self._controller.set_lan(self._lan_var.get())
        self.refresh()

    def _open(self) -> None:
        url = self._controller.local_url()
        if url:
            webbrowser.open(url)

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._url_var.get())

    def _stop(self) -> None:
        self._controller.stop()
        self._on_stop()
        self.destroy()
