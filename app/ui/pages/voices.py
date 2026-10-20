"""Voices page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from app.services.app_context import AppContext
from app.services.generation_service import GenerationController, GenerationRequest
from app.tts.base import VoiceSettings
from app.workers.tasks import GenerationWorker


class VoicesPage(QWidget):
    notify = Signal(str)

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.worker: GenerationWorker | None = None

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search voices…")
        self.lang = QComboBox()
        self.lang.addItem("All languages", "")
        self.list = QListWidget()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_favorite = QPushButton("Toggle Favorite")
        self.btn_preview = QPushButton("Preview")
        self.btn_compare = QPushButton("A/B Compare")
        self.btn_save_clone = QPushButton("Save Clone…")
        self.btn_use = QPushButton("Use in Studio")
        self.btn_use.setObjectName("primaryButton")
        self.info = QLabel("Select a voice")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)

        tools = QHBoxLayout()
        tools.addWidget(self.search, 2)
        tools.addWidget(self.lang)
        tools.addWidget(self.btn_refresh)

        actions = QHBoxLayout()
        for b in (self.btn_favorite, self.btn_preview, self.btn_compare, self.btn_save_clone, self.btn_use):
            actions.addWidget(b)
        actions.addStretch()

        layout = QVBoxLayout(self)
        heading = QLabel("Voices")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        layout.addLayout(tools)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.info)
        layout.addLayout(actions)

        self.search.textChanged.connect(self.reload)
        self.lang.currentIndexChanged.connect(self.reload)
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_favorite.clicked.connect(self._toggle_fav)
        self.btn_preview.clicked.connect(self._preview)
        self.btn_compare.clicked.connect(self._compare)
        self.btn_save_clone.clicked.connect(self._save_clone)
        self.btn_use.clicked.connect(self._use)
        self.list.currentItemChanged.connect(self._on_select)
        self.on_use_voice = None  # set by main window
        self.reload()
    def reload(self) -> None:
        q = self.search.text()
        lang = self.lang.currentData() or ""
        favorites = set(self.ctx.db.list_favorites())
        recent = self.ctx.db.list_recent_voices()
        voices = self.ctx.registry.all_voices()

        # refresh language filter options once
        if self.lang.count() <= 1:
            langs = sorted({v.language for v in voices})
            for l in langs:
                self.lang.addItem(l, l)

        self.list.clear()
        # Favorites first, then recent, then rest
        def sort_key(v):
            return (
                0 if v.id in favorites else 1,
                0 if v.id in recent else 1,
                v.name.lower(),
            )

        for v in sorted(voices, key=sort_key):
            if not v.matches_query(q):
                continue
            if lang and v.language != lang:
                continue
            star = "★ " if v.id in favorites else ""
            status = "Installed" if v.installed else "Not installed"
            item = QListWidgetItem(f"{star}{v.name} — {v.language} — {v.provider} [{status}]")
            item.setData(256, v.id)
            self.list.addItem(item)

    def _selected_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(256) if item else None

    def _on_select(self, *_args) -> None:
        vid = self._selected_id()
        if not vid:
            return
        v = self.ctx.registry.find_voice(vid)
        if not v:
            return
        caps = self.ctx.registry.get(v.provider).get_capabilities()
        pitch_note = caps.notes.get("pitch", "")
        clone_note = caps.notes.get("cloning", "") if getattr(caps, "voice_cloning", False) else ""
        self.info.setText(
            f"{v.name}\nLanguage: {v.language}\nGender: {v.gender or '—'}\n"
            f"Accent: {v.accent or '—'}\nQuality: {v.quality}\n"
            f"Installed: {v.installed}\nPath: {v.model_path or '—'}\n"
            f"{pitch_note}\n{clone_note}".strip()
        )

    def _toggle_fav(self) -> None:
        vid = self._selected_id()
        if not vid:
            return
        favs = set(self.ctx.db.list_favorites())
        if vid in favs:
            self.ctx.db.remove_favorite(vid)
        else:
            self.ctx.db.add_favorite(vid)
        self.reload()

    def _preview(self) -> None:
        vid = self._selected_id()
        if not vid:
            return
        v = self.ctx.registry.find_voice(vid)
        if not v or not v.installed:
            QMessageBox.information(self, "Voice", "Install this voice first in Model Manager.")
            return
        out = self.ctx.paths["temp"] / "voice_preview.wav"
        req = GenerationRequest(
            text=f"Hello, my name is {v.name}. This is a VoiceForge preview.",
            voice_id=vid,
            output_path=out,
            title="Preview",
            settings=VoiceSettings(speed=1.0),
            chunk_max_chars=200,
        )
        self.worker = GenerationWorker(self.ctx.generation, req, GenerationController(), self)
        self.worker.finished_ok.connect(lambda r: self.notify.emit(f"Preview ready: {r.output_path}"))
        self.worker.failed.connect(lambda e: QMessageBox.warning(self, "Preview failed", e))
        self.worker.start()
        self.notify.emit("Generating preview…")

    def _compare(self) -> None:
        vid = self._selected_id()
        if not vid:
            return
        v = self.ctx.registry.find_voice(vid)
        if not v or not v.installed:
            QMessageBox.information(self, "Voice", "Install this voice first in Model Manager.")
            return
        dlg = VoiceCompareDialog(self.ctx, vid, self)
        dlg.exec()

    def _save_clone(self) -> None:
        """Import a reference WAV as a named Chatterbox clone profile."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select reference audio (~10 seconds recommended)",
            "",
            "Audio (*.wav *.flac *.mp3 *.ogg)",
        )
        if not path:
            return
        default_name = Path(path).stem
        name, ok = QInputDialog.getText(self, "Clone name", "Name for this voice clone:", text=default_name)
        if not ok or not name.strip():
            return
        try:
            dest = self.ctx.models.import_clone(Path(path), name.strip())
            QMessageBox.information(
                self,
                "Clone saved",
                f"Saved clone to {dest}\n\n"
                "Download Chatterbox Nano in Model Manager and install chatterbox-tts "
                "if you have not already, then select the clone in Studio.",
            )
            self.reload()
            self.notify.emit(f"Clone saved: {dest.name}")
        except Exception as exc:
            QMessageBox.warning(self, "Clone failed", str(exc))

    def _use(self) -> None:
        vid = self._selected_id()
        if not vid:
            return
        self.ctx.settings.set("default_voice", vid)
        if callable(self.on_use_voice):
            self.on_use_voice(vid)
        self.notify.emit("Default voice updated")


