from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import replace
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from token_footprint.agents import claude_scan, pi_scan, gemini_scan, opencode_scan, qwen_scan, kimi_scan
from token_footprint.usage_imports import import_cursor, import_trae
from token_footprint.discovery import doctor, NATIVE_SOURCES, source_roots
from token_footprint.history import merge_history, read_timeline
from token_footprint.model import UsageError
from token_footprint.__main__ import main

AT = "2026-10-01T00:00:00Z"
PRIVATE = "PRIVATE-PROMPT-AND-CREDENTIAL-MUST-NOT-LEAVE"


def claude(mid="response", output=10, at=AT):
    return {"type": "assistant", "uuid": "stream-event", "timestamp": at,
            "message": {"id": mid, "model": "fixture", "content": PRIVATE,
                        "usage": {"input_tokens": 20, "output_tokens": output,
                                  "cache_read_input_tokens": 70, "cache_creation_input_tokens": 10}}}


def pi(key="one", role="assistant"):
    return {"type": "message", "id": key, "timestamp": AT, "message": {"role": role, "content": PRIVATE,
        "provider": "fixture", "model": "fixture", "usage": {"input": 20, "output": 10, "cacheRead": 70,
        "cacheWrite": 10, "cacheWrite1h": 5, "reasoning": 4, "totalTokens": 110}}}


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, relative, value, lines=False):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(x) for x in value) if lines else json.dumps(value), encoding="utf-8")
        return path

    def test_claude_stream_fork_subagent_and_privacy(self):
        rows = [claude(), claude(output=20, at="2026-10-01T00:00:01Z")]
        self.write("projects/main.jsonl", rows, True)
        self.write("projects/subagents/fork.jsonl", rows + [claude("subagent")], True)
        result = claude_scan(self.root)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(sum(r.total_tokens for r in result.records), 230)
        self.assertNotIn(PRIVATE, json.dumps([r.to_dict() for r in result.records]))
        self.assertEqual(result.diagnostics["duplicate_observations"], 3)

    def test_claude_missing_cache_is_unknown_not_zero(self):
        row = claude()
        del row["message"]["usage"]["cache_read_input_tokens"]
        self.write("projects/one.jsonl", [row], True)
        result = claude_scan(self.root)
        self.assertEqual(result.records, [])
        self.assertEqual(result.diagnostics["invalid_usage_records"], 1)

    def test_conflicting_replay_fails_instead_of_selecting_arbitrary_total(self):
        self.write("projects/one.jsonl", [claude(), claude(output=99)], True)
        with self.assertRaises(UsageError):
            claude_scan(self.root)

    def test_pi_nested_work_summary_and_replay(self):
        summary = {"type": "compaction", "id": "summary", "timestamp": AT, "usage": pi()["message"]["usage"],
                   "tokensBefore": 9999999, "summary": PRIVATE}
        rows = [pi(), pi("tool", "toolResult"), summary, pi("user", "user")]
        self.write("one.jsonl", rows, True)
        self.write("fork.jsonl", rows, True)
        result = pi_scan(self.root)
        self.assertEqual(len(result.records), 3)
        self.assertEqual(sum(r.total_tokens for r in result.records), 330)
        self.assertTrue(all(r.reasoning_output_tokens == 4 for r in result.records))

    def test_pi_response_id_deduplicates_rekeyed_fork(self):
        first, second = pi(), pi("other")
        first["message"]["responseId"] = second["message"]["responseId"] = "response-1"
        self.write("one.jsonl", [first, second], True)
        self.assertEqual(len(pi_scan(self.root).records), 1)

    def test_pi_zero_and_malformed_rows_do_not_create_active_days(self):
        row = pi()
        row["message"]["usage"] = dict(input=0, output=0, cacheRead=0, cacheWrite=0, totalTokens=0)
        path = self.write("one.jsonl", [row], True)
        with path.open("a", encoding="utf-8") as f:
            f.write('\n{"truncated":')
        result = pi_scan(self.root)
        self.assertFalse(result.records)
        self.assertEqual(result.diagnostics["malformed_json_lines"], 1)
        self.assertEqual(result.diagnostics["zero_usage_records"], 1)

    def test_gemini_reasoning_and_cache_are_normalized(self):
        msg = {"id": "m", "type": "gemini", "timestamp": AT, "model": "fixture",
               "tokens": dict(input=100, output=10, thoughts=5, cached=70, total=115, tool=0)}
        self.write("proj/chats/session.json", {"sessionId": "s", "messages": [msg]})
        result = gemini_scan(self.root)
        self.assertEqual(result.records[0].total_tokens, 115)
        self.assertEqual(result.records[0].output_tokens, 15)
        self.assertEqual(result.records[0].cached_input_tokens, 70)

    def test_gemini_jsonl_rewind_keeps_spent_usage_and_deduplicates_json(self):
        msg = {"id": "m", "type": "gemini", "timestamp": AT,
               "tokens": dict(input=100, output=10, thoughts=5, cached=70, total=115)}
        self.write("proj/chats/a.json", {"sessionId": "s", "messages": [msg]})
        self.write("proj/chats/a.jsonl", [{"sessionId": "s", "projectHash": "hash"}, msg, msg, {"$rewindTo": "m"}], True)
        self.assertEqual(len(gemini_scan(self.root).records), 1)

    def test_gemini_unknown_tool_accounting_is_diagnosed(self):
        self.write("proj/chats/session.json", {"sessionId": "s", "messages": [
            {"id": "m", "type": "gemini", "timestamp": AT, "tokens": dict(input=100, output=10, thoughts=0, total=112, tool=2)}]})
        result = gemini_scan(self.root)
        self.assertFalse(result.records)
        self.assertEqual(result.diagnostics["unsupported_tool_token_accounting"], 1)

    def test_opencode_sqlite_and_json_same_message_once(self):
        msg = {"id": "m", "role": "assistant", "modelID": "fixture", "providerID": "fixture",
               "time": {"created": 1790812800000, "completed": 1790812801000},
               "tokens": {"input": 20, "output": 10, "reasoning": 5, "cache": {"read": 70, "write": 10}, "total": 115}}
        self.write("storage/message/s/m.json", msg)
        with closing(sqlite3.connect(self.root / "opencode.db")) as db, db:
            db.execute("CREATE TABLE message (id TEXT, data TEXT)")
            db.execute("INSERT INTO message VALUES (?, ?)", ("m", json.dumps(msg)))
        result = opencode_scan(self.root)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].total_tokens, 115)
        self.assertEqual(result.records[0].output_tokens, 15)

    def test_qwen_usage_not_context_window_and_fork_identity(self):
        row = {"type": "assistant", "sessionId": "s", "uuid": "m", "timestamp": AT, "model": "fixture",
               "contextWindowSize": 1000000, "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 10,
               "thoughtsTokenCount": 5, "cachedContentTokenCount": 70, "totalTokenCount": 115}}
        self.write("proj/chats/one.jsonl", [row], True)
        row["sessionId"] = "fork"
        self.write("proj/chats/fork.jsonl", [row], True)
        result = qwen_scan(self.root)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].total_tokens, 115)

    def test_kimi_both_wire_schemas_and_scope_guard(self):
        old = {"timestamp": 1790812800.5, "message": {"type": "StatusUpdate", "payload": {"message_id": "old",
               "token_usage": {"input_other": 20, "output": 10, "input_cache_read": 70, "input_cache_creation": 10}}}}
        new = {"type": "usage.record", "usageScope": "turn", "time": 1790812801500, "model": "fixture",
               "usage": {"inputOther": 20, "output": 10, "inputCacheRead": 70, "inputCacheCreation": 10}}
        cumulative = {**new, "usageScope": "session"}
        self.write("session/wire.jsonl", [old, old, new, cumulative], True)
        result = kimi_scan([self.root, self.root])
        self.assertEqual(len(result.records), 2)
        self.assertEqual(sum(r.total_tokens for r in result.records), 220)
        self.assertEqual(result.diagnostics["unsupported_usage_scope"], 1)

    def cursor(self, rows=None, extra=None):
        row = {"Date": AT, "Model": "fixture", "Input (w/ Cache Write)": "10", "Input (w/o Cache Write)": "20",
               "Cache Read": "70", "Output Tokens": "10", "Total Tokens": "110", "Cost": "$99"}
        row.update(extra or {})
        path = self.root / "cursor.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            writer.writeheader()
            writer.writerows(rows or [row])
        return path

    def test_cursor_column_order_optional_columns_and_thousands(self):
        result = import_cursor(self.cursor(extra={"Cloud Agent ID": "agent", "Kind": "Included",
                                                "Input (w/o Cache Write)": "1,020", "Total Tokens": "1,110"}))
        self.assertEqual(result.records[0].total_tokens, 1110)
        self.assertEqual(result.records[0].cache_write_input_tokens, 10)
        self.assertEqual(result.coverage, "provided_usage_export_only")

    def test_cursor_reimport_idempotent_and_correction_conflict(self):
        store = self.root / "history.sqlite3"
        records = import_cursor(self.cursor()).records
        merge_history(store, records, offset="+08:00")
        _, stats = merge_history(store, import_cursor(self.cursor()).records, offset="+08:00")
        self.assertFalse(stats["snapshot_created"])
        with self.assertRaises(UsageError):
            merge_history(store, import_cursor(self.cursor(extra={"Output Tokens": "11", "Total Tokens": "111"})).records, offset="+08:00")
        self.assertEqual(len(read_timeline(store)), 1)

    def test_cursor_rejects_ambiguous_date_rounded_totals_and_duplicate_events(self):
        for change in ({"Date": "2026-10-01 00:00:00"}, {"Total Tokens": "111"}, {"Total Tokens": "1.1K"}):
            with self.subTest(change=change), self.assertRaises(UsageError):
                import_cursor(self.cursor(extra=change))
        path = self.cursor()
        with path.open("a", encoding="utf-8") as f:
            f.write(path.read_text(encoding="utf-8-sig").splitlines()[1] + "\n")
        with self.assertRaises(UsageError):
            import_cursor(path)

    def test_trae_exact_usage_only_never_credits(self):
        row = {"session_id": "s", "usage_time": 1790812800, "model_name": "fixture", "dollar_float": 99,
               "extra_info": {"input_token": 20, "output_token": 10, "cache_read_token": 70, "cache_write_token": 10}}
        result = import_trae(self.write("trae.json", [row, row]))
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].total_tokens, 110)
        del row["extra_info"]["input_token"]
        with self.assertRaises(UsageError):
            import_trae(self.write("trae.json", [row]))
        with self.assertRaises(UsageError):
            import_trae(self.write("qoder.json", {"usages": [{"credits": 100}]}))

    def test_doctor_overrides_do_not_read_logs_and_sandbox_does_not_use_real_home(self):
        root = self.root / "custom"
        self.write("custom/projects/invalid.jsonl", ["broken"], True)
        with patch("pathlib.Path.open", side_effect=AssertionError("doctor must not read logs")):
            data = doctor(self.root, claude_root=root)
        self.assertTrue(next(s for s in data["sources"] if s["source"] == "claude")["directory_found"])
        self.assertEqual(len(data["sources"]), 8)
        with patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": "/unrelated-home"}):
            self.assertEqual(source_roots(self.root)["claude"], self.root / ".claude")

    def test_default_scan_integrates_new_sources_and_truthful_coverage(self):
        self.write(".claude/projects/s.jsonl", [claude()], True)
        self.write(".pi/agent/sessions/s.jsonl", [pi()], True)
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            code = main(["run", "--home", str(self.root), "--out", str(self.root / "report"), "--json"])
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["data"]["local_recorded_tokens"], 220)
        report = json.loads((self.root / "report/report-data.json").read_text(encoding="utf-8"))
        states = {s["source"]: s["state"] for s in report["platforms"]}
        self.assertEqual(states["claude"], "recorded")
        self.assertEqual(states["cursor"], "import_required")
        self.assertEqual(states["doubao"], "needs_adapter")
        self.assertEqual({s["source"] for s in report["source_status"]}, set(NATIVE_SOURCES))
        self.assertNotIn(PRIVATE, (self.root / "report/report.html").read_text(encoding="utf-8"))

    def test_bad_import_stops_before_history_write(self):
        path = self.cursor(extra={"Total Tokens": "111"})
        with redirect_stdout(io.StringIO()):
            code = main(["run", "--sources", "none", "--cursor-csv", str(path), "--out", str(self.root / "report"), "--json"])
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "report/history.sqlite3").exists())

    def test_daily_alias_cannot_double_count_native_records_in_existing_history(self):
        self.write("projects/a.jsonl", [claude()], True)
        native = claude_scan(self.root).records[0]
        daily = replace(native, source="claude-code", record_id="imported", granularity="daily_bucket",
                        occurred_at="2026-10-01T00:00:00+08:00")
        store = self.root / "history.sqlite3"
        merge_history(store, [daily], offset="+08:00")
        with self.assertRaises(UsageError):
            merge_history(store, [native], offset="+08:00")


if __name__ == "__main__":
    unittest.main()
