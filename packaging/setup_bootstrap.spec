# -*- mode: python ; coding: utf-8 -*-
# Builds dist/installer/VoiceForge Setup.exe (self-contained)
# Requires dist/VoiceForge-Portable.zip from the app build.

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
ZIP = ROOT / "dist" / "VoiceForge-Portable.zip"
if not ZIP.is_file():
    raise SystemExit(f"Missing payload: {ZIP}. Run scripts/build_installer.ps1 first.")

a = Analysis(
    [str(ROOT / "packaging" / "setup_bootstrap.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ZIP), ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "shiboken6", "numpy", "onnxruntime", "torch"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VoiceForge Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
