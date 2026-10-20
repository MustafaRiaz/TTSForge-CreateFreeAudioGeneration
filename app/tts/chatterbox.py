"""Chatterbox Nano TTS provider — optional CPU voice cloning (MIT)."""

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

# Hugging Face repo + files needed for local Nano weights
CHATTERBOX_REPO = "ResembleAI/chatterbox-nano"
CHATTERBOX_HF_BASE = f"https://huggingface.co/{CHATTERBOX_REPO}/resolve/main"

# Approximate total download size shown in Model Manager consent dialogs
CHATTERBOX_SIZE_MB = 1950.0

# Core weight / tokenizer files (Nano single-step path uses s3gen_meanflow)
CHATTERBOX_FILES: list[dict[str, Any]] = [
    {"name": "t3_nano_v1.safetensors", "size_mb": 830.0, "required": True},
    {"name": "t3_nano_v1.yaml", "size_mb": 0.01, "required": True},
    {"name": "s3gen_meanflow.safetensors", "size_mb": 1015.0, "required": True},
    {"name": "ve.safetensors", "size_mb": 5.5, "required": True},
    {"name": "conds.pt", "size_mb": 0.2, "required": True},
    {"name": "vocab.json", "size_mb": 1.0, "required": True},
    {"name": "merges.txt", "size_mb": 0.5, "required": True},
    {"name": "tokenizer_config.json", "size_mb": 0.01, "required": True},
    {"name": "special_tokens_map.json", "size_mb": 0.01, "required": True},
    {"name": "added_tokens.json", "size_mb": 0.01, "required": True},
]

CHATTERBOX_FILE_URLS = {
    f["name"]: f"{CHATTERBOX_HF_BASE}/{f['name']}" for f in CHATTERBOX_FILES
}


def _safe_clone_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())[:64].strip("_")
    return cleaned or "clone"


