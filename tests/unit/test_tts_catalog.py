"""TTS catalog / provider unit tests (no real model downloads)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from app.services.model_manager import ModelManagerService
from app.tts.base import ProviderCapabilities, VoiceSettings
from app.tts.chatterbox import ChatterboxProvider, _safe_clone_name
from app.tts.kokoro import KOKORO_VOICES, KokoroProvider
from app.tts.piper import PIPER_CATALOG
from app.tts.registry import ProviderRegistry


def test_kokoro_full_voice_catalog():
    assert len(KOKORO_VOICES) >= 50
    ids = [v["id"] for v in KOKORO_VOICES]
    assert len(ids) == len(set(ids))
    assert "af_heart" in ids
    assert "jf_alpha" in ids
    assert "zf_xiaobei" in ids
    assert "ff_siwis" in ids
    assert "pf_dora" in ids
    langs = {v["language"] for v in KOKORO_VOICES}
    assert "en-US" in langs
    assert "ja" in langs
    assert "zh" in langs


def test_kokoro_capabilities_include_languages(tmp_path: Path):
    p = KokoroProvider(models_dir=tmp_path)
    caps = p.get_capabilities()
    assert "en-US" in caps.languages
    assert "ja" in caps.languages
    voices = p.get_voices()
    assert len(voices) == len(KOKORO_VOICES)
    assert all(v.id.startswith("kokoro:") for v in voices)


def test_piper_catalog_shape():
    assert len(PIPER_CATALOG) >= 30
    ids = [v["id"] for v in PIPER_CATALOG]
    assert len(ids) == len(set(ids))
    for meta in PIPER_CATALOG:
        assert meta["url_onnx"].startswith("https://huggingface.co/rhasspy/piper-voices/")
        assert meta["url_json"].endswith(".onnx.json")
        assert meta["id"] in meta["url_onnx"]
        assert meta["language"]
        assert meta["quality"]


def test_registry_includes_chatterbox(tmp_path: Path):
    reg = ProviderRegistry(tmp_path)
    assert {p.id for p in reg.list_providers()} >= {"kokoro", "piper", "chatterbox"}
    voices = reg.all_voices()
    assert any(v.provider == "chatterbox" for v in voices)
    assert any(v.id == "chatterbox:custom" for v in voices)


def test_chatterbox_unavailable_without_package(tmp_path: Path):
    p = ChatterboxProvider(models_dir=tmp_path)
    assert p.is_available() is False
    caps = p.get_capabilities()
    assert caps.voice_cloning is True
    assert caps.speed is False


def test_chatterbox_clone_discovery(tmp_path: Path):
    clones = tmp_path / "chatterbox" / "clones" / "alice"
    clones.mkdir(parents=True)
    (clones / "ref.wav").write_bytes(b"RIFF")
    p = ChatterboxProvider(models_dir=tmp_path)
    voices = p.get_voices()
    ids = [v.id for v in voices]
    assert "chatterbox:custom" in ids
    assert "chatterbox:clone_alice" in ids
    alice = next(v for v in voices if v.id == "chatterbox:clone_alice")
    assert alice.metadata["reference_audio"].endswith("ref.wav")


def test_safe_clone_name():
    assert _safe_clone_name("My Voice!") == "My_Voice"
    assert _safe_clone_name("@@@") == "clone"


def test_model_manager_catalog_and_clone_import(tmp_path: Path):
    mgr = ModelManagerService(tmp_path)
    catalog = {m.id: m for m in mgr.list_catalog()}
    assert "kokoro-core" in catalog
    assert "chatterbox-nano" in catalog
    assert catalog["chatterbox-nano"].installed is False
    assert len([m for m in catalog.values() if m.provider == "piper"]) >= 30

    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"RIFF....WAVE")
    dest = mgr.import_clone(wav, "Demo Voice")
    assert (dest / "ref.wav").is_file()
    assert dest.name == "Demo_Voice"

    ok, msg = mgr.verify("chatterbox-nano")
    assert ok is False
    assert "missing" in msg.lower()


def test_chatterbox_synthesize_mocked(tmp_path: Path):
    root = tmp_path / "chatterbox"
    clones = root / "clones" / "bob"
    clones.mkdir(parents=True)
    ref = clones / "ref.wav"
    ref.write_bytes(b"RIFF")

    provider = ChatterboxProvider(models_dir=tmp_path)
    voice = next(v for v in provider.get_voices() if v.id == "chatterbox:clone_bob")

    fake_model = MagicMock()
    fake_model.sr = 24000
    fake_model.generate.return_value = np.zeros(2400, dtype=np.float32)

    provider._model = fake_model
    provider._loaded_voice_id = voice.id
    provider._reference_path = str(ref)
    provider._sample_rate = 24000

    result = provider.synthesize(
        "Hello there.",
        VoiceSettings(extra={"reference_audio": str(ref)}),
    )
    assert result.sample_rate == 24000
    assert len(result.samples) == 2400
    fake_model.generate.assert_called()


def test_provider_capabilities_voice_cloning_flag():
    caps = ProviderCapabilities(voice_cloning=True)
    assert caps.voice_cloning is True
    assert ProviderCapabilities().voice_cloning is False
