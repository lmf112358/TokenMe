from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from token_footprint.__main__ import main
from token_footprint.history import merge_history, read_history, read_timeline, backup_history
from token_footprint.model import UsageRecord, UsageError


def row(**changes):
    values = dict(record_id="one", source="workbuddy", provider="demo", model="demo",
                  occurred_at="2026-10-01T00:00:00+08:00", input_tokens=100, output_tokens=20,
                  granularity="trace_total")
    return UsageRecord(**{**values, **changes})


class V02Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "history.sqlite3"

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(list(args))
        return result, json.loads(stdout.getvalue()), stderr.getvalue()

    def legacy(self):
        with closing(sqlite3.connect(self.store)) as connection, connection:
            connection.execute("CREATE TABLE records (record_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO records VALUES (?, ?)", ("one", json.dumps(row().to_dict())))
            connection.execute("PRAGMA user_version = 1")

    def test_legacy_read_is_readonly_and_first_write_preserves_backup(self):
        self.legacy()
        self.assertEqual(read_timeline(self.store), [])
        self.assertEqual(read_history(self.store), [row()])
        with closing(sqlite3.connect(self.store)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
        _, stats = merge_history(self.store, [row()], offset="+08:00")
        self.assertEqual(stats["net_tokens"], 0)
        backup = self.store.with_name(self.store.name + ".pre-v2.sqlite3")
        self.assertEqual(read_history(backup), [row()])
        self.assertEqual(read_timeline(backup), [])
        self.assertEqual(len(read_timeline(self.store)), 1)
        self.assertIsNone(read_timeline(self.store)[0]["since_previous_tokens"])

    def test_repeated_scan_does_not_duplicate_snapshot(self):
        merge_history(self.store, [row()], offset="+08:00")
        _, stats = merge_history(self.store, [row()], offset="+08:00")
        self.assertFalse(stats["snapshot_created"])
        self.assertEqual(stats["unchanged"], 1)
        self.assertEqual(len(read_timeline(self.store)), 1)

    def test_added_and_negative_correction_are_separate(self):
        original = row(granularity="daily_bucket")
        merge_history(self.store, [original], offset="+08:00")
        new = row(record_id="two", source="qwen", granularity="daily_bucket", input_tokens=10, output_tokens=0)
        _, stats = merge_history(self.store, [replace(original, input_tokens=50), new], offset="+08:00")
        self.assertEqual(stats["added_tokens"], 10)
        self.assertEqual(stats["revised_tokens"], -50)
        self.assertEqual(stats["net_tokens"], -40)
        snapshots = read_timeline(self.store)
        self.assertEqual(snapshots[0]["since_previous_tokens"], -40)
        self.assertEqual(snapshots[1]["summary"]["total_tokens"], 120)

    def test_conflict_rolls_back_records_and_snapshots(self):
        merge_history(self.store, [row()], offset="+08:00")
        before = read_timeline(self.store)
        with self.assertRaises(UsageError):
            merge_history(self.store, [row(record_id="two"), row(record_id="bucket", granularity="daily_bucket")], offset="+08:00")
        self.assertEqual(read_timeline(self.store), before)
        self.assertEqual(read_history(self.store), [row()])

    def test_full_backup_preserves_timeline_and_refuses_overwrite(self):
        merge_history(self.store, [row()], offset="+08:00")
        target = self.root / "backup.sqlite3"
        backup_history(self.store, target)
        self.assertEqual(read_timeline(target), read_timeline(self.store))
        with self.assertRaises(UsageError):
            backup_history(self.store, target)

    def test_json_success_and_failure_contract(self):
        code, result, stderr = self.cli("doctor", "--home", str(self.root), "--json")
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["preflight_only"])
        self.assertEqual(result["schema_version"], "0.2")
        self.assertEqual(stderr, "")
        code, result, stderr = self.cli("report", "--store", str(self.store), "--json")
        self.assertEqual(code, 2)
        self.assertFalse(result["ok"])
        self.assertEqual(stderr, "")
        self.assertFalse(self.store.exists())

    def test_argument_errors_use_json_and_exit_nonzero(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as error:
            main(["unknown-command", "--json"])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], "invalid_arguments")

    def test_run_uses_stable_directory_across_working_directories(self):
        home = self.root / "data"
        with patch.dict(os.environ, {"TOKENME_HOME": str(home)}):
            code, result, _ = self.cli("run", "--sources", "none", "--json")
            self.assertEqual(code, 0)
            self.assertEqual(result["data"]["store"], str((home / "report/history.sqlite3").resolve()))
            self.assertEqual(result["command"], "run")
            with patch("pathlib.Path.cwd", return_value=self.root / "another-project"):
                _, other, _ = self.cli("run", "--sources", "none", "--json")
            self.assertEqual(other["data"]["store"], result["data"]["store"])
            self.assertFalse(other["data"]["history"]["snapshot_created"])

    def test_report_rebuild_never_creates_snapshot(self):
        merge_history(self.store, [row()], offset="+08:00")
        before = read_timeline(self.store)
        code, _, _ = self.cli("report", "--store", str(self.store), "--out", str(self.root / "report"), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(read_timeline(self.store), before)
        data = json.loads((self.root / "report/report-data.json").read_text(encoding="utf-8"))
        self.assertEqual(data["snapshots"], before)


if __name__ == "__main__":
    unittest.main()
