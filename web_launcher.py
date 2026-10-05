"""Owns the lifecycle of the local web server (no tkinter): start once, restart, stop."""
import sys
from pathlib import Path

from PIL import Image
import segno

from web_api import WebContext
from webserver import WebServer, lan_ip

LOOPBACK = "127.0.0.1"


def default_web_dir() -> Path:
    """web/ next to the sources, or inside the PyInstaller bundle when frozen."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "web"
    return Path(__file__).parent / "web"


def qr_image(text: str, scale: int = 6, border: int = 2) -> Image.Image:
    """Render `text` as a QR code PIL image (black on white, crisp pixels)."""
    code = segno.make(text, error="m")
    matrix = [list(row) for row in code.matrix]
    size = len(matrix) + 2 * border
    img = Image.new("L", (size, size), 255)
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                img.putpixel((x + border, y + border), 0)
    return img.resize((size * scale, size * scale), Image.NEAREST)


class WebController:
    def __init__(self, ctx: WebContext, web_dir=None):
        self._ctx = ctx
        self._web_dir = Path(web_dir) if web_dir else default_web_dir()
        self._server = None
        self.lan = True

    @property
    def server(self):
        return self._server

    @property
    def running(self) -> bool:
        return self._server is not None and self._server.running

    def ensure_started(self, lan: bool = None) -> WebServer:
        """Start the server if needed; calling again returns the same instance."""
        if lan is not None and not self.running:
            self.lan = lan
        if not self.running:
            host = "0.0.0.0" if self.lan else LOOPBACK
            self._server = WebServer(self._ctx, self._web_dir, host=host)
            self._server.start()
        return self._server

    def set_lan(self, lan: bool) -> None:
        """Switch between LAN and loopback-only; a restart also rotates the token."""
        if lan == self.lan and self.running:
            return
        was_running = self.running
        self.stop()
        self.lan = lan
        if was_running:
            self.ensure_started()

    def stop(self) -> None:
        if self._server is not None:
            self._server.stop()
            self._server = None

    def local_url(self):
        return self._server.url(LOOPBACK) if self.running else None

    def share_url(self):
        if not self.running:
            return None
        return self._server.url(lan_ip() if self.lan else LOOPBACK)
