"""Background workers for GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from app.services.generation_service import GenerationController, GenerationRequest, GenerationService
from app.services.model_manager import DownloadController, ModelManagerService


class GenerationWorker(QThread):
    progress = Signal(dict)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: GenerationService,
        request: GenerationRequest,
        controller: GenerationController,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.request = request
        self.controller = controller

    def run(self) -> None:
        try:
            result = self.service.generate(
                self.request,
                controller=self.controller,
                on_progress=lambda p: self.progress.emit(p),
            )
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    progress = Signal(str, float)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        service: ModelManagerService,
        model_id: str,
        controller: DownloadController,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.model_id = model_id
        self.controller = controller

    def run(self) -> None:
        try:
            self.service.download(
                self.model_id,
                controller=self.controller,
                on_progress=lambda msg, pct: self.progress.emit(msg, pct),
            )
            self.finished_ok.emit(self.model_id)
        except Exception as exc:
            self.failed.emit(str(exc))


class BatchWorker(QThread):
    progress = Signal(dict)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        service: GenerationService,
        jobs: list[GenerationRequest],
        controller: GenerationController,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.jobs = jobs
        self.controller = controller

    def run(self) -> None:
        results: list[Any] = []
        try:
            total = len(self.jobs)
            for i, req in enumerate(self.jobs):
                if self.controller.cancelled:
                    break
                self.progress.emit(
                    {
                        "status": "batch",
                        "index": i + 1,
                        "total": total,
                        "message": f"Batch {i + 1}/{total}: {req.title}",
                    }
                )
                result = self.service.generate(req, controller=self.controller, on_progress=None)
                results.append(result)
            self.finished_ok.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))
