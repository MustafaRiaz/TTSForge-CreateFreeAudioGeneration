"""First-run welcome wizard."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QRadioButton,
    QButtonGroup,
    QTextEdit,
    QVBoxLayout,
)

from app.core.hardware import detect_hardware
from app.services.app_context import AppContext


class FirstRunDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Welcome to VoiceForge")
        self.resize(560, 520)

        hw = detect_hardware()
        self.engine_group = QButtonGroup(self)
        self.radio_kokoro = QRadioButton("Kokoro — Recommended (higher quality)")
        self.radio_piper = QRadioButton("Piper — Lightweight (faster / smaller)")
        if hw.recommendation == "piper":
            self.radio_piper.setChecked(True)
        else:
            self.radio_kokoro.setChecked(True)
        self.engine_group.addButton(self.radio_kokoro)
        self.engine_group.addButton(self.radio_piper)

        info = QTextEdit()
        info.setReadOnly(True)
        info.setHtml(
            "<h3>Welcome to VoiceForge</h3>"
            "<p>Generate natural speech <b>entirely offline</b> after models are installed. "
            "No paid API or subscription is required.</p>"
            "<p><b>Compute device</b></p><pre>"
            + "\n".join(hw.summary_lines())
            + "</pre>"
            + "<p>"
            + "<br/>".join(hw.notes)
            + "</p>"
            "<p>Choose your preferred TTS engine. You can install models next in Model Manager "
            "(downloads require confirmation).</p>"
        )

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(QLabel("Preferred engine"))
        layout.addWidget(self.radio_kokoro)
        layout.addWidget(self.radio_piper)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._finish)
        layout.addWidget(buttons)

    def _finish(self) -> None:
        engine = "kokoro" if self.radio_kokoro.isChecked() else "piper"
        self.ctx.settings.set("default_engine", engine)
        self.ctx.settings.set("first_run_completed", True)
        QMessageBox.information(
            self,
            "Next step",
            "Open Model Manager to download your first voice/model.\n\n"
            "You will see size, language, and quality before confirming.",
        )
        self.accept()
