"""Audio processing, export, and tools — local only."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from typing import Iterable

import numpy as np

logger = logging.getLogger(__name__)

_FFMPEG_PATH: str | None = None


def _bundled_ffmpeg() -> Path | None:
    """Look for ffmpeg shipped beside the app or in resources."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                base / "ffmpeg" / "ffmpeg.exe",
                base / "ffmpeg.exe",
                base / "_internal" / "ffmpeg" / "ffmpeg.exe",
            ]
        )
    root = Path(__file__).resolve().parents[2]
    candidates.extend([root / "packaging" / "ffmpeg" / "ffmpeg.exe", root / "ffmpeg" / "ffmpeg.exe"])
    for c in candidates:
        if c.is_file():
            return c
    return None


def find_ffmpeg() -> str | None:
    global _FFMPEG_PATH
    if _FFMPEG_PATH and Path(_FFMPEG_PATH).is_file():
        return _FFMPEG_PATH
    bundled = _bundled_ffmpeg()
    if bundled:
        _FFMPEG_PATH = str(bundled)
        return _FFMPEG_PATH
    configured = os.environ.get("VOICEFORGE_FFMPEG")
    if configured and Path(configured).is_file():
        _FFMPEG_PATH = configured
        return _FFMPEG_PATH
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG_PATH = found
    return found


def set_ffmpeg_path(path: str | Path | None) -> None:
    global _FFMPEG_PATH
    if path and Path(path).is_file():
        _FFMPEG_PATH = str(Path(path).resolve())
    else:
        _FFMPEG_PATH = None


def write_wav(path: Path | str, samples: np.ndarray, sample_rate: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(samples, dtype=np.float32)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())
    return path


def read_wav(path: Path | str) -> tuple[np.ndarray, int]:
    path = Path(path)
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        channels = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())
        width = wf.getsampwidth()
    if width == 2:
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        data = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, int(sr)


def silence(duration_ms: int, sample_rate: int) -> np.ndarray:
    n = int(sample_rate * (duration_ms / 1000.0))
    return np.zeros(max(n, 0), dtype=np.float32)


def concat_audio(parts: Iterable[np.ndarray]) -> np.ndarray:
    arrays = [np.asarray(p, dtype=np.float32) for p in parts if p is not None and len(p)]
    if not arrays:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(arrays)


def normalize_peak(samples: np.ndarray, peak: float = 0.95) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32)
    max_abs = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if max_abs <= 1e-8:
        return audio
    return audio * (peak / max_abs)


def adjust_volume(samples: np.ndarray, gain: float) -> np.ndarray:
    return np.clip(np.asarray(samples, dtype=np.float32) * float(gain), -1.0, 1.0)


def fade_in(samples: np.ndarray, ms: int, sample_rate: int) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32).copy()
    n = min(len(audio), int(sample_rate * ms / 1000.0))
    if n > 0:
        audio[:n] *= np.linspace(0.0, 1.0, n, dtype=np.float32)
    return audio


def fade_out(samples: np.ndarray, ms: int, sample_rate: int) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32).copy()
    n = min(len(audio), int(sample_rate * ms / 1000.0))
    if n > 0:
        audio[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
    return audio


def trim_silence(samples: np.ndarray, sample_rate: int, threshold: float = 0.02, pad_ms: int = 50) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32)
    if not len(audio):
        return audio
    mask = np.abs(audio) > threshold
    if not np.any(mask):
        return audio[:0]
    idx = np.where(mask)[0]
    pad = int(sample_rate * pad_ms / 1000.0)
    start = max(0, int(idx[0]) - pad)
    end = min(len(audio), int(idx[-1]) + pad)
    return audio[start:end]


def trim(samples: np.ndarray, sample_rate: int, start_sec: float, end_sec: float | None = None) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32)
    start = max(0, int(start_sec * sample_rate))
    end = len(audio) if end_sec is None else max(start, int(end_sec * sample_rate))
    return audio[start:end]


def split_at(samples: np.ndarray, sample_rate: int, points_sec: list[float]) -> list[np.ndarray]:
    audio = np.asarray(samples, dtype=np.float32)
    cuts = sorted(set([0.0] + points_sec + [len(audio) / sample_rate]))
    parts: list[np.ndarray] = []
    for a, b in zip(cuts, cuts[1:]):
        parts.append(trim(audio, sample_rate, a, b))
    return parts


