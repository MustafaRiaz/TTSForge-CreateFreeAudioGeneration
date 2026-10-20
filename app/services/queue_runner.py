"""Queue runner — processes JobQueue jobs sequentially in background."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, QTimer

from app.services.generation_service import GenerationController, GenerationRequest, GenerationService
from app.tts.base import ComputeDevice, VoiceSettings
from app.workers.tasks import GenerationWorker

logger = logging.getLogger(__name__)


def request_from_payload(payload: dict[str, Any]) -> GenerationRequest:
    settings_data = payload.get("settings") or {}
    settings = VoiceSettings(
        speed=float(settings_data.get("speed", 1.0)),
        volume=float(settings_data.get("volume", 1.0)),
        sentence_pause_ms=int(settings_data.get("sentence_pause_ms", 180)),
        paragraph_pause_ms=int(settings_data.get("paragraph_pause_ms", 400)),
        speaker_pause_ms=int(settings_data.get("speaker_pause_ms", 350)),
    )
    return GenerationRequest(
        text=payload["text"],
        voice_id=payload["voice_id"],
        output_path=Path(payload["output_path"]),
        title=payload.get("title", "Queued"),
        settings=settings,
        chunk_max_chars=int(payload.get("chunk_max_chars", 400)),
        normalize=bool(payload.get("normalize", True)),
        audio_format=str(payload.get("audio_format", "wav")),
        bitrate=str(payload.get("bitrate", "192k")),
        channels=int(payload.get("channels", 1)),
        speaker_map=payload.get("speaker_map") or {},
        use_multi_voice=bool(payload.get("use_multi_voice")),
        cache_enabled=bool(payload.get("cache_enabled", True)),
        device=ComputeDevice(payload.get("device", "auto")),
        resume_from_chunk=int(payload.get("resume_from_chunk", 0)),
        existing_chunk_dir=Path(payload["existing_chunk_dir"]) if payload.get("existing_chunk_dir") else None,
        post_process_preset=str(payload.get("post_process_preset", "none")),
    )


def payload_from_request(req: GenerationRequest) -> dict[str, Any]:
    s = req.settings or VoiceSettings()
    return {
        "text": req.text,
        "voice_id": req.voice_id,
        "output_path": str(req.output_path),
        "title": req.title,
        "settings": {
            "speed": s.speed,
            "volume": s.volume,
            "sentence_pause_ms": s.sentence_pause_ms,
            "paragraph_pause_ms": s.paragraph_pause_ms,
            "speaker_pause_ms": s.speaker_pause_ms,
        },
        "chunk_max_chars": req.chunk_max_chars,
        "normalize": req.normalize,
        "audio_format": req.audio_format,
        "bitrate": req.bitrate,
        "channels": req.channels,
        "speaker_map": req.speaker_map,
        "use_multi_voice": req.use_multi_voice,
        "cache_enabled": req.cache_enabled,
        "device": req.device.value if hasattr(req.device, "value") else str(req.device),
        "resume_from_chunk": req.resume_from_chunk,
        "existing_chunk_dir": str(req.existing_chunk_dir) if req.existing_chunk_dir else None,
        "post_process_preset": req.post_process_preset,
    }


class QueueRunner(QObject):
    """Polls JobQueue and runs one generation worker at a time."""

    job_started = Signal(int, str)
    job_finished = Signal(int, object)
    job_failed = Signal(int, str)
    progress = Signal(dict)
    queue_idle = Signal()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._worker: GenerationWorker | None = None
        self._controller = GenerationController()
        self._current_job_id: int | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        if self._worker and self._worker.isRunning():
            self._controller.cancel()

    def _tick(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        if self.ctx.job_queue.paused:
            return
        job = self.ctx.job_queue.next_waiting()
        if not job:
            return
        self._current_job_id = job["id"]
        try:
            req = request_from_payload(job["payload"])
        except Exception as exc:
            self.ctx.job_queue.mark(job["id"], "failed")
            self.job_failed.emit(job["id"], str(exc))
            return
        self._controller = GenerationController()
        self._worker = GenerationWorker(self.ctx.generation, req, self._controller, self)
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self.job_started.emit(job["id"], job.get("title", ""))
        self._worker.start()

    def _on_done(self, result) -> None:
        jid = self._current_job_id
        if jid is not None:
            self.ctx.job_queue.mark(jid, "completed")
            self.job_finished.emit(jid, result)
        self._current_job_id = None
        QTimer.singleShot(100, self._tick)

    def _on_fail(self, message: str) -> None:
        jid = self._current_job_id
        if jid is not None:
            self.ctx.job_queue.mark(jid, "failed")
            self.job_failed.emit(jid, message)
        self._current_job_id = None
        QTimer.singleShot(100, self._tick)

    def cancel_current(self) -> None:
        self._controller.cancel()
