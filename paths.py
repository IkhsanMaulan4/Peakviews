"""Resolve runtime paths so the app works both as a PyInstaller bundle and from source."""
import sys
from pathlib import Path


def app_dir() -> Path:
    """User-facing app folder for calibration.json and output/.
    - Frozen (PyInstaller bundle): the folder containing PeakView.exe.
    - Source: the repo root (parent of this file).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _bundle_resources_dir() -> Path:
    """Where PyInstaller put our `datas` files at runtime.
    - --onedir frozen: _internal/ sibling of the .exe (set via sys._MEIPASS).
    - --onefile frozen: the temp-extraction dir (also sys._MEIPASS).
    - Source: repo root.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).parent


def bundled_tesseract() -> Path | None:
    """Return path to bundled tesseract.exe if present, else None.
    Frozen: _MEIPASS/tesseract/tesseract.exe (PyInstaller datas layout).
    Source: vendor/tesseract/tesseract.exe (same binary we ship in the bundle),
    so `python main.py` works without a system-wide Tesseract install.
    """
    for candidate in (
        _bundle_resources_dir() / "tesseract" / "tesseract.exe",
        Path(__file__).parent / "vendor" / "tesseract" / "tesseract.exe",
    ):
        if candidate.exists():
            return candidate
    return None
