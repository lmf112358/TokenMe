"""Local, transactional history. Store normalized counters, never source documents."""
from contextlib import closing
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .model import UsageError, UsageRecord, aggregate, timestamp, fingerprint, validate_source_scopes


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
    if connection.execute("PRAGMA user_version").fetchone()[0] not in (1, 2):
        raise UsageError("unsupported history database version")
    return [record_from_dict(json.loads(row[0])) for row in connection.execute("SELECT payload FROM records ORDER BY record_id")]


def read_history(path):
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        return _read(connection)


def read_timeline(path, limit=50):
    """Newest meaningful snapshots first. v1 read-only reports do not migrate."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 1:
            return []
        if version != 2:
            raise UsageError("unsupported history database version")
        return [json.loads(row[0]) for row in connection.execute("SELECT payload FROM snapshots ORDER BY id DESC LIMIT ?", (limit,))]


def backup_history(path, destination):
    """Consistent SQLite backup including snapshots; refuse to replace a file."""
    source = Path(path).resolve()
    target = Path(destination).resolve()
    if target == source or target.exists():
        raise UsageError("backup destination must be a new file")
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as connection:
        _read(connection)
        # Reserve exclusively, so an existing database is never overwritten.
        with target.open("xb"):
            pass
        with closing(sqlite3.connect(target)) as backup:
            connection.backup(backup)


def merge_history(path, incoming, *, offset, source_status=None):
    """One ledger per person. Native counters and daily buckets cannot overlap a source."""
    aggregate(incoming)  # Reject conflicts within one scan before creating the database.
    incoming = {r.record_id: r for r in incoming}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with closing(sqlite3.connect(path)) as probe:
            version = probe.execute("PRAGMA user_version").fetchone()[0]
        if version == 1:
            backup = path.with_name(path.name + ".pre-v2.sqlite3")
            if not backup.exists():
                backup_history(path, backup)
    stats = dict(added=0, updated=0, unchanged=0, older_ignored=0, added_tokens=0, revised_tokens=0)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("PRAGMA user_version").fetchone()[0] == 0:
            if connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise UsageError("refusing to use an unrelated SQLite database")
            connection.execute("CREATE TABLE records (record_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("PRAGMA user_version = 1")
        existing = {r.record_id: r for r in _read(connection)}
        stats["before_tokens"] = sum(r.total_tokens for r in existing.values())
        connection.execute("CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY, digest TEXT NOT NULL, offset TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.execute("PRAGMA user_version = 2")
        validate_source_scopes([*existing.values(), *incoming.values()])
        if any(r.granularity == "daily_bucket" for r in [*existing.values(), *incoming.values()]):
            old_offset = connection.execute("SELECT value FROM metadata WHERE key='daily_offset'").fetchone()
            if old_offset and old_offset[0] != offset:
                raise UsageError("daily-import history requires its original --offset " + old_offset[0])
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
                stats["revised_tokens"] += new.total_tokens - old.total_tokens
            else:
                stats["added"] += 1
                stats["added_tokens"] += new.total_tokens
            connection.execute("INSERT OR REPLACE INTO records VALUES (?, ?)", (identifier, json.dumps(new.to_dict(), ensure_ascii=False)))
            existing[identifier] = new
        stats["records"] = len(existing)
        ordered = sorted(existing.values(), key=lambda r: r.record_id)
        stats["after_tokens"] = sum(r.total_tokens for r in ordered)
        stats["net_tokens"] = stats["after_tokens"] - stats["before_tokens"]
        digest = fingerprint([r.to_dict() for r in ordered])
        previous = connection.execute("SELECT id, digest, offset, payload FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
        changed = not previous or (previous[1], previous[2]) != (digest, offset)
        stats["snapshot_created"] = changed
        stats["snapshot_id"] = (previous[0] + 1 if previous else 1) if changed else previous[0]
        if changed:
            summary = aggregate(ordered, offset=offset)
            prior = json.loads(previous[3]) if previous else None
            snapshot = {"id": stats["snapshot_id"], "created_at": datetime.now(timezone.utc).isoformat(),
                        "summary": summary, "changes": dict(stats), "source_status": source_status or [],
                        "previous_id": previous[0] if previous else None,
                        "since_previous_tokens": summary["total_tokens"] - prior["summary"]["total_tokens"] if prior else None}
            connection.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?)",
                               (snapshot["id"], digest, offset, json.dumps(snapshot, ensure_ascii=False)))
    return sorted(existing.values(), key=lambda r: r.record_id), stats
