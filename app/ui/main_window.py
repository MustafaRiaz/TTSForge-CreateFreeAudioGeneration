"""Main application window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from app import __app_name__, __version__
from app.core.hardware import detect_hardware
from app.services.app_context import AppContext
from app.ui.dialogs.first_run import FirstRunDialog
from app.ui.pages.misc_pages import (
    AboutPage,
    AudioToolsPage,
    BatchPage,
    HistoryPage,
    ProjectsPage,
    SettingsPage,
)
from app.ui.pages.models import ModelsPage
from app.ui.pages.queue import QueuePage
from app.ui.pages.studio import StudioPage
from app.ui.pages.voices import VoicesPage
from app.services.queue_runner import QueueRunner
from app.audio.processing import find_ffmpeg, set_ffmpeg_path
from app.ui.themes.manager import apply_theme, resolve_theme
from app.ui.icons import decorate_buttons


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1440, 900)
        self.setMinimumSize(1200, 850)

        self.stack = QStackedWidget()
        self.studio = StudioPage(ctx)
        self.queue = QueuePage(ctx)
        self.queue_runner = QueueRunner(ctx, self)
        self.queue.set_runner(self.queue_runner)
        self.studio.set_queue_page(self.queue)
        self.projects = ProjectsPage(ctx)
        self.voices = VoicesPage(ctx)
        self.history = HistoryPage(ctx)
        self.audio_tools = AudioToolsPage(ctx)
        self.batch = BatchPage(ctx)
        self.settings = SettingsPage(ctx)
        self.models = ModelsPage(ctx)
        self.about = AboutPage()

        self.pages = [
            ("Studio", self.studio),
            ("Queue", self.queue),
            ("Projects", self.projects),
            ("Voices", self.voices),
            ("History", self.history),
            ("Audio Tools", self.audio_tools),
            ("Batch", self.batch),
            ("Settings", self.settings),
            ("Model Manager", self.models),
            ("About", self.about),
        ]
        for _, page in self.pages:
            self.stack.addWidget(page)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(14, 20, 14, 16)
        side_layout.setSpacing(5)
        brand = QLabel(__app_name__)
        brand.setObjectName("brandTitle")
        sub = QLabel("Offline TTS Studio")
        sub.setObjectName("brandSubtitle")
        side_layout.addWidget(brand)
        side_layout.addWidget(sub)

        self.nav_buttons: list[QPushButton] = []
        for i, (name, _) in enumerate(self.pages):
            if i in (0, 5, 7):
                section = QLabel({0: "WORKSPACE", 5: "PRODUCTION", 7: "APPLICATION"}[i])
                section.setObjectName("navSection")
                side_layout.addWidget(section)
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setProperty("class", "navButton")
            btn.setObjectName("navBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, idx=i: self._navigate(idx))
            side_layout.addWidget(btn)
            self.nav_buttons.append(btn)
            # Apply class for QSS
            btn.setProperty("class", "navButton")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        side_layout.addStretch()

        appearance_label = QLabel("APPEARANCE")
        appearance_label.setObjectName("navSection")
        side_layout.addWidget(appearance_label)
        self.theme_selector = QComboBox()
        self.theme_selector.setAccessibleName("Appearance theme")
        for title, value in (("Light", "light"), ("Dark", "dark"), ("System", "system")):
            self.theme_selector.addItem(title, value)
        self.theme_selector.setCurrentIndex(max(0, self.theme_selector.findData(ctx.settings.get("theme", "dark"))))
        self.theme_selector.currentIndexChanged.connect(self._change_theme)
        side_layout.addWidget(self.theme_selector)

        footer = QLabel("LOCAL WORKSPACE\nVoiceForge · " + __version__)
        footer.setObjectName("sidebarFooter")
        side_layout.addWidget(footer)

        root = QWidget()
        root.setObjectName("appRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        status = QStatusBar()
        self.setStatusBar(status)
        hw = detect_hardware()
        status.showMessage(" · ".join(hw.summary_lines()[:4]))

        # Wire notifications
        for page in (
            self.studio,
            self.queue,
            self.projects,
            self.voices,
            self.history,
            self.audio_tools,
            self.batch,
            self.settings,
            self.models,
        ):
            if hasattr(page, "notify"):
                page.notify.connect(self._toast)

        self.projects.set_text_provider(lambda: self.studio.editor.toPlainText())
        self.projects.openInStudio.connect(self._open_text_in_studio)
        self.voices.on_use_voice = lambda vid: (self.ctx.settings.set("default_voice", vid), self.studio.reload_voices(), self._navigate(0))
        self.models.modelsChanged.connect(self.studio.reload_voices)
        self.models.modelsChanged.connect(self.voices.reload)
        self.settings.themeChanged.connect(self._apply_theme)
        self.history.openPath.connect(self._open_audio)
        self.history.regenerateText.connect(self._open_text_in_studio)

        ffmpeg_cfg = self.ctx.settings.get("ffmpeg_path") or ""
        if ffmpeg_cfg:
            set_ffmpeg_path(ffmpeg_cfg)
        elif find_ffmpeg():
            self.ctx.settings.set("ffmpeg_path", find_ffmpeg())

        self.queue_runner.start()

        decorate_buttons(self)
        self._navigate(0)
        QTimer.singleShot(200, self._post_show)

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

    def _toast(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    def _open_text_in_studio(self, text: str) -> None:
        self.studio.set_text(text)
        self._navigate(0)

    def _open_audio(self, path: str) -> None:
        p = Path(path)
        if p.is_file():
            self.studio.player.load_file(p)
            self._navigate(0)
            self._toast(f"Loaded {p.name}")
        else:
            QMessageBox.warning(self, "Missing file", f"File not found:\n{path}")

    def _change_theme(self) -> None:
        preference = self.theme_selector.currentData()
        self.ctx.settings.set("theme", preference)
        self._apply_theme(preference)

    def _apply_theme(self, preference: str) -> None:
        for combo in (self.theme_selector, self.settings.theme):
            previous = combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(preference)))
            combo.blockSignals(previous)
        app = QApplication.instance()
        if app:
            apply_theme(app, preference)
            self._navigate(self.stack.currentIndex())

    def _post_show(self) -> None:
        if not self.ctx.settings.get("first_run_completed"):
            dlg = FirstRunDialog(self.ctx, self)
            dlg.exec()
            self._navigate(8)  # Model Manager
        # Crash recovery
        state = self.ctx.db.load_crash_state()
        if state and state.get("text"):
            reply = QMessageBox.question(
                self,
                "Unfinished project",
                "An unfinished generation was found.\n\nResume from last completed chunk?",
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.studio.set_pending_resume(state)
                self._navigate(0)
                QTimer.singleShot(300, self.studio.resume_generation)
            else:
                self.ctx.db.clear_crash_state()
