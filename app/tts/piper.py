"""Piper TTS provider — lightweight multi-language engine."""

from __future__ import annotations

import json
import logging
import wave
from dataclasses import dataclass
from io import BytesIO
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

# Curated catalog (downloaded on demand from Hugging Face rhasspy/piper-voices)
def _piper(
    voice_id: str,
    name: str,
    language: str,
    gender: str,
    accent: str,
    quality: str,
    size_mb: float,
    lang_dir: str,
    locale: str,
    speaker: str,
) -> dict[str, Any]:
    """Build a Piper catalog entry from HF path segments."""
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang_dir}/{locale}/{speaker}/{quality}"
    return {
        "id": voice_id,
        "name": name,
        "language": language,
        "gender": gender,
        "accent": accent,
        "quality": quality,
        "size_mb": size_mb,
        "url_onnx": f"{base}/{voice_id}.onnx",
        "url_json": f"{base}/{voice_id}.onnx.json",
    }


PIPER_CATALOG: list[dict[str, Any]] = [
    # English (US)
    _piper("en_US-lessac-medium", "Lessac", "en-US", "female", "American", "medium", 63.0, "en", "en_US", "lessac"),
    _piper("en_US-lessac-high", "Lessac High", "en-US", "female", "American", "high", 114.0, "en", "en_US", "lessac"),
    _piper("en_US-amy-medium", "Amy", "en-US", "female", "American", "medium", 63.0, "en", "en_US", "amy"),
    _piper("en_US-amy-low", "Amy Low", "en-US", "female", "American", "low", 28.0, "en", "en_US", "amy"),
    _piper("en_US-ryan-high", "Ryan", "en-US", "male", "American", "high", 114.0, "en", "en_US", "ryan"),
    _piper("en_US-ryan-medium", "Ryan Medium", "en-US", "male", "American", "medium", 63.0, "en", "en_US", "ryan"),
    _piper("en_US-joe-medium", "Joe", "en-US", "male", "American", "medium", 63.0, "en", "en_US", "joe"),
    _piper("en_US-kusal-medium", "Kusal", "en-US", "male", "American", "medium", 63.0, "en", "en_US", "kusal"),
    _piper("en_US-libritts-high", "LibriTTS", "en-US", "female", "American", "high", 114.0, "en", "en_US", "libritts"),
    _piper("en_US-libritts_r-medium", "LibriTTS R", "en-US", "female", "American", "medium", 63.0, "en", "en_US", "libritts_r"),
    _piper("en_US-ljspeech-high", "LJ Speech", "en-US", "female", "American", "high", 114.0, "en", "en_US", "ljspeech"),
    _piper("en_US-ljspeech-medium", "LJ Speech Medium", "en-US", "female", "American", "medium", 63.0, "en", "en_US", "ljspeech"),
    _piper("en_US-hfc_female-medium", "HFC Female", "en-US", "female", "American", "medium", 63.0, "en", "en_US", "hfc_female"),
    _piper("en_US-hfc_male-medium", "HFC Male", "en-US", "male", "American", "medium", 63.0, "en", "en_US", "hfc_male"),
    _piper("en_US-john-medium", "John", "en-US", "male", "American", "medium", 63.0, "en", "en_US", "john"),
    _piper("en_US-norman-medium", "Norman", "en-US", "male", "American", "medium", 63.0, "en", "en_US", "norman"),
    # English (GB)
    _piper("en_GB-alba-medium", "Alba", "en-GB", "female", "British", "medium", 63.0, "en", "en_GB", "alba"),
    _piper("en_GB-southern_english_female-low", "Southern English Female", "en-GB", "female", "British Southern", "low", 28.0, "en", "en_GB", "southern_english_female"),
    _piper("en_GB-northern_english_male-medium", "Northern English Male", "en-GB", "male", "British Northern", "medium", 63.0, "en", "en_GB", "northern_english_male"),
    _piper("en_GB-vctk-medium", "VCTK", "en-GB", "female", "British", "medium", 63.0, "en", "en_GB", "vctk"),
    _piper("en_GB-semaine-medium", "Semaine", "en-GB", "female", "British", "medium", 63.0, "en", "en_GB", "semaine"),
    # German
    _piper("de_DE-thorsten-high", "Thorsten", "de-DE", "male", "German", "high", 114.0, "de", "de_DE", "thorsten"),
    _piper("de_DE-thorsten-medium", "Thorsten Medium", "de-DE", "male", "German", "medium", 63.0, "de", "de_DE", "thorsten"),
    _piper("de_DE-kerstin-low", "Kerstin", "de-DE", "female", "German", "low", 28.0, "de", "de_DE", "kerstin"),
    _piper("de_DE-eva_k-x_low", "Eva K", "de-DE", "female", "German", "x_low", 15.0, "de", "de_DE", "eva_k"),
    # French
    _piper("fr_FR-siwis-medium", "Siwis", "fr-FR", "female", "French", "medium", 63.0, "fr", "fr_FR", "siwis"),
    _piper("fr_FR-upmc-medium", "UPMC", "fr-FR", "female", "French", "medium", 63.0, "fr", "fr_FR", "upmc"),
    _piper("fr_FR-tom-medium", "Tom", "fr-FR", "male", "French", "medium", 63.0, "fr", "fr_FR", "tom"),
    # Spanish
    _piper("es_ES-sharvard-medium", "Sharvard", "es-ES", "female", "Spanish", "medium", 63.0, "es", "es_ES", "sharvard"),
    _piper("es_ES-davefx-medium", "DaveFX", "es-ES", "male", "Spanish", "medium", 63.0, "es", "es_ES", "davefx"),
    _piper("es_MX-ald-medium", "ALD", "es-MX", "male", "Mexican Spanish", "medium", 63.0, "es", "es_MX", "ald"),
    # Italian
    _piper("it_IT-riccardo-medium", "Riccardo", "it-IT", "male", "Italian", "medium", 63.0, "it", "it_IT", "riccardo"),
    _piper("it_IT-paola-medium", "Paola", "it-IT", "female", "Italian", "medium", 63.0, "it", "it_IT", "paola"),
    # Dutch
    _piper("nl_NL-mls-medium", "MLS Dutch", "nl-NL", "female", "Dutch", "medium", 63.0, "nl", "nl_NL", "mls"),
    _piper("nl_NL-rdh-medium", "RDH", "nl-NL", "male", "Dutch", "medium", 63.0, "nl", "nl_NL", "rdh"),
    # Portuguese (BR)
    _piper("pt_BR-faber-medium", "Faber", "pt-BR", "male", "Brazilian", "medium", 63.0, "pt", "pt_BR", "faber"),
    _piper("pt_BR-edresson-low", "Edresson", "pt-BR", "male", "Brazilian", "low", 28.0, "pt", "pt_BR", "edresson"),
    # Polish
    _piper("pl_PL-darkman-medium", "Darkman", "pl-PL", "male", "Polish", "medium", 63.0, "pl", "pl_PL", "darkman"),
    _piper("pl_PL-gosia-medium", "Gosia", "pl-PL", "female", "Polish", "medium", 63.0, "pl", "pl_PL", "gosia"),
    # Russian
    _piper("ru_RU-dmitri-medium", "Dmitri", "ru-RU", "male", "Russian", "medium", 63.0, "ru", "ru_RU", "dmitri"),
    _piper("ru_RU-irina-medium", "Irina", "ru-RU", "female", "Russian", "medium", 63.0, "ru", "ru_RU", "irina"),
    # Chinese
    _piper("zh_CN-huayan-medium", "Huayan", "zh-CN", "female", "Mandarin", "medium", 63.0, "zh", "zh_CN", "huayan"),
    # Swedish / Norwegian / Danish / Finnish (lightweight extras)
    _piper("sv_SE-nst-medium", "NST", "sv-SE", "male", "Swedish", "medium", 63.0, "sv", "sv_SE", "nst"),
    _piper("no_NO-talesyntese-medium", "Talesyntese", "no-NO", "male", "Norwegian", "medium", 63.0, "no", "no_NO", "talesyntese"),
    _piper("da_DK-talesyntese-medium", "Talesyntese DK", "da-DK", "female", "Danish", "medium", 63.0, "da", "da_DK", "talesyntese"),
    _piper("fi_FI-harri-medium", "Harri", "fi-FI", "male", "Finnish", "medium", 63.0, "fi", "fi_FI", "harri"),
]


