"""Application paths, constants, and environment helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "VoiceForge"
APP_VERSION = "1.0.0"
ORG_NAME = "VoiceForge"
ORG_DOMAIN = "voiceforge.local"

PRODUCT = {
    "name": APP_NAME,
    "version": APP_VERSION,
    "org": ORG_NAME,
    "domain": ORG_DOMAIN,
}


def _portable_root() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("VOICEFORGE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return None


def user_data_dir() -> Path:
    portable = _portable_root()
    if portable and (portable / "data").exists():
        return portable / "data"
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Directory that contains bundled assets (handles PyInstaller 6 _internal/)."""
    root = project_root()
    if getattr(sys, "frozen", False):
        internal = root / "_internal"
        if (internal / "assets").is_dir():
            return internal
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return root


def ensure_dirs() -> dict[str, Path]:
    root = user_data_dir()
    paths = {
        "data": root,
        "db": root / "voiceforge.db",
        "projects": root / "projects",
        "models": root / "models",
        "cache": root / "cache",
        "audio_cache": root / "cache" / "audio",
        "exports": root / "exports",
        "logs": root / "logs",
        "temp": root / "temp",
        "autosave": root / "autosave",
    }
    for key, path in paths.items():
        if key == "db":
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)
    (project_root() / "logs").mkdir(parents=True, exist_ok=True)
    return paths


QUALITY_PRESETS = {
    "fast": {
        "label": "Fast",
        "chunk_max_chars": 280,
        "sentence_pause_ms": 120,
        "paragraph_pause_ms": 280,
        "normalize": False,
    },
    "balanced": {
        "label": "Balanced",
        "chunk_max_chars": 400,
        "sentence_pause_ms": 180,
        "paragraph_pause_ms": 400,
        "normalize": True,
    },
    "high_quality": {
        "label": "High Quality",
        "chunk_max_chars": 320,
        "sentence_pause_ms": 220,
        "paragraph_pause_ms": 500,
        "normalize": True,
    },
    "long_document": {
        "label": "Long Document",
        "chunk_max_chars": 500,
        "sentence_pause_ms": 150,
        "paragraph_pause_ms": 350,
        "normalize": True,
    },
}
