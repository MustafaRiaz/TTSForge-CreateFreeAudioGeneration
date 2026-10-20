"""TTS provider base types and contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ComputeDevice(str, Enum):
    AUTO = "auto"
    CPU = "cpu"
    GPU = "gpu"


@dataclass
class VoiceInfo:
    id: str
    name: str
    provider: str
    language: str
    gender: str | None = None
    accent: str | None = None
    quality: str = "medium"
    sample_rate: int = 22050
    model_path: str | None = None
    installed: bool = False
    size_mb: float | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches_query(self, query: str) -> bool:
        q = query.lower().strip()
        if not q:
            return True
        blob = " ".join(
            [
                self.id,
                self.name,
                self.language,
                self.gender or "",
                self.accent or "",
                self.quality,
                " ".join(self.tags),
                self.description,
            ]
        ).lower()
        return all(part in blob for part in q.split())


@dataclass
class VoiceSettings:
    speed: float = 1.0
    pitch: float = 1.0  # only applied when provider supports it
    volume: float = 1.0
    sentence_pause_ms: int = 180
    paragraph_pause_ms: int = 400
    speaker_pause_ms: int = 350
    sample_rate: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderCapabilities:
    speed: bool = True
    pitch: bool = False
    volume: bool = True  # post-process
    multi_speaker: bool = False
    native_ssml: bool = False
    voice_cloning: bool = False
    languages: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)


@dataclass
class AudioResult:
    samples: Any  # numpy ndarray float32
    sample_rate: int
    duration_sec: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


class TTSProvider(ABC):
    """Abstract local TTS engine."""

    id: str = "base"
    name: str = "Base"
    description: str = ""

    def __init__(self) -> None:
        self._loaded_voice_id: str | None = None
        self._device: ComputeDevice = ComputeDevice.AUTO

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        ...

    @abstractmethod
    def get_voices(self) -> list[VoiceInfo]:
        ...

    @abstractmethod
    def load_voice(self, voice: VoiceInfo, device: ComputeDevice = ComputeDevice.AUTO) -> None:
        ...

    @abstractmethod
    def synthesize(self, text: str, settings: VoiceSettings | None = None) -> AudioResult:
        ...

    def unload(self) -> None:
        self._loaded_voice_id = None

    def supports(self, setting: str) -> bool:
        caps = self.get_capabilities()
        return bool(getattr(caps, setting, False))

    def ensure_model_files(self, voice: VoiceInfo, models_dir: Path) -> list[Path]:
        """Return required local files; override in subclasses."""
        if voice.model_path:
            return [Path(voice.model_path)]
        return []
