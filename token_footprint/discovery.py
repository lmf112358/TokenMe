"""Agent preflight: identify supported directories without opening credentials or logs."""
import os
from pathlib import Path
import sys

from . import __version__


def data_directory():
    return Path(os.environ.get("TOKENME_HOME") or Path.home() / ".tokenme").expanduser().resolve()


def source_roots(home, codex_root=None, workbuddy_root=None):
    default_codex = Path(os.environ.get("CODEX_HOME") or home / ".codex") if home == Path.home() else home / ".codex"
    return {"codex": codex_root or default_codex, "workbuddy": workbuddy_root or home / ".workbuddy"}


def doctor(home, codex_root=None, workbuddy_root=None):
    roots = source_roots(home, codex_root, workbuddy_root)
    sources = []
    for name, root in roots.items():
        paths = [root / "sessions", root / "archived_sessions"] if name == "codex" else [root / "traces"]
        sources.append({"source": name, "directory_found": any(path.is_dir() for path in paths),
                        "usage_verified": False})
    return {"version": __version__, "python": sys.version.split()[0], "python_executable": sys.executable, "sources": sources,
            "default_report": str(data_directory() / "report" / "report.html"),
            "legacy_history_in_cwd": (Path.cwd() / ".local/report/history.sqlite3").is_file(),
            "commands": ["doctor", "run", "scan", "report", "timeline", "backup", "export", "account"],
            "network_required_for_scan": False, "preflight_only": True,
            "note": "Directory presence does not establish valid usage or complete coverage."}
