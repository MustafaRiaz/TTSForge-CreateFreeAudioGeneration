"""Dialogue editor for multi-voice speaker → voice assignment."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from app.services.app_context import AppContext


class DialogueEditorDialog(QDialog):
    def __init__(self, speakers: list[str], default_voice: str, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Assign Voices to Speakers")
        self.resize(480, 320)
        self._combos: dict[str, QComboBox] = {}
        voices = [v for v in ctx.registry.all_voices() if v.installed]

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Map each speaker tag to an installed voice."))
        form = QFormLayout()
        for speaker in speakers:
            combo = QComboBox()
            for v in voices:
                combo.addItem(f"{v.name} ({v.provider})", v.id)
            i = combo.findData(default_voice)
            if i >= 0:
                combo.setCurrentIndex(i)
            self._combos[speaker] = combo
            form.addRow(speaker, combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mapping(self) -> dict[str, str]:
        return {speaker: combo.currentData() for speaker, combo in self._combos.items()}
