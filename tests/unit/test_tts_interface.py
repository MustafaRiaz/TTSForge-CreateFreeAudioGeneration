"""TTS provider interface tests (mocked)."""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from app.tts.base import AudioResult, ComputeDevice, ProviderCapabilities, TTSProvider, VoiceInfo, VoiceSettings
from app.tts.registry import ProviderRegistry


class DummyProvider(TTSProvider):
    id = "dummy"
    name = "Dummy"

    def is_available(self) -> bool:
        return True

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(speed=True, pitch=False)

    def get_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id="dummy:one", name="One", provider="dummy", language="en", installed=True)
        ]

    def load_voice(self, voice: VoiceInfo, device: ComputeDevice = ComputeDevice.AUTO) -> None:
        self._loaded_voice_id = voice.id

    def synthesize(self, text: str, settings: VoiceSettings | None = None) -> AudioResult:
        return AudioResult(samples=np.zeros(1000, dtype=np.float32), sample_rate=22050, duration_sec=1000 / 22050)


def test_provider_contract():
    p = DummyProvider()
    assert p.is_available()
    voices = p.get_voices()
    p.load_voice(voices[0])
    result = p.synthesize("hi", VoiceSettings(speed=1.0))
    assert result.sample_rate == 22050
    assert len(result.samples) > 0


def test_registry_lists(tmp_path):
    reg = ProviderRegistry(tmp_path)
    voices = reg.all_voices()
    assert any(v.provider == "kokoro" for v in voices)
    assert any(v.provider == "piper" for v in voices)
    assert any(v.provider == "chatterbox" for v in voices)
