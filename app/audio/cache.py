"""Deterministic audio cache for repeated generations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from app.audio.processing import read_wav, write_wav


class AudioCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_key(text: str, voice_id: str, model: str, settings: dict) -> str:
        payload = {
            "text": text,
            "voice": voice_id,
            "model": model,
            "settings": settings,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def path_for(self, key: str) -> Path:
        return self.cache_dir / f"{key}.wav"

    def get(self, key: str) -> tuple[np.ndarray, int] | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        try:
            return read_wav(path)
        except Exception:
            return None

    def put(self, key: str, samples: np.ndarray, sample_rate: int) -> Path:
        path = self.path_for(key)
        write_wav(path, samples, sample_rate)
        return path

    def clear(self) -> int:
        count = 0
        for p in self.cache_dir.glob("*.wav"):
            p.unlink(missing_ok=True)
            count += 1
        return count

    def size_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.cache_dir.glob("*.wav"))