class ChatterboxProvider(TTSProvider):
    id = "chatterbox"
    name = "Chatterbox Nano"
    description = "Optional CPU voice cloning (MIT). Requires a short reference WAV (~10s)."

    def __init__(self, models_dir: Path | None = None) -> None:
        super().__init__()
        self.models_dir = models_dir
        self._model = None
        self._sample_rate = 24000
        self._reference_path: str | None = None

    def _root(self) -> Path:
        assert self.models_dir is not None
        return self.models_dir / "chatterbox"

    def _clones_dir(self) -> Path:
        return self._root() / "clones"

    def is_package_available(self) -> bool:
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS  # noqa: F401

            return True
        except Exception:
            return False

    def is_installed(self) -> bool:
        if self.models_dir is None:
            return False
        root = self._root()
        for meta in CHATTERBOX_FILES:
            if meta.get("required") and not (root / meta["name"]).is_file():
                return False
        return True

    def is_available(self) -> bool:
        return self.is_package_available() and self.is_installed()

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            speed=False,
            pitch=False,
            volume=True,
            multi_speaker=False,
            native_ssml=False,
            voice_cloning=True,
            languages=["en", "multi"],
            notes={
                "speed": "Chatterbox Nano does not expose a reliable speed control in this integration.",
                "pitch": "Pitch control is not available.",
                "cloning": "Provide ~10 seconds of clean reference audio (WAV recommended).",
                "license": "MIT engine/weights; Resemble PerTh watermark is applied to output.",
                "device": "Forced to CPU in VoiceForge.",
            },
        )

    def list_clone_dirs(self) -> list[Path]:
        if self.models_dir is None:
            return []
        root = self._clones_dir()
        if not root.is_dir():
            return []
        found: list[Path] = []
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / "ref.wav").is_file():
                found.append(d)
        return found

    def get_voices(self) -> list[VoiceInfo]:
        installed = self.is_installed()
        root = str(self._root()) if self.models_dir else None
        voices: list[VoiceInfo] = [
            VoiceInfo(
                id="chatterbox:custom",
                name="Custom (reference audio)",
                provider=self.id,
                language="en",
                gender=None,
                accent=None,
                quality="high",
                sample_rate=24000,
                model_path=root,
                installed=installed,
                size_mb=0.0 if installed else CHATTERBOX_SIZE_MB,
                description="Clone any voice using a reference WAV chosen at generation time",
                tags=["chatterbox", "clone", "cpu"],
                metadata={"clone_kind": "custom"},
            )
        ]
        for clone_dir in self.list_clone_dirs():
            voices.append(
                VoiceInfo(
                    id=f"chatterbox:clone_{clone_dir.name}",
                    name=f"Clone — {clone_dir.name}",
                    provider=self.id,
                    language="en",
                    quality="high",
                    sample_rate=24000,
                    model_path=str(clone_dir / "ref.wav"),
                    installed=installed and True,
                    size_mb=0.0,
                    description=f"Saved clone from {clone_dir / 'ref.wav'}",
                    tags=["chatterbox", "clone", "saved"],
                    metadata={
                        "clone_kind": "saved",
                        "reference_audio": str(clone_dir / "ref.wav"),
                        "clone_name": clone_dir.name,
                    },
                )
            )
        return voices

    def _resolve_reference(self, voice: VoiceInfo, settings: VoiceSettings | None) -> Path:
        settings = settings or VoiceSettings()
        candidates: list[str] = []
        extra_ref = settings.extra.get("reference_audio")
        if extra_ref:
            candidates.append(str(extra_ref))
        meta_ref = voice.metadata.get("reference_audio")
        if meta_ref:
            candidates.append(str(meta_ref))
        if voice.model_path and voice.metadata.get("clone_kind") == "saved":
            candidates.append(str(voice.model_path))
        for c in candidates:
            p = Path(c)
            if p.is_file():
                return p
        raise FileNotFoundError(
            "Chatterbox requires a reference audio file. "
            "Pick one in Studio (Reference audio…) or save a clone on the Voices page."
        )

    def load_voice(self, voice: VoiceInfo, device: ComputeDevice = ComputeDevice.AUTO) -> None:
        # CPU-only by design for this integration
        if not self.is_package_available():
            raise RuntimeError(
                "chatterbox-tts is not installed. Optional install: pip install chatterbox-tts"
            )
        if not self.is_installed():
            raise FileNotFoundError(
                "Chatterbox Nano weights are not installed. Use Model Manager to download them."
            )
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        local = str(self._root())
        self._model = None
        errors: list[str] = []
        for kwargs in (
            {"device": "cpu", "nano": True},
        ):
            # Prefer loading from the local Model Manager folder
            for args in ((local,), ()):
                try:
                    if args:
                        self._model = ChatterboxTurboTTS.from_pretrained(*args, **kwargs)
                    else:
                        self._model = ChatterboxTurboTTS.from_pretrained(**kwargs)
                    break
                except TypeError as exc:
                    errors.append(str(exc))
                    continue
                except Exception as exc:
                    errors.append(str(exc))
                    continue
            if self._model is not None:
                break

        if self._model is None:
            # Last attempt: keyword local dir variants
            for key in ("ckpt_dir", "local_path", "model_dir"):
                try:
                    self._model = ChatterboxTurboTTS.from_pretrained(
                        device="cpu", nano=True, **{key: local}
                    )
                    break
                except Exception as exc:
                    errors.append(f"{key}: {exc}")
            if self._model is None:
                raise RuntimeError(
                    "Failed to load Chatterbox Nano on CPU. "
                    + ("; ".join(errors[-3:]) if errors else "Unknown error.")
                )

        self._sample_rate = int(getattr(self._model, "sr", 24000) or 24000)
        self._loaded_voice_id = voice.id
        self._device = ComputeDevice.CPU
        ref = voice.metadata.get("reference_audio")
        if not ref and voice.metadata.get("clone_kind") == "saved" and voice.model_path:
            ref = voice.model_path
        self._reference_path = str(ref) if ref else None
        logger.info("Loaded Chatterbox Nano on CPU (voice=%s)", voice.id)

    def synthesize(self, text: str, settings: VoiceSettings | None = None) -> AudioResult:
        if self._model is None:
            raise RuntimeError("No Chatterbox model loaded. Call load_voice() first.")
        settings = settings or VoiceSettings()
        # Reconstruct a VoiceInfo-like reference resolution using loaded voice metadata
        voice = VoiceInfo(
            id=self._loaded_voice_id or "chatterbox:custom",
            name="Chatterbox",
            provider=self.id,
            language="en",
            metadata={
                "reference_audio": self._reference_path,
                "clone_kind": "saved" if self._reference_path else "custom",
            },
            model_path=self._reference_path,
        )
        # Prefer live settings / find voice from registry metadata if available
        if self._loaded_voice_id and self._loaded_voice_id.startswith("chatterbox:clone_"):
            clone_name = self._loaded_voice_id.split("chatterbox:clone_", 1)[-1]
            ref_guess = self._clones_dir() / clone_name / "ref.wav"
            if ref_guess.is_file():
                voice.metadata["reference_audio"] = str(ref_guess)
                voice.model_path = str(ref_guess)
                voice.metadata["clone_kind"] = "saved"

        ref = self._resolve_reference(voice, settings)
        from app.text.processor import TextProcessor

        speak = TextProcessor().prepare_for_synthesis(text)
        if not speak:
            return AudioResult(
                samples=np.zeros(0, dtype=np.float32),
                sample_rate=self._sample_rate,
                duration_sec=0.0,
                meta={"skipped": True},
            )

        wav = self._model.generate(speak, audio_prompt_path=str(ref))
        audio = self._to_numpy(wav)
        if settings.volume != 1.0:
            audio = np.clip(audio * float(settings.volume), -1.0, 1.0)
        sr = int(getattr(self._model, "sr", self._sample_rate) or self._sample_rate)
        return AudioResult(
            samples=audio,
            sample_rate=sr,
            duration_sec=float(len(audio) / sr) if sr else 0.0,
            meta={"reference_audio": str(ref), "watermark": "PerTh"},
        )

    @staticmethod
    def _to_numpy(wav: Any) -> np.ndarray:
        if hasattr(wav, "detach"):
            arr = wav.detach().cpu().numpy()
        else:
            arr = np.asarray(wav)
        arr = np.squeeze(arr).astype(np.float32)
        if arr.ndim > 1:
            arr = arr.reshape(-1)
        return arr

    def unload(self) -> None:
        self._model = None
        self._reference_path = None
        super().unload()
