"""Waveform widget with real peak data, zoom, cursor, and chunk markers."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPalette
from PySide6.QtWidgets import QWidget

import numpy as np


class WaveformWidget(QWidget):
    positionClicked = Signal(float)  # 0..1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(60)
        self._peaks = np.zeros(0, dtype=np.float32)
        self._position = 0.0
        self._zoom = 1.0
        self._scroll = 0.0
        self._markers: list[float] = []  # 0..1
        self._selection: tuple[float, float] | None = None

    def set_peaks(self, peaks: np.ndarray) -> None:
        self._peaks = np.asarray(peaks, dtype=np.float32)
        self.update()

    def set_position(self, frac: float) -> None:
        self._position = max(0.0, min(1.0, frac))
        self.update()

    def set_markers(self, markers: list[float]) -> None:
        self._markers = markers
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(1.0, min(20.0, zoom))
        self.update()

    def set_selection(self, start: float | None, end: float | None) -> None:
        if start is None or end is None:
            self._selection = None
        else:
            self._selection = (min(start, end), max(start, end))
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta > 0:
            self.set_zoom(self._zoom * 1.1)
        else:
            self.set_zoom(self._zoom / 1.1)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.width() > 0:
            visible = 1.0 / self._zoom
            start = self._scroll
            frac = start + (event.position().x() / self.width()) * visible
            self.positionClicked.emit(max(0.0, min(1.0, frac)))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Base))
        w, h = self.width(), self.height()
        if w <= 1 or h <= 1:
            return
        mid = h / 2
        if len(self._peaks) == 0:
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Your audio will appear here\nGenerate a script to start listening")
            return

        visible = 1.0 / self._zoom
        start_frac = min(self._scroll, 1.0 - visible)
        start_i = int(start_frac * len(self._peaks))
        end_i = max(start_i + 1, int((start_frac + visible) * len(self._peaks)))
        view = self._peaks[start_i:end_i]
        if len(view) == 0:
            return

        if self._selection:
            x1 = int((self._selection[0] - start_frac) / visible * w)
            x2 = int((self._selection[1] - start_frac) / visible * w)
            painter.fillRect(x1, 0, max(1, x2 - x1), h, QColor(61, 126, 166, 80))

        painter.setPen(QPen(QColor("#8974ee"), 1))
        for x in range(w):
            idx = int(x / w * len(view))
            peak = float(view[idx]) if idx < len(view) else 0.0
            amp = peak * (h * 0.45)
            painter.drawLine(x, int(mid - amp), x, int(mid + amp))

        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.PlaceholderText), 1, Qt.PenStyle.DashLine))
        for m in self._markers:
            x = int((m - start_frac) / visible * w)
            if 0 <= x <= w:
                painter.drawLine(x, 0, x, h)

        px = int((self._position - start_frac) / visible * w)
        painter.setPen(QPen(QColor("#f0c56e"), 2))
        painter.drawLine(px, 0, px, h)
