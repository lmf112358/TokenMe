import json
from pathlib import Path
import tempfile
import unittest

from token_footprint.account import sanitize_account_usage
from token_footprint.adapters import codex_scan, workbuddy_scan
from token_footprint.ccusage import import_ccusage
from token_footprint.model import UsageError, aggregate, normalize_usage
from token_footprint.__main__ import main


def record(**changes):
    usage = {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 70,
             "cache_write_input_tokens": 10, "reasoning_output_tokens": 5, "total_tokens": 120}
    usage.update(changes)
    return normalize_usage(usage, record_id="fixture", source="fixture", provider="fixture",
                           model="fixture", occurred_at="2026-10-01T17:00:00Z")


def counter(inp, out, cached=0):
    return {"input_tokens": inp, "output_tokens": out, "cached_input_tokens": cached,
            "reasoning_output_tokens": 0, "cache_write_input_tokens": 0, "total_tokens": inp + out}


def event(at, total, last):
    return {"timestamp": at, "type": "event_msg", "payload": {"type": "token_count",
            "info": {"total_token_usage": total, "last_token_usage": last}}}


def write_codex(root, name, events):
    prefix = [{"type": "session_meta", "payload": {"model_provider": "test-provider"}},
              {"type": "turn_context", "payload": {"model": "test-model"}}]
    path = root / name
    path.write_text("\n".join(json.dumps(x) for x in prefix + events) + "\n", encoding="utf-8")
    return path


def trace(identifier="trace-one", inp=100, out=20, cached=70, **extra):
    return {"trace": {"traceId": identifier, "startedAt": "2026-10-01T00:00:00Z",
                      "endedAt": "2026-10-01T00:01:00Z", "totalTokens": inp + out,
                      "modelInfo": {"models": ["fixture-model"], "totalInputTokens": inp,
                                    "totalOutputTokens": out, "totalCachedTokens": cached}, **extra},
            "spans": [{"toolInput": "PRIVATE PROMPT DO NOT EXPORT"}]}


