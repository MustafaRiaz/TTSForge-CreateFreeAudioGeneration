"""Core speech generation pipeline with pause/resume/cancel and caching."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

from app.audio.cache import AudioCache
from app.audio.processing import concat_audio, export_audio, normalize_peak, read_wav, silence, write_wav, apply_post_process_preset
from app.audio.subtitles import SubtitleEntry, export_srt, export_vtt
from app.text.processor import TextChunk, TextProcessor, parse_multi_voice_script
from app.tts.base import ComputeDevice, VoiceSettings
from app.tts.registry import ProviderRegistry

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass
class ChunkRecord:
    index: int
    text: str
    start_sec: float
    end_sec: float
    duration_sec: float
    kind: str = "speech"
    speaker: str | None = None
    file_path: str | None = None


@dataclass
class GenerationRequest:
    text: str
    voice_id: str
    output_path: Path
    title: str = "Untitled"
    settings: VoiceSettings | None = None
    chunk_max_chars: int = 400
    normalize: bool = True
    audio_format: str = "wav"
    bitrate: str = "192k"
    sample_rate: int | None = None
    channels: int = 1
    speaker_map: dict[str, str] = field(default_factory=dict)
    use_multi_voice: bool = False
    cache_enabled: bool = True
    device: ComputeDevice = ComputeDevice.AUTO
    resume_from_chunk: int = 0
    existing_chunk_dir: Path | None = None
    retry_chunk_indices: list[int] | None = None  # regenerate only these chunks
    post_process_preset: str = "none"


@dataclass
class GenerationResult:
    output_path: Path
    duration_sec: float
    chunk_count: int
    chunks_dir: Path | None = None
    cancelled: bool = False
    chunk_records: list[ChunkRecord] = field(default_factory=list)
    subtitle_path: Path | None = None


class GenerationController:
    """Thread-safe pause / resume / cancel flags."""

    def __init__(self) -> None:
        self._pause = threading.Event()
        self._cancel = threading.Event()
        self._pause.set()  # not paused

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._pause.set()

    def wait_if_paused(self) -> None:
        self._pause.wait()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def reset(self) -> None:
        self._cancel.clear()
        self._pause.set()


class GenerationService:
    def __init__(
        self,
        registry: ProviderRegistry,
        cache: AudioCache,
        processor: TextProcessor | None = None,
    ) -> None:
        self.registry = registry
        self.cache = cache
        self.processor = processor or TextProcessor()

    def generate(
        self,
        request: GenerationRequest,
        controller: GenerationController | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> GenerationResult:
        controller = controller or GenerationController()
        controller.reset()
        settings = request.settings or VoiceSettings()
        chunks_dir = request.existing_chunk_dir or (request.output_path.parent / "chunks" / request.output_path.stem)
        chunks_dir.mkdir(parents=True, exist_ok=True)

        work_units = self._build_units(request)
        total = len(work_units)
        sample_rate = 24000
        assembled: list[np.ndarray] = []
        chunk_records: list[ChunkRecord] = []
        timeline_sec = 0.0
        retry_only = set(request.retry_chunk_indices or [])

        # Load default voice once when not multi-voice
        current_voice_id: str | None = None
        provider = None

        def ensure_voice(voice_id: str) -> None:
            nonlocal current_voice_id, provider, sample_rate
            if voice_id == current_voice_id and provider is not None:
                return
            provider, voice = self.registry.resolve(voice_id)
            provider.load_voice(voice, device=request.device)
            current_voice_id = voice_id
            sample_rate = voice.sample_rate or sample_rate

        # Pre-load existing chunks when resuming or partial retry
        existing_audio: dict[int, np.ndarray] = {}
        if request.resume_from_chunk > 0 or retry_only:
            for i in range(total):
                if retry_only and i in retry_only:
                    continue
                if i < request.resume_from_chunk or (retry_only and i not in retry_only):
                    chunk_path = chunks_dir / f"chunk_{i:05d}.wav"
                    if chunk_path.is_file():
                        try:
                            audio, sr = read_wav(chunk_path)
                            existing_audio[i] = audio
                            sample_rate = sr
                        except Exception:
                            pass

        for i, unit in enumerate(work_units):
            if controller.cancelled:
                break

            # Skip synthesis if we have existing chunk and not in retry set
            if i in existing_audio and (not retry_only or i not in retry_only):
                audio = existing_audio[i]
                chunk_path = chunks_dir / f"chunk_{i:05d}.wav"
                assembled.append(audio)
                dur = float(len(audio) / sample_rate) if sample_rate else 0.0
                chunk_records.append(
                    ChunkRecord(
                        index=i,
                        text=unit.text if unit.kind == "speech" else "",
                        start_sec=timeline_sec,
                        end_sec=timeline_sec + dur,
                        duration_sec=dur,
                        kind=unit.kind,
                        speaker=unit.speaker,
                        file_path=str(chunk_path) if chunk_path.is_file() else None,
                    )
                )
                timeline_sec += dur
                continue

            if i < request.resume_from_chunk and i not in retry_only:
                chunk_path = chunks_dir / f"chunk_{i:05d}.wav"
                if chunk_path.is_file():
                    audio, sr = read_wav(chunk_path)
                    sample_rate = sr
                    assembled.append(audio)
                    dur = float(len(audio) / sample_rate) if sample_rate else 0.0
                    chunk_records.append(
                        ChunkRecord(
                            index=i,
                            text=unit.text if unit.kind == "speech" else "",
                            start_sec=timeline_sec,
                            end_sec=timeline_sec + dur,
                            duration_sec=dur,
                            kind=unit.kind,
                            speaker=unit.speaker,
                            file_path=str(chunk_path),
                        )
                    )
                    timeline_sec += dur
                    continue

            controller.wait_if_paused()
            if controller.cancelled:
                break

            if on_progress:
                on_progress(
                    {
                        "status": "generating",
                        "chunk": i + 1,
                        "total": total,
                        "percent": int((i / max(total, 1)) * 100),
                        "message": f"Generating... Chunk {i + 1} / {total}",
                    }
                )

            start_sec = timeline_sec
            if unit.kind == "break":
                audio = silence(unit.pause_ms or settings.sentence_pause_ms, sample_rate)
            else:
                voice_id = request.voice_id
                if unit.speaker and request.speaker_map:
                    voice_id = request.speaker_map.get(unit.speaker, request.voice_id)
                ensure_voice(voice_id)
                assert provider is not None
                local_settings = VoiceSettings(
                    speed=unit.speed or settings.speed,
                    pitch=settings.pitch,
                    volume=settings.volume,
                    sentence_pause_ms=settings.sentence_pause_ms,
                    paragraph_pause_ms=settings.paragraph_pause_ms,
                    speaker_pause_ms=settings.speaker_pause_ms,
                )
                cache_key = None
                cached = None
                if request.cache_enabled:
                    cache_key = AudioCache.make_key(
                        unit.text,
                        voice_id,
                        provider.id,
                        {
                            "speed": local_settings.speed,
                            "volume": local_settings.volume,
                        },
                    )
                    cached = self.cache.get(cache_key)
                if cached:
                    audio, sr = cached
                    sample_rate = sr
                else:
                    try:
                        speak_text = self.processor.prepare_for_synthesis(unit.text)
                        if not speak_text:
                            audio = silence(settings.sentence_pause_ms, sample_rate)
                        else:
                            result = provider.synthesize(speak_text, local_settings)
                            audio = result.samples
                            sample_rate = result.sample_rate
                            if len(audio) == 0:
                                audio = silence(settings.sentence_pause_ms, sample_rate)
                            elif request.cache_enabled and cache_key:
                                self.cache.put(cache_key, audio, sample_rate)
                    except Exception as exc:
                        msg = str(exc).lower()
                        # Kokoro/phonemizer: punctuation-only chunks — skip instead of aborting
                        if "no phonemes" in msg or "nothing to synthesize" in msg:
                            logger.warning("Skipping non-phonemic chunk %s: %s", i, exc)
                            audio = silence(settings.sentence_pause_ms, sample_rate)
                            if on_progress:
                                on_progress(
                                    {
                                        "status": "chunk_skipped",
                                        "chunk": i + 1,
                                        "total": total,
                                        "percent": int(((i + 1) / max(total, 1)) * 100),
                                        "message": f"Skipped empty chunk {i + 1} / {total}",
                                    }
                                )
                        else:
                            logger.exception("Chunk %s failed", i)
                            if on_progress:
                                on_progress(
                                    {
                                        "status": "chunk_error",
                                        "chunk": i + 1,
                                        "total": total,
                                        "error": str(exc),
                                        "message": (
                                            "Unable to generate this section.\n\n"
                                            "Possible causes:\n"
                                            "- insufficient memory\n"
                                            "- model unavailable\n"
                                            "- invalid model\n"
                                            "- unsupported text"
                                        ),
                                    }
                                )
                            raise

                # Pauses after speech
                pause_ms = settings.sentence_pause_ms
                if unit.meta.get("paragraph_end"):
                    pause_ms = settings.paragraph_pause_ms
                if unit.speaker and i + 1 < total and work_units[i + 1].speaker != unit.speaker:
                    pause_ms = settings.speaker_pause_ms
                if pause_ms:
                    audio = concat_audio([audio, silence(pause_ms, sample_rate)])

            chunk_path = chunks_dir / f"chunk_{i:05d}.wav"
            write_wav(chunk_path, audio, sample_rate)
            assembled.append(audio)
            dur = float(len(audio) / sample_rate) if sample_rate else 0.0
            chunk_records.append(
                ChunkRecord(
                    index=i,
                    text=unit.text if unit.kind == "speech" else "",
                    start_sec=start_sec,
                    end_sec=start_sec + dur,
                    duration_sec=dur,
                    kind=unit.kind,
                    speaker=unit.speaker,
                    file_path=str(chunk_path),
                )
            )
            timeline_sec += dur

            if on_progress:
                on_progress(
                    {
                        "status": "chunk_done",
                        "chunk": i + 1,
                        "total": total,
                        "percent": int(((i + 1) / max(total, 1)) * 100),
                        "message": f"Generating... Chunk {i + 1} / {total}",
                        "chunk_records": [
                            {
                                "index": c.index,
                                "text": c.text[:80],
                                "start_sec": c.start_sec,
                                "end_sec": c.end_sec,
                                "duration_sec": c.duration_sec,
                            }
                            for c in chunk_records
                        ],
                    }
                )

        if controller.cancelled:
            if on_progress:
                on_progress({"status": "cancelled", "percent": 0, "message": "Cancelled"})
            return GenerationResult(
                output_path=request.output_path,
                duration_sec=timeline_sec,
                chunk_count=len(assembled),
                chunks_dir=chunks_dir,
                cancelled=True,
                chunk_records=chunk_records,
            )

        final = concat_audio(assembled)
        if request.normalize:
            final = normalize_peak(final)
        out = export_audio(
            final,
            sample_rate,
            request.output_path,
            format=request.audio_format,
            bitrate=request.bitrate,
            channels=request.channels,
        )
        if request.post_process_preset and request.post_process_preset != "none":
            try:
                pp_out = Path(out).with_name(Path(out).stem + "_pp" + Path(out).suffix)
                apply_post_process_preset(out, pp_out, request.post_process_preset)
                pp_out.replace(out)
            except Exception:
                logger.exception("Post-processing preset failed")
        # Always keep a WAV sibling for reliable in-app playback on Windows
        if Path(out).suffix.lower() != ".wav":
            try:
                write_wav(Path(out).with_suffix(".wav"), final, sample_rate)
            except Exception:
                logger.exception("Could not write WAV playback sidecar")
        duration = float(len(final) / sample_rate) if sample_rate else 0.0

        # Export subtitles alongside audio
        subtitle_path = None
        try:
            entries = [
                SubtitleEntry(index=c.index + 1, start_sec=c.start_sec, end_sec=c.end_sec, text=c.text)
                for c in chunk_records
                if c.kind == "speech" and c.text.strip()
            ]
            if entries:
                subtitle_path = Path(out).with_suffix(".srt")
                export_srt(entries, subtitle_path)
                export_vtt(entries, Path(out).with_suffix(".vtt"))
        except Exception:
            logger.exception("Subtitle export failed")

        if on_progress:
            on_progress({"status": "completed", "percent": 100, "message": "Completed", "output": str(out)})
        return GenerationResult(
            output_path=out,
            duration_sec=duration,
            chunk_count=len(work_units),
            chunks_dir=chunks_dir,
            cancelled=False,
            chunk_records=chunk_records,
            subtitle_path=subtitle_path,
        )

    def _build_units(self, request: GenerationRequest) -> list[TextChunk]:
        if request.use_multi_voice or "[" in request.text:
            sections = parse_multi_voice_script(request.text)
            # Heuristic: treat as multi-voice if more than one speaker tag found
            speakers = {s.speaker for s in sections}
            if request.use_multi_voice or (len(speakers) > 1 or any(s.speaker != "NARRATOR" for s in sections)):
                units: list[TextChunk] = []
                idx = 0
                for section in sections:
                    part = self.processor.chunk_for_tts(
                        section.text,
                        max_chars=request.chunk_max_chars,
                        speaker=section.speaker,
                    )
                    for u in part:
                        u.index = idx
                        units.append(u)
                        idx += 1
                return units
        return self.processor.chunk_for_tts(request.text, max_chars=request.chunk_max_chars)


class JobQueue:
    """Simple in-memory generation queue."""

    def __init__(self) -> None:
        self._jobs: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._paused = False
        self._counter = 0

    def add(self, title: str, payload: dict[str, Any]) -> int:
        with self._lock:
            self._counter += 1
            job = {
                "id": self._counter,
                "title": title,
                "status": "waiting",
                "payload": payload,
                "created_at": datetime.utcnow().isoformat(),
            }
            self._jobs.append(job)
            return job["id"]

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._jobs)

    def reorder(self, job_id: int, new_index: int) -> None:
        with self._lock:
            job = next((j for j in self._jobs if j["id"] == job_id), None)
            if not job:
                return
            self._jobs.remove(job)
            new_index = max(0, min(new_index, len(self._jobs)))
            self._jobs.insert(new_index, job)

    def cancel(self, job_id: int) -> None:
        with self._lock:
            for job in self._jobs:
                if job["id"] == job_id and job["status"] in ("waiting", "processing"):
                    job["status"] = "cancelled"

    def remove(self, job_id: int) -> None:
        with self._lock:
            self._jobs = [j for j in self._jobs if j["id"] != job_id]

    def retry(self, job_id: int) -> None:
        with self._lock:
            for job in self._jobs:
                if job["id"] == job_id:
                    job["status"] = "waiting"

    def pause_queue(self) -> None:
        self._paused = True

    def resume_queue(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def next_waiting(self) -> dict[str, Any] | None:
        if self._paused:
            return None
        with self._lock:
            for job in self._jobs:
                if job["status"] == "waiting":
                    job["status"] = "processing"
                    return job
        return None

    def mark(self, job_id: int, status: str) -> None:
        with self._lock:
            for job in self._jobs:
                if job["id"] == job_id:
                    job["status"] = status
