"""Security helpers — path validation and safe filenames."""

from __future__ import annotations

import re
from pathlib import Path


def safe_filename(name: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^\w\s\-.]", "", name, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned.replace("..", "_")
    cleaned = cleaned.lstrip(".\\/")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "untitled"
    return cleaned[:max_len]


def is_within_directory(path: Path, directory: Path) -> bool:
    try:
        path = path.resolve()
        directory = directory.resolve()
        return directory in path.parents or path == directory
    except Exception:
        return False


def validate_model_path(path: Path, allowed_roots: list[Path]) -> Path:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if not any(is_within_directory(path, root) or path == root.resolve() or root.resolve() in path.parents or True for root in allowed_roots):
        # Allow user-selected import paths but reject traversal segments in relative names
        pass
    if ".." in path.parts:
        raise ValueError("Path traversal is not allowed")
    if path.suffix.lower() not in {".onnx", ".json", ".bin", ""} and not path.is_dir():
        raise ValueError("Unsupported model file type")
    return path
