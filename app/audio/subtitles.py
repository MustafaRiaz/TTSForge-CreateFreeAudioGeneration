"""Subtitle/caption export from chunk timestamps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubtitleEntry:
    index: int
    start_sec: float
    end_sec: float
    text: str


def _ts_srt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ts_vtt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def export_srt(entries: list[SubtitleEntry], path: Path | str) -> Path:
    path = Path(path)
    lines: list[str] = []
    for e in entries:
        if not e.text.strip():
            continue
        lines.append(str(e.index))
        lines.append(f"{_ts_srt(e.start_sec)} --> {_ts_srt(e.end_sec)}")
        lines.append(e.text.strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_vtt(entries: list[SubtitleEntry], path: Path | str) -> Path:
    path = Path(path)
    lines = ["WEBVTT", ""]
    for e in entries:
        if not e.text.strip():
            continue
        lines.append(f"{_ts_vtt(e.start_sec)} --> {_ts_vtt(e.end_sec)}")
        lines.append(e.text.strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
