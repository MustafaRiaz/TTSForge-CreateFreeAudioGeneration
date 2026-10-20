"""Model download / import / verify — requires explicit user consent."""

from __future__ import annotations

import logging
import shutil
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.tts.chatterbox import (
    CHATTERBOX_FILE_URLS,
    CHATTERBOX_FILES,
    CHATTERBOX_SIZE_MB,
    _safe_clone_name,
)
from app.tts.kokoro import MODEL_FILES, MODEL_SIZES_MB, MODEL_URLS
from app.tts.piper import PIPER_CATALOG

logger = logging.getLogger(__name__)

ProgressCb = Callable[[str, float], None]  # message, percent 0-100


@dataclass
class CatalogModel:
    id: str
    name: str
    provider: str
    language: str
    quality: str
    size_mb: float
    installed: bool
    description: str = ""


class DownloadController:
    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._pause.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._pause.set()

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def wait_if_paused(self) -> None:
        self._pause.wait()


class ModelManagerService:
    def __init__(self, models_dir: Path, offline_mode: bool = False) -> None:
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.offline_mode = offline_mode

    def list_catalog(self) -> list[CatalogModel]:
        items: list[CatalogModel] = []
        kokoro_dir = self.models_dir / "kokoro"
        kokoro_installed = (kokoro_dir / MODEL_FILES["model"]).is_file() and (
            kokoro_dir / MODEL_FILES["voices"]
        ).is_file()
        items.append(
            CatalogModel(
                id="kokoro-core",
                name="Kokoro Core Models",
                provider="kokoro",
                language="multi",
                quality="high",
                size_mb=sum(MODEL_SIZES_MB.values()),
                installed=kokoro_installed,
                description="ONNX model + voice embeddings for all Kokoro voices (~54)",
            )
        )
        chatter_dir = self.models_dir / "chatterbox"
        chatter_installed = all(
            (chatter_dir / f["name"]).is_file() for f in CHATTERBOX_FILES if f.get("required")
        )
        items.append(
            CatalogModel(
                id="chatterbox-nano",
                name="Chatterbox Nano (CPU cloning)",
                provider="chatterbox",
                language="en",
                quality="high",
                size_mb=CHATTERBOX_SIZE_MB,
                installed=chatter_installed,
                description="Optional MIT voice-cloning model. Requires pip install chatterbox-tts. CPU only.",
            )
        )
        for meta in PIPER_CATALOG:
            voice_dir = self.models_dir / "piper" / meta["id"]
            installed = (voice_dir / f"{meta['id']}.onnx").is_file()
            items.append(
                CatalogModel(
                    id=meta["id"],
                    name=f"Piper — {meta['name']}",
                    provider="piper",
                    language=meta["language"],
                    quality=meta.get("quality", "medium"),
                    size_mb=float(meta.get("size_mb", 60)),
                    installed=installed,
                    description="Piper ONNX voice package",
                )
            )
        return items

    def download(
        self,
        model_id: str,
        controller: DownloadController | None = None,
        on_progress: ProgressCb | None = None,
    ) -> None:
        if self.offline_mode:
            raise RuntimeError("Offline Mode is enabled. Disable it to download models.")
        controller = controller or DownloadController()
        if model_id == "kokoro-core":
            self._download_kokoro(controller, on_progress)
            return
        if model_id == "chatterbox-nano":
            self._download_chatterbox(controller, on_progress)
            return
        meta = next((m for m in PIPER_CATALOG if m["id"] == model_id), None)
        if not meta:
            raise KeyError(f"Unknown model: {model_id}")
        self._download_piper(meta, controller, on_progress)

    def _download_file(
        self,
        url: str,
        dest: Path,
        controller: DownloadController,
        on_progress: ProgressCb | None,
        label: str,
        weight_start: float,
        weight_end: float,
    ) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_suffix(dest.suffix + ".partial")
        req = urllib.request.Request(url, headers={"User-Agent": "VoiceForge/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(partial, "wb") as f:
                while True:
                    controller.wait_if_paused()
                    if controller.cancelled:
                        partial.unlink(missing_ok=True)
                        raise RuntimeError("Download cancelled")
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress and total:
                        frac = downloaded / total
                        pct = weight_start + (weight_end - weight_start) * frac
                        on_progress(f"{label}: {downloaded // (1024*1024)} MB", pct)
        partial.replace(dest)

    def _download_kokoro(self, controller: DownloadController, on_progress: ProgressCb | None) -> None:
        base = self.models_dir / "kokoro"
        self._download_file(
            MODEL_URLS["model"],
            base / MODEL_FILES["model"],
            controller,
            on_progress,
            "Kokoro model",
            0,
            85,
        )
        self._download_file(
            MODEL_URLS["voices"],
            base / MODEL_FILES["voices"],
            controller,
            on_progress,
            "Kokoro voices",
            85,
            100,
        )
        if on_progress:
            on_progress("Kokoro install complete", 100)

    def _download_chatterbox(
        self, controller: DownloadController, on_progress: ProgressCb | None
    ) -> None:
        base = self.models_dir / "chatterbox"
        base.mkdir(parents=True, exist_ok=True)
        files = [f for f in CHATTERBOX_FILES if f.get("required")]
        n = max(len(files), 1)
        for i, meta in enumerate(files):
            start = 100.0 * i / n
            end = 100.0 * (i + 1) / n
            name = meta["name"]
            self._download_file(
                CHATTERBOX_FILE_URLS[name],
                base / name,
                controller,
                on_progress,
                name,
                start,
                end,
            )
        (base / "clones").mkdir(parents=True, exist_ok=True)
        if on_progress:
            on_progress("Chatterbox Nano install complete", 100)

    def _download_piper(self, meta: dict, controller: DownloadController, on_progress: ProgressCb | None) -> None:
        dest_dir = self.models_dir / "piper" / meta["id"]
        self._download_file(
            meta["url_onnx"],
            dest_dir / f"{meta['id']}.onnx",
            controller,
            on_progress,
            meta["id"],
            0,
            90,
        )
        self._download_file(
            meta["url_json"],
            dest_dir / f"{meta['id']}.onnx.json",
            controller,
            on_progress,
            f"{meta['id']} config",
            90,
            100,
        )
        if on_progress:
            on_progress("Piper voice install complete", 100)

    def delete_model(self, model_id: str) -> None:
        if model_id == "kokoro-core":
            shutil.rmtree(self.models_dir / "kokoro", ignore_errors=True)
            return
        if model_id == "chatterbox-nano":
            root = self.models_dir / "chatterbox"
            # Keep user clones; remove weight files only
            for meta in CHATTERBOX_FILES:
                (root / meta["name"]).unlink(missing_ok=True)
            return
        shutil.rmtree(self.models_dir / "piper" / model_id, ignore_errors=True)

    def import_local(self, provider: str, source: Path, name: str | None = None) -> Path:
        source = Path(source).resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        # Path traversal guard — only copy files, never execute
        safe = "".join(c for c in (name or source.stem) if c.isalnum() or c in "-_")[:80] or "imported"
        if provider == "piper":
            dest = self.models_dir / "piper" / safe
            dest.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                for f in source.glob("*"):
                    if f.suffix.lower() in {".onnx", ".json"}:
                        shutil.copy2(f, dest / f.name)
            else:
                if source.suffix.lower() != ".onnx":
                    raise ValueError("Piper import expects an .onnx file or directory")
                shutil.copy2(source, dest / f"{safe}.onnx")
                cfg = Path(str(source) + ".json")
                if cfg.is_file():
                    shutil.copy2(cfg, dest / f"{safe}.onnx.json")
            return dest
        if provider == "kokoro":
            dest = self.models_dir / "kokoro"
            dest.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                for f in source.iterdir():
                    if f.name in MODEL_FILES.values():
                        shutil.copy2(f, dest / f.name)
            else:
                shutil.copy2(source, dest / source.name)
            return dest
        if provider == "chatterbox":
            # Import a reference WAV as a named clone, or a folder of Nano weights
            if source.is_file() and source.suffix.lower() in {".wav", ".flac", ".mp3", ".ogg"}:
                return self.import_clone(source, name or source.stem)
            dest = self.models_dir / "chatterbox"
            dest.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                for f in source.iterdir():
                    if f.is_file() and f.name in CHATTERBOX_FILE_URLS:
                        shutil.copy2(f, dest / f.name)
            else:
                if source.name not in CHATTERBOX_FILE_URLS:
                    raise ValueError(
                        "Chatterbox import expects a reference audio file, a clone folder, "
                        "or a directory containing Nano weight files."
                    )
                shutil.copy2(source, dest / source.name)
            (dest / "clones").mkdir(parents=True, exist_ok=True)
            return dest
        raise ValueError(f"Unknown provider for import: {provider}")

    def import_clone(self, reference_audio: Path, name: str) -> Path:
        """Save a reference WAV as a named Chatterbox clone profile."""
        reference_audio = Path(reference_audio).resolve()
        if not reference_audio.is_file():
            raise FileNotFoundError(reference_audio)
        if reference_audio.suffix.lower() not in {".wav", ".flac", ".mp3", ".ogg"}:
            raise ValueError("Clone reference must be an audio file (wav/flac/mp3/ogg)")
        safe = _safe_clone_name(name)
        dest = self.models_dir / "chatterbox" / "clones" / safe
        dest.mkdir(parents=True, exist_ok=True)
        # Normalize to ref.wav name; keep original format if not wav by copying as-is with .wav preferred
        target = dest / "ref.wav"
        if reference_audio.suffix.lower() == ".wav":
            shutil.copy2(reference_audio, target)
        else:
            # Store original alongside a copy named ref.wav for the provider path contract
            shutil.copy2(reference_audio, dest / f"ref{reference_audio.suffix.lower()}")
            shutil.copy2(reference_audio, target)
        return dest

    def verify(self, model_id: str) -> tuple[bool, str]:
        if model_id == "kokoro-core":
            model = self.models_dir / "kokoro" / MODEL_FILES["model"]
            voices = self.models_dir / "kokoro" / MODEL_FILES["voices"]
            if model.is_file() and voices.is_file() and model.stat().st_size > 1_000_000:
                return True, "Kokoro files present and non-empty"
            return False, "Kokoro model files missing or too small"
        if model_id == "chatterbox-nano":
            root = self.models_dir / "chatterbox"
            missing = [
                f["name"]
                for f in CHATTERBOX_FILES
                if f.get("required") and not (root / f["name"]).is_file()
            ]
            if missing:
                return False, f"Chatterbox files missing: {', '.join(missing[:5])}"
            t3 = root / "t3_nano_v1.safetensors"
            if t3.stat().st_size < 100_000_000:
                return False, "Chatterbox Nano weights look too small"
            return True, "Chatterbox Nano files look valid"
        voice_dir = self.models_dir / "piper" / model_id
        onnx = voice_dir / f"{model_id}.onnx"
        cfg = voice_dir / f"{model_id}.onnx.json"
        if onnx.is_file() and cfg.is_file() and onnx.stat().st_size > 100_000:
            return True, "Piper voice files look valid"
        return False, "Piper voice files missing or invalid"
