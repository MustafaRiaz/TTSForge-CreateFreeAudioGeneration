"""Text normalization, pronunciation, segmentation, chunking, and markup."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable


# --- Numbers / currency / dates ---

_ORDINAL_MAP = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
    11: "eleventh",
    12: "twelfth",
    13: "thirteenth",
    20: "twentieth",
    21: "twenty first",
    22: "twenty second",
    23: "twenty third",
    30: "thirtieth",
}

_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

_ABBREVIATIONS = {
    "Mr.": "Mister",
    "Mrs.": "Misses",
    "Ms.": "Miss",
    "Dr.": "Doctor",
    "Prof.": "Professor",
    "Sr.": "Senior",
    "Jr.": "Junior",
    "St.": "Street",
    "Ave.": "Avenue",
    "Blvd.": "Boulevard",
    "etc.": "et cetera",
    "e.g.": "for example",
    "i.e.": "that is",
    "vs.": "versus",
    "approx.": "approximately",
    "Dept.": "Department",
    "Inc.": "Incorporated",
    "Ltd.": "Limited",
    "Co.": "Company",
    "US": "U S",
    "USA": "U S A",
    "UK": "U K",
    "AI": "A I",
    "TTS": "T T S",
}


def _int_to_words(n: int) -> str:
    if n < 0:
        return "minus " + _int_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        ten, one = divmod(n, 10)
        return _TENS[ten] + (f" {_ONES[one]}" if one else "")
    if n < 1000:
        hund, rest = divmod(n, 100)
        return _ONES[hund] + " hundred" + (f" {_int_to_words(rest)}" if rest else "")
    if n < 1_000_000:
        thou, rest = divmod(n, 1000)
        return _int_to_words(thou) + " thousand" + (f" {_int_to_words(rest)}" if rest else "")
    if n < 1_000_000_000:
        mill, rest = divmod(n, 1_000_000)
        return _int_to_words(mill) + " million" + (f" {_int_to_words(rest)}" if rest else "")
    return str(n)


def _number_to_words(num_str: str) -> str:
    if "." in num_str:
        whole, frac = num_str.split(".", 1)
        whole_part = _int_to_words(int(whole)) if whole else "zero"
        frac_part = " ".join(_ONES[int(d)] for d in frac if d.isdigit())
        return f"{whole_part} point {frac_part}"
    return _int_to_words(int(num_str))


@dataclass
class PronunciationRule:
    pattern: str
    replacement: str
    is_regex: bool = False
    case_sensitive: bool = False


@dataclass
class TextStats:
    characters: int = 0
    characters_no_spaces: int = 0
    words: int = 0
    paragraphs: int = 0
    sentences: int = 0
    estimated_duration_sec: float = 0.0


@dataclass
class TextChunk:
    index: int
    text: str
    kind: str = "speech"  # speech | break
    pause_ms: int = 0
    speaker: str | None = None
    speed: float | None = None
    emphasis: bool = False
    meta: dict = field(default_factory=dict)


class TextProcessor:
    """Intelligent preprocessing for TTS."""

    def __init__(self, rules: list[PronunciationRule] | None = None, wpm: float = 160.0) -> None:
        self.rules = rules or []
        self.wpm = wpm

    def stats(self, text: str) -> TextStats:
        stripped = text.strip()
        words = re.findall(r"\b[\w']+\b", stripped)
        paragraphs = [p for p in re.split(r"\n\s*\n", stripped) if p.strip()] if stripped else []
        sentences = self.split_sentences(stripped)
        chars = len(text)
        chars_ns = len(re.sub(r"\s+", "", text))
        duration = (len(words) / self.wpm) * 60.0 if words else 0.0
        return TextStats(
            characters=chars,
            characters_no_spaces=chars_ns,
            words=len(words),
            paragraphs=len(paragraphs) if paragraphs else (1 if stripped else 0),
            sentences=len(sentences),
            estimated_duration_sec=duration,
        )

    def normalize(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = self._sanitize_symbols(text)
        text = self._replace_urls_emails(text)
        text = self._replace_emojis(text)
        text = self._expand_abbreviations(text)
        text = self._expand_currency(text)
        text = self._expand_percentages(text)
        text = self._expand_dates(text)
        text = self._expand_numbers(text)
        text = self._apply_custom_rules(text)
        text = self._sanitize_symbols(text)  # again after expansions
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _sanitize_symbols(self, text: str) -> str:
        """Convert punctuation that phonemizers reject into speakable forms."""
        # Em/en dashes and double hyphens → short pause (comma)
        text = text.replace("\u2014", ", ")  # —
        text = text.replace("\u2013", ", ")  # –
        text = text.replace("\u2212", "-")  # minus
        text = re.sub(r"-{2,}", ", ", text)
        # Ellipsis
        text = text.replace("\u2026", ".")
        text = re.sub(r"\.{4,}", "...", text)
        # Smart quotes → plain
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u00ab", '"').replace("\u00bb", '"')
        # Bullets / markdown leftovers that yield no phonemes alone
        text = re.sub(r"^[\s]*[•·▪◦\*_-]+[\s]+", "", text, flags=re.MULTILINE)
        text = re.sub(r"[#|_~`^]+", " ", text)
        text = re.sub(r"[<>{}[\]\\]+", " ", text)
        # Standalone symbol-only tokens → remove
        text = re.sub(r"(?<!\w)[^\w\s.,!?;:'\"%$€£/+-]+(?!\w)", " ", text)
        text = re.sub(r" ,", ",", text)
        text = re.sub(r" +", " ", text)
        return text

    @staticmethod
    def is_speakable(text: str) -> bool:
        """True if text contains at least one letter or digit for phonemization."""
        return bool(re.search(r"[A-Za-z0-9\u00C0-\u024F]", text or ""))

    def prepare_for_synthesis(self, text: str) -> str:
        """Final per-chunk cleanup before sending to a TTS engine."""
        cleaned = self._sanitize_symbols(text or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
        cleaned = cleaned.strip()
        # Avoid lone punctuation chunks like "--" or "..."
        if not self.is_speakable(cleaned):
            return ""
        return cleaned

    def _apply_custom_rules(self, text: str) -> str:
        for rule in self.rules:
            flags = 0 if rule.case_sensitive else re.IGNORECASE
            if rule.is_regex:
                text = re.sub(rule.pattern, rule.replacement, text, flags=flags)
            else:
                if rule.case_sensitive:
                    text = text.replace(rule.pattern, rule.replacement)
                else:
                    text = re.sub(re.escape(rule.pattern), rule.replacement, text, flags=re.IGNORECASE)
        return text

    def _expand_abbreviations(self, text: str) -> str:
        for abbr, expansion in sorted(_ABBREVIATIONS.items(), key=lambda x: -len(x[0])):
            if abbr.endswith("."):
                text = re.sub(rf"(?<!\w){re.escape(abbr)}(?!\w)", expansion, text)
            else:
                text = re.sub(rf"\b{re.escape(abbr)}\b", expansion, text)
        return text

    def _replace_urls_emails(self, text: str) -> str:
        text = re.sub(
            r"https?://[^\s]+",
            lambda m: "link " + re.sub(r"[^\w\s]", " ", m.group(0).replace("https://", "").replace("http://", "")),
            text,
        )
        text = re.sub(
            r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
            lambda m: " ".join(m.group(0).replace(".", " dot ").replace("@", " at ")),
            text,
        )
        return text

    def _replace_emojis(self, text: str) -> str:
        # Strip most emoji / symbols that confuse phonemizers; keep basic punctuation
        return re.sub(
            r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F600-\U0001F64F]",
            "",
            text,
        )

    def _expand_currency(self, text: str) -> str:
        def repl(m: re.Match) -> str:
            amount = m.group(1)
            spoken = _number_to_words(amount.replace(",", ""))
            if "." in amount:
                return f"{spoken} dollars"
            return f"{spoken} dollars"

        text = re.sub(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)", repl, text)

        def euro(m: re.Match) -> str:
            return _number_to_words(m.group(1).replace(",", "")) + " euros"

        text = re.sub(r"€\s*([0-9]+(?:\.[0-9]{1,2})?)", euro, text)

        def gbp(m: re.Match) -> str:
            return _number_to_words(m.group(1).replace(",", "")) + " pounds"

        text = re.sub(r"£\s*([0-9]+(?:\.[0-9]{1,2})?)", gbp, text)
        return text

    def _expand_percentages(self, text: str) -> str:
        return re.sub(
            r"([0-9]+(?:\.[0-9]+)?)\s*%",
            lambda m: _number_to_words(m.group(1)) + " percent",
            text,
        )

    def _expand_dates(self, text: str) -> str:
        # ISO-ish YYYY-MM-DD
        def iso(m: re.Match) -> str:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            months = [
                "",
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
            day = _ORDINAL_MAP.get(d, _number_to_words(d))
            return f"{months[mo]} {day} {_int_to_words(y)}"

        text = re.sub(r"\b(20[0-9]{2}|19[0-9]{2})-([01]?[0-9])-([0-3]?[0-9])\b", iso, text)
        return text

    def _expand_numbers(self, text: str) -> str:
        return re.sub(
            r"\b([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\b",
            lambda m: _number_to_words(m.group(1).replace(",", "")),
            text,
        )

    def split_paragraphs(self, text: str) -> list[str]:
        parts = re.split(r"\n\s*\n", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def split_sentences(self, text: str) -> list[str]:
        if not text.strip():
            return []
        # Protect common abbreviations temporarily
        protected = text
        repls: list[tuple[str, str]] = []
        for i, abbr in enumerate(["Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "e.g.", "i.e.", "etc.", "vs."]):
            token = f"__ABBR{i}__"
            if abbr in protected:
                protected = protected.replace(abbr, token)
                repls.append((token, abbr))
        pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'\(])", protected)
        out: list[str] = []
        for piece in pieces:
            for token, abbr in repls:
                piece = piece.replace(token, abbr)
            piece = piece.strip()
            if piece:
                out.append(piece)
        return out

    def parse_markup(self, text: str) -> list[TextChunk]:
        """Application-level markup (not native SSML)."""
        chunks: list[TextChunk] = []
        pattern = re.compile(
            r"<break\s+time=\"(\d+)(ms|s)\"\s*/?>|"
            r"<speed\s+rate=\"(slow|fast|normal|[0-9.]+)\"\s*>(.*?)</speed>|"
            r"<emphasis>(.*?)</emphasis>",
            re.IGNORECASE | re.DOTALL,
        )
        idx = 0
        pos = 0
        for m in pattern.finditer(text):
            if m.start() > pos:
                plain = text[pos : m.start()].strip()
                if plain:
                    chunks.append(TextChunk(index=idx, text=plain))
                    idx += 1
            if m.group(1):
                amount = int(m.group(1))
                pause = amount if m.group(2) == "ms" else amount * 1000
                chunks.append(TextChunk(index=idx, text="", kind="break", pause_ms=pause))
                idx += 1
            elif m.group(3):
                rate = m.group(3).lower()
                speed = {"slow": 0.8, "fast": 1.25, "normal": 1.0}.get(rate)
                if speed is None:
                    try:
                        speed = float(rate)
                    except ValueError:
                        speed = 1.0
                inner = m.group(4).strip()
                if inner:
                    chunks.append(TextChunk(index=idx, text=inner, speed=speed))
                    idx += 1
            elif m.group(5):
                inner = m.group(5).strip()
                if inner:
                    chunks.append(TextChunk(index=idx, text=inner, emphasis=True, speed=0.9))
                    idx += 1
            pos = m.end()
        if pos < len(text):
            plain = text[pos:].strip()
            if plain:
                chunks.append(TextChunk(index=idx, text=plain))
        if not chunks and text.strip():
            chunks.append(TextChunk(index=0, text=text.strip()))
        return chunks

    def chunk_for_tts(
        self,
        text: str,
        max_chars: int = 400,
        speaker: str | None = None,
        normalize: bool = True,
    ) -> list[TextChunk]:
        """Split into manageable synthesis chunks without dumping whole books into the engine."""
        working = self.normalize(text) if normalize else text.strip()
        if not working:
            return []

        # Expand markup first into logical units
        units = self.parse_markup(working)
        result: list[TextChunk] = []
        idx = 0
        for unit in units:
            if unit.kind == "break":
                unit.index = idx
                unit.speaker = speaker
                result.append(unit)
                idx += 1
                continue
            paragraphs = self.split_paragraphs(unit.text)
            for pi, para in enumerate(paragraphs):
                sentences = self.split_sentences(para) or [para]
                buf = ""
                for sent in sentences:
                    if buf and len(buf) + 1 + len(sent) > max_chars:
                        result.append(
                            TextChunk(
                                index=idx,
                                text=buf.strip(),
                                speaker=speaker,
                                speed=unit.speed,
                                emphasis=unit.emphasis,
                            )
                        )
                        idx += 1
                        buf = sent
                    else:
                        buf = f"{buf} {sent}".strip() if buf else sent
                    # Hard split oversized sentences
                    while len(buf) > max_chars:
                        cut = buf.rfind(" ", 0, max_chars)
                        if cut < max_chars // 3:
                            cut = max_chars
                        piece = buf[:cut].strip()
                        buf = buf[cut:].strip()
                        if piece:
                            result.append(
                                TextChunk(
                                    index=idx,
                                    text=piece,
                                    speaker=speaker,
                                    speed=unit.speed,
                                    emphasis=unit.emphasis,
                                )
                            )
                            idx += 1
                if buf.strip():
                    result.append(
                        TextChunk(
                            index=idx,
                            text=buf.strip(),
                            speaker=speaker,
                            speed=unit.speed,
                            emphasis=unit.emphasis,
                            pause_ms=0,
                        )
                    )
                    idx += 1
                # paragraph boundary marker (pause applied during generation)
                if pi < len(paragraphs) - 1 and result:
                    result[-1].meta["paragraph_end"] = True

        # Drop empty / non-phonemic speech chunks; keep explicit breaks
        cleaned: list[TextChunk] = []
        for unit in result:
            if unit.kind == "break":
                unit.index = len(cleaned)
                cleaned.append(unit)
                continue
            speak = self.prepare_for_synthesis(unit.text)
            if not speak:
                continue
            unit.text = speak
            unit.index = len(cleaned)
            cleaned.append(unit)
        return cleaned


@dataclass
class SpeakerSection:
    speaker: str
    text: str
    start_line: int = 0


_SPEAKER_RE = re.compile(r"^\[([^\]]+)\]\s*$")


def parse_multi_voice_script(text: str) -> list[SpeakerSection]:
    lines = text.replace("\r\n", "\n").split("\n")
    sections: list[SpeakerSection] = []
    current: str | None = None
    buf: list[str] = []
    start = 0
    for i, line in enumerate(lines):
        m = _SPEAKER_RE.match(line.strip())
        if m:
            if current is not None and "".join(buf).strip():
                sections.append(SpeakerSection(speaker=current, text="\n".join(buf).strip(), start_line=start))
            current = m.group(1).strip()
            buf = []
            start = i
        else:
            if current is None:
                current = "NARRATOR"
                start = i
            buf.append(line)
    if current is not None and "".join(buf).strip():
        sections.append(SpeakerSection(speaker=current, text="\n".join(buf).strip(), start_line=start))
    if not sections and text.strip():
        sections.append(SpeakerSection(speaker="NARRATOR", text=text.strip()))
    return sections