def resample_linear(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32)
    if src_rate == dst_rate or len(audio) == 0:
        return audio
    duration = len(audio) / src_rate
    new_len = int(duration * dst_rate)
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def compute_waveform_peaks(samples: np.ndarray, buckets: int = 2000) -> np.ndarray:
    """Return peak envelope suitable for UI waveform drawing."""
    audio = np.asarray(samples, dtype=np.float32)
    if len(audio) == 0:
        return np.zeros(buckets, dtype=np.float32)
    if len(audio) <= buckets:
        # pad
        out = np.zeros(buckets, dtype=np.float32)
        out[: len(audio)] = np.abs(audio)
        return out
    bucket_size = len(audio) / buckets
    peaks = np.zeros(buckets, dtype=np.float32)
    for i in range(buckets):
        start = int(i * bucket_size)
        end = int((i + 1) * bucket_size)
        peaks[i] = float(np.max(np.abs(audio[start:end]))) if end > start else 0.0
    return peaks


def export_audio(
    samples: np.ndarray,
    sample_rate: int,
    output_path: Path | str,
    format: str = "wav",
    bitrate: str = "192k",
    channels: int = 1,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = format.lower().lstrip(".")
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)

    wav_tmp = output_path.with_suffix(".tmp.wav")
    write_wav(wav_tmp, audio, sample_rate)

    if fmt == "wav":
        final = output_path.with_suffix(".wav")
        if final.exists():
            final.unlink()
        wav_tmp.replace(final)
        return final

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        if fmt == "flac":
            try:
                import soundfile as sf

                final = output_path.with_suffix(".flac")
                sf.write(str(final), audio, sample_rate)
                wav_tmp.unlink(missing_ok=True)
                return final
            except Exception as exc:
                wav_tmp.unlink(missing_ok=True)
                raise RuntimeError("FFmpeg not found and FLAC export via soundfile failed.") from exc
        wav_tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"FFmpeg is required to export {fmt.upper()}. Install FFmpeg and ensure it is on PATH."
        )

    final = output_path.with_suffix(f".{fmt}")
    cmd = [ffmpeg, "-y", "-i", str(wav_tmp)]
    if fmt == "mp3":
        cmd += ["-codec:a", "libmp3lame", "-b:a", bitrate]
    elif fmt == "ogg":
        cmd += ["-codec:a", "libvorbis", "-b:a", bitrate]
    elif fmt == "flac":
        cmd += ["-codec:a", "flac"]
    else:
        wav_tmp.unlink(missing_ok=True)
        raise ValueError(f"Unsupported format: {fmt}")
    if channels in (1, 2):
        cmd += ["-ac", str(channels)]
    cmd.append(str(final))
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        wav_tmp.unlink(missing_ok=True)
    return final


def convert_file(
    input_path: Path | str,
    output_path: Path | str,
    sample_rate: int | None = None,
    bitrate: str = "192k",
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        # wav↔wav via numpy
        samples, sr = read_wav(input_path)
        if sample_rate and sample_rate != sr:
            samples = resample_linear(samples, sr, sample_rate)
            sr = sample_rate
        return export_audio(samples, sr, output_path, format=output_path.suffix.lstrip(".") or "wav", bitrate=bitrate)
    cmd = [ffmpeg, "-y", "-i", str(input_path)]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]
    if output_path.suffix.lower() == ".mp3":
        cmd += ["-b:a", bitrate]
    cmd.append(str(output_path))
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def set_wav_metadata_comment(path: Path | str, comment: str) -> None:
    """Best-effort metadata via ffmpeg when available."""
    path = Path(path)
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return
    tmp = path.with_suffix(path.suffix + ".meta.tmp" + path.suffix)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(path),
        "-c",
        "copy",
        "-metadata",
        f"comment={comment}",
        str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)


# Post-processing presets for export pipeline
POST_PROCESS_PRESETS: dict[str, dict] = {
    "none": {"label": "None", "filters": ""},
    "podcast": {
        "label": "Podcast (-16 LUFS)",
        "filters": "loudnorm=I=-16:TP=-1.5:LRA=11",
    },
    "audiobook": {
        "label": "Audiobook (gentle compression)",
        "filters": "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,loudnorm=I=-18:TP=-1.5:LRA=9",
    },
    "broadcast": {
        "label": "Broadcast (-23 LUFS)",
        "filters": "loudnorm=I=-23:TP=-2:LRA=7",
    },
}


def apply_ffmpeg_filter(input_path: Path | str, output_path: Path | str, af_filter: str) -> Path:
    """Apply an FFmpeg audio filter chain to a file."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for post-processing presets.")
    input_path = Path(input_path)
    output_path = Path(output_path)
    cmd = [ffmpeg, "-y", "-i", str(input_path), "-af", af_filter, str(output_path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def apply_post_process_preset(
    input_path: Path | str,
    output_path: Path | str,
    preset_id: str = "none",
) -> Path:
    preset = POST_PROCESS_PRESETS.get(preset_id, POST_PROCESS_PRESETS["none"])
    if not preset.get("filters"):
        return Path(input_path)
    return apply_ffmpeg_filter(input_path, output_path, preset["filters"])
