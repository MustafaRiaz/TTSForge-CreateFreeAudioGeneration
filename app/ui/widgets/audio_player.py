"""Audio player backed by QMediaPlayer with reliable load + autoplay."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, QTimer, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.audio.processing import compute_waveform_peaks, convert_file, read_wav
from app.ui.widgets.waveform import WaveformWidget

logger = logging.getLogger(__name__)


def _fmt_ms(ms: int) -> str:
    s = max(0, ms) // 1000
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}"


class AudioPlayerWidget(QWidget):
    chunkJumpRequested = Signal(int)
    statusMessage = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self._apply_output_device()
        self.audio_out.setMuted(False)
        self.audio_out.setVolume(0.9)
        self._duration_ms = 0
        self._chunk_markers: list[float] = []
        self._current_path: Path | None = None
        self._preview_path: Path | None = None
        self._autoplay = False
        self._load_retries = 0

        self.waveform = WaveformWidget()
        self.btn_play = QPushButton("Play")
        self.btn_pause = QPushButton("Pause")
        self.btn_stop = QPushButton("Stop")
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(90)
        self.speed = QSlider(Qt.Orientation.Horizontal)
        self.speed.setRange(50, 200)
        self.speed.setValue(100)
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setObjectName("muted")
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(100, 800)
        self.zoom.setValue(100)

        controls = QHBoxLayout()
        for b in (self.btn_play, self.btn_pause, self.btn_stop):
            b.setStyleSheet("padding: 6px 8px;")
            controls.addWidget(b)
        controls.addStretch()
        controls.addWidget(self.lbl_time)
        adjustments = QHBoxLayout()
        for title, slider in (("Volume", self.volume), ("Speed", self.speed), ("Zoom", self.zoom)):
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            column.addWidget(slider)
            adjustments.addLayout(column, 1)
            slider.setMinimumWidth(45)
            slider.setToolTip(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        # A tab can be allocated less than its size hint. Enforce the actual
        # control minimums; the studio scroll area handles short viewports.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        for widget in (self.position, self.volume, self.speed, self.zoom,
                       self.btn_play, self.btn_pause, self.btn_stop, self.lbl_time):
            widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.position.setMinimumHeight(20)
        for slider in (self.volume, self.speed, self.zoom):
            slider.setMinimumHeight(20)
        layout.addWidget(self.waveform, 1)
        layout.addWidget(self.position)
        layout.addLayout(controls)
        layout.addLayout(adjustments)

        self.btn_play.clicked.connect(self._play_clicked)
        self.btn_pause.clicked.connect(self.player.pause)
        self.btn_stop.clicked.connect(self._stop)
        self.volume.valueChanged.connect(self._on_volume)
        self.speed.valueChanged.connect(lambda v: self.player.setPlaybackRate(v / 100.0))
        self.zoom.valueChanged.connect(lambda v: self.waveform.set_zoom(v / 100.0))
        self.position.sliderMoved.connect(self.player.setPosition)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)
        self.waveform.positionClicked.connect(self._seek_frac)

    def _apply_output_device(self) -> None:
        try:
            device = QMediaDevices.defaultAudioOutput()
            if not device.isNull():
                self.audio_out.setDevice(device)
        except Exception as exc:
            logger.warning("Could not set audio output device: %s", exc)

    def _on_volume(self, value: int) -> None:
        self.audio_out.setMuted(False)
        self.audio_out.setVolume(max(0.0, min(1.0, value / 100.0)))

    def _play_clicked(self) -> None:
        self._apply_output_device()
        self.audio_out.setMuted(False)
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return
        # If media never loaded, retry current file
        if self._current_path and self.player.mediaStatus() in (
            QMediaPlayer.MediaStatus.NoMedia,
            QMediaPlayer.MediaStatus.InvalidMedia,
        ):
            self.load_file(self._current_path, autoplay=True)
            return
        self.player.play()

    def load_file(
        self,
        path: Path | str,
        chunk_durs: list[float] | None = None,
        autoplay: bool = True,
    ) -> None:
        path = Path(path).resolve()
        self._autoplay = autoplay
        self._load_retries = 0
        self._current_path = path

        # Stop and detach previous source so Windows releases file locks / cache
        self.player.stop()
        self.player.setSource(QUrl())

        play_path = self._ensure_playable(path)
        self._load_waveform(play_path, chunk_durs)

        # Brief delay so the file is fully flushed to disk
        QTimer.singleShot(80, lambda: self._set_source(play_path))

    def _ensure_playable(self, path: Path) -> Path:
        """QMediaPlayer is most reliable with WAV on Windows."""
        if path.suffix.lower() == ".wav" and path.is_file():
            return path
        # Convert other formats to a temp WAV for playback
        try:
            tmp_dir = Path(tempfile.gettempdir()) / "VoiceForgePlayback"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            preview = tmp_dir / f"{path.stem}_preview.wav"
            if path.suffix.lower() == ".wav":
                shutil.copy2(path, preview)
            else:
                convert_file(path, preview)
            self._preview_path = preview
            return preview
        except Exception as exc:
            logger.warning("Playback conversion failed, using original: %s", exc)
            return path

    def _load_waveform(self, path: Path, chunk_durs: list[float] | None) -> None:
        try:
            samples, _sr = read_wav(path)
            peaks = compute_waveform_peaks(samples, buckets=2500)
            self.waveform.set_peaks(peaks)
        except Exception:
            import numpy as np

            self.waveform.set_peaks(np.zeros(0))
        markers: list[float] = []
        if chunk_durs:
            total = sum(chunk_durs) or 1.0
            acc = 0.0
            for d in chunk_durs[:-1]:
                acc += d
                markers.append(acc / total)
        self._chunk_markers = markers
        self.waveform.set_markers(markers)

    def _set_source(self, path: Path) -> None:
        if not path.is_file():
            self.statusMessage.emit(f"Audio file missing: {path}")
            return
        self._apply_output_device()
        self.audio_out.setMuted(False)
        self.audio_out.setVolume(self.volume.value() / 100.0)
        url = QUrl.fromLocalFile(str(path))
        self.player.setSource(url)
        self.statusMessage.emit(f"Loaded {path.name}")

    def _on_media_status(self, status) -> None:
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            if self._autoplay:
                self._autoplay = False
                self.player.setPosition(0)
                self.player.play()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            if self._current_path and self._load_retries < 2:
                self._load_retries += 1
                QTimer.singleShot(150, lambda: self.load_file(self._current_path, autoplay=True))
            else:
                self.statusMessage.emit("Could not load audio for playback")

    def _on_error(self, error, message: str = "") -> None:
        # Qt6 signature: errorOccurred(Error error, QString errorString)
        text = message or str(error)
        logger.error("Media player error: %s", text)
        self.statusMessage.emit(f"Playback error: {text}")
        if self._current_path and self._load_retries < 2:
            self._load_retries += 1
            QTimer.singleShot(200, lambda: self.load_file(self._current_path, autoplay=True))

    def _stop(self) -> None:
        self.player.stop()
        self.waveform.set_position(0)

    def _on_pos(self, pos: int) -> None:
        if not self.position.isSliderDown():
            self.position.setValue(pos)
        self.lbl_time.setText(f"{_fmt_ms(pos)} / {_fmt_ms(self._duration_ms)}")
        if self._duration_ms:
            self.waveform.set_position(pos / self._duration_ms)

    def _on_dur(self, dur: int) -> None:
        self._duration_ms = dur
        self.position.setRange(0, max(dur, 0))
        self.lbl_time.setText(f"00:00 / {_fmt_ms(dur)}")

    def _seek_frac(self, frac: float) -> None:
        if self._duration_ms:
            self.player.setPosition(int(frac * self._duration_ms))

    def seek(self, seconds: float) -> None:
        """Seek to absolute position in seconds."""
        if self._duration_ms:
            ms = int(max(0.0, seconds) * 1000)
            self.player.setPosition(min(ms, self._duration_ms))
