"""VoiceForge application entrypoint."""

from __future__ import annotations

import sys
import traceback


def run_gui() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app import __app_name__
    from app.core.logging_setup import setup_logging
    from app.core.paths import ORG_DOMAIN, ORG_NAME, ensure_dirs
    from app.services.app_context import AppContext
    from app.ui.main_window import MainWindow
    from app.ui.themes.manager import apply_theme

    # Disable optional ONNX Runtime telemetry (not app analytics)
    try:
        import onnxruntime as ort

        ort.disable_telemetry_events()
    except Exception:
        pass

    paths = ensure_dirs()
    setup_logging(paths["logs"])

    # Also mirror logs into repo logs/ during development
    try:
        from app.core.paths import project_root
        import logging
        from logging.handlers import RotatingFileHandler

        repo_logs = project_root() / "logs"
        repo_logs.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(repo_logs / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        logging.getLogger().addHandler(handler)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName(ORG_NAME)
    app.setOrganizationDomain(ORG_DOMAIN)

    try:
        ctx = AppContext()
        apply_theme(app, ctx.settings.get("theme", "dark"))
        window = MainWindow(ctx)
        window.show()
        return app.exec()
    except Exception as exc:
        traceback.print_exc()
        try:
            QMessageBox.critical(None, __app_name__, f"Startup failed:\n{exc}")
        except Exception:
            pass
        return 1


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] not in ("--gui",):
        # Delegate to CLI unless explicitly GUI
        if sys.argv[1] == "gui":
            return run_gui()
        from app.cli import main as cli_main

        return cli_main(sys.argv[1:])
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
