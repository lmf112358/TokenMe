from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import sqlite3
import webbrowser

from .account import read_account_usage, sanitize_account_usage
from .adapters import codex_scan, workbuddy_scan
from .agents import claude_scan, pi_scan, gemini_scan, opencode_scan, qwen_scan, kimi_scan
from .usage_imports import import_cursor, import_trae
from .ccusage import import_ccusage
from .tokscale import import_tokscale, client_id
from .model import UsageError, aggregate, utc_offset, source_family, validate_source_scopes
from .history import import_records, merge_history, read_history, read_timeline, backup_history
from .discovery import data_directory, doctor, source_roots, data_paths, coverage_catalog, NATIVE_SOURCES
from . import __version__


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    class CLIParser(argparse.ArgumentParser):
        def error(self, message):
            if "--json" in argv:
                print(json.dumps({"schema_version": "0.2", "ok": False, "error": {"code": "invalid_arguments", "message": "Invalid arguments; consult --help."}}))
                raise SystemExit(2)
            super().error(message)
    parser = CLIParser(description="TokenMe · 本地 AI 协作档案")
    parser.add_argument("--version", action="version", version="TokenMe " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", aliases=["run"], help="采集并生成报告；run 使用固定用户数据目录")
    scan.add_argument("--home", type=Path, default=Path.home(), help="用户目录；可用沙箱样本目录")
    scan.add_argument("--codex-root", type=Path, help="Codex 数据目录（内含 sessions）")
    scan.add_argument("--workbuddy-root", type=Path, help="WorkBuddy 数据目录（内含 traces）")
    scan.add_argument("--sources", default="all", help="all、none，或逗号分隔的 " + ",".join(NATIVE_SOURCES))
    for source in NATIVE_SOURCES[2:]:
        scan.add_argument("--" + source + "-root", type=Path, help="指定客户端数据根目录")
    scan.add_argument("--offset", default="+08:00", help="本地日志日界线 UTC 偏移，默认 +08:00")
    scan.add_argument("--month", help="主视图月份 YYYY-MM，省略则全部本地历史")
    scan.add_argument("--out", type=Path)
    scan.add_argument("--account-file", type=Path, help="导入 account/usage/read 的本地结果；仅保留白名单字段")
    scan.add_argument("--ccusage", type=Path, help="导入已有 ccusage daily --by-agent --json 文件")
    scan.add_argument("--cursor-csv", type=Path, action="append", default=[], help="导入 Cursor Token CSV；可重复指定")
    scan.add_argument("--trae-json", type=Path, action="append", default=[], help="导入 TRAE 国际版会话用量数组；可重复指定")
    scan.add_argument("--tokscale", type=Path, action="append", default=[], help="导入 Tokscale 4.x graph --output JSON；可重复指定")
    scan.add_argument("--tokscale-offset", help="必须显式声明 Tokscale 导出日界线，如 +08:00；须与 --offset 一致")
    scan.add_argument("--tokscale-clients", help="仅导入指定 client ID，逗号分隔；省略则导入文件中全部来源")
    scan.add_argument("--store", type=Path, help="历史库；默认输出目录下 history.sqlite3")
    scan.add_argument("--no-history", action="store_true", help="仅本次扫描，不读写历史库")
    scan.add_argument("--import-records", type=Path, help="恢复 TokenMe 导出的 records.jsonl")
    scan.add_argument("--open", action="store_true", help="完成后用默认浏览器打开报告")
    report = sub.add_parser("report", help="仅用已保存历史重建离线报告")
    report.add_argument("--store", type=Path, default=Path(".local/report/history.sqlite3"))
    report.add_argument("--out", type=Path, default=Path(".local/report"))
    report.add_argument("--offset", default="+08:00")
    report.add_argument("--month")
    report.add_argument("--account-file", type=Path)
    report.add_argument("--open", action="store_true")
    export = sub.add_parser("export", help="导出可迁移的白名单历史 JSONL")
    export.add_argument("--store", type=Path, default=Path(".local/report/history.sqlite3"))
    export.add_argument("--out", type=Path, required=True)
    account = sub.add_parser("account", help="通过已登录的 Codex 客户端查询官方账号活动（联网）")
    account.add_argument("--codex-bin", required=True, help="已安装 codex 可执行文件路径；不接受 shell 脚本")
    account.add_argument("--out", type=Path, default=Path(".local/account-usage.json"))
    check = sub.add_parser("doctor", help="检查运行环境和支持的来源目录，不读取日志正文")
    check.add_argument("--home", type=Path, default=Path.home())
    check.add_argument("--codex-root", type=Path)
    check.add_argument("--workbuddy-root", type=Path)
    for source in NATIVE_SOURCES[2:]:
        check.add_argument("--" + source + "-root", type=Path)
    timeline = sub.add_parser("timeline", help="读取最近 50 个有变化的历史快照")
    timeline.add_argument("--store", type=Path, default=data_directory() / "report/history.sqlite3")
    backup = sub.add_parser("backup", help="备份完整历史库和快照，不覆盖已有文件")
    backup.add_argument("--store", type=Path, default=data_directory() / "report/history.sqlite3")
    backup.add_argument("--out", type=Path, required=True)
    for command in (scan, report, export, account, check, timeline, backup):
        command.add_argument("--json", action="store_true", help="返回稳定 JSON 协议，含 ok、schema_version 和 data/error")
    args = parser.parse_args(argv)
    operation = args.command
    if operation in ("scan", "run"):
        args.out = args.out or (data_directory() / "report" if operation == "run" else Path(".local/report"))
        args.command = "scan"
    def reply(value):
        output = {"schema_version": "0.2", "ok": True, "command": operation, "data": value} if args.json else value
        print(json.dumps(output, ensure_ascii=False))
    try:
        if args.command == "doctor":
            reply(doctor(args.home, args.codex_root, args.workbuddy_root,
                         **{s + "_root": getattr(args, s + "_root") for s in NATIVE_SOURCES[2:]}))
            return 0
        if args.command == "timeline":
            reply({"snapshots": read_timeline(args.store)})
            return 0
        if args.command == "backup":
            backup_history(args.store, args.out)
            reply({"backup": str(args.out.resolve())})
            return 0
        if args.command == "account":
            if Path(args.codex_bin).suffix.lower() in (".ps1", ".cmd", ".bat", ".sh"):
                raise UsageError("pass the native codex executable, not a shell wrapper")
            data = read_account_usage(args.codex_bin)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            save_json(args.out, data)
            reply({"saved": str(args.out), "summary": data["summary"],
                   "daily_buckets": len(data["dailyUsageBuckets"] or [])})
            return 0
        if args.command == "export":
            records = read_history(args.store)
            if args.out.resolve() == args.store.resolve():
                raise UsageError("export output must not overwrite the history database")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("w", encoding="utf-8") as stream:
                for record in records:
                    stream.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            reply({"exported_records": len(records), "file": str(args.out)})
            return 0
        utc_offset(args.offset)
        aggregate([], offset=args.offset, month=args.month)  # Validate before writing history.
        store = args.store if args.command == "report" else (args.store or args.out / "history.sqlite3")
        if store.resolve() in {(args.out / name).resolve() for name in ("report.html", "report-data.json", "summary.json", "records.jsonl")}:
            raise UsageError("history database must not overlap report output files")
        sources = {s.strip() for s in args.sources.split(",")} if args.command == "scan" else {"none"}
        if sources == {"all"}:
            sources = set(NATIVE_SOURCES)
        if not sources <= {*NATIVE_SOURCES, "none"} or ("none" in sources and len(sources) > 1):
            raise UsageError("sources must be all, none or supported native source names; use import flags for Cursor/TRAE")
        results = []
        roots = source_roots(args.home, args.codex_root, args.workbuddy_root,
                             **{s + "_root": getattr(args, s + "_root") for s in NATIVE_SOURCES[2:]}) if args.command == "scan" else {}
        if "codex" in sources:
            root = roots["codex"]
            results.append(codex_scan([root / "sessions", root / "archived_sessions"]))
        if "workbuddy" in sources:
            root = roots["workbuddy"]
            results.append(workbuddy_scan(root / "traces"))
        readers = {"claude": claude_scan, "pi": pi_scan, "gemini": gemini_scan, "opencode": opencode_scan, "qwen": qwen_scan}
        for source, reader in readers.items():
            if source in sources:
                root = roots[source]
                location = root if source in ("claude", "opencode") else data_paths(source, root, args.home)[0]
                results.append(reader(location))
        if "kimi" in sources:
            results.append(kimi_scan(data_paths("kimi", roots["kimi"], args.home, bool(args.kimi_root))))
        if args.command == "scan":
            if args.tokscale:
                if args.tokscale_offset is None or args.tokscale_offset != args.offset:
                    raise UsageError("Tokscale requires explicit --tokscale-offset matching --offset and the export's day boundary")
                selected_clients = [client_id(c.strip()) for c in args.tokscale_clients.split(",")] if args.tokscale_clients else None
                results.extend(import_tokscale(path, args.tokscale_offset, selected_clients) for path in args.tokscale)
            elif args.tokscale_offset is not None or args.tokscale_clients is not None:
                raise UsageError("--tokscale-offset / --tokscale-clients requires --tokscale")
            for paths, reader in ((args.cursor_csv, import_cursor), (args.trae_json, import_trae)):
                results.extend(reader(path) for path in paths)
        if args.command == "scan" and args.ccusage:
            imported = import_ccusage(args.ccusage, args.offset)
            overlapping = {source_family(r.source) for r in imported.records} & {source_family(r.source) for s in results for r in s.records}
            if overlapping:
                raise UsageError("ccusage overlaps collected/imported sources: " + ", ".join(sorted(overlapping)) + "; filter those sources")
            results.append(imported)
        records = [record for result in results for record in result.records]
        account_data = None
        if args.account_file:
            raw = json.loads(args.account_file.read_text(encoding="utf-8-sig"))
            account_data = sanitize_account_usage(raw)
            # Keep the real fetch timestamp, not the report rebuild time, when present.
            if raw.get("observed_at"):
                from .model import timestamp
                timestamp(raw["observed_at"])
                account_data["observed_at"] = raw["observed_at"]
        history = {"enabled": True, "mode": args.command}
        if args.command == "report":
            records = read_history(args.store)
            if any(r.granularity == "daily_bucket" and not r.occurred_at.endswith(args.offset) for r in records):
                raise UsageError("daily-import history requires its original --offset")
            history["records"] = len(records)
        else:
            if args.no_history and args.store:
                raise UsageError("--store cannot be combined with --no-history")
            if args.import_records:
                records.extend(import_records(args.import_records))
            if args.no_history:
                if any(r.granularity == "daily_bucket" and not r.occurred_at.endswith(args.offset) for r in records):
                    raise UsageError("daily bucket timestamp must match --offset")
                validate_source_scopes(records)
                aggregate(records)
                records = list({r.record_id: r for r in records}.values())
                history.update(enabled=False, records=len(records))
            else:
                records, stats = merge_history(store, records, offset=args.offset, source_status=[r.status() for r in results])
                history.update(stats)
        selected = aggregate(records, offset=args.offset, month=args.month)
        # Every month is generated from event timestamps, not by redistributing account buckets.
        all_local = aggregate(records, offset=args.offset)
        months = sorted({row["date"][:7] for row in all_local["daily"]})
        views = {"all": all_local, **{month: aggregate(records, offset=args.offset, month=month) for month in months}}
        if args.month and args.month not in views:
            views[args.month] = selected
        share = json.loads((Path(__file__).parent / "share-qr.json").read_text(encoding="utf-8"))
        snapshots = read_timeline(store) if history["enabled"] else []
        bundle = {"project": "TokenMe", "version": __version__,
                  "generated_at": datetime.now(timezone.utc).isoformat(),
                  "default_view": args.month or "all", "views": views,
                  "source_status": [r.status() for r in results], "account": account_data,
                  "history": history, "share": share, "snapshots": snapshots,
                  "platforms": coverage_catalog(records, [r.status() for r in results]),
                  "unconnected": ["Kimi 网页 / App", "千问网页 / App", "DeepSeek 网页 / App", "ChatGPT 常规聊天全量范围待确认"]}
        args.out.mkdir(parents=True, exist_ok=True)
        save_json(args.out / "summary.json", selected)
        save_json(args.out / "report-data.json", bundle)
        with (args.out / "records.jsonl").open("w", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        template = (Path(__file__).parent / "report.html").read_text(encoding="utf-8")
        card_script = (Path(__file__).parent / "share-card.js").read_text(encoding="utf-8")
        template = template.replace("__SHARE_CARD_SCRIPT__", card_script)
        cyber_script = (Path(__file__).parent / "share-cyber.js").read_text(encoding="utf-8")
        template = template.replace("__CYBER_CARD_SCRIPT__", cyber_script)
        safe = json.dumps(bundle, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (args.out / "report.html").write_text(template.replace("__REPORT_DATA__", safe), encoding="utf-8")
        reply({"report": str((args.out / "report.html").resolve()), "period": selected["period"],
                          "python": sys.executable,
                          "store": str(store.resolve()) if history["enabled"] else None,
                          "local_recorded_tokens": selected["total_tokens"],
                          "sources": selected["sources"], "source_status": bundle["source_status"], "history": history})
        if args.open:
            webbrowser.open((args.out / "report.html").resolve().as_uri())
        return 0
    except (UsageError, ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        # Expected errors never include raw message bodies or credentials.
        message = str(exc) if isinstance(exc, (UsageError, OSError, sqlite3.Error)) else "invalid input data"
        if args.json:
            print(json.dumps({"schema_version": "0.2", "ok": False, "command": operation,
                              "error": {"code": "operation_failed", "message": message}}, ensure_ascii=False))
        else:
            print("TokenMe: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
