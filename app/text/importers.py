"""Document importers — local only."""

from __future__ import annotations

import re
from pathlib import Path


ALLOWED_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".docx", ".pdf", ".epub"}


def _safe_read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def import_txt(path: Path) -> str:
    return _safe_read_text(path)


def import_markdown(path: Path) -> str:
    text = _safe_read_text(path)
    # Light markdown → speech-friendly plain text
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


def import_html(path: Path) -> str:
    raw = _safe_read_text(path)
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", " ", text).strip()


def import_docx(path: Path) -> str:
    try:
        from docx import Document
    except Exception as exc:
        raise RuntimeError("python-docx is required to import DOCX files.") from exc
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n\n".join(parts)


def import_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("pypdf is required to import PDF files.") from exc
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def import_epub(path: Path) -> str:
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except Exception as exc:
        raise RuntimeError("ebooklib and beautifulsoup4 are required to import EPUB files.") from exc
    book = epub.read_epub(str(path))
    parts: list[str] = []
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        try:
            html = item.get_content().decode("utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text("\n").strip()
            if text:
                parts.append(text)
        except Exception:
            continue
    text = "\n\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def import_epub_chapters(path: Path) -> list[dict[str, str]]:
    """Return EPUB spine items as chapter dicts with title and text."""
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except Exception as exc:
        raise RuntimeError("ebooklib is required for EPUB chapter import.") from exc
    book = epub.read_epub(str(path))
    chapters: list[dict[str, str]] = []
    idx = 0
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        try:
            html = item.get_content().decode("utf-8", errors="replace")
            soup = BeautifulSoup(html, "html.parser")
            title_tag = soup.find(["h1", "h2", "title"])
            title = title_tag.get_text().strip() if title_tag else f"Chapter {idx + 1}"
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text("\n").strip()
            if text:
                chapters.append({"title": title, "text": text, "order": idx})
                idx += 1
        except Exception:
            continue
    return chapters


def import_document(path: Path | str) -> str:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    # Prevent obvious path tricks when called with untrusted strings
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")
    if suffix == ".txt":
        return import_txt(path)
    if suffix in {".md", ".markdown"}:
        return import_markdown(path)
    if suffix in {".html", ".htm"}:
        return import_html(path)
    if suffix == ".docx":
        return import_docx(path)
    if suffix == ".pdf":
        return import_pdf(path)
    if suffix == ".epub":
        return import_epub(path)
    raise ValueError(f"Unsupported file type: {suffix}")
