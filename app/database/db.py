"""SQLite persistence for settings, history, favorites, queue, and crash recovery."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT,
                    title TEXT,
                    voice_id TEXT,
                    created_at TEXT NOT NULL,
                    duration_sec REAL,
                    output_format TEXT,
                    output_path TEXT,
                    status TEXT,
                    text_preview TEXT
                );

                CREATE TABLE IF NOT EXISTS favorites (
                    voice_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recent_voices (
                    voice_id TEXT PRIMARY KEY,
                    used_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    status TEXT,
                    payload TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    position INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS crash_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    project_id TEXT,
                    payload TEXT,
                    updated_at TEXT
                );
                """
            )

    # Settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    def get_all_settings(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        out: dict[str, Any] = {}
        for row in rows:
            try:
                out[row["key"]] = json.loads(row["value"])
            except Exception:
                out[row["key"]] = row["value"]
        return out

    # History
    def add_history(self, **kwargs: Any) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO history(project_name, title, voice_id, created_at, duration_sec,
                                    output_format, output_path, status, text_preview)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kwargs.get("project_name"),
                    kwargs.get("title"),
                    kwargs.get("voice_id"),
                    kwargs.get("created_at", _utc_now()),
                    kwargs.get("duration_sec"),
                    kwargs.get("output_format"),
                    kwargs.get("output_path"),
                    kwargs.get("status", "completed"),
                    kwargs.get("text_preview"),
                ),
            )
            return int(cur.lastrowid)

    def list_history(self, query: str = "", limit: int = 200) -> list[dict[str, Any]]:
        q = f"%{query.lower()}%"
        with self.connect() as conn:
            if query:
                rows = conn.execute(
                    """
                    SELECT * FROM history
                    WHERE lower(coalesce(title,'')) LIKE ?
                       OR lower(coalesce(project_name,'')) LIKE ?
                       OR lower(coalesce(voice_id,'')) LIKE ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (q, q, q, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def delete_history(self, history_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM history WHERE id = ?", (history_id,))

    # Favorites / recent
    def add_favorite(self, voice_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO favorites(voice_id, created_at) VALUES(?, ?)",
                (voice_id, _utc_now()),
            )

    def remove_favorite(self, voice_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM favorites WHERE voice_id = ?", (voice_id,))

    def list_favorites(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT voice_id FROM favorites ORDER BY created_at DESC").fetchall()
        return [r["voice_id"] for r in rows]

    def touch_recent_voice(self, voice_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO recent_voices(voice_id, used_at) VALUES(?, ?)",
                (voice_id, _utc_now()),
            )

    def list_recent_voices(self, limit: int = 12) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT voice_id FROM recent_voices ORDER BY used_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["voice_id"] for r in rows]

    # Crash recovery
    def save_crash_state(self, payload: dict[str, Any], project_id: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO crash_state(id, project_id, payload, updated_at) VALUES(1, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id, payload=excluded.payload, updated_at=excluded.updated_at",
                (project_id, json.dumps(payload), _utc_now()),
            )

    def load_crash_state(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM crash_state WHERE id = 1").fetchone()
        if not row or not row["payload"]:
            return None
        data = json.loads(row["payload"])
        data["_project_id"] = row["project_id"]
        return data

    def clear_crash_state(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM crash_state WHERE id = 1")
