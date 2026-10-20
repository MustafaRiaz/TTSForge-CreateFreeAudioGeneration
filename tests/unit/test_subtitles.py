"""Subtitle export tests."""

from pathlib import Path

from app.audio.subtitles import SubtitleEntry, export_srt, export_vtt


def test_export_srt_vtt(tmp_path: Path) -> None:
    entries = [
        SubtitleEntry(index=1, start_sec=0.0, end_sec=2.5, text="Hello world"),
        SubtitleEntry(index=2, start_sec=2.5, end_sec=5.0, text="Second line"),
    ]
    srt = export_srt(entries, tmp_path / "out.srt")
    vtt = export_vtt(entries, tmp_path / "out.vtt")
    srt_text = srt.read_text(encoding="utf-8")
    vtt_text = vtt.read_text(encoding="utf-8")
    assert "Hello world" in srt_text
    assert "00:00:00,000 --> 00:00:02,500" in srt_text
    assert vtt_text.startswith("WEBVTT")
    assert "00:00:02.500 --> 00:00:05.000" in vtt_text
