"""Project chapter model tests."""

from app.projects.manager import Chapter, ProjectData


def test_project_chapters() -> None:
    data = ProjectData(
        name="book",
        text="fallback",
        chapters=[
            {"title": "Intro", "text": "Once upon a time", "order": 0},
            {"title": "End", "text": "The end", "order": 1},
        ],
    )
    chapters = data.get_chapters()
    assert len(chapters) == 2
    assert chapters[0].title == "Intro"
    assert isinstance(chapters[0], Chapter)

    empty = ProjectData(name="empty", text="")
    assert empty.get_chapters() == []

    single = ProjectData(name="single", text="Hello")
    assert len(single.get_chapters()) == 1
    assert single.get_chapters()[0].title == "Main"
