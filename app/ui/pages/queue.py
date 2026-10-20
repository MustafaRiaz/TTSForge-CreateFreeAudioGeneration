"""Generation queue management page."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QFileDialog,
)

from app.services.app_context import AppContext
from app.services.queue_runner import payload_from_request, request_from_payload


class QueuePage(QWidget):
    notify = Signal(str)

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._runner = None

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "Title", "Voice", "Status", "Created"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_up = QPushButton("Move Up")
        self.btn_down = QPushButton("Move Down")
        self.btn_pause = QPushButton("Pause Queue")
        self.btn_resume = QPushButton("Resume Queue")
        self.btn_cancel = QPushButton("Cancel Job")
        self.btn_cancel.setObjectName("dangerButton")
        self.btn_retry = QPushButton("Retry")
        self.btn_remove = QPushButton("Remove")
        self.btn_clear_done = QPushButton("Clear Completed")
        self.status = QLabel("Queue idle")
        self.status.setObjectName("muted")

        row = QHBoxLayout()
        for b in (
            self.btn_refresh,
            self.btn_up,
            self.btn_down,
            self.btn_pause,
            self.btn_resume,
            self.btn_cancel,
            self.btn_retry,
            self.btn_remove,
            self.btn_clear_done,
        ):
            row.addWidget(b)
        row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Generation Queue", objectName="heading"))
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        layout.addLayout(row)

        self.btn_refresh.clicked.connect(self.reload)
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        self.btn_pause.clicked.connect(self._pause)
        self.btn_resume.clicked.connect(self._resume)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_retry.clicked.connect(self._retry)
        self.btn_remove.clicked.connect(self._remove)
        self.btn_clear_done.clicked.connect(self._clear_done)
        self.reload()

    def set_runner(self, runner) -> None:
        self._runner = runner
        if runner:
            runner.job_started.connect(lambda jid, title: (self.reload(), self.status.setText(f"Processing: {title}")))
            runner.job_finished.connect(lambda jid, _: (self.reload(), self.notify.emit(f"Queue job {jid} completed")))
            runner.job_failed.connect(lambda jid, msg: (self.reload(), self.notify.emit(f"Queue job {jid} failed")))
            runner.progress.connect(lambda p: self.status.setText(p.get("message", "")))

    def reload(self) -> None:
        jobs = self.ctx.job_queue.list()
        self.table.setRowCount(0)
        for job in jobs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            payload = job.get("payload") or {}
            voice = payload.get("voice_id", "")
            vals = [
                str(job["id"]),
                job.get("title", ""),
                voice,
                job.get("status", ""),
                job.get("created_at", "")[:19],
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job["id"])
                self.table.setItem(row, col, item)
        paused = "paused" if self.ctx.job_queue.paused else "running"
        self.status.setText(f"Queue {paused} — {len(jobs)} job(s)")

    def _selected_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _move(self, delta: int) -> None:
        jid = self._selected_id()
        if jid is None:
            return
        jobs = self.ctx.job_queue.list()
        idx = next((i for i, j in enumerate(jobs) if j["id"] == jid), -1)
        if idx < 0:
            return
        new_idx = max(0, min(len(jobs) - 1, idx + delta))
        self.ctx.job_queue.reorder(jid, new_idx)
        self.reload()

    def _pause(self) -> None:
        self.ctx.job_queue.pause_queue()
        self.reload()

    def _resume(self) -> None:
        self.ctx.job_queue.resume_queue()
        self.reload()

    def _cancel(self) -> None:
        jid = self._selected_id()
        if jid:
            self.ctx.job_queue.cancel(jid)
            if self._runner:
                self._runner.cancel_current()
            self.reload()

    def _retry(self) -> None:
        jid = self._selected_id()
        if jid:
            self.ctx.job_queue.retry(jid)
            self.reload()

    def _remove(self) -> None:
        jid = self._selected_id()
        if jid:
            self.ctx.job_queue.remove(jid)
            self.reload()

    def _clear_done(self) -> None:
        for job in list(self.ctx.job_queue.list()):
            if job.get("status") in ("completed", "cancelled", "failed"):
                self.ctx.job_queue.remove(job["id"])
        self.reload()

    def add_job_from_request(self, req, title: str | None = None) -> int:
        payload = payload_from_request(req)
        return self.ctx.job_queue.add(title or req.title, payload)
