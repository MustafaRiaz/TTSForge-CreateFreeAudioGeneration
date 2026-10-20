"""Project save/load and portable export."""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Chapter:
    title: str
    text: str
    voice_id: str = ""
    order: int = 0


@dataclass
class ProjectData:
    name: str
    text: str = ""
    voice_id: str = ""
    speaker_map: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_chapters(self) -> list[Chapter]:
        if not self.chapters:
            if self.text.strip():
                return [Chapter(title="Main", text=self.text, voice_id=self.voice_id, order=0)]
            return []
        return [
            Chapter(
                title=c.get("title", f"Chapter {i+1}"),
                text=c.get("text", ""),
                voice_id=c.get("voice_id", self.voice_id),
                order=int(c.get("order", i)),
            )
            for i, c in enumerate(self.chapters)
        ]


class ProjectManager:
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = Path(projects_root)
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, name: str) -> str:
        cleaned = "".join(c for c in name.strip() if c.isalnum() or c in (" ", "-", "_")).strip()
        cleaned = cleaned.replace(" ", "_") or "Untitled"
        # Prevent path traversal
        if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError("Invalid project name")
        return cleaned[:80]

    def project_dir(self, name: str) -> Path:
        return self.projects_root / self._safe_name(name)

    def create(self, name: str, data: ProjectData | None = None) -> Path:
        safe = self._safe_name(name)
        root = self.projects_root / safe
        if root.exists():
            raise FileExistsError(f"Project already exists: {safe}")
        for sub in ("source", "audio", "chunks", "exports"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        project = data or ProjectData(name=safe)
        project.name = safe
        self._write(root, project)
        return root

    def _write(self, root: Path, project: ProjectData) -> None:
        project.updated_at = _utc_now()
        db_path = root / "project.db"
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO project(id, json) VALUES(1, ?) "
                "ON CONFLICT(id) DO UPDATE SET json = excluded.json",
                (json.dumps(asdict(project), ensure_ascii=False),),
            )
            conn.commit()
        finally:
            conn.close()
        (root / "source" / "document.txt").write_text(project.text, encoding="utf-8")

    def save(self, project: ProjectData) -> Path:
        root = self.project_dir(project.name)
        root.mkdir(parents=True, exist_ok=True)
        for sub in ("source", "audio", "chunks", "exports"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        self._write(root, project)
        return root

    def load(self, name: str) -> ProjectData:
        root = self.project_dir(name)
        db_path = root / "project.db"
        if not db_path.is_file():
            raise FileNotFoundError(root)
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT json FROM project WHERE id = 1").fetchone()
        finally:
            conn.close()
        if not row:
            raise FileNotFoundError("Project metadata missing")
        data = json.loads(row[0])
        return ProjectData(**data)

    def list_projects(self) -> list[str]:
        names: list[str] = []
        for p in sorted(self.projects_root.iterdir()):
            if p.is_dir() and (p / "project.db").is_file():
                names.append(p.name)
        return names

    def delete(self, name: str) -> None:
        root = self.project_dir(name)
        if root.exists():
            shutil.rmtree(root)

    def export_archive(self, name: str, destination: Path) -> Path:
        root = self.project_dir(name)
        if not root.exists():
            raise FileNotFoundError(root)
        destination = Path(destination)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in root.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(root.parent)))
        return destination

    def import_archive(self, archive: Path) -> str:
        archive = Path(archive)
        with zipfile.ZipFile(archive, "r") as zf:
            # Validate no path traversal
            for info in zf.infolist():
                name = info.filename
                if name.startswith("/") or ".." in Path(name).parts:
                    raise ValueError("Archive contains unsafe paths")
            zf.extractall(self.projects_root)
        # Find extracted project
        for p in self.projects_root.iterdir():
            if p.is_dir() and (p / "project.db").is_file():
                # return latest-ish match by archive stem
                if archive.stem.replace(" ", "_") in p.name or True:
                    return p.name
        raise RuntimeError("No project found in archive")
