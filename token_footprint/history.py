"""Local, transactional history. Store normalized counters, never source documents."""
from contextlib import closing
from dataclasses import fields
import json
from pathlib import Path
import sqlite3

from .model import UsageError, UsageRecord, aggregate, timestamp


def record_from_dict(row):
    if not isinstance(row, dict):
        raise UsageError("history record must be an object")
    allowed = {field.name for field in fields(UsageRecord)}
    record = UsageRecord(**{key: value for key, value in row.items() if key in allowed})
    for key in ("record_id", "source", "provider", "model"):
        value = getattr(record, key)
        if not isinstance(value, str) or not value or len(value) > 512:
            raise UsageError("invalid history metadata: " + key)
    if record.evidence != "local_record" or record.granularity not in ("request_delta", "trace_total", "daily_bucket"):
        raise UsageError("unsupported history evidence or granularity")
    if "total_tokens" in row and (type(row["total_tokens"]) is not int or row["total_tokens"] != record.total_tokens):
        raise UsageError("history total does not match input + output")
    return record


def import_records(path):
    records = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                records.append(record_from_dict(json.loads(line)))
            except (ValueError, TypeError, KeyError) as exc:
                # Never echo malformed user input or a conversation body.
                raise UsageError(f"invalid normalized record at line {number}") from exc
    aggregate(records)
    return records


def _read(connection):
    if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise UsageError("unsupported history database version")
    return [record_from_dict(json.loads(row[0])) for row in connection.execute("SELECT payload FROM records ORDER BY record_id")]


def read_history(path):
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        return _read(connection)


def merge_history(path, incoming, *, offset):
    """One ledger per person. Native counters and daily buckets cannot overlap a source."""
    aggregate(incoming)  # Reject conflicts within one scan before creating the database.
    incoming = {r.record_id: r for r in incoming}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stats = dict(added=0, updated=0, unchanged=0, older_ignored=0)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("PRAGMA user_version").fetchone()[0] == 0:
            if connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise UsageError("refusing to use an unrelated SQLite database")
            connection.execute("CREATE TABLE records (record_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("PRAGMA user_version = 1")
        existing = {r.record_id: r for r in _read(connection)}
        kinds = {}
        for r in [*existing.values(), *incoming.values()]:
            kind = "daily" if r.granularity == "daily_bucket" else "native"
            kinds.setdefault(r.source, set()).add(kind)
        if any(len(kinds_) > 1 for kinds_ in kinds.values()):
            raise UsageError("history contains overlapping native and ccusage sources; use a separate --store")
        if any("daily" in value for value in kinds.values()):
            old_offset = connection.execute("SELECT value FROM metadata WHERE key='daily_offset'").fetchone()
            if old_offset and old_offset[0] != offset:
                raise UsageError("ccusage history requires its original --offset " + old_offset[0])
            # Imported portable daily records retain the export's offset in their timestamp.
            for r in [*existing.values(), *incoming.values()]:
                if r.granularity == "daily_bucket" and not r.occurred_at.endswith(offset):
                    raise UsageError("daily bucket timestamp must match --offset")
            connection.execute("INSERT OR REPLACE INTO metadata VALUES ('daily_offset', ?)", (offset,))
        for identifier, new in incoming.items():
            old = existing.get(identifier)
            if old == new:
                stats["unchanged"] += 1
                continue
            if old:
                if (old.source, old.granularity) != (new.source, new.granularity):
                    raise UsageError("history record identity conflicts with an existing source")
                if old.granularity == "trace_total" and timestamp(new.occurred_at) < timestamp(old.occurred_at):
                    stats["older_ignored"] += 1
                    continue
                if old.granularity == "request_delta":
                    counts = ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens")
                    if timestamp(old.occurred_at) != timestamp(new.occurred_at) or any(getattr(old, k) != getattr(new, k) for k in counts):
                        raise UsageError("conflicting request delta in history; inspect source logs or use a separate --store")
                stats["updated"] += 1
            else:
                stats["added"] += 1
            connection.execute("INSERT OR REPLACE INTO records VALUES (?, ?)", (identifier, json.dumps(new.to_dict(), ensure_ascii=False)))
            existing[identifier] = new
        stats["records"] = len(existing)
    return sorted(existing.values(), key=lambda r: r.record_id), stats
