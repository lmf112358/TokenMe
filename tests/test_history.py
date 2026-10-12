from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from token_footprint.__main__ import main
from token_footprint.history import import_records, merge_history, read_history
from token_footprint.model import UsageError, aggregate, UsageRecord


def record(**changes):
    values = dict(record_id="test-id", source="codex", provider="test", model="test",
                  occurred_at="2026-10-01T00:00:00+08:00", input_tokens=100, output_tokens=20)
    values.update(changes)
    return UsageRecord(**values)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "history.sqlite3"

    def merge(self, rows, offset="+08:00"):
        return merge_history(self.store, rows, offset=offset)

    def cli(self, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return main(list(args))

    def test_rescan_and_missing_logs_preserve_history(self):
        self.merge([record()])
        records, stats = self.merge([record()])
        self.assertEqual(stats["unchanged"], 1)
        self.assertEqual(aggregate(records)["total_tokens"], 120)
        records, stats = self.merge([])
        self.assertEqual(aggregate(records)["total_tokens"], 120)
        self.assertEqual(stats["added"], 0)

    def test_trace_updates_replace_and_stale_snapshot_cannot_regress(self):
        old = record(source="workbuddy", granularity="trace_total")
        new = replace(old, input_tokens=200, occurred_at="2026-10-02T00:00:00+08:00")
        self.merge([old])
        records, stats = self.merge([new])
        self.assertEqual(aggregate(records)["total_tokens"], 220)
        self.assertEqual(stats["updated"], 1)
        records, stats = self.merge([old])
        self.assertEqual(records, [new])
        self.assertEqual(stats["older_ignored"], 1)

    def test_daily_reimport_is_authoritative_correction_not_addition(self):
        original = record(granularity="daily_bucket")
        self.merge([original])
        records, _ = self.merge([replace(original, input_tokens=50)])
        self.assertEqual(aggregate(records)["total_tokens"], 70)

    def test_native_and_daily_conflict_across_scans_rolls_back(self):
        self.merge([record()])
        with self.assertRaises(UsageError):
            self.merge([record(record_id="new", source="qwen"), record(record_id="bucket", granularity="daily_bucket")])
        self.assertEqual(read_history(self.store), [record()])

    def test_conflicting_delta_rolls_back_entire_transaction(self):
        self.merge([record()])
        with self.assertRaises(UsageError):
            self.merge([record(record_id="new"), record(input_tokens=200)])
        self.assertEqual(read_history(self.store), [record()])

    def test_daily_timezone_cannot_change(self):
        self.merge([record(granularity="daily_bucket")])
        with self.assertRaises(UsageError):
            self.merge([], offset="+00:00")
        self.assertEqual(len(read_history(self.store)), 1)

    def test_export_restore_report_round_trip(self):
        self.merge([record(), record(record_id="second", source="workbuddy", granularity="trace_total")])
        export = self.root / "backup.jsonl"
        self.assertEqual(self.cli("export", "--store", str(self.store), "--out", str(export)), 0)
        self.assertEqual(len(import_records(export)), 2)
        out = self.root / "restored"
        self.assertEqual(self.cli("scan", "--sources", "none", "--import-records", str(export), "--out", str(out)), 0)
        rebuilt = self.root / "rebuilt"
        self.assertEqual(self.cli("report", "--store", str(out / "history.sqlite3"), "--out", str(rebuilt), "--month", "2026-09"), 0)
        data = json.loads((rebuilt / "report-data.json").read_text(encoding="utf-8"))
        self.assertEqual(data["views"]["all"]["total_tokens"], 240)
        self.assertEqual(data["views"]["2026-09"]["total_tokens"], 0)
        self.assertEqual(data["source_status"], [])
        self.assertEqual(data["history"]["mode"], "report")
        self.assertFalse((rebuilt / "history.sqlite3").exists())

    def test_invalid_import_is_atomic_and_error_does_not_echo_contents(self):
        self.merge([record()])
        backup = self.root / "bad.jsonl"
        backup.write_text(json.dumps(record(record_id="second").to_dict()) + '\n{"PRIVATE CONTENT":', encoding="utf-8")
        output = io.StringIO()
        with redirect_stderr(output):
            result = main(["scan", "--sources", "none", "--import-records", str(backup), "--store", str(self.store)])
        self.assertEqual(result, 2)
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertEqual(read_history(self.store), [record()])

    def test_bad_month_or_missing_database_does_not_create_history(self):
        out = self.root / "output"
        self.assertEqual(self.cli("scan", "--sources", "none", "--out", str(out), "--month", "2026-13"), 2)
        self.assertFalse(out.exists())
        self.assertEqual(self.cli("report", "--store", str(self.store), "--out", str(out)), 2)
        self.assertFalse(self.store.exists())

    def test_temporary_scan_and_export_cannot_overwrite_database(self):
        out = self.root / "temporary"
        self.assertEqual(self.cli("scan", "--sources", "none", "--no-history", "--out", str(out)), 0)
        self.assertFalse((out / "history.sqlite3").exists())
        self.merge([record()])
        self.assertEqual(self.cli("export", "--store", str(self.store), "--out", str(self.store)), 2)
        self.assertEqual(read_history(self.store), [record()])

    def test_portable_import_whitelists_and_validates_fields(self):
        path = self.root / "records.jsonl"
        path.write_text(json.dumps({**record().to_dict(), "prompt": "PRIVATE CONTENT"}), encoding="utf-8")
        self.assertNotIn("PRIVATE", str(import_records(path)))
        path.write_text(json.dumps({**record().to_dict(), "total_tokens": 999}), encoding="utf-8")
        with self.assertRaises(UsageError):
            import_records(path)

    def test_store_cannot_be_overwritten_by_generated_report(self):
        out = self.root / "out"
        for name in ("report.html", "records.jsonl", "summary.json", "report-data.json"):
            self.assertEqual(self.cli("scan", "--sources", "none", "--out", str(out), "--store", str(out / name)), 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
