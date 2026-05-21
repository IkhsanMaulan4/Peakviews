# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_all

# Anaconda Python ships tcl86t.dll, tk86t.dll, libmpdec, liblzma, etc. in
# <base_prefix>/Library/bin (instead of the standard <base>/DLLs). That dir
# isn't on PATH when building from a venv, so PyInstaller's bindepend resolver
# can't find them and silently drops them — _tkinter.pyd then fails to load
# in the bundled .exe. Prepending the directory makes bindepend see them.
_lib_bin = os.path.join(sys.base_prefix, "Library", "bin")
if os.path.isdir(_lib_bin):
    os.environ["PATH"] = _lib_bin + os.pathsep + os.environ.get("PATH", "")

# RapidOCR ships ONNX model files + per-model yaml configs that pyinstaller's
# import scanner can't see (they're loaded by string path at runtime).
_rapidocr_datas, _rapidocr_binaries, _rapidocr_hidden = collect_all("rapidocr_onnxruntime")

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_rapidocr_binaries,
    datas=_rapidocr_datas,
    hiddenimports=['PIL._tkinter_finder', 'PIL.ImageTk', *_rapidocr_hidden],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PeakView',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PeakView',
)
