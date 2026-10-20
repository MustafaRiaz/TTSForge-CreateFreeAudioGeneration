"""Cache and audio helper tests."""

import numpy as np

from app.audio.cache import AudioCache
from app.audio.processing import concat_audio, normalize_peak, silence, write_wav, read_wav, compute_waveform_peaks


def test_cache_roundtrip(tmp_path):
    cache = AudioCache(tmp_path)
    key = AudioCache.make_key("hello", "voice", "kokoro", {"speed": 1.0})
    samples = np.random.randn(1000).astype(np.float32) * 0.1
    cache.put(key, samples, 22050)
    got = cache.get(key)
    assert got is not None
    audio, sr = got
    assert sr == 22050
    assert len(audio) == len(samples)


def test_wav_roundtrip(tmp_path):
    path = tmp_path / "t.wav"
    samples = np.sin(np.linspace(0, 10, 22050)).astype(np.float32) * 0.5
    write_wav(path, samples, 22050)
    audio, sr = read_wav(path)
    assert sr == 22050
    assert abs(len(audio) - 22050) < 2


def test_normalize_and_silence():
    x = np.array([0.1, -0.2, 0.05], dtype=np.float32)
    y = normalize_peak(x, 0.95)
    assert abs(float(np.max(np.abs(y))) - 0.95) < 1e-5
    z = silence(100, 1000)
    assert len(z) == 100


def test_waveform_peaks():
    x = np.random.randn(10000).astype(np.float32)
    peaks = compute_waveform_peaks(x, buckets=100)
    assert len(peaks) == 100


def test_concat():
    a = np.ones(10, dtype=np.float32)
    b = np.zeros(5, dtype=np.float32)
    c = concat_audio([a, b])
    assert len(c) == 15
