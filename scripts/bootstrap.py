"""Install this reviewed checkout in an isolated environment; optionally generate a report."""
import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import venv
import zipfile
from email.parser import Parser


def main(argv=None):
    parser = argparse.ArgumentParser(description="TokenMe isolated installer (Python 3.10+)")
    parser.add_argument("--prefix", type=Path, default=Path(os.environ.get("TOKENME_HOME") or Path.home() / ".tokenme"))
    parser.add_argument("--wheel", type=Path, help="Optional matching local wheel; installs without network")
    parser.add_argument("--check", action="store_true", help="Print installation plan without changing files")
    parser.add_argument("--run", action="store_true", help="Scan local usage after installation")
    parser.add_argument("--open", action="store_true", help="Open report after --run")
    parser.add_argument("--sources", default="codex,workbuddy", choices=("codex,workbuddy", "codex", "workbuddy", "none"))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    version = next(ast.literal_eval(n.value) for n in ast.parse((root / "token_footprint/__init__.py").read_text(encoding="utf-8")).body
                   if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))
    prefix = args.prefix.expanduser().resolve()
    environment = prefix / "venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    plan = {"version": version, "python": str(python), "report": str(prefix / "report/report.html"),
            "source": str(args.wheel.resolve() if args.wheel else root), "network_for_install": not bool(args.wheel),
            "scan_requested": args.run}
    try:
        if sys.version_info < (3, 10):
            raise ValueError("Python 3.10 or newer is required")
        if args.open and not args.run:
            raise ValueError("--open requires --run")
        if args.wheel:
            with zipfile.ZipFile(args.wheel) as wheel:
                metadata = [n for n in wheel.namelist() if n.endswith('.dist-info/METADATA')]
                if len(metadata) != 1:
                    raise ValueError("Invalid wheel metadata")
                info = Parser().parsestr(wheel.read(metadata[0]).decode('utf-8'))
                if info['Name'] != 'token-footprint-local' or info['Version'] != version:
                    raise ValueError("Wheel must match this TokenMe checkout version")
        if args.check:
            print(json.dumps({"ok": True, "plan": plan}))
            return 0
        if environment.exists() and not (environment / "pyvenv.cfg").is_file():
            raise ValueError("Installation directory exists but is not a virtual environment; choose another --prefix")
        if not python.is_file():
            venv.EnvBuilder(with_pip=True).create(environment)
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
        command = [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-deps"]
        command += ["--no-index", str(args.wheel.resolve())] if args.wheel else [str(root)]
        # Keep stdout machine-readable; pip progress goes to stderr.
        subprocess.run(command, cwd=prefix, env=env, stdout=sys.stderr, check=True)
        if args.run:
            command = [str(python), "-m", "token_footprint", "run", "--json", "--out", str(prefix / "report"), "--sources", args.sources]
            if args.open:
                command.append("--open")
            return subprocess.run(command, cwd=prefix, env=env, check=False).returncode
        print(json.dumps({"ok": True, "installed": plan}))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
