"""Generation service with mocked provider."""

from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.audio.cache import AudioCache
from app.services.generation_service import GenerationController, GenerationRequest, GenerationService
from app.tts.base import AudioResult, VoiceInfo, VoiceSettings
from app.tts.registry import ProviderRegistry


def test_generation_with_mock(tmp_path):
    registry = ProviderRegistry(tmp_path / "models")
    cache = AudioCache(tmp_path / "cache")
    service = GenerationService(registry, cache)

    fake_voice = VoiceInfo(
        id="kokoro:af_heart",
        name="Heart",
        provider="kokoro",
        language="en-US",
        installed=True,
        sample_rate=24000,
        metadata={"kokoro_voice": "af_heart"},
    )

    class FakeProvider:
        id = "kokoro"

        def load_voice(self, voice, device=None):
            pass

        def synthesize(self, text, settings=None):
            return AudioResult(
                samples=np.random.randn(4800).astype(np.float32) * 0.1,
                sample_rate=24000,
                duration_sec=0.2,
            )

    out = tmp_path / "out.wav"
    req = GenerationRequest(
        text="Hello world. This is a test.",
        voice_id="kokoro:af_heart",
        output_path=out,
        settings=VoiceSettings(),
        chunk_max_chars=50,
        cache_enabled=True,
    )

    with patch.object(registry, "resolve", return_value=(FakeProvider(), fake_voice)):
        result = service.generate(req, controller=GenerationController())
    assert not result.cancelled
    assert result.output_path.exists()
    assert result.duration_sec > 0
