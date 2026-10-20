"""Unit tests for text processing."""

from app.text.processor import TextProcessor, parse_multi_voice_script


def test_currency_and_percent():
    tp = TextProcessor()
    out = tp.normalize("Price is $25.50 and tax is 8%.")
    assert "dollars" in out.lower()
    assert "percent" in out.lower()


def test_abbreviations():
    tp = TextProcessor()
    out = tp.normalize("Dr. Smith met Mr. Jones.")
    assert "Doctor" in out
    assert "Mister" in out


def test_stats():
    tp = TextProcessor()
    s = tp.stats("Hello world.\n\nSecond paragraph.")
    assert s.words == 4
    assert s.paragraphs == 2


def test_chunking_respects_max():
    tp = TextProcessor()
    text = " ".join(["Sentence number %d." % i for i in range(50)])
    chunks = tp.chunk_for_tts(text, max_chars=80)
    assert len(chunks) > 1
    assert all(len(c.text) <= 120 for c in chunks if c.kind == "speech")


def test_markup_break_and_speed():
    tp = TextProcessor()
    chunks = tp.parse_markup('Hello <break time="500ms"/> <speed rate="slow">world</speed>')
    kinds = [c.kind for c in chunks]
    assert "break" in kinds
    assert any(c.speed == 0.8 for c in chunks if c.kind == "speech")


def test_dashes_do_not_create_empty_chunks():
    tp = TextProcessor()
    assert tp.prepare_for_synthesis("--") == ""
    assert tp.prepare_for_synthesis("—") == ""
    out = tp.normalize("Hello -- world — there.")
    assert "--" not in out
    assert "—" not in out
    assert "Hello" in out and "world" in out
    chunks = tp.chunk_for_tts("Wait --\n\nOkay then.")
    assert chunks
    assert all(tp.is_speakable(c.text) for c in chunks if c.kind == "speech")


def test_multi_voice_parse():
    script = """[NARRATOR]
Welcome.

[JOHN]
Hello.

[SARAH]
Hi there.
"""
    sections = parse_multi_voice_script(script)
    assert [s.speaker for s in sections] == ["NARRATOR", "JOHN", "SARAH"]
