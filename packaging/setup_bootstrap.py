"""
VoiceForge Windows installer bootstrap.

Bundled as a single "VoiceForge Setup.exe" that extracts the portable app
into the user's Programs folder and creates Start Menu / Desktop shortcuts.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


APP_NAME = "VoiceForge"
APP_VERSION = "1.0.0"
EXE_NAME = "VoiceForge.exe"


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / name
    # Dev: look next to this file / dist
    here = Path(__file__).resolve().parent
    candidates = [
        here / name,
        here.parent / "dist" / name,
        here.parent / "dist" / "VoiceForge-Portable.zip",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return here / name


def default_install_dir() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local / "Programs" / APP_NAME


def message(title: str, text: str, error: bool = False) -> None:
    flags = 0x10 if error else 0x40
    ctypes.windll.user32.MessageBoxW(0, text, title, flags)


def ask_yes_no(title: str, text: str) -> bool:
    # MB_YESNO | MB_ICONQUESTION
    result = ctypes.windll.user32.MessageBoxW(0, text, title, 0x04 | 0x20)
    return result == 6  # IDYES


def create_shortcut(link_path: Path, target: Path, workdir: Path, description: str) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{str(link_path).replace("'", "''")}')
$sc.TargetPath = '{str(target).replace("'", "''")}'
$sc.WorkingDirectory = '{str(workdir).replace("'", "''")}'
$sc.Description = '{description.replace("'", "''")}'
$sc.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=True,
        capture_output=True,
        text=True,
    )


def find_payload() -> Path:
    # Preferred embedded name inside the frozen installer
    for name in ("VoiceForge-Portable.zip", "payload.zip"):
        p = resource_path(name)
        if p.is_file():
            return p
    # Adjacent to Setup.exe when not embedded
    if getattr(sys, "frozen", False):
        side = Path(sys.executable).resolve().parent / "VoiceForge-Portable.zip"
        if side.is_file():
            return side
    raise FileNotFoundError(
        "Installer payload not found (VoiceForge-Portable.zip). Rebuild the installer package."
    )


def install(dest: Path, desktop: bool) -> Path:
    payload = find_payload()
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="vfsetup_") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(payload, "r") as zf:
            zf.extractall(tmp_path)
        # Zip may contain files at root or under VoiceForge/
        extracted = tmp_path
        nested = tmp_path / "VoiceForge"
        if nested.is_dir() and (nested / EXE_NAME).is_file():
            extracted = nested
        elif not (tmp_path / EXE_NAME).is_file():
            # Find folder containing the exe
            found = next(tmp_path.rglob(EXE_NAME), None)
            if not found:
                raise RuntimeError("VoiceForge.exe missing from installer payload")
            extracted = found.parent
        # Copy tree
        for item in extracted.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)

    exe = dest / EXE_NAME
    if not exe.is_file():
        raise RuntimeError(f"Installation failed — {EXE_NAME} not found in {dest}")

    start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
    create_shortcut(start_menu / f"{APP_NAME}.lnk", exe, dest, f"{APP_NAME} Offline TTS")

    if desktop:
        desktop_dir = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
        create_shortcut(desktop_dir / f"{APP_NAME}.lnk", exe, dest, f"{APP_NAME} Offline TTS")

    # Uninstall helper
    uninstall = dest / "Uninstall VoiceForge.bat"
    uninstall.write_text(
        f"""@echo off
echo Uninstalling {APP_NAME}...
rmdir /s /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP_NAME}" 2>nul
del "%USERPROFILE%\\Desktop\\{APP_NAME}.lnk" 2>nul
cd /d "%TEMP%"
rmdir /s /q "{dest}"
echo Done.
pause
""",
        encoding="utf-8",
    )
    return exe


def main() -> int:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VoiceForge.Setup")
    except Exception:
        pass

    if not ask_yes_no(
        f"{APP_NAME} Setup",
        f"Install {APP_NAME} {APP_VERSION}?\n\n"
        f"Destination:\n{default_install_dir()}\n\n"
        "No Python install is required. TTS models are downloaded later inside the app.",
    ):
        return 0

    desktop = ask_yes_no(f"{APP_NAME} Setup", "Create a Desktop shortcut?")
    dest = default_install_dir()
    try:
        exe = install(dest, desktop=desktop)
    except Exception as exc:
        message(f"{APP_NAME} Setup", f"Installation failed:\n\n{exc}", error=True)
        return 1

    launch = ask_yes_no(
        f"{APP_NAME} Setup",
        f"{APP_NAME} was installed successfully.\n\nLocation:\n{dest}\n\nLaunch now?",
    )
    if launch:
        subprocess.Popen([str(exe)], cwd=str(dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
