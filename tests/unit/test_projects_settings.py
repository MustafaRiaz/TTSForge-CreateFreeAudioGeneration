"""Project and settings tests."""

from app.database.db import Database
from app.projects.manager import ProjectData, ProjectManager
from app.services.settings_service import SettingsService
from app.utils.security import safe_filename


def test_settings_defaults(tmp_path):
    db = Database(tmp_path / "t.db")
    settings = SettingsService(db)
    assert settings.get("theme") in ("dark", "light", "system")
    settings.set("theme", "light")
    assert settings.get("theme") == "light"


def test_project_save_load(tmp_path):
    pm = ProjectManager(tmp_path / "projects")
    data = ProjectData(name="Demo", text="Hello", voice_id="kokoro:af_heart")
    pm.create("Demo", data)
    loaded = pm.load("Demo")
    assert loaded.text == "Hello"
    assert "Demo" in pm.list_projects()


def test_history_and_favorites(tmp_path):
    db = Database(tmp_path / "h.db")
    hid = db.add_history(title="t", voice_id="v", duration_sec=1.2, output_format="wav", status="completed")
    assert hid > 0
    rows = db.list_history()
    assert rows
    db.add_favorite("v1")
    assert "v1" in db.list_favorites()


def test_safe_filename():
    assert ".." not in safe_filename("../etc/passwd")
    assert safe_filename("My Book!") 
