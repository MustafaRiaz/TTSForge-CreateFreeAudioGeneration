"""Studio page — main TTS workspace."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QTabWidget,
    QScrollArea,
    QFrame,
    QMenu,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QSplitter,
)

from app.services.app_context import AppContext
from app.services.generation_service import GenerationController, GenerationRequest
from app.tts.base import ComputeDevice, VoiceSettings
from app.ui.widgets.audio_player import AudioPlayerWidget
from app.ui.widgets.voice_picker import VoiceComboBox
from app.workers.tasks import GenerationWorker
from app.text.importers import import_document, ALLOWED_EXTENSIONS


class StudioPage(QWidget):
    notify = Signal(str)
    generationFinished = Signal(object)

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.controller = GenerationController()
        self.worker: GenerationWorker | None = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(15000)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("studioEditor")
        self.editor.setPlaceholderText("Start writing your script…\n\nOr import a document to turn it into natural speech.")
        self.editor.setAcceptDrops(True)
        self.editor.dragEnterEvent = self._drag_enter  # type: ignore
        self.editor.dropEvent = self._drop  # type: ignore

        self.stats = QLabel("0 chars · 0 words · 0 paragraphs · ~0s")
        self.stats.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress_label = QLabel("Ready")
        self.progress_label.setObjectName("muted")

        self.voice_combo = VoiceComboBox()
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.5, 2.0)
        self.speed.setSingleStep(0.05)
        self.speed.setValue(float(ctx.settings.get("speed", 1.0)))
        self.volume = QDoubleSpinBox()
        self.volume.setRange(0.1, 2.0)
        self.volume.setSingleStep(0.05)
        self.volume.setValue(float(ctx.settings.get("volume", 1.0)))
        self.preset = QComboBox()
        for key, meta in __import__("app.core.paths", fromlist=["QUALITY_PRESETS"]).QUALITY_PRESETS.items():
            self.preset.addItem(meta["label"], key)
        idx = self.preset.findData(ctx.settings.get("quality_preset", "balanced"))
        if idx >= 0:
            self.preset.setCurrentIndex(idx)

        self.reference_audio = QLineEdit()
        self.reference_audio.setPlaceholderText("Reference audio for cloning (Chatterbox)…")
        self.reference_audio.setReadOnly(True)
        remembered_ref = ctx.settings.get("last_reference_audio") or ""
        if remembered_ref:
            self.reference_audio.setText(str(remembered_ref))
        self.btn_browse_ref = QPushButton("Reference…")
        self.ref_row_label = QLabel("Clone ref")
        self._ref_widgets = (self.ref_row_label, self.reference_audio, self.btn_browse_ref)

        self.btn_generate = QPushButton("Generate")
        self.btn_generate.setObjectName("primaryButton")
        self.btn_save = QPushButton("Save Audio")
        self.btn_save.setEnabled(False)
        self.btn_stop = QPushButton("Stop")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")
        self.btn_clear = QPushButton("Clear")
        self.btn_paste = QPushButton("Paste")
        self.btn_import = QPushButton("Import…")
        self.btn_find = QPushButton("Find/Replace")
        self.btn_queue = QPushButton("Add to Queue")
        self.btn_export_srt = QPushButton("Export SRT")
        self.btn_retry_chunk = QPushButton("Retry Chunk")

        self.save_location = QLineEdit()
        self.save_location.setPlaceholderText("Save location (optional — browse once, then Save reuses it)")
        self.save_location.setReadOnly(True)
        self.btn_browse_save = QPushButton("Browse…")
        remembered = (
            ctx.settings.get("last_save_folder")
            or ctx.settings.get("default_output_folder")
            or ""
        )
        if remembered:
            self.save_location.setText(str(remembered))

        self.chunk_list = QListWidget()
        self.chunk_list.setMaximumHeight(120)
        self.chunk_list.itemDoubleClicked.connect(self._play_chunk)

        self.player = AudioPlayerWidget()
        self.player.statusMessage.connect(self.notify)

        self._last_result = None
        self._last_request = None
        self._chunk_records: list[dict] = []
        self._pending_resume: dict | None = None
        self._queue_page = None
        self._saved_output_path: Path | None = None

        def label(text, name="sectionTitle"):
            widget = QLabel(text)
            widget.setObjectName(name)
            return widget

        def card():
            frame = QFrame()
            frame.setObjectName("card")
            box = QVBoxLayout(frame)
            box.setContentsMargins(20, 18, 20, 18)
            box.setSpacing(12)
            return frame, box

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("VOICE WORKSPACE", "eyebrow"))
        titles.addWidget(label("Studio", "heading"))
        titles.addWidget(label("Shape your script. Find your voice. Create something worth hearing.", "muted"))
        header.addLayout(titles, 1)
        self.btn_generate.setText("Generate audio")
        self.btn_generate.setToolTip("Generate the script · Ctrl+Enter")
        header.addWidget(self.btn_queue)
        header.addWidget(self.btn_generate)
        layout.addLayout(header)

        settings_card, settings_layout = card()
        top = QHBoxLayout()
        top.setSpacing(16)
        self.voice_combo.setMinimumWidth(170)
        for title, widget, stretch in (("VOICE", self.voice_combo, 4), ("SPEED", self.speed, 1),
                                        ("VOLUME", self.volume, 1), ("QUALITY", self.preset, 2)):
            column = QVBoxLayout()
            column.addWidget(label(title, "eyebrow"))
            column.addWidget(widget)
            top.addLayout(column, stretch)
        self.speed.setSuffix(" ×")
        self.volume.setSuffix(" ×")
        settings_layout.addLayout(top)
        ref_row = QHBoxLayout()
        for widget in self._ref_widgets:
            ref_row.addWidget(widget)
        settings_layout.addLayout(ref_row)
        layout.addWidget(settings_card)

        editor_panel, editor_layout = card()
        editor_header = QHBoxLayout()
        editor_header.addWidget(label("Script"), 1)
        editor_header.addWidget(self.btn_import)
        self.btn_script_tools = QPushButton("Script tools")
        menu = QMenu(self)
        for title, callback in (("Paste text", self._paste), ("Find and replace…", self._find_replace),
                                ("Insert 500 ms pause", lambda: self.editor.insertPlainText('<break time="500ms"/>')),
                                ("Undo", self.editor.undo), ("Redo", self.editor.redo),
                                ("Clear script", self.editor.clear)):
            menu.addAction(title, callback)
        self.btn_script_tools.setMenu(menu)
        editor_header.addWidget(self.btn_script_tools)
        self.btn_focus = QPushButton("Focus")
        self.btn_focus.setCheckable(True)
        self.btn_focus.setToolTip("Expand the script editor · Ctrl+Shift+F")
        editor_header.addWidget(self.btn_focus)
        editor_layout.addLayout(editor_header)
        editor_layout.addWidget(self.editor, 1)
        self.stats.setWordWrap(True)
        editor_layout.addWidget(self.stats)
        editor_layout.addWidget(label("Draft autosaves every 15 seconds · Ctrl+Enter to generate", "muted"))

        right_panel, right_layout = card()
        right_layout.addWidget(label("Audio preview"))
        right_layout.addWidget(label("Listen, review, and export your narration.", "muted"))
        review_tabs = QTabWidget()
        self.player_scroll = QScrollArea()
        self.player_scroll.setObjectName("playerScroll")
        self.player_scroll.setWidgetResizable(True)
        self.player_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.player_scroll.setWidget(self.player)
        review_tabs.addTab(self.player_scroll, "Player")
        sections_panel = QWidget()
        sections_layout = QVBoxLayout(sections_panel)
        sections_layout.setContentsMargins(12, 12, 12, 12)
        review_tabs.addTab(sections_panel, "Sections")
        right_layout.addWidget(review_tabs, 1)
        chunk_header = QHBoxLayout()
        chunk_header.addWidget(label("Generated sections"), 1)
        chunk_header.addWidget(self.btn_retry_chunk)
        sections_layout.addLayout(chunk_header)
        self.chunk_list.setMinimumHeight(85)
        self.chunk_list.setMaximumHeight(16777215)
        sections_layout.addWidget(self.chunk_list, 1)
        self.chunk_hint = label("Sections appear here as audio is generated. Double-click to seek.", "muted")
        self.chunk_hint.setWordWrap(True)
        sections_layout.addWidget(self.chunk_hint)
        self.progress_label.setWordWrap(True)
        right_layout.addWidget(self.progress_label)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        right_layout.addWidget(self.progress)
        transport = QHBoxLayout()
        for button in (self.btn_pause, self.btn_resume, self.btn_stop):
            transport.addWidget(button)
            button.setEnabled(False)
        transport.addStretch()
        right_layout.addLayout(transport)
        self.btn_retry_chunk.setEnabled(False)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(14)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(editor_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([620, 460])
        self.btn_focus.toggled.connect(lambda checked: (right_panel.setVisible(not checked), self.btn_focus.setText("Exit focus" if checked else "Focus")))
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, activated=self.btn_focus.click)
        layout.addWidget(self.splitter, 1)

        export_card, export_layout = card()
        save_row = QHBoxLayout()
        save_row.addWidget(label("EXPORT TO", "eyebrow"))
        save_row.addWidget(self.save_location, 1)
        save_row.addWidget(self.btn_browse_save)
        save_row.addWidget(self.btn_export_srt)
        save_row.addWidget(self.btn_save)
        export_layout.addLayout(save_row)
        layout.addWidget(export_card)
        # These commands now live in the script menu.
        for button in (self.btn_clear, self.btn_paste, self.btn_find):
            button.hide()

        self.editor.textChanged.connect(self._update_stats)
        self.btn_generate.clicked.connect(self.start_generation)
        self.btn_save.clicked.connect(self.save_audio)
        self.btn_browse_save.clicked.connect(self._browse_save_location)
        self.btn_browse_ref.clicked.connect(self._browse_reference_audio)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        self.btn_stop.clicked.connect(self.stop_generation)
        self.btn_pause.clicked.connect(self._pause_generation)
        self.btn_resume.clicked.connect(self._resume_generation)
        self.btn_clear.clicked.connect(self.editor.clear)
        self.btn_paste.clicked.connect(self._paste)
        self.btn_import.clicked.connect(self._import)
        self.btn_find.clicked.connect(self._find_replace)
        self.btn_queue.clicked.connect(self._add_to_queue)
        self.btn_export_srt.clicked.connect(self._export_srt)
        self.btn_retry_chunk.clicked.connect(self._retry_selected_chunk)
        self.preset.currentIndexChanged.connect(self._on_preset)

        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._find_replace)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_generation)

        self.reload_voices()
        self._load_autosave()
        self._update_stats()
        self._on_voice_changed()

    def _voice_supports_cloning(self, voice_id: str | None) -> bool:
        if not voice_id:
            return False
        voice = self.ctx.registry.find_voice(voice_id)
        if not voice:
            return False
        try:
            caps = self.ctx.registry.get(voice.provider).get_capabilities()
        except Exception:
            return False
        return bool(getattr(caps, "voice_cloning", False))

    def _on_voice_changed(self, *_args) -> None:
        cloning = self._voice_supports_cloning(self.voice_combo.currentData())
        for w in self._ref_widgets:
            w.setVisible(cloning)
        # Prefill from saved clone metadata when available
        if cloning:
            voice = self.ctx.registry.find_voice(self.voice_combo.currentData() or "")
            if voice and voice.metadata.get("reference_audio") and not self.reference_audio.text():
                self.reference_audio.setText(str(voice.metadata["reference_audio"]))

    def _browse_reference_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select reference audio for cloning",
            "",
            "Audio (*.wav *.flac *.mp3 *.ogg)",
        )
        if path:
            self.reference_audio.setText(path)
            self.ctx.settings.set("last_reference_audio", path)
    def reload_voices(self) -> None:
        current = self.voice_combo.currentData()
        self.voice_combo.clear()
        voices = [v for v in self.ctx.registry.all_voices() if v.installed]
        if not voices:
            self.voice_combo.addItem("No installed voices — open Model Manager", "")
            return
        for v in voices:
            label = f"{v.name} ({v.language}) — {v.provider}"
            self.voice_combo.addItem(label, v.id)
        default = self.ctx.settings.get("default_voice") or current
        if default:
            i = self.voice_combo.findData(default)
            if i >= 0:
                self.voice_combo.setCurrentIndex(i)
        self._on_voice_changed()

    def _update_stats(self) -> None:
        text = self.editor.toPlainText()
        s = self.ctx.processor.stats(text)
        mins = int(s.estimated_duration_sec // 60)
        secs = int(s.estimated_duration_sec % 60)
        self.stats.setText(
            f"{s.characters:,} chars · {s.words:,} words · {s.paragraphs} paragraphs · "
            f"{s.sentences} sentences · ~{mins}m {secs}s"
        )

    def _paste(self) -> None:
        self.editor.paste()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import document",
            "",
            "Documents (*.txt *.md *.markdown *.html *.htm *.docx *.pdf *.epub)",
        )
        if path:
            self._load_file(Path(path))

    def _load_file(self, path: Path) -> None:
        try:
            text = import_document(path)
            self.editor.setPlainText(text)
            self.notify.emit(f"Imported {path.name}")
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    def _drag_enter(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop(self, event) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in ALLOWED_EXTENSIONS:
                self._load_file(path)
                break

    def _find_replace(self) -> None:
        find, ok = QInputDialog.getText(self, "Find", "Find:")
        if not ok or not find:
            return
        replace, ok2 = QInputDialog.getText(self, "Replace", "Replace with:")
        if not ok2:
            return
        text = self.editor.toPlainText()
        self.editor.setPlainText(text.replace(find, replace))

    def _on_preset(self) -> None:
        key = self.preset.currentData()
        if key:
            self.ctx.settings.apply_quality_preset(key)

    def set_queue_page(self, queue_page) -> None:
        self._queue_page = queue_page

    def set_pending_resume(self, state: dict) -> None:
        """Called from main window when crash recovery is accepted."""
        self._pending_resume = state
        if state.get("text"):
            self.editor.setPlainText(state["text"])
        voice = state.get("voice_id")
        if voice:
            i = self.voice_combo.findData(voice)
            if i >= 0:
                self.voice_combo.setCurrentIndex(i)

    def resume_generation(self) -> None:
        """Resume from last completed chunk after crash/cancel."""
        if not self._pending_resume:
            QMessageBox.information(self, "Resume", "No pending generation to resume.")
            return
        state = self._pending_resume
        out_path = Path(state.get("output_path", ""))
        chunks_dir = out_path.parent / "chunks" / out_path.stem if out_path else None
        resume_from = int(state.get("resume_from_chunk", 0))
        if chunks_dir and chunks_dir.is_dir():
            existing = sorted(chunks_dir.glob("chunk_*.wav"))
            resume_from = len(existing)
        text = self.editor.toPlainText().strip() or state.get("text", "")
        if not text:
            return
        voice_id = self.voice_combo.currentData() or state.get("voice_id")
        if not voice_id:
            return
        req = self._build_request(text, voice_id, out_path if out_path else None)
        if not req:
            return
        req.resume_from_chunk = resume_from
        req.existing_chunk_dir = chunks_dir
        self._start_worker(req)
        self._pending_resume = None

    def _build_request(self, text: str, voice_id: str, out_path: Path | None = None) -> GenerationRequest | None:
        fmt = str(self.ctx.settings.get("audio_format", "wav")).lower().lstrip(".")
        if fmt not in {"wav", "mp3", "flac", "ogg"}:
            fmt = "wav"
        if out_path is None:
            # Generate into a temp file first; user picks a final location via Save Audio.
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_dir = Path(self.ctx.paths["temp"]) / "studio"
            temp_dir.mkdir(parents=True, exist_ok=True)
            out_path = temp_dir / f"voiceforge_{stamp}.{fmt}"

        out_path.parent.mkdir(parents=True, exist_ok=True)

        device = ComputeDevice(self.ctx.settings.get("compute_device", "auto"))
        extra: dict = {}
        ref = self.reference_audio.text().strip()
        if ref and self._voice_supports_cloning(voice_id):
            extra["reference_audio"] = ref
        settings = VoiceSettings(
            speed=float(self.speed.value()),
            volume=float(self.volume.value()),
            sentence_pause_ms=int(self.ctx.settings.get("sentence_pause_ms", 180)),
            paragraph_pause_ms=int(self.ctx.settings.get("paragraph_pause_ms", 400)),
            speaker_pause_ms=int(self.ctx.settings.get("speaker_pause_ms", 350)),
            extra=extra,
        )
        if self._voice_supports_cloning(voice_id):
            voice = self.ctx.registry.find_voice(voice_id)
            needs_ref = not (voice and voice.metadata.get("reference_audio"))
            if needs_ref and not ref:
                QMessageBox.warning(
                    self,
                    "Reference audio required",
                    "This Chatterbox voice needs a reference WAV (~10 seconds).\n"
                    "Click Reference… to choose one, or save a clone on the Voices page.",
                )
                return None

        use_multi = "[" in text and "]" in text
        speaker_map = {}
        if use_multi:
            from app.text.processor import parse_multi_voice_script
            from app.ui.dialogs.dialogue_editor import DialogueEditorDialog

            sections = parse_multi_voice_script(text)
            speakers = sorted({s.speaker for s in sections})
            dlg = DialogueEditorDialog(speakers, voice_id, self.ctx, self)
            if dlg.exec():
                speaker_map = dlg.mapping()
            else:
                return None

        return GenerationRequest(
            text=text,
            voice_id=voice_id,
            output_path=out_path,
            title=out_path.stem,
            settings=settings,
            chunk_max_chars=int(self.ctx.settings.get("chunk_max_chars", 400)),
            normalize=bool(self.ctx.settings.get("normalize_audio", True)),
            audio_format=fmt,
            bitrate=str(self.ctx.settings.get("audio_bitrate", "192k")),
            channels=int(self.ctx.settings.get("audio_channels", 1)),
            speaker_map=speaker_map,
            use_multi_voice=bool(speaker_map),
            cache_enabled=bool(self.ctx.settings.get("cache_enabled", True)),
            device=device,
            post_process_preset=str(self.ctx.settings.get("post_process_preset", "none")),
        )

    def _browse_save_location(self) -> None:
        start = self.save_location.text().strip() or str(self.ctx.paths["exports"])
        path = QFileDialog.getExistingDirectory(self, "Select save location", start)
        if path:
            self.save_location.setText(path)
            self.ctx.settings.set("last_save_folder", path)
            self.ctx.settings.set("default_output_folder", path)
            self.notify.emit(f"Save location set: {path}")

    def _audio_filters(self, preferred_fmt: str) -> tuple[str, str]:
        filters = {
            "wav": "WAV Audio (*.wav)",
            "mp3": "MP3 Audio (*.mp3)",
            "flac": "FLAC Audio (*.flac)",
            "ogg": "OGG Audio (*.ogg)",
        }
        selected = filters.get(preferred_fmt, "WAV Audio (*.wav)")
        all_filters = ";;".join(
            [
                "WAV Audio (*.wav)",
                "MP3 Audio (*.mp3)",
                "FLAC Audio (*.flac)",
                "OGG Audio (*.ogg)",
                "All Files (*.*)",
            ]
        )
        return all_filters, selected

    def _resolve_save_destination(self, source: Path) -> Path | None:
        """Return destination path. Ask only when no save location is set yet."""
        folder_text = self.save_location.text().strip()
        if folder_text:
            folder = Path(folder_text)
            folder.mkdir(parents=True, exist_ok=True)
            return folder / source.name

        fmt = source.suffix.lower().lstrip(".") or "wav"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        start_dir = Path(
            self.ctx.settings.get("last_save_folder")
            or self.ctx.settings.get("default_output_folder")
            or self.ctx.paths["exports"]
        )
        start_dir.mkdir(parents=True, exist_ok=True)
        default_name = str(start_dir / f"voiceforge_{stamp}.{fmt}")
        all_filters, selected = self._audio_filters(fmt)
        chosen, chosen_filter = QFileDialog.getSaveFileName(
            self,
            "Save generated audio as…",
            default_name,
            all_filters,
            selected,
        )
        if not chosen:
            return None
        out_path = Path(chosen)
        ext = out_path.suffix.lower().lstrip(".")
        if ext not in {"wav", "mp3", "flac", "ogg"}:
            if "MP3" in (chosen_filter or ""):
                out_path = out_path.with_suffix(".mp3")
            elif "FLAC" in (chosen_filter or ""):
                out_path = out_path.with_suffix(".flac")
            elif "OGG" in (chosen_filter or ""):
                out_path = out_path.with_suffix(".ogg")
            else:
                out_path = out_path.with_suffix(source.suffix or ".wav")

        self.save_location.setText(str(out_path.parent))
        self.ctx.settings.set("last_save_folder", str(out_path.parent))
        self.ctx.settings.set("default_output_folder", str(out_path.parent))
        return out_path

    def save_audio(self) -> None:
        if not self._last_result or self._last_result.cancelled:
            QMessageBox.information(self, "Save", "Generate audio first.")
            return
        source = Path(self._last_result.output_path)
        if not source.is_file():
            QMessageBox.warning(self, "Save", "Generated audio file is missing.")
            return

        dest = self._resolve_save_destination(source)
        if not dest:
            return

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != dest.resolve():
                # Same extension: copy. Different extension: re-export via convert if needed.
                if source.suffix.lower() == dest.suffix.lower():
                    shutil.copy2(source, dest)
                else:
                    from app.audio.processing import convert_file, read_wav, export_audio

                    if source.suffix.lower() == ".wav":
                        samples, sr = read_wav(source)
                        export_audio(samples, sr, dest, format=dest.suffix.lstrip("."))
                    else:
                        convert_file(source, dest)
            # Copy subtitle sidecar when present
            src_srt = source.with_suffix(".srt")
            if getattr(self._last_result, "subtitle_path", None):
                src_srt = Path(self._last_result.subtitle_path)
            if src_srt.is_file():
                shutil.copy2(src_srt, dest.with_suffix(".srt"))
            wav_sidecar = source.with_suffix(".wav")
            if source.suffix.lower() != ".wav" and wav_sidecar.is_file() and dest.suffix.lower() != ".wav":
                # Keep optional WAV next to saved export for editing
                pass
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return

        self._saved_output_path = dest
        self.progress_label.setText(f"Saved — {dest}")
        self.ctx.db.add_history(
            title=dest.stem,
            voice_id=self.voice_combo.currentData(),
            duration_sec=getattr(self._last_result, "duration_sec", 0),
            output_format=dest.suffix.lstrip("."),
            output_path=str(dest),
            status="completed",
            text_preview=self.editor.toPlainText()[:200],
        )
        self.notify.emit(f"Saved to {dest}")

    def start_generation(self) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Busy", "Generation already in progress.")
            return
        text = self.editor.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Empty", "Enter some text first.")
            return
        voice_id = self.voice_combo.currentData()
        if not voice_id:
            QMessageBox.warning(self, "No voice", "Install and select a voice in Model Manager.")
            return
        req = self._build_request(text, voice_id)
        if not req:
            return
        self.ctx.db.save_crash_state(
            {
                "text": text,
                "voice_id": voice_id,
                "output_path": str(req.output_path),
                "resume_from_chunk": 0,
            }
        )
        self._start_worker(req)
        self.ctx.db.touch_recent_voice(voice_id)

    def _start_worker(self, req: GenerationRequest) -> None:
        self.controller = GenerationController()
        self.worker = GenerationWorker(self.ctx.generation, req, self.controller, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self._last_request = req
        self.chunk_list.clear()
        self._chunk_records = []
        self.progress.setValue(0)
        self.progress_label.setText("Generating…")
        self.btn_generate.setEnabled(False)
        self.btn_save.setEnabled(False)
        self._saved_output_path = None
        self._set_generation_controls(True)
        self.worker.start()

    def _add_to_queue(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Empty", "Enter some text first.")
            return
        voice_id = self.voice_combo.currentData()
        if not voice_id:
            QMessageBox.warning(self, "No voice", "Install and select a voice first.")
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        last_dir = Path(
            self.ctx.settings.get("last_save_folder")
            or self.ctx.settings.get("default_output_folder")
            or self.ctx.paths["exports"]
        )
        last_dir.mkdir(parents=True, exist_ok=True)
        fmt = str(self.ctx.settings.get("audio_format", "wav")).lower().lstrip(".")
        out_path = last_dir / f"voiceforge_{stamp}.{fmt}"
        req = self._build_request(text, voice_id, out_path)
        if not req:
            return
        if self._queue_page:
            jid = self._queue_page.add_job_from_request(req)
            self.notify.emit(f"Added job #{jid} to queue")
        else:
            self.ctx.job_queue.add(req.title, __import__("app.services.queue_runner", fromlist=["payload_from_request"]).payload_from_request(req))
            self.notify.emit("Added to queue")

    def _export_srt(self) -> None:
        if self._last_result and getattr(self._last_result, "subtitle_path", None):
            src = Path(self._last_result.subtitle_path)
            if src.is_file():
                dest, _ = QFileDialog.getSaveFileName(self, "Export SRT", str(src), "SRT (*.srt)")
                if dest:
                    import shutil
                    shutil.copy2(src, dest)
                    self.notify.emit(f"Exported {dest}")
                return
        if self._last_result and self._last_result.output_path:
            srt = Path(self._last_result.output_path).with_suffix(".srt")
            if srt.is_file():
                dest, _ = QFileDialog.getSaveFileName(self, "Export SRT", str(srt), "SRT (*.srt)")
                if dest:
                    import shutil
                    shutil.copy2(srt, dest)
                    self.notify.emit(f"Exported {dest}")
                return
        QMessageBox.information(self, "Export SRT", "Generate audio first — subtitles are created automatically.")

    def _retry_selected_chunk(self) -> None:
        item = self.chunk_list.currentItem()
        if not item or not self._last_request:
            QMessageBox.information(self, "Retry", "Select a chunk after generation.")
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        req = GenerationRequest(
            text=self._last_request.text,
            voice_id=self._last_request.voice_id,
            output_path=self._last_request.output_path,
            title=self._last_request.title,
            settings=self._last_request.settings,
            chunk_max_chars=self._last_request.chunk_max_chars,
            normalize=self._last_request.normalize,
            audio_format=self._last_request.audio_format,
            bitrate=self._last_request.bitrate,
            channels=self._last_request.channels,
            speaker_map=self._last_request.speaker_map,
            use_multi_voice=self._last_request.use_multi_voice,
            cache_enabled=self._last_request.cache_enabled,
            device=self._last_request.device,
            existing_chunk_dir=self._last_result.chunks_dir if self._last_result else None,
            retry_chunk_indices=[int(idx)],
        )
        self._start_worker(req)

    def _play_chunk(self, item: QListWidgetItem) -> None:
        start_sec = item.data(Qt.ItemDataRole.UserRole + 1)
        if start_sec is not None and self.player:
            self.player.seek(float(start_sec))

    def _update_chunk_list(self, records: list[dict]) -> None:
        self._chunk_records = records
        self.chunk_list.clear()
        for rec in records:
            idx = rec.get("index", 0)
            label = f"#{idx + 1} · {rec.get('duration_sec', 0):.1f}s · {rec.get('text', '')[:40]}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            item.setData(Qt.ItemDataRole.UserRole + 1, rec.get("start_sec", 0))
            self.chunk_list.addItem(item)

    def _set_generation_controls(self, running: bool) -> None:
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(False)
        self.btn_stop.setEnabled(running)
        self.btn_queue.setEnabled(not running)
        self.btn_retry_chunk.setEnabled(not running and bool(self._chunk_records))

    def _pause_generation(self) -> None:
        self.controller.pause()
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(True)
        self.progress_label.setText("Paused · resume when you are ready")

    def _resume_generation(self) -> None:
        self.controller.resume()
        self.btn_pause.setEnabled(True)
        self.btn_resume.setEnabled(False)
        self.progress_label.setText("Generating…")

    def stop_generation(self) -> None:
        self.controller.cancel()

    def _on_progress(self, payload: dict) -> None:
        self.progress.setValue(int(payload.get("percent", 0)))
        self.progress_label.setText(payload.get("message", ""))
        if payload.get("chunk_records"):
            self._update_chunk_list(payload["chunk_records"])
        chunk = payload.get("chunk")
        total = payload.get("total")
        if chunk and total:
            self.ctx.db.save_crash_state(
                {
                    "text": self.editor.toPlainText(),
                    "voice_id": self.voice_combo.currentData(),
                    "output_path": str(self._last_request.output_path) if self._last_request else "",
                    "resume_from_chunk": int(chunk),
                }
            )

    def _on_finished(self, result) -> None:
        self._set_generation_controls(False)
        self.btn_generate.setEnabled(True)
        self._last_result = result
        if result.cancelled:
            self.btn_save.setEnabled(False)
            self.progress_label.setText("Cancelled")
            self.notify.emit("Generation cancelled")
            return
        self.ctx.db.clear_crash_state()
        self.progress.setValue(100)
        self.btn_save.setEnabled(True)
        loc = self.save_location.text().strip()
        if loc:
            self.progress_label.setText("Audio ready · Save Audio to keep your narration")
            self.progress_label.setToolTip(f"Save destination: {loc}")
        else:
            self.progress_label.setText("Ready to save — click Save Audio to choose a location")
        if result.chunk_records:
            self._update_chunk_list(
                [
                    {
                        "index": c.index,
                        "text": c.text[:80],
                        "start_sec": c.start_sec,
                        "end_sec": c.end_sec,
                        "duration_sec": c.duration_sec,
                    }
                    for c in result.chunk_records
                ]
            )
        self._set_generation_controls(False)
        # Prefer a WAV sidecar for reliable Windows playback when export isn't WAV
        play_path = Path(result.output_path)
        wav_sidecar = play_path.with_suffix(".wav")
        if play_path.suffix.lower() != ".wav" and wav_sidecar.is_file():
            play_path = wav_sidecar
        try:
            self.player.load_file(play_path, autoplay=True)
        except Exception as exc:
            self.notify.emit(f"Generated, but playback failed: {exc}")
        self.notify.emit("Generation completed — use Save Audio to keep the file")
        self.generationFinished.emit(result)

    def _on_failed(self, message: str) -> None:
        self._set_generation_controls(False)
        self.btn_generate.setEnabled(True)
        self.btn_save.setEnabled(False)
        self.progress_label.setText("Failed")
        QMessageBox.critical(
            self,
            "Generation failed",
            "Unable to generate this section.\n\n"
            "Possible causes:\n"
            "- insufficient memory\n"
            "- model unavailable\n"
            "- invalid model\n"
            "- unsupported text\n\n"
            f"Details: {message}",
        )
        self.notify.emit("Generation failed")

    def _autosave(self) -> None:
        path = self.ctx.paths["autosave"] / "studio.txt"
        try:
            path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except Exception:
            pass

    def _load_autosave(self) -> None:
        path = self.ctx.paths["autosave"] / "studio.txt"
        if path.is_file():
            try:
                self.editor.setPlainText(path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)