class AccountingTests(unittest.TestCase):
    def test_cache_and_reasoning_are_not_double_counted(self):
        self.assertEqual(record().total_tokens, 120)

    def test_exclusive_input_contract(self):
        r = normalize_usage({"input_tokens": 20, "output_tokens": 20, "cached_input_tokens": 70,
                             "cache_write_input_tokens": 10, "total_tokens": 120},
                            input_semantics="exclusive", record_id="a", source="test", provider="test",
                            model="test", occurred_at="2026-10-01T00:00:00Z")
        self.assertEqual(r.input_tokens, 100)

    def test_invalid_counts_and_totals_are_rejected(self):
        for change in ({"input_tokens": -1}, {"input_tokens": True}, {"output_tokens": 1.5},
                       {"cached_input_tokens": 110}, {"reasoning_output_tokens": 21},
                       {"total_tokens": 125}, {"cached_input_tokens": 95}):
            with self.subTest(change=change), self.assertRaises(UsageError):
                record(**change)

    def test_unknown_cache_is_not_reported_as_zero(self):
        r = record(cached_input_tokens=None, cache_write_input_tokens=None)
        self.assertIsNone(aggregate([r])["cached_input_tokens"])

    def test_dedupe_and_timezone(self):
        result = aggregate([record(), record()], offset="+08:00", month="2026-10")
        self.assertEqual(result["total_tokens"], 120)
        self.assertEqual(result["duplicates_removed"], 1)
        self.assertEqual(result["daily"][0]["date"], "2026-10-02")

    def test_month_filter(self):
        self.assertEqual(aggregate([record()], month="2026-09")["total_tokens"], 0)
        with self.assertRaises(UsageError):
            aggregate([record()], month="2026-13")

    def test_cumulative_deltas_repeated_snapshots_and_fork_replay(self):
        a = event("2026-10-01T00:00:00Z", counter(100, 10), counter(100, 10))
        b = event("2026-10-01T00:01:00Z", counter(250, 30, 80), counter(150, 20, 80))
        repeated = event("2026-10-01T00:01:30Z", counter(250, 30, 80), counter(150, 20, 80))
        c = event("2026-10-01T00:02:00Z", counter(300, 35, 100), counter(50, 5, 20))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_codex(root, "parent.jsonl", [a, b, repeated])
            write_codex(root, "fork.jsonl", [a, b, c])
            result = codex_scan([root, root])
        self.assertEqual(sum(r.total_tokens for r in result.records), 335)
        self.assertEqual(result.diagnostics["replayed_history_removed"], 2)
        self.assertEqual(result.diagnostics["repeated_cumulative_snapshots"], 1)

    def test_counter_reset_and_truncated_prefix(self):
        events = [event("2026-10-01T00:00:00Z", counter(1000, 100), counter(100, 10)),
                  event("2026-10-01T00:01:00Z", counter(40, 5), counter(40, 5))]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            write_codex(root, "session.jsonl", events)
            result = codex_scan([root])
        self.assertEqual(sum(r.total_tokens for r in result.records), 155)
        self.assertEqual(result.diagnostics["initial_cumulative_prefix_not_attributed"], 1)
        self.assertEqual(result.diagnostics["counter_reset"], 1)

    def test_truncated_last_line_does_not_destroy_prior_usage(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = write_codex(root, "s.jsonl", [event("2026-10-01T00:00:00Z", counter(100, 10), counter(100, 10))])
            with p.open("a") as f:
                f.write('{"type":"event_msg","payload":')
            result = codex_scan([root])
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.diagnostics["malformed_json_lines"], 1)

    def test_workbuddy_trace_totals_and_duplicate_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ["a.json", "copy.json"]:
                (root / name).write_text(json.dumps(trace()), encoding="utf-8")
            result = workbuddy_scan(root)
        self.assertEqual(sum(r.total_tokens for r in result.records), 120)
        self.assertEqual(result.diagnostics["duplicate_trace_snapshots"], 1)
        self.assertNotIn("PRIVATE", json.dumps([r.to_dict() for r in result.records]))

    def test_workbuddy_latest_snapshot_replaces_previous(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.json").write_text(json.dumps(trace()), encoding="utf-8")
            (root / "b.json").write_text(json.dumps(trace(inp=200, endedAt="2026-10-01T00:02:00Z")), encoding="utf-8")
            result = workbuddy_scan(root)
        self.assertEqual(sum(r.total_tokens for r in result.records), 220)

    def test_incomplete_trace_is_not_presented_as_final(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.json").write_text(json.dumps(trace(endedAt=None)), encoding="utf-8")
            result = workbuddy_scan(root)
        self.assertEqual(result.records, [])
        self.assertEqual(result.diagnostics["unfinished_traces_skipped"], 1)

    def test_account_whitelist_and_null_handling(self):
        result = sanitize_account_usage({"summary": {"lifetimeTokens": 123}, "dailyUsageBuckets": None,
                                         "threadUsage": [{"title": "PRIVATE"}], "email": "PRIVATE"})
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertIsNone(result["summary"]["peakDailyTokens"])
        self.assertIsNone(result["dailyUsageBuckets"])
        self.assertEqual(result["merge_policy"], "separate_from_local_ledger")

    def test_account_duplicate_day_not_summed(self):
        bucket = {"startDate": "2026-10-01", "tokens": 123}
        result = sanitize_account_usage({"dailyUsageBuckets": [bucket, bucket]})
        self.assertEqual(len(result["dailyUsageBuckets"]), 1)
        with self.assertRaises(UsageError):
            sanitize_account_usage({"dailyUsageBuckets": [bucket, {**bucket, "tokens": 124}]})

    def test_ccusage_unified_input_is_exclusive(self):
        data = {"daily": [{"period": "2026-10-01", "agents": [{"agent": "qwen", "inputTokens": 500,
                "outputTokens": 100, "cacheReadTokens": 30, "cacheCreationTokens": 20, "totalTokens": 650}]}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ccusage.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            result = import_ccusage(p, "+08:00")
        self.assertEqual(result.records[0].input_tokens, 550)
        self.assertEqual(result.records[0].total_tokens, 650)

    def test_ccusage_requires_attribution(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ccusage.json"
            p.write_text(json.dumps({"daily": [{"period": "2026-10-01", "agent": "all"}]}), encoding="utf-8")
            with self.assertRaises(UsageError):
                import_ccusage(p, "+08:00")

    def test_ccusage_and_native_source_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sessions = root / ".codex/sessions"
            sessions.mkdir(parents=True)
            write_codex(sessions, "a.jsonl", [event("2026-10-01T00:00:00Z", counter(100, 10), counter(100, 10))])
            cc = root / "ccusage.json"
            cc.write_text(json.dumps({"daily": [{"period": "2026-10-01", "agents": [{
                "agent": "codex", "inputTokens": 100, "outputTokens": 10,
                "cacheReadTokens": 0, "cacheCreationTokens": 0, "totalTokens": 110}]}]}), encoding="utf-8")
            self.assertEqual(main(["scan", "--home", str(root), "--ccusage", str(cc), "--out", str(root / "out")]), 2)
            self.assertFalse((root / "out").exists())

    def test_end_to_end_missing_platforms_and_report_escaping(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            traces = root / ".workbuddy/traces"
            traces.mkdir(parents=True)
            obj = trace()
            obj["trace"]["modelInfo"]["models"] = ['</script><script>alert("PRIVATE")</script>']
            (traces / "a.json").write_text(json.dumps(obj), encoding="utf-8")
            out = root / "output"
            self.assertEqual(main(["scan", "--home", str(root), "--out", str(out)]), 0)
            report = (out / "report.html").read_text(encoding="utf-8")
            data = json.loads((out / "report-data.json").read_text(encoding="utf-8"))
            self.assertNotIn('</script><script>alert', report)
            self.assertNotIn("PRIVATE PROMPT", report)
            self.assertFalse(data["source_status"][0]["available"])
            self.assertTrue(data["unconnected"])
            self.assertEqual(data["views"]["all"]["total_tokens"], 120)


if __name__ == "__main__":
    unittest.main()
