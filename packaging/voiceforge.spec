# -*- mode: python ; coding: utf-8 -*-
# Build from repo root:
#   .\.venv\Scripts\pyinstaller.exe packaging\voiceforge.spec

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None
ROOT = Path(SPECPATH).resolve().parent

# Bundle optional FFmpeg for MP3/OGG export
_ffmpeg = ROOT / "packaging" / "ffmpeg" / "ffmpeg.exe"

datas = [
    (str(ROOT / "assets" / "styles" / "dark.qss"), "assets/styles"),
    (str(ROOT / "assets" / "styles" / "light.qss"), "assets/styles"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_LICENSES.md"), "."),
    (str(ROOT / "README.md"), "."),
]
if _ffmpeg.is_file():
    datas.append((str(_ffmpeg), "ffmpeg"))

hiddenimports = [
    "kokoro_onnx",
    "onnxruntime",
    "soundfile",
    "espeakng_loader",
    "phonemizer",
    "psutil",
    "pypdf",
    "docx",
    "bs4",
    "ebooklib",
    "PySide6.QtMultimedia",
    "PySide6.QtNetwork",
    "app",
    "app.cli",
    "app.ui.main_window",
    "app.tts.kokoro",
    "app.tts.piper",
]

binaries = []

# Bundle kokoro / onnxruntime / espeak data files when available
for pkg in ("kokoro_onnx", "onnxruntime", "espeakng_loader", "soundfile"):
    try:
        pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_bins
        hiddenimports += pkg_hidden
    except Exception:
        pass

# phonemizer language data
try:
    datas += collect_data_files("phonemizer")
except Exception:
    pass

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "IPython"],
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
    name="VoiceForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icons" / "voiceforge.ico")
    if (ROOT / "assets" / "icons" / "voiceforge.ico").is_file()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="VoiceForge",
)
