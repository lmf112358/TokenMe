"""Read-only native usage adapters. No transcript bodies leave these readers."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .adapters import ScanResult
from .model import UsageError, count, fingerprint, normalize_usage, timestamp


def epoch(value, divisor=1000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise UsageError("invalid usage timestamp")
    return datetime.fromtimestamp(value / divisor, timezone.utc).isoformat()


def identity(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise UsageError("missing usage identity")
    return value


def json_lines(path, result):
    try:
        with path.open(encoding="utf-8-sig") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if isinstance(row, dict):
                        yield row
                except ValueError:
                    result.diagnostics["malformed_json_lines"] += 1
    except (OSError, UnicodeError):
        result.diagnostics["unreadable_files"] += 1


def finish(result):
    """Keep a single latest observation per response; fail on ambiguous counters."""
    unique = {}
    for record in result.records:
        if record.total_tokens == 0:
            result.diagnostics["zero_usage_records"] += 1
            continue
        old = unique.get(record.record_id)
        if old:
            result.diagnostics["duplicate_observations"] += 1
            if timestamp(old.occurred_at) == timestamp(record.occurred_at) and old != record:
                raise UsageError(result.source + ": conflicting observations for one usage identity")
            if timestamp(old.occurred_at) > timestamp(record.occurred_at):
                continue
        unique[record.record_id] = record
    result.records = list(unique.values())
    return result


def claude_scan(root):
    root = Path(root)
    result = ScanResult("claude", available=root.is_dir())
    # Include subagent JSONL recursively, but never settings or credentials.
    paths = sorted({p.resolve() for area in (root / "projects", root / "transcripts")
                    if area.is_dir() for p in area.rglob("*.jsonl")})
    for path in paths:
        result.files += 1
        for row in json_lines(path, result):
            msg = row.get("message")
            if row.get("type") != "assistant" or not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                continue
            try:
                usage = msg["usage"]
                # Anthropic input excludes both cache buckets. Missing buckets are unknown.
                record = normalize_usage({"input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "cached_input_tokens": usage.get("cache_read_input_tokens"),
                    "cache_write_input_tokens": usage.get("cache_creation_input_tokens"),
                    "reasoning_output_tokens": (usage.get("output_tokens_details") or {}).get("thinking_tokens")},
                    input_semantics="exclusive", record_id=fingerprint("claude", identity(msg.get("id"))),
                    source="claude", provider="unknown", model=msg.get("model") or "unknown",
                    occurred_at=row.get("timestamp"), granularity="trace_total")
                result.records.append(record)
            except (ValueError, TypeError, AttributeError):
                result.diagnostics["invalid_usage_records"] += 1
    return finish(result)


def pi_scan(root):
    root = Path(root)
    result = ScanResult("pi", available=root.is_dir())
    for path in sorted(root.rglob("*.jsonl")) if root.is_dir() else []:
        result.files += 1
        for row in json_lines(path, result):
            kind = row.get("type")
            msg = row.get("message", {}) if kind == "message" else row
            if not isinstance(msg, dict):
                continue
            if kind == "message" and msg.get("role") not in ("assistant", "toolResult"):
                continue
            if kind not in ("message", "usage", "compaction", "branch_summary") or not isinstance(msg.get("usage"), dict):
                continue
            try:
                usage = msg["usage"]
                # Response IDs survive fork copies. Entry ID + original time is the fallback.
                provider = msg.get("provider") or "unknown"
                key = (provider, msg["responseId"]) if msg.get("responseId") else (identity(row.get("id")), row.get("timestamp"))
                result.records.append(normalize_usage({"input_tokens": usage.get("input"),
                    "output_tokens": usage.get("output"), "cached_input_tokens": usage.get("cacheRead"),
                    "cache_write_input_tokens": usage.get("cacheWrite"), "total_tokens": usage.get("totalTokens"),
                    "reasoning_output_tokens": usage.get("reasoning")}, input_semantics="exclusive",
                    record_id=fingerprint("pi", key), source="pi", provider=provider,
                    model=msg.get("model") or "unknown", occurred_at=row.get("timestamp"), granularity="trace_total"))
            except (ValueError, TypeError, AttributeError):
                result.diagnostics["invalid_usage_records"] += 1
    return finish(result)


def gemini_scan(root):
    """Gemini CLI persisted JSON/JSONL chat recordings, including spent rewound turns."""
    root = Path(root)
    result = ScanResult("gemini", available=root.is_dir())
    paths = sorted([*root.glob("*/chats/*.json"), *root.glob("*/chats/*.jsonl")]) if root.is_dir() else []
    for path in paths:
        result.files += 1
        try:
            if path.suffix == ".jsonl":
                sid, messages = None, {}
                for row in json_lines(path, result):
                    if row.get("sessionId"):
                        sid = row["sessionId"]
                    if row.get("type") == "gemini" and row.get("id") and isinstance(row.get("tokens"), dict):
                        messages[identity(row["id"])] = row
                    # Rewind/content patches affect conversation context, not already spent tokens.
                session = {"sessionId": sid, "messages": list(messages.values())}
            else:
                session = json.loads(path.read_text(encoding="utf-8-sig"))
            for msg in session.get("messages", []):
                if not isinstance(msg, dict) or msg.get("type") != "gemini" or not isinstance(msg.get("tokens"), dict):
                    continue
                try:
                    t = msg["tokens"]
                    inp, output, thoughts = count(t.get("input")), count(t.get("output")), count(t.get("thoughts", 0))
                    # Tool-use prompt tokens cannot be assigned without a documented contract.
                    if t.get("tool", 0) != 0:
                        result.diagnostics["unsupported_tool_token_accounting"] += 1
                        continue
                    result.records.append(normalize_usage({"input_tokens": inp, "output_tokens": output + thoughts,
                        "cached_input_tokens": t.get("cached"), "reasoning_output_tokens": thoughts,
                        "total_tokens": t.get("total")}, record_id=fingerprint("gemini", identity(session.get("sessionId")), identity(msg.get("id"))),
                        source="gemini", provider="unknown", model=msg.get("model") or "unknown", occurred_at=msg.get("timestamp"), granularity="trace_total"))
                except (ValueError, TypeError, AttributeError):
                    result.diagnostics["invalid_usage_records"] += 1
        except (ValueError, OSError, TypeError, AttributeError):
            result.diagnostics["invalid_or_unreadable_files"] += 1
    return finish(result)


def opencode_scan(root):
    root = Path(root)
    result = ScanResult("opencode", available=root.is_dir())
    def consume(msg):
        if not isinstance(msg, dict) or msg.get("role") != "assistant" or not isinstance(msg.get("tokens"), dict):
            return
        try:
            t, time = msg["tokens"], msg.get("time") or {}
            if not time.get("completed"):
                result.diagnostics["unfinished_messages_skipped"] += 1
                return
            cache = t.get("cache") or {}
            reasoning = count(t.get("reasoning", 0))
            result.records.append(normalize_usage({"input_tokens": t.get("input"), "output_tokens": count(t.get("output")) + reasoning,
                "cached_input_tokens": cache.get("read"), "cache_write_input_tokens": cache.get("write"),
                "reasoning_output_tokens": reasoning, "total_tokens": t.get("total")}, input_semantics="exclusive",
                record_id=fingerprint("opencode", identity(msg.get("id"))), source="opencode",
                provider=msg.get("providerID") or "unknown", model=msg.get("modelID") or "unknown",
                occurred_at=epoch(time["completed"]), granularity="trace_total"))
        except (ValueError, TypeError, AttributeError, OverflowError, OSError):
            result.diagnostics["invalid_usage_records"] += 1
    for path in sorted((root / "storage/message").rglob("*.json")) if (root / "storage/message").is_dir() else []:
        result.files += 1
        try:
            consume(json.loads(path.read_text(encoding="utf-8-sig")))
        except (ValueError, OSError):
            result.diagnostics["invalid_or_unreadable_files"] += 1
    for path in sorted(root.glob("opencode*.db")) if root.is_dir() else []:
        result.files += 1
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                for identifier, payload in db.execute("SELECT id, data FROM message"):
                    try:
                        msg = json.loads(payload)
                        msg.setdefault("id", identifier)
                        consume(msg)
                    except (ValueError, TypeError, AttributeError):
                        result.diagnostics["invalid_usage_records"] += 1
        except (sqlite3.Error, OSError):
            result.diagnostics["unsupported_or_unreadable_database"] += 1
    return finish(result)


def qwen_scan(root):
    root = Path(root)
    result = ScanResult("qwen", available=root.is_dir())
    for path in sorted(root.glob("*/chats/*.jsonl")) if root.is_dir() else []:
        result.files += 1
        for row in json_lines(path, result):
            if row.get("type") != "assistant" or not isinstance(row.get("usageMetadata"), dict):
                continue
            try:
                u = row["usageMetadata"]
                thinking = count(u.get("thoughtsTokenCount", 0))
                sid = identity(row.get("sessionId"))
                at = row.get("timestamp")
                key = row.get("uuid") or row.get("id") or (timestamp(at).isoformat(), row.get("model"))
                result.records.append(normalize_usage({"input_tokens": u.get("promptTokenCount"),
                    "output_tokens": count(u.get("candidatesTokenCount")) + thinking,
                    "cached_input_tokens": u.get("cachedContentTokenCount"), "reasoning_output_tokens": thinking,
                    "total_tokens": u.get("totalTokenCount")}, source="qwen", provider="unknown",
                    record_id=fingerprint("qwen", key if row.get("uuid") or row.get("id") else (sid, key)), model=row.get("model") or "unknown",
                    occurred_at=at, granularity="trace_total"))
            except (ValueError, TypeError, AttributeError):
                result.diagnostics["invalid_usage_records"] += 1
    return finish(result)


def kimi_scan(roots):
    result = ScanResult("kimi", available=any(Path(p).is_dir() for p in roots))
    paths = sorted({p.resolve() for root in roots if Path(root).is_dir() for p in Path(root).rglob("wire.jsonl")})
    for path in paths:
        result.files += 1
        for row in json_lines(path, result):
            try:
                if row.get("type") == "usage.record":
                    if row.get("usageScope") != "turn":
                        result.diagnostics["unsupported_usage_scope"] += 1
                        continue
                    u = row.get("usage") or {}
                    at = epoch(row.get("time"))
                    key = row.get("messageId") or row.get("requestId") or (at, row.get("model"))
                    keys = ("inputOther", "output", "inputCacheRead", "inputCacheCreation")
                    model = row.get("model") or "unknown"
                else:
                    msg = row.get("message") or {}
                    if msg.get("type") != "StatusUpdate":
                        continue
                    payload = msg.get("payload") or {}
                    if not payload.get("token_usage"):
                        continue
                    u = payload["token_usage"]
                    at = epoch(row.get("timestamp"), 1)
                    key = identity(payload.get("message_id"))
                    keys = ("input_other", "output", "input_cache_read", "input_cache_creation")
                    model = "unknown"
                result.records.append(normalize_usage(dict(zip(
                    ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens"),
                    (u.get(k) for k in keys))), input_semantics="exclusive", source="kimi", provider="unknown",
                    model=model, record_id=fingerprint("kimi", key), occurred_at=at, granularity="trace_total"))
            except (ValueError, TypeError, AttributeError, OverflowError, OSError):
                result.diagnostics["invalid_usage_records"] += 1
    return finish(result)
