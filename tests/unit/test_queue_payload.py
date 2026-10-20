"""Queue payload serialization tests."""

from pathlib import Path

from app.services.generation_service import GenerationRequest
from app.services.queue_runner import payload_from_request, request_from_payload
from app.tts.base import ComputeDevice, VoiceSettings


def test_queue_payload_roundtrip(tmp_path: Path) -> None:
    req = GenerationRequest(
        text="Hello queue",
        voice_id="test-voice",
        output_path=tmp_path / "out.wav",
        title="Test",
        settings=VoiceSettings(speed=1.1, volume=0.9),
        post_process_preset="podcast",
        device=ComputeDevice.CPU,
    )
    payload = payload_from_request(req)
    restored = request_from_payload(payload)
    assert restored.text == req.text
    assert restored.voice_id == req.voice_id
    assert restored.post_process_preset == "podcast"
    assert restored.settings is not None
    assert restored.settings.speed == 1.1
