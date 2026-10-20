"""Theme loading helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QGuiApplication, QPalette, QColor
from PySide6.QtWidgets import QApplication

from app.core.paths import resource_root


def style_path(theme: str) -> Path:
    name = "dark.qss" if theme == "dark" else "light.qss"
    return resource_root() / "assets" / "styles" / name


def resolve_theme(preference: str) -> str:
    if preference in ("dark", "light"):
        return preference
    # system
    hints = QGuiApplication.styleHints()
    try:
        scheme = hints.colorScheme()
        # Qt.ColorScheme.Dark == 2 in Qt6
        from PySide6.QtCore import Qt

        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        return "light"
    except Exception:
        return "dark"


def apply_theme(app: QApplication, preference: str) -> str:
    theme = resolve_theme(preference)
    app.setStyle("Fusion")
    palette = app.palette()
    dark = theme == "dark"
    for role, color in ((QPalette.ColorRole.Window, "#101318" if dark else "#f3f4f8"),
                        (QPalette.ColorRole.Base, "#12161c" if dark else "#f8f9fc"),
                        (QPalette.ColorRole.Text, "#edf0f5" if dark else "#202636"),
                        (QPalette.ColorRole.PlaceholderText, "#98a3b4" if dark else "#697386")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    path = style_path(theme)
    if path.is_file():
        app.setStyleSheet(path.read_text(encoding="utf-8"))
    return theme
