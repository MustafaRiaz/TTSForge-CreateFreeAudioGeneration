"""Application settings service."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.paths import QUALITY_PRESETS
from app.database.db import Database

DEFAULTS: dict[str, Any] = {
    "theme": "dark",
    "ui_language": "en",
    "startup_open_studio": True,
    "first_run_completed": False,
    "offline_mode": False,
    "default_output_folder": "",
    "last_save_folder": "",
    "default_engine": "kokoro",
    "default_voice": "",
    "compute_device": "auto",
    "worker_threads": 1,
    "chunk_max_chars": 400,
    "audio_format": "wav",
    "audio_bitrate": "192k",
    "audio_sample_rate": 24000,
    "audio_channels": 1,
    "normalize_audio": True,
    "filename_template": "{title}_{voice}_{date}",
    "quality_preset": "balanced",
    "sentence_pause_ms": 180,
    "paragraph_pause_ms": 400,
    "speaker_pause_ms": 350,
    "speed": 1.0,
    "volume": 1.0,
    "cache_enabled": True,
    "pronunciation_rules": [],
    "model_location": "",
    "cache_location": "",
    "ffmpeg_path": "",
    "post_process_preset": "none",
}


class SettingsService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        existing = self.db.get_all_settings()
        for key, value in DEFAULTS.items():
            if key not in existing:
                self.db.set_setting(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        if default is None:
            default = DEFAULTS.get(key)
        return self.db.get_setting(key, default)

    def set(self, key: str, value: Any) -> None:
        self.db.set_setting(key, value)

    def all(self) -> dict[str, Any]:
        data = deepcopy(DEFAULTS)
        data.update(self.db.get_all_settings())
        return data

    def apply_quality_preset(self, preset_id: str) -> None:
        preset = QUALITY_PRESETS.get(preset_id)
        if not preset:
            return
        self.set("quality_preset", preset_id)
        self.set("chunk_max_chars", preset["chunk_max_chars"])
        self.set("sentence_pause_ms", preset["sentence_pause_ms"])
        self.set("paragraph_pause_ms", preset["paragraph_pause_ms"])
        self.set("normalize_audio", preset["normalize"])