class VoiceCompareDialog:
    """Generate side-by-side previews for two voices."""

    def __init__(self, ctx: AppContext, voice_a: str, parent=None) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit

        self._ctx = ctx
        self._voice_a = voice_a
        self._dlg = QDialog(parent)
        self._dlg.setWindowTitle("Voice A/B Compare")
        self._dlg.resize(520, 320)
        self._text = QPlainTextEdit("The quick brown fox jumps over the lazy dog.")
        self._voice_b = QComboBox()
        for v in ctx.registry.all_voices():
            if v.installed:
                self._voice_b.addItem(f"{v.name} ({v.language})", v.id)
        idx = self._voice_b.findData(voice_a)
        if idx >= 0:
            self._voice_b.setCurrentIndex(idx)
        btn_gen = QPushButton("Generate Both")
        btn_gen.clicked.connect(self._generate)
        self._status = QLabel("Select voices and click Generate Both")
        self._status.setObjectName("muted")
        layout = QVBoxLayout(self._dlg)
        layout.addWidget(QLabel("Sample text"))
        layout.addWidget(self._text)
        layout.addWidget(QLabel("Voice B"))
        layout.addWidget(self._voice_b)
        layout.addWidget(btn_gen)
        layout.addWidget(self._status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self._dlg.reject)
        buttons.accepted.connect(self._dlg.accept)
        layout.addWidget(buttons)
        self._workers: list[GenerationWorker] = []

    def exec(self) -> bool:
        return self._dlg.exec()

    def _generate(self) -> None:
        text = self._text.toPlainText().strip() or "Preview sample."
        voice_b = self._voice_b.currentData()
        if not voice_b:
            return
        out_a = self._ctx.paths["temp"] / "compare_a.wav"
        out_b = self._ctx.paths["temp"] / "compare_b.wav"
        va = self._ctx.registry.find_voice(self._voice_a)
        vb = self._ctx.registry.find_voice(voice_b)
        self._status.setText("Generating…")
        pending = {"count": 2}

        def done(which: str, path: Path):
            pending["count"] -= 1
            if pending["count"] <= 0:
                self._status.setText(f"A: {out_a.name} | B: {out_b.name} — open from temp folder")
                import subprocess
                import sys
                folder = str(path.parent)
                if sys.platform == "win32":
                    subprocess.Popen(["explorer", folder])
                else:
                    subprocess.Popen(["xdg-open", folder])

        for vid, out, label in ((self._voice_a, out_a, "A"), (voice_b, out_b, "B")):
            req = GenerationRequest(
                text=text,
                voice_id=vid,
                output_path=out,
                title=f"Compare {label}",
                settings=VoiceSettings(speed=1.0),
                chunk_max_chars=200,
            )
            w = GenerationWorker(self._ctx.generation, req, GenerationController(), self._dlg)
            w.finished_ok.connect(lambda r, lbl=label, p=out: done(lbl, p))
            w.failed.connect(lambda e: self._status.setText(f"Failed: {e}"))
            self._workers.append(w)
            w.start()
