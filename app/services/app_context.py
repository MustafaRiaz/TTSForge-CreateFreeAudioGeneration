"""Application service container."""

from __future__ import annotations

from pathlib import Path

from app.audio.cache import AudioCache
from app.core.paths import ensure_dirs
from app.database.db import Database
from app.projects.manager import ProjectManager
from app.services.generation_service import GenerationService, JobQueue
from app.services.model_manager import ModelManagerService
from app.services.settings_service import SettingsService
from app.text.processor import PronunciationRule, TextProcessor
from app.tts.registry import ProviderRegistry


class AppContext:
    def __init__(self) -> None:
        self.paths = ensure_dirs()
        self.db = Database(self.paths["db"])
        self.settings = SettingsService(self.db)

        models_dir = Path(self.settings.get("model_location") or self.paths["models"])
        models_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = Path(self.settings.get("cache_location") or self.paths["audio_cache"])
        cache_dir.mkdir(parents=True, exist_ok=True)

        self.models_dir = models_dir
        self.registry = ProviderRegistry(models_dir)
        self.cache = AudioCache(cache_dir)
        rules_raw = self.settings.get("pronunciation_rules") or []
        rules = [
            PronunciationRule(
                pattern=r["pattern"],
                replacement=r["replacement"],
                is_regex=r.get("is_regex", False),
                case_sensitive=r.get("case_sensitive", False),
            )
            for r in rules_raw
            if isinstance(r, dict) and "pattern" in r and "replacement" in r
        ]
        self.processor = TextProcessor(rules=rules)
        self.generation = GenerationService(self.registry, self.cache, self.processor)
        self.models = ModelManagerService(
            models_dir, offline_mode=bool(self.settings.get("offline_mode"))
        )
        self.projects = ProjectManager(self.paths["projects"])
        self.job_queue = JobQueue()

    def refresh_offline_flag(self) -> None:
        self.models.offline_mode = bool(self.settings.get("offline_mode"))
