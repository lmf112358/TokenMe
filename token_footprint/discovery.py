"""Agent preflight: identify supported directories without opening credentials or logs."""
import os
from pathlib import Path
import sys

from . import __version__
from .model import source_family
from .tokscale import CLIENT_NAMES, PREFIX

NATIVE_SOURCES = ("codex", "workbuddy", "claude", "pi", "gemini", "opencode", "qwen", "kimi")
CATALOG = (
    ("codex", "Codex", "native", "本地会话与归档"),
    ("workbuddy", "WorkBuddy", "native", "已结束任务 trace"),
    ("claude", "Claude Code", "native", "本地会话，含子代理；不包含 Claude 网页聊天"),
    ("pi", "Pi Agent", "native", "本地消息、工具用量与已记录摘要用量"),
    ("gemini", "Gemini CLI", "native", "JSON / JSONL chat 记录；非零 tool 用量口径待扩充"),
    ("opencode", "OpenCode", "native", "SQLite 与旧版 JSON 消息"),
    ("qwen", "Qwen Code", "native", "本地 usageMetadata；不包含千问 App"),
    ("kimi", "Kimi Code", "native", "wire.jsonl 用量；不包含 Kimi 网页/App"),
    ("cursor", "Cursor", "import", "--cursor-csv 导入完整 Token CSV；个人账单样本待验证"),
    ("trae", "TRAE 国际版", "import", "--trae-json 导入会话用量数组；真实账号样本待验证"),
    ("trae_cn", "TRAE 中国版", "pending", "企业用量导出格式待适配；个人版入口待确认"),
    ("qoder", "Qoder", "pending", "Token 持久化格式待验证；Credits 不换算成 Token"),
    ("doubao", "豆包电脑版", "pending", "尚无已验证的原始 Token 数据入口；次数、时长不换算"),
)


def data_directory():
    return Path(os.environ.get("TOKENME_HOME") or Path.home() / ".tokenme").expanduser().resolve()


def source_roots(home, codex_root=None, workbuddy_root=None, **overrides):
    home = Path(home)
    def configured(name, fallback):
        return Path(os.environ[name]).expanduser() if home == Path.home() and os.environ.get(name) else fallback
    default_codex = Path(os.environ.get("CODEX_HOME") or home / ".codex") if home == Path.home() else home / ".codex"
    roots = {"codex": codex_root or default_codex, "workbuddy": workbuddy_root or home / ".workbuddy",
             "claude": configured("CLAUDE_CONFIG_DIR", home / ".claude"),
             "pi": configured("PI_CODING_AGENT_DIR", home / ".pi/agent"),
             "gemini": configured("GEMINI_CLI_HOME", home / ".gemini"),
             "opencode": configured("XDG_DATA_HOME", home / ".local/share") / "opencode",
             "qwen": home / ".qwen", "kimi": home / ".kimi"}
    roots.update({key.removesuffix("_root"): value for key, value in overrides.items() if value is not None})
    return roots


def data_paths(name, root, home, kimi_override=False):
    parts = {"codex": ("sessions", "archived_sessions"), "workbuddy": ("traces",),
             "claude": ("projects", "transcripts"), "pi": ("sessions",), "gemini": ("tmp",),
             "opencode": ("",), "qwen": ("projects",), "kimi": ("sessions",)}
    paths = [Path(root) / part for part in parts[name]]
    if name == "kimi" and not kimi_override:
        paths.append(Path(home) / ".kimi-code/sessions")
    return paths


def coverage_catalog(records=(), statuses=()):
    counts = {}
    imported = set()
    for record in records:
        family = source_family(record.source)
        counts[family] = counts.get(family, 0) + 1
        if record.record_id.startswith(PREFIX):
            imported.add(family)
    latest = {s["source"]: s for s in statuses}
    result = []
    for key, label, mode, note in CATALOG:
        s = latest.get(key)
        state = ("recorded" if counts.get(key) else
                 "needs_adapter" if mode == "pending" else
                 "no_valid_records" if s and s["available"] else
                 "not_found" if s else "import_required" if mode == "import" else "not_scanned")
        result.append({"source": key, "name": label, "mode": mode, "state": state,
                       "records": counts.get(key, 0), "note": note})
    known = {item["source"] for item in result}
    for key in sorted(imported - known):
        result.append({"source": key, "name": CLIENT_NAMES.get(key, key), "mode": "import",
                       "state": "recorded", "records": counts[key], "note": ""})
    for item in result:
        if item["source"] in imported:
            item.update(state="imported_daily", note="经 Tokscale 导入的平台日汇总；非逐请求采集，完整性取决于原导出")
    return result


def doctor(home, codex_root=None, workbuddy_root=None, **overrides):
    roots = source_roots(home, codex_root, workbuddy_root, **overrides)
    sources = []
    for name, root in roots.items():
        paths = data_paths(name, root, home, bool(overrides.get("kimi_root")))
        sources.append({"source": name, "directory_found": any(path.is_dir() for path in paths),
                        "usage_verified": False})
    return {"version": __version__, "python": sys.version.split()[0], "python_executable": sys.executable, "sources": sources,
            "default_report": str(data_directory() / "report" / "report.html"),
            "legacy_history_in_cwd": (Path.cwd() / ".local/report/history.sqlite3").is_file(),
            "commands": ["doctor", "run", "scan", "report", "timeline", "backup", "export", "account"],
            "network_required_for_scan": False, "preflight_only": True, "platforms": coverage_catalog(),
            "note": "Directory presence does not establish valid usage or complete coverage."}
