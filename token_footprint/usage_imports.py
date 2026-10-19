"""Explicit offline imports; strict schemas, no login/cookie extraction or network."""
import csv
import json
from pathlib import Path

from .adapters import ScanResult
from .agents import epoch, identity, finish
from .model import UsageError, fingerprint, normalize_usage, timestamp


def csv_count(value):
    # Exported integers may use quoted thousands separators. Never round decimals.
    if not isinstance(value, str):
        raise UsageError("missing CSV token count")
    value = value.strip()
    import re
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", value):
        raise UsageError("CSV token counts must be nonnegative integers")
    return int(value.replace(",", ""))


def import_cursor(path):
    result = ScanResult("cursor", files=1, available=True)
    result.coverage = "provided_usage_export_only"
    required = {"Date", "Model", "Input (w/ Cache Write)", "Input (w/o Cache Write)",
                "Cache Read", "Output Tokens", "Total Tokens"}
    seen = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        if not required <= set(rows.fieldnames or []):
            raise UsageError("Cursor CSV requires Date, Model and the complete token breakdown; credits-only exports are unsupported")
        for number, row in enumerate(rows, 2):
            if not any(row.values()):
                continue
            try:
                at = timestamp(row["Date"]).isoformat()  # Never infer machine timezone.
                model = identity(row["Model"])
                request_id = row.get("Request ID") or row.get("RequestId")
                key = ("request", request_id) if request_id else (at, model, row.get("Kind", ""), row.get("Cloud Agent ID", ""), row.get("Automation ID", ""))
                rid = fingerprint("cursor", key)
                if rid in seen:
                    raise UsageError("ambiguous duplicate event in Cursor export")
                seen.add(rid)
                result.records.append(normalize_usage({
                    "input_tokens": csv_count(row["Input (w/o Cache Write)"]),
                    "output_tokens": csv_count(row["Output Tokens"]),
                    "cached_input_tokens": csv_count(row["Cache Read"]),
                    "cache_write_input_tokens": csv_count(row["Input (w/ Cache Write)"]),
                    "total_tokens": csv_count(row["Total Tokens"])}, input_semantics="exclusive",
                    source="cursor", provider="unknown", model=model, record_id=rid, occurred_at=at))
            except (ValueError, TypeError, KeyError):
                raise UsageError(f"invalid or ambiguous Cursor CSV row {number}; check timestamp, token totals and event identity") from None
    return finish(result)


def import_trae(path):
    """International session usage export/cache array, with four disjoint buckets."""
    result = ScanResult("trae", files=1, available=True)
    result.coverage = "provided_usage_export_only"
    rows = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list):
        raise UsageError("TRAE import requires a session usage array; CN enterprise exports need a separate adapter")
    for number, row in enumerate(rows, 1):
        try:
            session = identity(row.get("session_id"))
            at = epoch(row.get("usage_time"), 1)
            u = row["extra_info"]
            model = row.get("model_name") or "mixed/unknown"
            result.records.append(normalize_usage({"input_tokens": u.get("input_token"),
                "output_tokens": u.get("output_token"), "cached_input_tokens": u.get("cache_read_token"),
                "cache_write_input_tokens": u.get("cache_write_token"), "total_tokens": u.get("total_token")},
                input_semantics="exclusive", source="trae", provider="unknown", model=model,
                record_id=fingerprint("trae", session, at, model), occurred_at=at, granularity="trace_total"))
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, OSError):
            raise UsageError(f"invalid TRAE usage row {number}; expected real session identity and complete token breakdown") from None
    return finish(result)
