from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import sqlite3
import webbrowser

from .account import read_account_usage, sanitize_account_usage
from .adapters import codex_scan, workbuddy_scan
from .ccusage import import_ccusage
from .model import UsageError, aggregate, utc_offset
from .history import import_records, merge_history, read_history


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="TokenMe · 本地 AI 用量档案")
    parser.add_argument("--version", action="version", version="TokenMe 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="读取指定来源并生成本地报告，不上传")
    scan.add_argument("--home", type=Path, default=Path.home(), help="用户目录；可用沙箱样本目录")
    scan.add_argument("--codex-root", type=Path, help="Codex 数据目录（内含 sessions）")
    scan.add_argument("--workbuddy-root", type=Path, help="WorkBuddy 数据目录（内含 traces）")
    scan.add_argument("--sources", default="codex,workbuddy", help="codex,workbuddy 或 none")
    scan.add_argument("--offset", default="+08:00", help="本地日志日界线 UTC 偏移，默认 +08:00")
    scan.add_argument("--month", help="主视图月份 YYYY-MM，省略则全部本地历史")
    scan.add_argument("--out", type=Path, default=Path(".local/report"))
    scan.add_argument("--account-file", type=Path, help="导入 account/usage/read 的本地结果；仅保留白名单字段")
    scan.add_argument("--ccusage", type=Path, help="导入已有 ccusage daily --by-agent --json 文件")
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
    args = parser.parse_args(argv)
    try:
        if args.command == "account":
            if Path(args.codex_bin).suffix.lower() in (".ps1", ".cmd", ".bat", ".sh"):
                raise UsageError("pass the native codex executable, not a shell wrapper")
            data = read_account_usage(args.codex_bin)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            save_json(args.out, data)
            print(json.dumps({"saved": str(args.out), "summary": data["summary"],
                              "daily_buckets": len(data["dailyUsageBuckets"] or [])}, ensure_ascii=False))
            return 0
        if args.command == "export":
            records = read_history(args.store)
            if args.out.resolve() == args.store.resolve():
                raise UsageError("export output must not overwrite the history database")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("w", encoding="utf-8") as stream:
                for record in records:
                    stream.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            print(json.dumps({"exported_records": len(records), "file": str(args.out)}, ensure_ascii=False))
            return 0
        utc_offset(args.offset)
        aggregate([], offset=args.offset, month=args.month)  # Validate before writing history.
        store = args.store if args.command == "report" else (args.store or args.out / "history.sqlite3")
        if store.resolve() in {(args.out / name).resolve() for name in ("report.html", "report-data.json", "summary.json", "records.jsonl")}:
            raise UsageError("history database must not overlap report output files")
        sources = {s.strip() for s in args.sources.split(",")} if args.command == "scan" else {"none"}
        if not sources <= {"codex", "workbuddy", "none"} or ("none" in sources and len(sources) > 1):
            raise UsageError("sources must be codex,workbuddy or none")
        results = []
        if "codex" in sources:
            default_root = Path(os.environ.get("CODEX_HOME") or args.home / ".codex") if args.home == Path.home() else args.home / ".codex"
            root = args.codex_root or default_root
            results.append(codex_scan([root / "sessions", root / "archived_sessions"]))
        if "workbuddy" in sources:
            root = args.workbuddy_root or args.home / ".workbuddy"
            results.append(workbuddy_scan(root / "traces"))
        if args.command == "scan" and args.ccusage:
            imported = import_ccusage(args.ccusage, args.offset)
            overlapping = {r.source for r in imported.records} & {r.source for s in results for r in s.records}
            if overlapping:
                raise UsageError("ccusage overlaps native sources: " + ", ".join(sorted(overlapping)) + "; exclude those native sources")
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
                raise UsageError("ccusage history requires its original --offset")
            history["records"] = len(records)
        else:
            if args.no_history and args.store:
                raise UsageError("--store cannot be combined with --no-history")
            if args.import_records:
                records.extend(import_records(args.import_records))
            if args.no_history:
                if any(r.granularity == "daily_bucket" and not r.occurred_at.endswith(args.offset) for r in records):
                    raise UsageError("daily bucket timestamp must match --offset")
                # Still enforce overlapping native/daily scope without persisting a database.
                for source in {r.source for r in records}:
                    if len({r.granularity == "daily_bucket" for r in records if r.source == source}) > 1:
                        raise UsageError("import overlaps native sources")
                aggregate(records)
                records = list({r.record_id: r for r in records}.values())
                history.update(enabled=False, records=len(records))
            else:
                records, stats = merge_history(args.store or args.out / "history.sqlite3", records, offset=args.offset)
                history.update(stats)
        selected = aggregate(records, offset=args.offset, month=args.month)
        # Every month is generated from event timestamps, not by redistributing account buckets.
        all_local = aggregate(records, offset=args.offset)
        months = sorted({row["date"][:7] for row in all_local["daily"]})
        views = {"all": all_local, **{month: aggregate(records, offset=args.offset, month=month) for month in months}}
        if args.month and args.month not in views:
            views[args.month] = selected
        share = json.loads((Path(__file__).parent / "share-qr.json").read_text(encoding="utf-8"))
        bundle = {"project": "TokenMe", "version": "0.1.0",
                  "generated_at": datetime.now(timezone.utc).isoformat(),
                  "default_view": args.month or "all", "views": views,
                  "source_status": [r.status() for r in results], "account": account_data,
                  "history": history, "share": share,
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
        safe = json.dumps(bundle, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (args.out / "report.html").write_text(template.replace("__REPORT_DATA__", safe), encoding="utf-8")
        print(json.dumps({"report": str(args.out / "report.html"), "period": selected["period"],
                          "local_recorded_tokens": selected["total_tokens"],
                          "sources": selected["sources"], "source_status": bundle["source_status"], "history": history}, ensure_ascii=False))
        if args.open:
            webbrowser.open((args.out / "report.html").resolve().as_uri())
        return 0
    except (UsageError, ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        # Expected errors never include raw message bodies or credentials.
        print("TokenMe: " + (str(exc) if isinstance(exc, (UsageError, OSError, sqlite3.Error)) else "invalid input data"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