@dataclass
class _PiperVoiceFiles:
    onnx: Path
    config: Path


class PiperProvider(TTSProvider):
    id = "piper"
    name = "Piper"
    description = "Fast lightweight VITS/ONNX voices. Optional GPL-licensed engine package."

    def __init__(self, models_dir: Path | None = None) -> None:
        super().__init__()
        self.models_dir = models_dir
        self._voice = None
        self._sample_rate = 22050

    def _voice_dir(self, catalog_id: str) -> Path:
        assert self.models_dir is not None
        return self.models_dir / "piper" / catalog_id

    def _files_for(self, catalog_id: str) -> _PiperVoiceFiles | None:
        d = self._voice_dir(catalog_id)
        onnx = d / f"{catalog_id}.onnx"
        cfg = d / f"{catalog_id}.onnx.json"
        if onnx.is_file() and cfg.is_file():
            return _PiperVoiceFiles(onnx=onnx, config=cfg)
        # Also accept any .onnx + .json pair
        onnx_files = list(d.glob("*.onnx"))
        if onnx_files:
            onnx = onnx_files[0]
            cfg = Path(str(onnx) + ".json")
            if cfg.is_file():
                return _PiperVoiceFiles(onnx=onnx, config=cfg)
        return None

    def is_available(self) -> bool:
        try:
            import piper  # noqa: F401

            return True
        except Exception:
            try:
                from piper.voice import PiperVoice  # noqa: F401

                return True
            except Exception:
                return False

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            speed=True,
            pitch=False,
            volume=True,
            multi_speaker=False,
            native_ssml=False,
            languages=sorted({v["language"] for v in PIPER_CATALOG}),
            notes={
                "pitch": "Piper does not provide pitch control in this integration.",
                "license": "The piper-tts Python package is GPL-3.0; see THIRD_PARTY_LICENSES.md.",
            },
        )

    def get_voices(self) -> list[VoiceInfo]:
        voices: list[VoiceInfo] = []
        for meta in PIPER_CATALOG:
            files = self._files_for(meta["id"]) if self.models_dir else None
            installed = files is not None
            voices.append(
                VoiceInfo(
                    id=f"piper:{meta['id']}",
                    name=meta["name"],
                    provider=self.id,
                    language=meta["language"],
                    gender=meta.get("gender"),
                    accent=meta.get("accent"),
                    quality=meta.get("quality", "medium"),
                    sample_rate=22050,
                    model_path=str(files.onnx) if files else None,
                    installed=installed,
                    size_mb=0.0 if installed else float(meta.get("size_mb", 60)),
                    description="Piper ONNX voice",
                    tags=["piper", "lightweight"],
                    metadata={
                        "catalog_id": meta["id"],
                        "url_onnx": meta["url_onnx"],
                        "url_json": meta["url_json"],
                    },
                )
            )
        # Discover locally imported voices
        if self.models_dir:
            piper_root = self.models_dir / "piper"
            if piper_root.is_dir():
                known = {m["id"] for m in PIPER_CATALOG}
                for d in piper_root.iterdir():
                    if not d.is_dir() or d.name in known:
                        continue
                    files = self._files_for(d.name)
                    if not files:
                        continue
                    voices.append(
                        VoiceInfo(
                            id=f"piper:{d.name}",
                            name=d.name,
                            provider=self.id,
                            language="unknown",
                            quality="custom",
                            model_path=str(files.onnx),
                            installed=True,
                            size_mb=0.0,
                            description="Imported Piper voice",
                            tags=["piper", "imported"],
                            metadata={"catalog_id": d.name},
                        )
                    )
        return voices

    def load_voice(self, voice: VoiceInfo, device: ComputeDevice = ComputeDevice.AUTO) -> None:
        catalog_id = voice.metadata.get("catalog_id") or voice.id.split(":")[-1]
        files = self._files_for(catalog_id)
        if not files:
            raise FileNotFoundError(f"Piper voice not installed: {catalog_id}")
        try:
            from piper.voice import PiperVoice
        except Exception as exc:
            raise RuntimeError(
                "piper-tts is not installed. Install optional dependency: pip install piper-tts"
            ) from exc

        use_cuda = False
        if device in (ComputeDevice.GPU, ComputeDevice.AUTO):
            try:
                import onnxruntime as ort

                use_cuda = "CUDAExecutionProvider" in ort.get_available_providers()
                if device == ComputeDevice.CPU:
                    use_cuda = False
            except Exception:
                use_cuda = False

        try:
            self._voice = PiperVoice.load(str(files.onnx), config_path=str(files.config), use_cuda=use_cuda)
        except TypeError:
            self._voice = PiperVoice.load(str(files.onnx), config_path=str(files.config))
        except Exception:
            # CUDA failed — CPU fallback
            self._voice = PiperVoice.load(str(files.onnx), config_path=str(files.config), use_cuda=False)

        try:
            cfg = json.loads(files.config.read_text(encoding="utf-8"))
            self._sample_rate = int(cfg.get("audio", {}).get("sample_rate", 22050))
        except Exception:
            self._sample_rate = 22050
        self._loaded_voice_id = voice.id
        self._device = device
        logger.info("Loaded Piper voice %s", catalog_id)

    def synthesize(self, text: str, settings: VoiceSettings | None = None) -> AudioResult:
        if self._voice is None:
            raise RuntimeError("No Piper voice loaded.")
        settings = settings or VoiceSettings()
        speed = max(0.5, min(2.0, float(settings.speed)))

        # Piper API variants across versions
        audio_bytes = BytesIO()
        try:
            with wave.open(audio_bytes, "wb") as wav_file:
                # Newer API
                try:
                    self._voice.synthesize(text, wav_file, length_scale=1.0 / speed)
                except TypeError:
                    try:
                        self._voice.synthesize(text, wav_file)
                    except Exception:
                        # Older iterator API
                        raise
        except Exception:
            audio_bytes = BytesIO()
            syn = getattr(self._voice, "synthesize_stream_raw", None) or getattr(self._voice, "synthesize", None)
            if syn is None:
                raise RuntimeError("Unsupported piper-tts API")
            # Fallback: collect raw PCM if possible
            frames = []
            result = syn(text)
            if hasattr(result, "__iter__") and not isinstance(result, (bytes, bytearray)):
                for chunk in result:
                    if hasattr(chunk, "audio_int16_bytes"):
                        frames.append(chunk.audio_int16_bytes)
                    elif isinstance(chunk, (bytes, bytearray)):
                        frames.append(bytes(chunk))
                pcm = b"".join(frames)
                audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                if settings.volume != 1.0:
                    audio = np.clip(audio * float(settings.volume), -1.0, 1.0)
                if speed != 1.0:
                    # crude resample for speed when length_scale unavailable
                    indices = np.round(np.arange(0, len(audio), speed)).astype(int)
                    indices = indices[indices < len(audio)]
                    audio = audio[indices]
                return AudioResult(
                    samples=audio,
                    sample_rate=self._sample_rate,
                    duration_sec=len(audio) / self._sample_rate,
                )
            raise

        audio_bytes.seek(0)
        with wave.open(audio_bytes, "rb") as wf:
            sr = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if settings.volume != 1.0:
            audio = np.clip(audio * float(settings.volume), -1.0, 1.0)
        return AudioResult(samples=audio, sample_rate=sr, duration_sec=len(audio) / sr)

    def unload(self) -> None:
        self._voice = None
        super().unload()
