"""Install a built wheel in an isolated environment and check its packaged assets."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=root / "dist")
    args = parser.parse_args()
    wheels = sorted(args.dist.resolve().glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one wheel in dist/")
    with tempfile.TemporaryDirectory(prefix="tokenme-wheel-") as temp:
        folder = Path(temp)
        environment = folder / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        binaries = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        env = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}

        def run(*args):
            subprocess.run([str(arg) for arg in args], cwd=folder, env=env, check=True)

        run(python, "-m", "pip", "install", "--no-index", "--no-deps", wheels[0])
        run(binaries / ("tokenme.exe" if os.name == "nt" else "tokenme"), "--version")
        run(python, "-m", "token_footprint", "doctor", "--json")
        run(python, "-m", "token_footprint", "scan", "--sources", "none", "--out", "report")
        html = (folder / "report/report.html").read_text(encoding="utf-8")
        data = json.loads((folder / "report/report-data.json").read_text(encoding="utf-8"))
        assert "__REPORT_DATA__" not in html and "__SHARE_CARD_SCRIPT__" not in html
        assert "TokenMeCard" in html and data["share"]["matrix"]
        assert data["views"]["all"]["total_tokens"] == 0
        run(python, "-m", "token_footprint", "report", "--store", "report/history.sqlite3", "--out", "rebuilt")
        run(python, "-m", "token_footprint", "timeline", "--store", "report/history.sqlite3", "--json")
        install = subprocess.run([sys.executable, str(root / "scripts/bootstrap.py"), "--prefix",
                                  str(folder / "agent install"), "--wheel", str(wheels[0]), "--run", "--sources", "none"],
                                 cwd=folder, env=env, check=True, capture_output=True, text=True)
        result = json.loads(install.stdout)
        assert result["ok"] and result["command"] == "run"
        assert Path(result["data"]["python"]).is_file() and Path(result["data"]["report"]).is_file()
        assert Path(result["data"]["store"]).parent == (folder / "agent install/report").resolve()
        print("Isolated wheel and Agent installer, CLI, database, HTML, Canvas and QR assets verified")


if __name__ == "__main__":
    main()
