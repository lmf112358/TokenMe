from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from token_footprint.__main__ import main
from token_footprint.discovery import coverage_catalog
from token_footprint.history import merge_history, read_history, read_timeline, import_records
from token_footprint.model import UsageError, aggregate
from token_footprint.tokscale import import_tokscale, CLIENT_NAMES

PRIVATE = "PRIVATE-PROMPT-DEVICE-AND-MCP-NOT-FOR-EXPORT"
FIELDS = ("input", "output", "cacheRead", "cacheWrite", "reasoning")


def client(name="openclaw", model="fixture", multiplier=1):
    return {"client": name, "modelId": model, "providerId": "fixture",
            "tokens": {key: n * multiplier for key, n in zip(FIELDS, [20, 10, 70, 5, 4])},
            "cost": 888, "messages": 1}


def graph(entries=None, day="2026-10-01"):
    entries = entries if entries is not None else [client(), client("cline")]
    buckets = {key: sum(row["tokens"][key] for row in entries) for key in FIELDS}
    total = sum(buckets.values())
    return {"meta": {"version": "4.18.0", "generatedAt": "2026-10-14T00:00:00Z",
                     "dateRange": {"start": day, "end": day}},
            "summary": {"totalTokens": total}, "years": [{"totalTokens": total}],
            "contributions": [{"date": day, "totals": {"tokens": total, "cost": 1776},
                               "tokenBreakdown": buckets, "clients": entries}],
            "device": {"name": PRIVATE}, "mcpServers": [PRIVATE], "prompt": PRIVATE}


class TokscaleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "usage.json"

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")
        return self.path

    def read(self, data=None, clients=None, offset="+08:00"):
        return import_tokscale(self.write(graph() if data is None else data), offset, clients)

    def cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([*args, "--json"])
        return code, json.loads(output.getvalue())

    def test_five_disjoint_buckets_and_no_summary_double_count(self):
        result = self.read(graph([client()]))
        record = result.records[0]
        self.assertEqual((record.input_tokens, record.output_tokens, record.total_tokens), (95, 14, 109))
        self.assertEqual(record.reasoning_output_tokens, 4)
        self.assertEqual(record.granularity, "daily_bucket")
        self.assertTrue(record.occurred_at.endswith("+08:00"))
        self.assertNotIn(PRIVATE, json.dumps(record.to_dict()))
        self.assertEqual(record.model, "mixed/unknown")

    def test_models_and_providers_roll_into_one_day_and_filter_after_validation(self):
        entries = [client(), client(model="other"), client("cline")]
        entries[1]["providerId"] = "other-provider"
        result = self.read(graph(entries), clients=["openclaw"])
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].total_tokens, 218)
        self.assertEqual(result.diagnostics["filtered_client_days"], 1)

    def test_all_reviewed_client_ids_are_importable_not_native_claims(self):
        entries = [client(name) for name in CLIENT_NAMES]
        result = self.read(graph(entries))
        self.assertEqual(len(result.records), len(CLIENT_NAMES))
        platforms = {p["source"]: p for p in coverage_catalog(result.records)}
        self.assertEqual(platforms["openclaw"]["name"], "OpenClaw")
        self.assertEqual(platforms["codex"]["state"], "imported_daily")
        self.assertEqual(platforms["doubao"]["state"], "needs_adapter")

    def test_repeated_and_revised_import_replaces_whole_client_day(self):
        store = self.root / "history.sqlite3"
        rows = self.read(graph([client(), client(model="other")])).records
        merge_history(store, rows, offset="+08:00")
        _, unchanged = merge_history(store, rows, offset="+08:00")
        self.assertFalse(unchanged["snapshot_created"])
        # A model disappears on correction; no stale per-model row survives.
        revised = self.read(graph([client(multiplier=3)])).records
        records, stats = merge_history(store, revised, offset="+08:00")
        self.assertEqual(len(records), 1)
        self.assertEqual(stats["net_tokens"], 109)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(len(read_timeline(store)), 2)

    def test_explicit_zero_revision_removes_activity_without_losing_history(self):
        store = self.root / "history.sqlite3"
        merge_history(store, self.read(graph([client()])).records, offset="+08:00")
        rows, stats = merge_history(store, self.read(graph([client(multiplier=0)])).records, offset="+08:00")
        self.assertEqual(stats["net_tokens"], -109)
        self.assertEqual(aggregate(rows)["active_days"], 0)
        self.assertEqual(aggregate(rows)["daily"], [])
        self.assertEqual(len(rows), 1)

    def test_partial_date_range_keeps_unmentioned_history(self):
        store = self.root / "history.sqlite3"
        merge_history(store, self.read(graph(day="2026-09-30")).records, offset="+08:00")
        rows, _ = merge_history(store, self.read().records, offset="+08:00")
        self.assertEqual(aggregate(rows)["active_days"], 2)

    def test_bad_contracts_fail_including_filtered_clients(self):
        valid = graph()
        bad = []
        for key, value in [("input", -1), ("output", 1.5), ("cacheRead", True), ("reasoning", None)]:
            item = deepcopy(valid)
            item["contributions"][0]["clients"][0]["tokens"][key] = value
            bad.append(item)
        for mutation in (
            lambda x: x["summary"].update(totalTokens=999),
            lambda x: x["meta"].update(version="5.0.0"),
            lambda x: x["meta"].update(generatedAt="2026-01-01T00:00:00Z"),
            lambda x: x["meta"]["dateRange"].update(end="2026-10-02"),
            lambda x: x["contributions"].append(deepcopy(x["contributions"][0])),
            lambda x: x["contributions"][0]["totals"].update(tokens=999),
            lambda x: x["contributions"][0]["clients"][0].update(client=PRIVATE),
            lambda x: x["contributions"][0]["clients"][0].update(models={}),
            lambda x: x["contributions"][0]["clients"].append(deepcopy(x["contributions"][0]["clients"][0])),
        ):
            item = deepcopy(valid)
            mutation(item)
            bad.append(item)
        bad += [{"daily": [], "sessions": []}, [], {"contributions": []}]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(UsageError) as raised:
                self.read(item, clients=["cline"])
            self.assertNotIn(PRIVATE, str(raised.exception))

    def test_inconsistent_components_rejected_even_when_total_matches(self):
        data = graph()
        data["contributions"][0]["tokenBreakdown"]["input"] += 1
        data["contributions"][0]["tokenBreakdown"]["output"] -= 1
        with self.assertRaises(UsageError):
            self.read(data)

    def test_empty_export_and_cost_only_do_not_fabricate_tokens(self):
        data = graph([])
        data["contributions"] = []
        self.assertEqual(self.read(data).records, [])
        result = self.read(graph([client("warp", multiplier=0)]))
        self.assertEqual(aggregate(result.records)["total_tokens"], 0)
        self.assertEqual(aggregate(result.records)["active_days"], 0)

    def test_native_and_ccusage_overlap_rolls_back_existing_ledger(self):
        imported = self.read(graph([client("claude")])).records
        for granularity in ("daily_bucket", "request_delta"):
            store = self.root / (granularity + ".sqlite3")
            original = replace(imported[0], record_id="existing-other-collector", granularity=granularity)
            merge_history(store, [original], offset="+08:00")
            with self.assertRaises(UsageError):
                merge_history(store, imported, offset="+08:00")
            self.assertEqual(read_history(store), [original])
            self.assertEqual(len(read_timeline(store)), 1)

    def test_daily_offset_and_alias_overlap_cannot_bypass_checks(self):
        store = self.root / "history.sqlite3"
        rows = self.read(graph([client("claude")])).records
        merge_history(store, rows, offset="+08:00")
        with self.assertRaises(UsageError):
            merge_history(store, rows, offset="+00:00")
        mirrored = self.read(graph([client("cc-mirror/work")])).records
        with self.assertRaises(UsageError):
            merge_history(store, mirrored, offset="+08:00")

    def test_cli_requires_declared_timezone_and_makes_no_database_on_error(self):
        self.write(graph())
        out = self.root / "out"
        base = ["run", "--sources", "none", "--tokscale", str(self.path), "--out", str(out)]
        for extra in ([], ["--tokscale-offset", "+00:00"], ["--tokscale-offset", "+08:00", "--tokscale-clients", "unknown"]):
            code, data = self.cli(*base, *extra)
            self.assertEqual(code, 2)
            self.assertFalse(data["ok"])
            self.assertFalse((out / "history.sqlite3").exists())

    def test_cli_report_backup_rebuild_and_privacy(self):
        self.write(graph())
        out = self.root / "out"
        args = ["run", "--sources", "none", "--tokscale", str(self.path), "--tokscale-offset", "+08:00", "--out", str(out)]
        code, reply = self.cli(*args)
        self.assertEqual(code, 0)
        self.assertEqual(reply["data"]["local_recorded_tokens"], 218)
        code, repeat = self.cli(*args)
        self.assertEqual(code, 0)
        self.assertFalse(repeat["data"]["history"]["snapshot_created"])
        for filename in ("report.html", "report-data.json", "records.jsonl"):
            self.assertNotIn(PRIVATE, (out / filename).read_text(encoding="utf-8"))
        self.assertIn("OpenClaw", (out / "report.html").read_text(encoding="utf-8"))
        restored = import_records(out / "records.jsonl")
        self.assertEqual(aggregate(restored)["total_tokens"], 218)
        rebuilt = self.root / "rebuilt"
        code, _ = self.cli("report", "--store", str(out / "history.sqlite3"), "--out", str(rebuilt))
        self.assertEqual(code, 0)
        bundle = json.loads((rebuilt / "report-data.json").read_text(encoding="utf-8"))
        self.assertEqual(next(p for p in bundle["platforms"] if p["source"] == "openclaw")["state"], "imported_daily")

    def test_no_history_restored_overlap_is_rejected(self):
        self.write(graph([client("claude")]))
        existing = self.read(graph([client("claude")])).records[0]
        backup = self.root / "backup.jsonl"
        backup.write_text(json.dumps(replace(existing, record_id="native", granularity="trace_total").to_dict()), encoding="utf-8")
        code, _ = self.cli("run", "--sources", "none", "--tokscale", str(self.path), "--tokscale-offset", "+08:00",
                           "--no-history", "--import-records", str(backup), "--out", str(self.root / "out"))
        self.assertEqual(code, 2)

    def test_source_offset_is_preserved_at_month_boundary(self):
        rows = self.read(graph(day="2026-10-01"), offset="-05:00").records
        self.assertEqual(aggregate(rows, offset="-05:00", month="2026-10")["active_days"], 1)
        self.assertTrue(all(r.occurred_at.endswith("-05:00") for r in rows))


if __name__ == "__main__":
    unittest.main()
