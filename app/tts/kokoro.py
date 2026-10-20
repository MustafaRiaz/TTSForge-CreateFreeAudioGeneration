"""Kokoro ONNX TTS provider — recommended default engine."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from app.tts.base import (
    AudioResult,
    ComputeDevice,
    ProviderCapabilities,
    TTSProvider,
    VoiceInfo,
    VoiceSettings,
)

logger = logging.getLogger(__name__)

# Full Kokoro v1.0 voice set (embeddings already in voices-v1.0.bin)
KOKORO_VOICES: list[dict[str, Any]] = [
    # American English
    {"id": "af_heart", "name": "Heart", "language": "en-US", "gender": "female", "accent": "American", "quality": "high", "lang": "en-us"},
    {"id": "af_alloy", "name": "Alloy", "language": "en-US", "gender": "female", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "af_aoede", "name": "Aoede", "language": "en-US", "gender": "female", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "af_bella", "name": "Bella", "language": "en-US", "gender": "female", "accent": "American", "quality": "high", "lang": "en-us"},
    {"id": "af_jessica", "name": "Jessica", "language": "en-US", "gender": "female", "accent": "American", "quality": "low", "lang": "en-us"},
    {"id": "af_kore", "name": "Kore", "language": "en-US", "gender": "female", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "af_nicole", "name": "Nicole", "language": "en-US", "gender": "female", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "af_nova", "name": "Nova", "language": "en-US", "gender": "female", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "af_river", "name": "River", "language": "en-US", "gender": "female", "accent": "American", "quality": "low", "lang": "en-us"},
    {"id": "af_sarah", "name": "Sarah", "language": "en-US", "gender": "female", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "af_sky", "name": "Sky", "language": "en-US", "gender": "female", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "am_adam", "name": "Adam", "language": "en-US", "gender": "male", "accent": "American", "quality": "low", "lang": "en-us"},
    {"id": "am_echo", "name": "Echo", "language": "en-US", "gender": "male", "accent": "American", "quality": "low", "lang": "en-us"},
    {"id": "am_eric", "name": "Eric", "language": "en-US", "gender": "male", "accent": "American", "quality": "low", "lang": "en-us"},
    {"id": "am_fenrir", "name": "Fenrir", "language": "en-US", "gender": "male", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "am_liam", "name": "Liam", "language": "en-US", "gender": "male", "accent": "American", "quality": "low", "lang": "en-us"},
    {"id": "am_michael", "name": "Michael", "language": "en-US", "gender": "male", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "am_onyx", "name": "Onyx", "language": "en-US", "gender": "male", "accent": "American", "quality": "low", "lang": "en-us"},
    {"id": "am_puck", "name": "Puck", "language": "en-US", "gender": "male", "accent": "American", "quality": "medium", "lang": "en-us"},
    {"id": "am_santa", "name": "Santa", "language": "en-US", "gender": "male", "accent": "American", "quality": "low", "lang": "en-us"},
    # British English
    {"id": "bf_alice", "name": "Alice", "language": "en-GB", "gender": "female", "accent": "British", "quality": "low", "lang": "en-gb"},
    {"id": "bf_emma", "name": "Emma", "language": "en-GB", "gender": "female", "accent": "British", "quality": "medium", "lang": "en-gb"},
    {"id": "bf_isabella", "name": "Isabella", "language": "en-GB", "gender": "female", "accent": "British", "quality": "medium", "lang": "en-gb"},
    {"id": "bf_lily", "name": "Lily", "language": "en-GB", "gender": "female", "accent": "British", "quality": "low", "lang": "en-gb"},
    {"id": "bm_daniel", "name": "Daniel", "language": "en-GB", "gender": "male", "accent": "British", "quality": "low", "lang": "en-gb"},
    {"id": "bm_fable", "name": "Fable", "language": "en-GB", "gender": "male", "accent": "British", "quality": "medium", "lang": "en-gb"},
    {"id": "bm_george", "name": "George", "language": "en-GB", "gender": "male", "accent": "British", "quality": "medium", "lang": "en-gb"},
    {"id": "bm_lewis", "name": "Lewis", "language": "en-GB", "gender": "male", "accent": "British", "quality": "low", "lang": "en-gb"},
    # Japanese
    {"id": "jf_alpha", "name": "Alpha", "language": "ja", "gender": "female", "accent": "Japanese", "quality": "medium", "lang": "ja"},
    {"id": "jf_gongitsune", "name": "Gongitsune", "language": "ja", "gender": "female", "accent": "Japanese", "quality": "medium", "lang": "ja"},
    {"id": "jf_nezumi", "name": "Nezumi", "language": "ja", "gender": "female", "accent": "Japanese", "quality": "medium", "lang": "ja"},
    {"id": "jf_tebukuro", "name": "Tebukuro", "language": "ja", "gender": "female", "accent": "Japanese", "quality": "medium", "lang": "ja"},
    {"id": "jm_kumo", "name": "Kumo", "language": "ja", "gender": "male", "accent": "Japanese", "quality": "medium", "lang": "ja"},
    # Mandarin Chinese
    {"id": "zf_xiaobei", "name": "Xiaobei", "language": "zh", "gender": "female", "accent": "Mandarin", "quality": "low", "lang": "cmn"},
    {"id": "zf_xiaoni", "name": "Xiaoni", "language": "zh", "gender": "female", "accent": "Mandarin", "quality": "low", "lang": "cmn"},
    {"id": "zf_xiaoxiao", "name": "Xiaoxiao", "language": "zh", "gender": "female", "accent": "Mandarin", "quality": "low", "lang": "cmn"},
    {"id": "zf_xiaoyi", "name": "Xiaoyi", "language": "zh", "gender": "female", "accent": "Mandarin", "quality": "low", "lang": "cmn"},
    {"id": "zm_yunjian", "name": "Yunjian", "language": "zh", "gender": "male", "accent": "Mandarin", "quality": "low", "lang": "cmn"},
    {"id": "zm_yunxi", "name": "Yunxi", "language": "zh", "gender": "male", "accent": "Mandarin", "quality": "low", "lang": "cmn"},
    {"id": "zm_yunxia", "name": "Yunxia", "language": "zh", "gender": "male", "accent": "Mandarin", "quality": "low", "lang": "cmn"},
    {"id": "zm_yunyang", "name": "Yunyang", "language": "zh", "gender": "male", "accent": "Mandarin", "quality": "low", "lang": "cmn"},
    # Spanish
    {"id": "ef_dora", "name": "Dora", "language": "es", "gender": "female", "accent": "Spanish", "quality": "medium", "lang": "es"},
    {"id": "em_alex", "name": "Alex", "language": "es", "gender": "male", "accent": "Spanish", "quality": "medium", "lang": "es"},
    {"id": "em_santa", "name": "Santa", "language": "es", "gender": "male", "accent": "Spanish", "quality": "medium", "lang": "es"},
    # French
    {"id": "ff_siwis", "name": "Siwis", "language": "fr", "gender": "female", "accent": "French", "quality": "medium", "lang": "fr-fr"},
    # Hindi
    {"id": "hf_alpha", "name": "Alpha", "language": "hi", "gender": "female", "accent": "Hindi", "quality": "medium", "lang": "hi"},
    {"id": "hf_beta", "name": "Beta", "language": "hi", "gender": "female", "accent": "Hindi", "quality": "medium", "lang": "hi"},
    {"id": "hm_omega", "name": "Omega", "language": "hi", "gender": "male", "accent": "Hindi", "quality": "medium", "lang": "hi"},
    {"id": "hm_psi", "name": "Psi", "language": "hi", "gender": "male", "accent": "Hindi", "quality": "medium", "lang": "hi"},
    # Italian
    {"id": "if_sara", "name": "Sara", "language": "it", "gender": "female", "accent": "Italian", "quality": "medium", "lang": "it"},
    {"id": "im_nicola", "name": "Nicola", "language": "it", "gender": "male", "accent": "Italian", "quality": "medium", "lang": "it"},
    # Brazilian Portuguese
    {"id": "pf_dora", "name": "Dora", "language": "pt-BR", "gender": "female", "accent": "Brazilian", "quality": "medium", "lang": "pt-br"},
    {"id": "pm_alex", "name": "Alex", "language": "pt-BR", "gender": "male", "accent": "Brazilian", "quality": "medium", "lang": "pt-br"},
    {"id": "pm_santa", "name": "Santa", "language": "pt-BR", "gender": "male", "accent": "Brazilian", "quality": "medium", "lang": "pt-br"},
]

KOKORO_VOICE_BY_ID = {v["id"]: v for v in KOKORO_VOICES}

MODEL_FILES = {
    "model": "kokoro-v1.0.onnx",
    "voices": "voices-v1.0.bin",
}

MODEL_URLS = {
    "model": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx",
    "voices": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin",
}

# Approximate sizes for UI consent dialogs
MODEL_SIZES_MB = {"model": 310.0, "voices": 26.0}


class KokoroProvider(TTSProvider):
    id = "kokoro"
    name = "Kokoro"
    description = "High-quality local neural TTS (ONNX). Recommended default."

    def __init__(self, models_dir: Path | None = None) -> None:
        super().__init__()
        self.models_dir = models_dir
        self._kokoro = None
        self._voice_id: str | None = None
        self._lang: str = "en-us"

    def _model_paths(self) -> tuple[Path, Path]:
        assert self.models_dir is not None
        base = self.models_dir / "kokoro"
        return base / MODEL_FILES["model"], base / MODEL_FILES["voices"]

    def is_installed(self) -> bool:
        if self.models_dir is None:
            return False
        model, voices = self._model_paths()
        return model.is_file() and voices.is_file()

    def is_available(self) -> bool:
        try:
            import kokoro_onnx  # noqa: F401
        except Exception:
            return False
        return self.is_installed()

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            speed=True,
            pitch=False,
            volume=True,
            multi_speaker=False,
            native_ssml=False,
            languages=sorted({v["language"] for v in KOKORO_VOICES}),
            notes={
                "pitch": "Kokoro ONNX does not expose pitch control; the control is disabled.",
                "ssml": "Markup is handled by VoiceForge preprocessing, not native SSML.",
            },
        )

    def get_voices(self) -> list[VoiceInfo]:
        installed = self.is_installed()
        model_path = None
        if self.models_dir:
            model_path = str(self._model_paths()[0])
        total = sum(MODEL_SIZES_MB.values())
        voices: list[VoiceInfo] = []
        for meta in KOKORO_VOICES:
            voices.append(
                VoiceInfo(
                    id=f"kokoro:{meta['id']}",
                    name=meta["name"],
                    provider=self.id,
                    language=meta["language"],
                    gender=meta.get("gender"),
                    accent=meta.get("accent"),
                    quality=meta.get("quality", "high"),
                    sample_rate=24000,
                    model_path=model_path,
                    installed=installed,
                    size_mb=total if not installed else 0.0,
                    description="Kokoro neural voice",
                    tags=["kokoro", "neural", meta["language"]],
                    metadata={"kokoro_voice": meta["id"], "lang": meta.get("lang", "en-us")},
                )
            )
        return voices

    def load_voice(self, voice: VoiceInfo, device: ComputeDevice = ComputeDevice.AUTO) -> None:
        if not self.is_installed():
            raise FileNotFoundError(
                "Kokoro model files are not installed. Use Model Manager to download them."
            )
        model_path, voices_path = self._model_paths()
        from kokoro_onnx import Kokoro

        providers = None
        if device == ComputeDevice.GPU:
            try:
                import onnxruntime as ort

                if "CUDAExecutionProvider" in ort.get_available_providers():
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            except Exception:
                providers = None
        elif device == ComputeDevice.CPU:
            providers = ["CPUExecutionProvider"]

        # kokoro-onnx may not accept providers in all versions — fall back gracefully
        try:
            if providers:
                self._kokoro = Kokoro(str(model_path), str(voices_path), providers=providers)
            else:
                self._kokoro = Kokoro(str(model_path), str(voices_path))
        except TypeError:
            self._kokoro = Kokoro(str(model_path), str(voices_path))

        self._voice_id = voice.metadata.get("kokoro_voice") or voice.id.split(":")[-1]
        meta = KOKORO_VOICE_BY_ID.get(self._voice_id, {})
        self._lang = str(voice.metadata.get("lang") or meta.get("lang") or "en-us")
        self._loaded_voice_id = voice.id
        self._device = device
        logger.info("Loaded Kokoro voice %s (lang=%s)", self._voice_id, self._lang)

    def synthesize(self, text: str, settings: VoiceSettings | None = None) -> AudioResult:
        if self._kokoro is None or not self._voice_id:
            raise RuntimeError("No Kokoro voice loaded. Call load_voice() first.")
        settings = settings or VoiceSettings()
        speed = max(0.5, min(2.0, float(settings.speed)))
        # Defensive cleanup — phonemizer rejects punctuation-only strings like "--"
        from app.text.processor import TextProcessor

        speak = TextProcessor().prepare_for_synthesis(text)
        if not speak:
            return AudioResult(
                samples=np.zeros(0, dtype=np.float32),
                sample_rate=24000,
                duration_sec=0.0,
                meta={"skipped": True},
            )
        lang = self._lang or "en-us"
        try:
            samples, sample_rate = self._kokoro.create(
                speak,
                voice=self._voice_id,
                speed=speed,
                lang=lang,
            )
        except Exception as exc:
            # Retry once with heavier stripping of non-letters
            cleaned = re.sub(r"[^\w\s.,!?;:'\"-]", " ", speak, flags=re.UNICODE)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
            if not cleaned or cleaned == speak:
                raise
            logger.warning("Kokoro retry after phoneme failure: %s", exc)
            samples, sample_rate = self._kokoro.create(
                cleaned,
                voice=self._voice_id,
                speed=speed,
                lang=lang,
            )
        audio = np.asarray(samples, dtype=np.float32)
        if settings.volume != 1.0:
            audio = np.clip(audio * float(settings.volume), -1.0, 1.0)
        duration = float(len(audio) / sample_rate) if sample_rate else 0.0
        return AudioResult(samples=audio, sample_rate=int(sample_rate), duration_sec=duration)

    def unload(self) -> None:
        self._kokoro = None
        self._voice_id = None
        self._lang = "en-us"
        super().unload()
