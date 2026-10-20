"""Projects, History, Audio Tools, Settings, About pages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QSplitter,
)

from app.audio.processing import (
    convert_file,
    export_audio,
    fade_in,
    fade_out,
    normalize_peak,
    read_wav,
    trim,
    trim_silence,
    write_wav,
    concat_audio,
    find_ffmpeg,
    set_ffmpeg_path,
    POST_PROCESS_PRESETS,
)
from app.core.hardware import detect_hardware
from app.projects.manager import ProjectData
from app.services.app_context import AppContext
from app.services.generation_service import GenerationController, GenerationRequest
from app.tts.base import ComputeDevice, VoiceSettings
from app.workers.tasks import BatchWorker
from app import __version__, __app_name__


class ProjectsPage(QWidget):
    notify = Signal(str)
    openInStudio = Signal(str)

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.list = QListWidget()
        self.btn_new = QPushButton("New Project")
        self.btn_open = QPushButton("Open in Studio")
        self.btn_open.setObjectName("primaryButton")
        self.btn_save = QPushButton("Save Current Text as Project")
        self.btn_export = QPushButton("Export Archive")
        self.btn_import = QPushButton("Import Archive")
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("dangerButton")
        self.btn_refresh = QPushButton("Refresh")
        self.btn_chapters = QPushButton("Edit Chapters")
        self._current_text_provider = lambda: ""
        self._chapters_provider = None
        self._current_chapters: list[dict] = []

        row = QHBoxLayout()
        for b in (self.btn_new, self.btn_open, self.btn_save, self.btn_chapters, self.btn_export, self.btn_import, self.btn_delete, self.btn_refresh):
            row.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Projects", objectName="heading"))
        layout.addWidget(self.list, 1)
        layout.addLayout(row)

        self.btn_refresh.clicked.connect(self.reload)
        self.btn_new.clicked.connect(self._new)
        self.btn_open.clicked.connect(self._open)
        self.btn_save.clicked.connect(self._save)
        self.btn_export.clicked.connect(self._export)
        self.btn_import.clicked.connect(self._import)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_chapters.clicked.connect(self._edit_chapters)
        self.reload()

    def set_text_provider(self, fn) -> None:
        self._current_text_provider = fn

    def set_chapters_provider(self, fn) -> None:
        self._chapters_provider = fn

    def _edit_chapters(self) -> None:
        name = self._selected()
        if not name:
            QMessageBox.information(self, "Chapters", "Select a project first.")
            return
        data = self.ctx.projects.load(name)
        chapters = data.get_chapters()
        dlg = ChapterEditorDialog(chapters, self)
        if dlg.exec():
            updated = dlg.chapters()
            data.chapters = [
                {"title": c.title, "text": c.text, "voice_id": c.voice_id, "order": c.order}
                for c in updated
            ]
            if updated:
                data.text = "\n\n".join(c.text for c in updated if c.text.strip())
            self.ctx.projects.save(data)
            self.notify.emit("Chapters saved")

    def reload(self) -> None:
        self.list.clear()
        for name in self.ctx.projects.list_projects():
            self.list.addItem(name)

    def _new(self) -> None:
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if not ok or not name.strip():
            return
        try:
            self.ctx.projects.create(name.strip(), ProjectData(name=name.strip(), text=""))
            self.reload()
            self.notify.emit("Project created")
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _selected(self) -> str | None:
        item = self.list.currentItem()
        return item.text() if item else None

    def _open(self) -> None:
        name = self._selected()
        if not name:
            return
        data = self.ctx.projects.load(name)
        chapters = data.get_chapters()
        if len(chapters) > 1 or (chapters and chapters[0].title != "Main"):
            text = "\n\n".join(f"## {c.title}\n\n{c.text}" for c in chapters if c.text.strip())
        else:
            text = data.text
        self.openInStudio.emit(text)
        self.notify.emit(f"Opened {name}")

    def _save(self) -> None:
        name = self._selected()
        if not name:
            name, ok = QInputDialog.getText(self, "Save Project", "Project name:")
            if not ok or not name.strip():
                return
            name = name.strip()
        text = self._current_text_provider()
        voice = self.ctx.settings.get("default_voice", "")
        data = ProjectData(name=name, text=text, voice_id=voice, settings=self.ctx.settings.all())
        if hasattr(self, "_chapters_provider") and callable(getattr(self, "_chapters_provider", None)):
            ch = self._chapters_provider()
            if ch:
                data.chapters = ch
        try:
            if name not in self.ctx.projects.list_projects():
                self.ctx.projects.create(name, data)
            else:
                self.ctx.projects.save(data)
            self.reload()
            self.notify.emit("Project saved")
        except FileExistsError:
            self.ctx.projects.save(data)
            self.reload()
            self.notify.emit("Project saved")
        except Exception as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _export(self) -> None:
        name = self._selected()
        if not name:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export project", f"{name}.zip", "ZIP (*.zip)")
        if path:
            self.ctx.projects.export_archive(name, Path(path))
            self.notify.emit("Project exported")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import project", "", "ZIP (*.zip);;EPUB (*.epub)")
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() == ".epub":
            try:
                from app.text.importers import import_epub_chapters, import_epub

                chapters = import_epub_chapters(p)
                name = p.stem
                if name in self.ctx.projects.list_projects():
                    name = f"{name}_import"
                text = import_epub(p)
                data = ProjectData(
                    name=name,
                    text=text,
                    chapters=chapters,
                    voice_id=self.ctx.settings.get("default_voice", ""),
                )
                self.ctx.projects.create(name, data)
                self.reload()
                self.notify.emit(f"Imported EPUB as project {name}")
            except Exception as exc:
                QMessageBox.warning(self, "Import failed", str(exc))
            return
        try:
            name = self.ctx.projects.import_archive(p)
            self.reload()
            self.notify.emit(f"Imported {name}")
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    def _delete(self) -> None:
        name = self._selected()
        if not name:
            return
        if QMessageBox.question(self, "Delete", f"Delete project {name}?") != QMessageBox.StandardButton.Yes:
            return
        self.ctx.projects.delete(name)
        self.reload()
        self.notify.emit(f"Deleted {name}")


class ChapterEditorDialog(QDialog):
    """Simple chapter list editor."""

    def __init__(self, chapters, parent=None) -> None:
        from app.projects.manager import Chapter

        super().__init__(parent)
        self.setWindowTitle("Chapter Editor")
        self.resize(800, 500)
        self._Chapter = Chapter
        self._chapters = list(chapters)
        self._list = QListWidget()
        self._title = QLineEdit()
        self._text = QPlainTextEdit()
        for c in self._chapters:
            self._list.addItem(c.title)
        if self._chapters:
            self._list.setCurrentRow(0)
            self._load_row(0)

        btn_add = QPushButton("Add Chapter")
        btn_remove = QPushButton("Remove")
        btn_add.clicked.connect(self._add)
        btn_remove.clicked.connect(self._remove)
        self._list.currentRowChanged.connect(self._load_row)

        left = QVBoxLayout()
        left.addWidget(self._list)
        left.addWidget(btn_add)
        left.addWidget(btn_remove)
        left_w = QWidget()
        left_w.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(QLabel("Title"))
        right.addWidget(self._title)
        right.addWidget(QLabel("Text"))
        right.addWidget(self._text, 1)
        right_w = QWidget()
        right_w.setLayout(right)

        splitter = QSplitter()
        splitter.addWidget(left_w)
        splitter.addWidget(right_w)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save_current)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(buttons)

    def _load_row(self, row: int) -> None:
        if row < 0 or row >= len(self._chapters):
            return
        c = self._chapters[row]
        self._title.setText(c.title)
        self._text.setPlainText(c.text)

    def _save_current(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._chapters):
            return
        c = self._chapters[row]
        c.title = self._title.text().strip() or c.title
        c.text = self._text.toPlainText()
        self._list.item(row).setText(c.title)

    def _add(self) -> None:
        self._save_current()
        c = self._Chapter(title=f"Chapter {len(self._chapters) + 1}", text="", order=len(self._chapters))
        self._chapters.append(c)
        self._list.addItem(c.title)
        self._list.setCurrentRow(len(self._chapters) - 1)

    def _remove(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self._chapters.pop(row)
        self._list.takeItem(row)

    def exec(self) -> bool:
        return super().exec()

    def chapters(self):
        self._save_current()
        return self._chapters


class HistoryPage(QWidget):
    notify = Signal(str)
    openPath = Signal(str)
    regenerateText = Signal(str)

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search history…")
        self.list = QListWidget()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_replay = QPushButton("Replay")
        self.btn_open = QPushButton("Open Output")
        self.btn_regen = QPushButton("Regenerate Text")
        self.btn_delete = QPushButton("Delete")
        row = QHBoxLayout()
        for b in (self.btn_refresh, self.btn_replay, self.btn_open, self.btn_regen, self.btn_delete):
            row.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("History", objectName="heading"))
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addLayout(row)
        self.search.textChanged.connect(self.reload)
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_open.clicked.connect(self._open)
        self.btn_replay.clicked.connect(self._open)
        self.btn_regen.clicked.connect(self._regen)
        self._rows: list[dict] = []
        self.reload()

    def reload(self) -> None:
        self._rows = self.ctx.db.list_history(self.search.text())
        self.list.clear()
        for r in self._rows:
            self.list.addItem(
                f"{r.get('created_at','')} | {r.get('title','')} | {r.get('voice_id','')} | "
                f"{r.get('duration_sec',0):.1f}s | {r.get('status','')}"
            )

    def _selected(self) -> dict | None:
        i = self.list.currentRow()
        if i < 0 or i >= len(self._rows):
            return None
        return self._rows[i]

    def _delete(self) -> None:
        row = self._selected()
        if row:
            self.ctx.db.delete_history(int(row["id"]))
            self.reload()

    def _open(self) -> None:
        row = self._selected()
        if row and row.get("output_path"):
            self.openPath.emit(row["output_path"])

    def _regen(self) -> None:
        row = self._selected()
        if row and row.get("text_preview"):
            self.regenerateText.emit(row["text_preview"])


class AudioToolsPage(QWidget):
    notify = Signal(str)

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.input_path = QLineEdit()
        self.btn_browse = QPushButton("Browse…")
        self.btn_normalize = QPushButton("Normalize")
        self.btn_trim_silence = QPushButton("Remove Silence")
        self.btn_fade_in = QPushButton("Fade In")
        self.btn_fade_out = QPushButton("Fade Out")
        self.btn_convert = QPushButton("Convert Format…")
        self.btn_merge = QPushButton("Merge Files…")
        self.btn_volume = QPushButton("Adjust Volume…")
        self.info = QLabel(f"FFmpeg: {'found' if find_ffmpeg() else 'not found (WAV/FLAC limited)'}")
        self.info.setObjectName("muted")

        row = QHBoxLayout()
        row.addWidget(self.input_path, 1)
        row.addWidget(self.btn_browse)
        grid = QHBoxLayout()
        for b in (
            self.btn_normalize,
            self.btn_trim_silence,
            self.btn_fade_in,
            self.btn_fade_out,
            self.btn_convert,
            self.btn_merge,
            self.btn_volume,
        ):
            grid.addWidget(b)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Audio Tools", objectName="heading"))
        layout.addLayout(row)
        layout.addLayout(grid)
        layout.addWidget(self.info)
        layout.addStretch()

        self.btn_browse.clicked.connect(self._browse)
        self.btn_normalize.clicked.connect(lambda: self._process("normalize"))
        self.btn_trim_silence.clicked.connect(lambda: self._process("silence"))
        self.btn_fade_in.clicked.connect(lambda: self._process("fade_in"))
        self.btn_fade_out.clicked.connect(lambda: self._process("fade_out"))
        self.btn_convert.clicked.connect(self._convert)
        self.btn_merge.clicked.connect(self._merge)
        self.btn_volume.clicked.connect(self._volume)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Audio file", "", "Audio (*.wav *.mp3 *.flac *.ogg)")
        if path:
            self.input_path.setText(path)

    def _load(self):
        path = Path(self.input_path.text())
        if not path.is_file():
            raise FileNotFoundError("Select a valid audio file (WAV preferred for editing).")
        # Convert non-wav via ffmpeg to temp if needed
        if path.suffix.lower() != ".wav":
            tmp = self.ctx.paths["temp"] / (path.stem + "_edit.wav")
            convert_file(path, tmp)
            path = tmp
        return read_wav(path)

    def _save(self, samples, sr, suffix: str) -> Path:
        src = Path(self.input_path.text())
        out = src.with_name(src.stem + suffix + ".wav")
        write_wav(out, samples, sr)
        self.input_path.setText(str(out))
        self.notify.emit(f"Saved {out.name}")
        return out

    def _process(self, kind: str) -> None:
        try:
            samples, sr = self._load()
            if kind == "normalize":
                samples = normalize_peak(samples)
            elif kind == "silence":
                samples = trim_silence(samples, sr)
            elif kind == "fade_in":
                samples = fade_in(samples, 500, sr)
            elif kind == "fade_out":
                samples = fade_out(samples, 500, sr)
            self._save(samples, sr, f"_{kind}")
        except Exception as exc:
            QMessageBox.warning(self, "Audio tools", str(exc))

    def _convert(self) -> None:
        path = Path(self.input_path.text())
        if not path.is_file():
            return
        out, _ = QFileDialog.getSaveFileName(self, "Convert to", str(path.with_suffix(".mp3")), "Audio (*.wav *.mp3 *.flac *.ogg)")
        if not out:
            return
        try:
            samples, sr = self._load()
            export_audio(samples, sr, out, format=Path(out).suffix.lstrip("."))
            self.notify.emit("Conversion complete")
        except Exception as exc:
            QMessageBox.warning(self, "Convert failed", str(exc))

    def _merge(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Merge WAV files", "", "WAV (*.wav)")
        if len(files) < 2:
            return
        parts = []
        sr = None
        for f in files:
            audio, rate = read_wav(f)
            sr = rate if sr is None else sr
            parts.append(audio)
        out, _ = QFileDialog.getSaveFileName(self, "Save merged", "merged.wav", "WAV (*.wav)")
        if out and sr:
            write_wav(out, concat_audio(parts), sr)
            self.notify.emit("Merged")

    def _volume(self) -> None:
        gain, ok = QInputDialog.getDouble(self, "Volume", "Gain multiplier:", 1.0, 0.1, 3.0, 2)
        if not ok:
            return
        try:
            samples, sr = self._load()
            samples = samples * gain
            self._save(samples, sr, "_vol")
        except Exception as exc:
            QMessageBox.warning(self, "Volume", str(exc))


class SettingsPage(QWidget):
    notify = Signal(str)
    themeChanged = Signal(str)

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._tts_tab(), "TTS")
        tabs.addTab(self._audio_tab(), "Audio")
        tabs.addTab(self._storage_tab(), "Storage")
        tabs.addTab(self._perf_tab(), "Performance")
        tabs.addTab(self._pronunciation_tab(), "Pronunciation")
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("primaryButton")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Settings", objectName="heading"))
        layout.addWidget(tabs, 1)
        layout.addWidget(self.btn_save)
        self.btn_save.clicked.connect(self.save)
        self._load()

    def _general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        self.theme.addItem("System", "system")
        self.offline = QCheckBox("Offline Mode (block network)")
        self.startup = QCheckBox("Open Studio on startup")
        self.out_folder = QLineEdit()
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda: self._browse_into(self.out_folder))
        row = QHBoxLayout()
        row.addWidget(self.out_folder)
        row.addWidget(browse)
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow("Theme", self.theme)
        form.addRow(self.offline)
        form.addRow(self.startup)
        form.addRow("Default output folder", wrap)
        return w

    def _tts_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.engine = QComboBox()
        self.engine.addItem("Kokoro", "kokoro")
        self.engine.addItem("Piper", "piper")
        self.device = QComboBox()
        self.device.addItem("Auto", "auto")
        self.device.addItem("CPU", "cpu")
        self.device.addItem("GPU", "gpu")
        self.chunk = QSpinBox()
        self.chunk.setRange(100, 2000)
        self.sent_pause = QSpinBox()
        self.sent_pause.setRange(0, 2000)
        self.para_pause = QSpinBox()
        self.para_pause.setRange(0, 5000)
        form.addRow("Default engine", self.engine)
        form.addRow("Compute device", self.device)
        form.addRow("Chunk size (chars)", self.chunk)
        form.addRow("Sentence pause (ms)", self.sent_pause)
        form.addRow("Paragraph pause (ms)", self.para_pause)
        note = QLabel("Pitch is disabled for Kokoro/Piper — engines do not expose it.")
        note.setObjectName("muted")
        form.addRow(note)
        return w

    def _audio_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.fmt = QComboBox()
        for f in ("wav", "mp3", "flac", "ogg"):
            self.fmt.addItem(f.upper(), f)
        self.bitrate = QLineEdit("192k")
        self.sr = QSpinBox()
        self.sr.setRange(16000, 48000)
        self.channels = QSpinBox()
        self.channels.setRange(1, 2)
        self.normalize = QCheckBox("Normalize output")
        self.post_process = QComboBox()
        for key, meta in POST_PROCESS_PRESETS.items():
            self.post_process.addItem(meta.get("label", key), key)
        self.ffmpeg_path = QLineEdit()
        self.ffmpeg_path.setReadOnly(True)
        self.btn_ffmpeg_browse = QPushButton("Browse FFmpeg…")
        self.btn_ffmpeg_detect = QPushButton("Detect")
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg_path, 1)
        ffmpeg_row.addWidget(self.btn_ffmpeg_detect)
        ffmpeg_row.addWidget(self.btn_ffmpeg_browse)
        ffmpeg_wrap = QWidget()
        ffmpeg_wrap.setLayout(ffmpeg_row)
        self.btn_ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        self.btn_ffmpeg_detect.clicked.connect(self._detect_ffmpeg)
        form.addRow("Format", self.fmt)
        form.addRow("Bitrate", self.bitrate)
        form.addRow("Sample rate", self.sr)
        form.addRow("Channels", self.channels)
        form.addRow(self.normalize)
        form.addRow("Post-processing", self.post_process)
        form.addRow("FFmpeg path", ffmpeg_wrap)
        ff_note = QLabel("MP3/OGG export requires FFmpeg. Place ffmpeg.exe in packaging/ffmpeg/ or set path here.")
        ff_note.setObjectName("muted")
        ff_note.setWordWrap(True)
        form.addRow(ff_note)
        return w

    def _storage_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.model_loc = QLineEdit()
        self.cache_loc = QLineEdit()
        self.cache_enabled = QCheckBox("Enable generation cache")
        clear = QPushButton("Clear Audio Cache")
        clear.clicked.connect(self._clear_cache)
        form.addRow("Model location", self.model_loc)
        form.addRow("Cache location", self.cache_loc)
        form.addRow(self.cache_enabled)
        form.addRow(clear)
        return w

    def _perf_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.workers = QSpinBox()
        self.workers.setRange(1, 4)
        form.addRow("Worker count", self.workers)
        hw = detect_hardware()
        form.addRow(QLabel("\n".join(hw.summary_lines())))
        return w

    def _pronunciation_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(
            QLabel(
                "Custom pronunciation rules (one per line: pattern => replacement).\n"
                "Prefix with re: for regex. Example: NSFW => N S F W"
            )
        )
        self.pronunciation_edit = QTextEdit()
        btn_import = QPushButton("Import CSV/JSON…")
        btn_export = QPushButton("Export…")
        btn_test = QPushButton("Test pronunciation")
        btn_import.clicked.connect(self._import_glossary)
        btn_export.clicked.connect(self._export_glossary)
        btn_test.clicked.connect(self._test_pronunciation)
        row = QHBoxLayout()
        row.addWidget(btn_import)
        row.addWidget(btn_export)
        row.addWidget(btn_test)
        row.addStretch()
        layout.addWidget(self.pronunciation_edit)
        layout.addLayout(row)
        return w

    def _browse_into(self, line: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder")
        if path:
            line.setText(path)

    def _load(self) -> None:
        s = self.ctx.settings
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.get("theme", "dark"))))
        self.offline.setChecked(bool(s.get("offline_mode")))
        self.startup.setChecked(bool(s.get("startup_open_studio", True)))
        self.out_folder.setText(str(s.get("default_output_folder") or ""))
        self.engine.setCurrentIndex(max(0, self.engine.findData(s.get("default_engine", "kokoro"))))
        self.device.setCurrentIndex(max(0, self.device.findData(s.get("compute_device", "auto"))))
        self.chunk.setValue(int(s.get("chunk_max_chars", 400)))
        self.sent_pause.setValue(int(s.get("sentence_pause_ms", 180)))
        self.para_pause.setValue(int(s.get("paragraph_pause_ms", 400)))
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(s.get("audio_format", "wav"))))
        self.bitrate.setText(str(s.get("audio_bitrate", "192k")))
        self.sr.setValue(int(s.get("audio_sample_rate", 24000)))
        self.channels.setValue(int(s.get("audio_channels", 1)))
        self.normalize.setChecked(bool(s.get("normalize_audio", True)))
        self.post_process.setCurrentIndex(max(0, self.post_process.findData(s.get("post_process_preset", "none"))))
        detected = s.get("ffmpeg_path") or find_ffmpeg() or ""
        self.ffmpeg_path.setText(str(detected))
        self.model_loc.setText(str(s.get("model_location") or self.ctx.models_dir))
        self.cache_loc.setText(str(s.get("cache_location") or self.ctx.paths["audio_cache"]))
        self.cache_enabled.setChecked(bool(s.get("cache_enabled", True)))
        self.workers.setValue(int(s.get("worker_threads", 1)))
        rules = s.get("pronunciation_rules") or []
        lines = []
        for r in rules:
            if not isinstance(r, dict):
                continue
            prefix = "re:" if r.get("is_regex") else ""
            lines.append(f"{prefix}{r.get('pattern','')} => {r.get('replacement','')}")
        self.pronunciation_edit.setPlainText("\n".join(lines))

    def save(self) -> None:
        s = self.ctx.settings
        theme = self.theme.currentData()
        s.set("theme", theme)
        s.set("offline_mode", self.offline.isChecked())
        s.set("startup_open_studio", self.startup.isChecked())
        s.set("default_output_folder", self.out_folder.text().strip())
        s.set("default_engine", self.engine.currentData())
        s.set("compute_device", self.device.currentData())
        s.set("chunk_max_chars", self.chunk.value())
        s.set("sentence_pause_ms", self.sent_pause.value())
        s.set("paragraph_pause_ms", self.para_pause.value())
        s.set("audio_format", self.fmt.currentData())
        s.set("audio_bitrate", self.bitrate.text().strip() or "192k")
        s.set("audio_sample_rate", self.sr.value())
        s.set("audio_channels", self.channels.value())
        s.set("normalize_audio", self.normalize.isChecked())
        s.set("post_process_preset", self.post_process.currentData())
        ffmpeg = self.ffmpeg_path.text().strip()
        s.set("ffmpeg_path", ffmpeg)
        set_ffmpeg_path(ffmpeg or None)
        s.set("model_location", self.model_loc.text().strip())
        s.set("cache_location", self.cache_loc.text().strip())
        s.set("cache_enabled", self.cache_enabled.isChecked())
        s.set("worker_threads", self.workers.value())
        parsed_rules = []
        for line in self.pronunciation_edit.toPlainText().splitlines():
            line = line.strip()
            if not line or "=>" not in line:
                continue
            left, right = line.split("=>", 1)
            left, right = left.strip(), right.strip()
            is_regex = left.startswith("re:")
            if is_regex:
                left = left[3:]
            parsed_rules.append(
                {
                    "pattern": left,
                    "replacement": right,
                    "is_regex": is_regex,
                    "case_sensitive": False,
                }
            )
        s.set("pronunciation_rules", parsed_rules)
        # Refresh processor rules live
        from app.text.processor import PronunciationRule, TextProcessor

        self.ctx.processor = TextProcessor(
            rules=[
                PronunciationRule(
                    pattern=r["pattern"],
                    replacement=r["replacement"],
                    is_regex=r.get("is_regex", False),
                )
                for r in parsed_rules
            ]
        )
        self.ctx.generation.processor = self.ctx.processor
        self.ctx.refresh_offline_flag()
        self.themeChanged.emit(theme)
        self.notify.emit("Settings saved")

    def _browse_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select ffmpeg", "", "ffmpeg (ffmpeg.exe);;All (*.*)")
        if path:
            self.ffmpeg_path.setText(path)

    def _detect_ffmpeg(self) -> None:
        found = find_ffmpeg()
        self.ffmpeg_path.setText(found or "")
        if found:
            self.notify.emit(f"FFmpeg found: {found}")
        else:
            QMessageBox.information(self, "FFmpeg", "FFmpeg not found. Install it or place ffmpeg.exe in packaging/ffmpeg/")

    def _import_glossary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import glossary", "", "CSV (*.csv);;JSON (*.json)")
        if not path:
            return
        import csv
        import json

        p = Path(path)
        lines: list[str] = []
        try:
            if p.suffix.lower() == ".json":
                data = json.loads(p.read_text(encoding="utf-8"))
                for item in data:
                    if isinstance(item, dict):
                        prefix = "re:" if item.get("is_regex") else ""
                        lines.append(f"{prefix}{item.get('pattern','')} => {item.get('replacement','')}")
            else:
                with p.open(encoding="utf-8", newline="") as f:
                    for row in csv.DictReader(f):
                        pat = row.get("pattern") or row.get("from") or ""
                        rep = row.get("replacement") or row.get("to") or ""
                        if pat:
                            is_re = str(row.get("is_regex", "")).lower() in ("1", "true", "yes")
                            prefix = "re:" if is_re else ""
                            lines.append(f"{prefix}{pat} => {rep}")
            self.pronunciation_edit.setPlainText("\n".join(lines))
            self.notify.emit("Glossary imported")
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    def _export_glossary(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export glossary", "glossary.json", "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        import csv
        import json

        rules = []
        for line in self.pronunciation_edit.toPlainText().splitlines():
            line = line.strip()
            if not line or "=>" not in line:
                continue
            left, right = line.split("=>", 1)
            left, right = left.strip(), right.strip()
            is_regex = left.startswith("re:")
            if is_regex:
                left = left[3:]
            rules.append({"pattern": left, "replacement": right, "is_regex": is_regex})
        p = Path(path)
        try:
            if p.suffix.lower() == ".csv":
                with p.open("w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=["pattern", "replacement", "is_regex"])
                    w.writeheader()
                    for r in rules:
                        w.writerow(r)
            else:
                p.write_text(json.dumps(rules, indent=2), encoding="utf-8")
            self.notify.emit("Glossary exported")
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def _test_pronunciation(self) -> None:
        sample, ok = QInputDialog.getText(self, "Test", "Enter text to test:")
        if not ok or not sample:
            return
        result = self.ctx.processor.prepare_for_synthesis(sample)
        QMessageBox.information(self, "Result", result or "(empty)")

    def _clear_cache(self) -> None:
        n = self.ctx.cache.clear()
        QMessageBox.information(self, "Cache", f"Removed {n} cached files.")


class AboutPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{__app_name__}", objectName="heading"))
        body = QTextEdit()
        body.setReadOnly(True)
        body.setHtml(
            f"""
            <h3>Version {__version__}</h3>
            <p><b>VoiceForge</b> is a professional offline text-to-speech desktop application.</p>
            <p>Core speech generation runs locally. No paid API, subscription, or API key is required.</p>
            <ul>
              <li><b>Internet required:</b> model downloads, optional metadata/update checks</li>
              <li><b>Internet NOT required:</b> text processing, TTS, audio tools, playback, projects</li>
            </ul>
            <p>Recommended engine: <b>Kokoro</b> (Apache-2.0 / MIT). Optional: <b>Piper</b> (GPL engine package).</p>
            <p>See <code>THIRD_PARTY_LICENSES.md</code> for full licensing details.</p>
            """
        )
        layout.addWidget(body)


class BatchPage(QWidget):
    """Batch processing embedded under Audio Tools conceptually; exposed as part of tools flow via Projects or here."""

    notify = Signal(str)

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.worker: BatchWorker | None = None
        self.controller = GenerationController()
        self.input_dir = QLineEdit()
        self.output_dir = QLineEdit()
        self.queue_list = QListWidget()
        self.btn_run = QPushButton("Batch Generate")
        self.btn_run.setObjectName("primaryButton")
        self.btn_cancel = QPushButton("Cancel")
        self.status = QLabel("Select an input folder of .txt/.md files.")
        self.status.setObjectName("muted")

        form = QFormLayout()
        b1 = QPushButton("Browse")
        b1.clicked.connect(lambda: self._browse(self.input_dir))
        b2 = QPushButton("Browse")
        b2.clicked.connect(lambda: self._browse(self.output_dir))
        r1 = QHBoxLayout(); r1.addWidget(self.input_dir); r1.addWidget(b1)
        r2 = QHBoxLayout(); r2.addWidget(self.output_dir); r2.addWidget(b2)
        w1, w2 = QWidget(), QWidget()
        w1.setLayout(r1); w2.setLayout(r2)
        form.addRow("Input folder", w1)
        form.addRow("Output folder", w2)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Batch Processing", objectName="heading"))
        layout.addLayout(form)
        layout.addWidget(self.queue_list, 1)
        row = QHBoxLayout()
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_cancel)
        layout.addLayout(row)
        layout.addWidget(self.status)
        self.btn_run.clicked.connect(self._run)
        self.btn_cancel.clicked.connect(self.controller.cancel)

    def _browse(self, line: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder")
        if path:
            line.setText(path)

    def _run(self) -> None:
        inp = Path(self.input_dir.text())
        out = Path(self.output_dir.text() or self.ctx.paths["exports"] / "batch")
        out.mkdir(parents=True, exist_ok=True)
        voice = self.ctx.settings.get("default_voice")
        if not voice:
            QMessageBox.warning(self, "Batch", "Set a default voice first.")
            return
        files = list(inp.glob("*.txt")) + list(inp.glob("*.md"))
        if not files:
            QMessageBox.information(self, "Batch", "No .txt/.md files found.")
            return
        self.queue_list.clear()
        jobs = []
        for f in files:
            self.queue_list.addItem(f"{f.name} — Waiting")
            text = f.read_text(encoding="utf-8", errors="replace")
            jobs.append(
                GenerationRequest(
                    text=text,
                    voice_id=voice,
                    output_path=out / f"{f.stem}.wav",
                    title=f.name,
                    settings=VoiceSettings(speed=float(self.ctx.settings.get("speed", 1.0))),
                    device=ComputeDevice(self.ctx.settings.get("compute_device", "auto")),
                )
            )
        self.controller = GenerationController()
        self.worker = BatchWorker(self.ctx.generation, jobs, self.controller, self)
        self.worker.progress.connect(lambda p: self.status.setText(p.get("message", "")))
        self.worker.finished_ok.connect(lambda _: self.notify.emit("Batch complete"))
        self.worker.failed.connect(lambda e: QMessageBox.critical(self, "Batch failed", e))
        self.worker.start()
