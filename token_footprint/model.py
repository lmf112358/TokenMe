"""A token ledger, not a billing or productivity score."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re


class UsageError(ValueError):
    pass


def source_family(source):
    """Aliases share an accounting scope, even in old imported ledgers."""
    if source.startswith("cc-mirror/"):
        return "claude"
    return {"claude-code": "claude", "claude_code": "claude", "codex-cli": "codex",
            "gemini-cli": "gemini", "qwen-code": "qwen", "kimi-code": "kimi",
            "pi-agent": "pi"}.get(source, source)


def validate_source_scopes(records):
    """A source must have one accounting authority across scans and backups."""
    kinds, labels = defaultdict(set), defaultdict(set)
    for record in records:
        scope = source_family(record.source)
        labels[scope].add(record.source)
        kind = ("tokscale" if record.record_id.startswith("tokscale-graph-v1:") else "daily") if record.granularity == "daily_bucket" else "native"
        kinds[scope].add(kind)
    if any(len(names) > 1 for names in labels.values()):
        raise UsageError("history source aliases overlap; reconcile the existing source names before importing")
    if any(len(values) > 1 for values in kinds.values()):
        raise UsageError("overlapping native / ccusage / Tokscale sources; filter import clients or use a separate --store")


def count(value, name="tokens", optional=False):
    if value is None and optional:
        return None
    if type(value) is not int or value < 0:
        raise UsageError(f"{name} must be a nonnegative integer")
    return value


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as exc:
        raise UsageError("invalid ISO timestamp") from exc
    if result.tzinfo is None:
        raise UsageError("timestamp must include timezone")
    return result.astimezone(timezone.utc)


def utc_offset(value):
    if not re.fullmatch(r"[+-]\d{2}:\d{2}", value):
        raise UsageError("timezone offset must look like +08:00")
    hours, minutes = map(int, value[1:].split(":"))
    if hours > 14 or minutes > 59 or (hours == 14 and minutes):
        raise UsageError("invalid UTC offset")
    return timezone(timedelta(minutes=(hours * 60 + minutes) * (1 if value[0] == "+" else -1)))


def fingerprint(*values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class UsageRecord:
    record_id: str
    source: str
    provider: str
    model: str
    occurred_at: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    evidence: str = "local_record"
    granularity: str = "request_delta"

    def __post_init__(self):
        for name in ("record_id", "source", "provider", "model"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 512:
                raise UsageError("invalid record metadata: " + name)
        timestamp(self.occurred_at)
        for name in ("input_tokens", "output_tokens"):
            count(getattr(self, name), name)
        for name in ("cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens"):
            value = count(getattr(self, name), name, optional=True)
            maximum = self.output_tokens if name == "reasoning_output_tokens" else self.input_tokens
            if value is not None and value > maximum:
                raise UsageError(f"{name} exceeds its inclusive total")
        if self.cached_input_tokens is not None and self.cache_write_input_tokens is not None:
            if self.cached_input_tokens + self.cache_write_input_tokens > self.input_tokens:
                raise UsageError("cache read + write exceeds input total")

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens

    def to_dict(self):
        return {**asdict(self), "total_tokens": self.total_tokens}


def normalize_usage(usage, *, input_semantics="inclusive", **metadata):
    """Cache/reasoning fields are subsets. Only explicitly exclusive inputs are expanded."""
    inp = count(usage.get("input_tokens"), "input_tokens")
    out = count(usage.get("output_tokens"), "output_tokens")
    cached = count(usage.get("cached_input_tokens"), "cached_input_tokens", True)
    written = count(usage.get("cache_write_input_tokens"), "cache_write_input_tokens", True)
    if input_semantics == "exclusive":
        if cached is None or written is None:
            raise UsageError("exclusive input requires both cache counters")
        inp += cached + written
    elif input_semantics != "inclusive":
        raise UsageError("unknown input semantics")
    reported = usage.get("total_tokens")
    if reported is not None and count(reported) != inp + out:
        raise UsageError("reported total does not match normalized input + output")
    return UsageRecord(**metadata, input_tokens=inp, output_tokens=out,
                       cached_input_tokens=cached, cache_write_input_tokens=written,
                       reasoning_output_tokens=usage.get("reasoning_output_tokens"))


def aggregate(records, *, offset="+08:00", month=None):
    tz = utc_offset(offset)
    if month is not None:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}", month):
                raise ValueError()
            datetime.strptime(month, "%Y-%m")
        except ValueError as exc:
            raise UsageError("month must be YYYY-MM") from exc
    unique = {}
    duplicates = 0
    for record in records:
        old = unique.get(record.record_id)
        if old:
            duplicates += 1
            if old != record:
                raise UsageError("conflicting observations for one record ID")
        else:
            unique[record.record_id] = record
    selected = []
    for record in unique.values():
        day = timestamp(record.occurred_at).astimezone(tz).date().isoformat()
        if month is None or day.startswith(month):
            selected.append((day, record))

    def totals(rows):
        result = {"records": len(rows), "input_tokens": sum(r.input_tokens for r in rows),
                  "output_tokens": sum(r.output_tokens for r in rows),
                  "total_tokens": sum(r.total_tokens for r in rows)}
        for name in ("cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens"):
            available = [getattr(r, name) for r in rows if getattr(r, name) is not None]
            result[name] = sum(available) if available else None
            result[name + "_known_records"] = len(available)
        return result

    daily, sources, models = defaultdict(list), defaultdict(list), defaultdict(list)
    for day, record in selected:
        if record.total_tokens > 0:
            daily[day].append(record)
        sources[record.source].append(record)
        models[(record.source, record.model)].append(record)
    result = totals([record for _, record in selected])
    result.update({"schema_version": "0.1", "timezone": "UTC" + offset,
                   "period": month or "all-local-history", "duplicates_removed": duplicates,
                   "active_days": len(daily), "first_observed_day": min(daily, default=None),
                   "last_observed_day": max(daily, default=None),
                   "daily": [{"date": day, **totals(rows)} for day, rows in sorted(daily.items())],
                   "sources": [{"source": source, **totals(rows)} for source, rows in sorted(sources.items())],
                   "models": [{"source": key[0], "model": key[1], **totals(rows)}
                              for key, rows in sorted(models.items())]})
    return result
