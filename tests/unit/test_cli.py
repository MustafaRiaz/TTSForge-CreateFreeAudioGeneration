"""CLI smoke tests."""

from app.cli import build_parser, main


def test_parser_list_voices():
    p = build_parser()
    args = p.parse_args(["--list-voices"])
    assert args.list_voices


def test_cli_list_voices_runs(tmp_path, monkeypatch):
    # Ensure dirs under temp if needed — CLI uses user data dir; just ensure no crash
    code = main(["--list-voices"])
    assert code == 0
