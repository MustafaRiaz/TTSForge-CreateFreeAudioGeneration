"""TTS provider registry."""

from __future__ import annotations

from pathlib import Path

from app.tts.base import TTSProvider, VoiceInfo
from app.tts.chatterbox import ChatterboxProvider
from app.tts.kokoro import KokoroProvider
from app.tts.piper import PiperProvider


class ProviderRegistry:
    def __init__(self, models_dir: Path) -> None:
        self.models_dir = models_dir
        self._providers: dict[str, TTSProvider] = {
            "kokoro": KokoroProvider(models_dir=models_dir),
            "piper": PiperProvider(models_dir=models_dir),
            "chatterbox": ChatterboxProvider(models_dir=models_dir),
        }

    def list_providers(self) -> list[TTSProvider]:
        return list(self._providers.values())

    def get(self, provider_id: str) -> TTSProvider:
        if provider_id not in self._providers:
            raise KeyError(f"Unknown TTS provider: {provider_id}")
        return self._providers[provider_id]

    def all_voices(self) -> list[VoiceInfo]:
        voices: list[VoiceInfo] = []
        for provider in self._providers.values():
            try:
                voices.extend(provider.get_voices())
            except Exception:
                continue
        return voices

    def find_voice(self, voice_id: str) -> VoiceInfo | None:
        for voice in self.all_voices():
            if voice.id == voice_id:
                return voice
        return None

    def resolve(self, voice_id: str) -> tuple[TTSProvider, VoiceInfo]:
        voice = self.find_voice(voice_id)
        if voice is None:
            raise KeyError(f"Voice not found: {voice_id}")
        return self.get(voice.provider), voice
