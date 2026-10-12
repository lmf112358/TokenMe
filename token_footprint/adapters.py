"""Read-only adapters. Raw messages and credentials are never exported."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import json

from .model import UsageError, count, fingerprint, normalize_usage, timestamp


@dataclass
class ScanResult:
    source: str
    records: list = field(default_factory=list)
    diagnostics: Counter = field(default_factory=Counter)
    files: int = 0
    available: bool = False

    def status(self):
        return {"source": self.source, "available": self.available, "files": self.files,
                "records": len(self.records), "diagnostics": dict(self.diagnostics),
                "coverage": "retained_local_records_only", "evidence": "local_record"}


def codex_scan(roots):
    result = ScanResult("codex")
    seen_paths = set()
    for root in roots:
        root = Path(root)
        result.available |= root.exists()
        for path in sorted(root.rglob("*.jsonl")) if root.exists() else []:
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            result.files += 1
            previous = None
            model, provider = "unknown", "unknown"
            try:
                with path.open(encoding="utf-8-sig") as stream:
                    for line in stream:
                        # Avoid parsing prompt/tool bodies. Only structured usage/metadata rows matter.
                        if not any(marker in line[:160] for marker in ('"session_meta"', '"turn_context"', '"event_msg"')):
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            result.diagnostics["malformed_json_lines"] += 1
                            continue
                        if not isinstance(obj, dict):
                            continue
                        payload = obj.get("payload") or {}
                        if not isinstance(payload, dict):
                            continue
                        if obj.get("type") == "session_meta":
                            provider = payload.get("model_provider") or provider
                            continue
                        if obj.get("type") == "turn_context":
                            model = payload.get("model") or model
                            continue
                        if obj.get("type") != "event_msg" or payload.get("type") != "token_count":
                            continue
                        info = payload.get("info") or {}
                        if not isinstance(info, dict):
                            result.diagnostics["invalid_usage_records"] += 1
                            continue
                        current = info.get("total_token_usage")
                        last = info.get("last_token_usage")
                        if not isinstance(current, dict):
                            result.diagnostics["usage_without_cumulative_counters"] += 1
                            continue
                        names = ("input_tokens", "output_tokens", "cached_input_tokens",
                                 "cache_write_input_tokens", "reasoning_output_tokens", "total_tokens")
                        try:
                            current = {k: count(current[k], k) for k in names if k in current}
                            if not all(k in current for k in ("input_tokens", "output_tokens", "total_tokens")):
                                raise UsageError("missing cumulative total")
                            if current["input_tokens"] + current["output_tokens"] != current["total_tokens"]:
                                raise UsageError("invalid cumulative total")
                            if previous == current:
                                result.diagnostics["repeated_cumulative_snapshots"] += 1
                                continue
                            if previous is None:
                                # A truncated/forked log may begin with an inherited balance.
                                delta = last if isinstance(last, dict) else None
                                if delta is None:
                                    result.diagnostics["unattributed_initial_snapshot"] += 1
                                    previous = current
                                    continue
                                if current.get("total_tokens") != delta.get("total_tokens"):
                                    result.diagnostics["initial_cumulative_prefix_not_attributed"] += 1
                            elif any(current[k] < previous.get(k, 0) for k in ("input_tokens", "output_tokens", "total_tokens")):
                                delta = last if isinstance(last, dict) else None
                                result.diagnostics["counter_reset"] += 1
                            else:
                                delta = {k: current[k] - previous[k] for k in names if k in current and k in previous}
                            previous = current
                            if not delta:
                                result.diagnostics["unattributed_usage"] += 1
                                continue
                            if not delta.get("total_tokens"):
                                continue
                            observed_at = obj.get("timestamp")
                            # Replayed fork histories keep timestamps + cumulative snapshots.
                            # Excluding file/session IDs avoids counting inherited history twice.
                            rid = fingerprint("codex", observed_at, current)
                            record = normalize_usage(delta, record_id=rid, source="codex",
                                                     provider=provider, model=model, occurred_at=observed_at)
                            result.records.append(record)
                        except (UsageError, TypeError, AttributeError):
                            result.diagnostics["invalid_usage_records"] += 1
            except (OSError, UnicodeError):
                result.diagnostics["unreadable_files"] += 1
    # Identical replayed observations may have different surrounding model metadata.
    unique = {}
    for record in result.records:
        old = unique.get(record.record_id)
        if old:
            result.diagnostics["replayed_history_removed"] += 1
            if (old.input_tokens, old.output_tokens) != (record.input_tokens, record.output_tokens):
                result.diagnostics["ambiguous_replay_delta"] += 1
                # Do not quietly resolve a true conflict by summing both observations.
                continue
            if old.model == "unknown" and record.model != "unknown":
                unique[record.record_id] = record
        else:
            unique[record.record_id] = record
    result.records = list(unique.values())
    return result


def workbuddy_scan(root):
    root = Path(root)
    result = ScanResult("workbuddy", available=root.exists())
    snapshots = {}
    for path in sorted(root.rglob("*.json")) if root.exists() else []:
        result.files += 1
        try:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
            trace = obj.get("trace") or {}
            info = trace.get("modelInfo") or {}
            if not info:
                result.diagnostics["traces_without_model_usage"] += 1
                continue
            trace_id = trace.get("traceId")
            if not trace_id:
                raise UsageError("missing trace identity")
            usage = {"input_tokens": info.get("totalInputTokens"),
                     "output_tokens": info.get("totalOutputTokens"),
                     "cached_input_tokens": info.get("totalCachedTokens"),
                     "total_tokens": trace.get("totalTokens")}
            models = info.get("models") or []
            # Trace-level totals cannot be split reliably when several models appear.
            model = models[0] if len(models) == 1 else "mixed/unknown"
            if not trace.get("endedAt"):
                result.diagnostics["unfinished_traces_skipped"] += 1
                continue
            ended = trace["endedAt"]
            record = normalize_usage(usage, record_id=fingerprint("workbuddy", trace_id),
                                     source="workbuddy", provider="unknown", model=model,
                                     occurred_at=ended, granularity="trace_total")
            old = snapshots.get(record.record_id)
            if old:
                result.diagnostics["duplicate_trace_snapshots"] += 1
                if timestamp(ended) < timestamp(old.occurred_at):
                    continue
                if timestamp(ended) == timestamp(old.occurred_at) and old != record:
                    result.diagnostics["conflicting_trace_snapshot"] += 1
                    continue
            snapshots[record.record_id] = record
        except (ValueError, OSError, TypeError, AttributeError, IndexError):
            result.diagnostics["invalid_or_unreadable_traces"] += 1
    result.records = list(snapshots.values())
    return result
