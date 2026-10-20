"""Model Manager page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from app.services.app_context import AppContext
from app.services.model_manager import DownloadController
from app.workers.tasks import DownloadWorker


class ModelsPage(QWidget):
    notify = Signal(str)
    modelsChanged = Signal()

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.controller = DownloadController()
        self.worker: DownloadWorker | None = None

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Model", "Language", "Size", "Quality", "Installed", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self.progress = QProgressBar()
        self.status = QLabel("Select a model to install. Downloads require confirmation and are not automatic.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_download = QPushButton("Download…")
        self.btn_download.setObjectName("primaryButton")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("dangerButton")
        self.btn_import = QPushButton("Import Local…")
        self.btn_verify = QPushButton("Verify")

        actions = QHBoxLayout()
        for b in (
            self.btn_refresh,
            self.btn_download,
            self.btn_pause,
            self.btn_resume,
            self.btn_cancel,
            self.btn_delete,
            self.btn_import,
            self.btn_verify,
        ):
            actions.addWidget(b)
        actions.addStretch()

        layout = QVBoxLayout(self)
        heading = QLabel("Model Manager")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addLayout(actions)

        self.btn_refresh.clicked.connect(self.reload)
        self.btn_download.clicked.connect(self._download)
        self.btn_pause.clicked.connect(lambda: self.controller.pause())
        self.btn_resume.clicked.connect(lambda: self.controller.resume())
        self.btn_cancel.clicked.connect(lambda: self.controller.cancel())
        self.btn_delete.clicked.connect(self._delete)
        self.btn_import.clicked.connect(self._import)
        self.btn_verify.clicked.connect(self._verify)
        self.reload()

    def reload(self) -> None:
        self.ctx.refresh_offline_flag()
        items = self.ctx.models.list_catalog()
        self.table.setRowCount(0)
        for m in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            vals = [
                m.name,
                m.language,
                f"{m.size_mb:.0f} MB",
                m.quality,
                "Yes" if m.installed else "No",
                m.provider,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(256, m.id)
                self.table.setItem(row, col, item)

    def _selected_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(256)

    def _download(self) -> None:
        mid = self._selected_id()
        if not mid:
            return
        if self.ctx.settings.get("offline_mode"):
            QMessageBox.warning(self, "Offline Mode", "Disable Offline Mode in Settings to download models.")
            return
        catalog = {m.id: m for m in self.ctx.models.list_catalog()}
        meta = catalog.get(mid)
        if not meta:
            return
        if meta.installed:
            QMessageBox.information(self, "Installed", "This model is already installed.")
            return
        confirm = QMessageBox.question(
            self,
            "Confirm download",
            f"Download {meta.name}?\n\n"
            f"Language: {meta.language}\n"
            f"Quality: {meta.quality}\n"
            f"Approximate size: {meta.size_mb:.0f} MB\n\n"
            "Internet is required for this step. Generation will work offline afterward.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.controller = DownloadController()
        self.worker = DownloadWorker(self.ctx.models, mid, self.controller, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(lambda e: QMessageBox.critical(self, "Download failed", e))
        self.progress.setValue(0)
        self.worker.start()

    def _on_progress(self, message: str, pct: float) -> None:
        self.status.setText(message)
        self.progress.setValue(int(pct))

    def _on_done(self, model_id: str) -> None:
        self.status.setText(f"Installed {model_id}")
        self.progress.setValue(100)
        self.reload()
        self.modelsChanged.emit()
        self.notify.emit("Model downloaded")

    def _delete(self) -> None:
        mid = self._selected_id()
        if not mid:
            return
        if QMessageBox.question(self, "Delete model", f"Delete {mid} from disk?") != QMessageBox.StandardButton.Yes:
            return
        self.ctx.models.delete_model(mid)
        self.reload()
        self.modelsChanged.emit()

    def _import(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Import model folder")
        if not path:
            # Also allow importing a single reference audio as a Chatterbox clone
            audio, _ = QFileDialog.getOpenFileName(
                self,
                "Or import Chatterbox reference audio",
                "",
                "Audio (*.wav *.flac *.mp3 *.ogg);;All files (*.*)",
            )
            if not audio:
                return
            from PySide6.QtWidgets import QInputDialog

            name, ok = QInputDialog.getText(self, "Clone name", "Name for this voice clone:", text=Path(audio).stem)
            if not ok or not name.strip():
                return
            try:
                dest = self.ctx.models.import_clone(Path(audio), name.strip())
                QMessageBox.information(self, "Imported", f"Clone imported to {dest}")
                self.reload()
                self.modelsChanged.emit()
            except Exception as exc:
                QMessageBox.warning(self, "Import failed", str(exc))
            return
        provider = "piper"
        p = Path(path)
        names = {f.name.lower() for f in p.iterdir() if f.is_file()}
        if any("kokoro" in n and n.endswith(".onnx") for n in names) or "voices-v1.0.bin" in names:
            provider = "kokoro"
        elif "t3_nano_v1.safetensors" in names or "s3gen_meanflow.safetensors" in names:
            provider = "chatterbox"
        try:
            dest = self.ctx.models.import_local(provider, p)
            QMessageBox.information(self, "Imported", f"Imported to {dest}")
            self.reload()
            self.modelsChanged.emit()
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    def _verify(self) -> None:
        mid = self._selected_id()
        if not mid:
            return
        ok, msg = self.ctx.models.verify(mid)
        QMessageBox.information(self, "Verify", f"{'OK' if ok else 'Failed'}: {msg}")
