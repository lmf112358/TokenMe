"""Offline bridge for Tokscale 4.x `graph --output` (camelCase) exports.

Contract reviewed at bd62b8c4e07269e5314fac06c6d23262dc714633, version 4.18.0.
Independent implementation; does not execute Tokscale or read its credentials.
"""
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import re

from .adapters import ScanResult
from .model import UsageError, count, fingerprint, normalize_usage, timestamp, utc_offset


# This is an import identity registry, not a claim of native client support.
CLIENT_NAMES = dict(pair.split("=", 1) for pair in (
    "opencode=OpenCode", "claude=Claude Code", "codex=Codex", "mcode=MiniMax Code",
    "copilot=GitHub Copilot", "gemini=Gemini CLI", "cursor=Cursor", "amp=Amp",
    "codebuff=Codebuff", "freebuff=Freebuff", "droid=Factory Droid", "openclaw=OpenClaw",
    "hermes=Hermes Agent", "pi=Pi Agent", "kimi=Kimi Code", "qwen=Qwen Code",
    "roocode=Roo Code", "kilocode=Kilo Code", "kilo=Kilo CLI", "mux=Mux",
    "crush=Crush", "goose=Goose", "antigravity=Antigravity", "kiro=Kiro", "zed=Zed",
    "trae=TRAE 国际版", "warp=Warp / Oz", "cline=Cline", "synthetic=Synthetic",
    "gjc=Gajae Code", "9router=9Router", "grok=Grok Build", "jcode=Jcode",
    "commandcode=Command Code", "micode=MiMo Code", "antigravity-cli=Antigravity CLI",
    "antigravity-extension=Antigravity Extension", "junie=Junie", "zcode=ZCode",
    "opencodereview=OpenCodeReview", "codebuddy=CodeBuddy", "workbuddy=WorkBuddy",
    "devin-cli=Devin CLI", "devin-desktop=Devin Desktop", "senpi=Senpi",
    "augment=Augment Code", "kimchi=Kimchi", "reasonix=Reasonix", "prime-agent=Prime Agent",
    "cherrystudio=Cherry Studio", "dsh=DeepSeek Harness", "fx=fx", "omp=Oh My Pi",
    "lmstudio=LM Studio", "unsloth=Unsloth Studio", "hindsight=Hindsight",
    "micode-desktop=MiMo Desktop", "muse=Muse Code",
))
BUCKETS = ("input", "output", "cacheRead", "cacheWrite", "reasoning")
PREFIX = "tokscale-graph-v1:"


def client_id(value):
    if isinstance(value, str) and (value in CLIENT_NAMES or re.fullmatch(r"cc-mirror/[a-z0-9][a-z0-9_-]{0,63}", value)):
        return value
    raise UsageError("unknown Tokscale client; review the export contract before adding this source")


def breakdown(value):
    if not isinstance(value, dict):
        raise UsageError("Tokscale export needs all five token buckets")
    return tuple(count(value.get(key), key) for key in BUCKETS)


def day_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise UsageError("Tokscale date must be YYYY-MM-DD")
    return datetime.strptime(value, "%Y-%m-%d")


def import_tokscale(path, offset, clients=None):
    """Store one authoritative snapshot per client/day; all models roll up together.

    The export carries no bucketing timezone. `offset` is an explicit declaration
    of its source day boundary, not a request to redistribute already grouped days.
    """
    tz = utc_offset(offset)
    selected = None if clients is None else {client_id(value) for value in clients}
    result = ScanResult("tokscale_import", files=1, available=True,
                        coverage="provided_tokscale_daily_export_only")
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    try:
        meta = data["meta"]
        if not re.fullmatch(r"4\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", meta["version"]):
            raise UsageError("unsupported Tokscale version; expected reviewed 4.x graph JSON")
        generated = timestamp(meta["generatedAt"]).astimezone(tz).date()
        rows = data["contributions"]
        if not isinstance(rows, list):
            raise UsageError("Tokscale contributions must be an array")
        seen_days, total = set(), 0
        for number, row in enumerate(rows, 1):
            try:
                day = row["date"]
                at = day_value(day).replace(tzinfo=tz)
                if at.date() > generated or day in seen_days:
                    raise UsageError("duplicate or future day")
                seen_days.add(day)
                daily = breakdown(row["tokenBreakdown"])
                if count(row["totals"]["tokens"]) != sum(daily):
                    raise UsageError("daily total mismatch")
                entries = row["clients"]
                if not isinstance(entries, list):
                    raise UsageError("clients must be an array")
                buckets, seen_models = defaultdict(lambda: [0] * 5), set()
                for entry in entries:
                    source = client_id(entry["client"])
                    model, provider = entry["modelId"], entry.get("providerId")
                    if not isinstance(model, str) or not model or len(model) > 512:
                        raise UsageError("invalid model identity")
                    if provider is not None and (not isinstance(provider, str) or len(provider) > 512):
                        raise UsageError("invalid provider identity")
                    key = (source, model, provider or "")
                    if key in seen_models or "models" in entry:
                        raise UsageError("duplicate or nested model contributions")
                    seen_models.add(key)
                    for index, value in enumerate(breakdown(entry["tokens"])):
                        buckets[source][index] += value
                if tuple(sum(b[i] for b in buckets.values()) for i in range(5)) != daily:
                    raise UsageError("client breakdown mismatch")
                total += sum(daily)
                for source, (inp, out, cached, written, reasoning) in sorted(buckets.items()):
                    if selected is not None and source not in selected:
                        result.diagnostics["filtered_client_days"] += 1
                        continue
                    # Keep explicit zero snapshots so a corrected day can replace
                    # an earlier nonzero value. They do not establish activity.
                    result.records.append(normalize_usage({
                        "input_tokens": inp, "output_tokens": out + reasoning,
                        "cached_input_tokens": cached, "cache_write_input_tokens": written,
                        "reasoning_output_tokens": reasoning,
                    }, input_semantics="exclusive", source=source, provider="unknown",
                        model="mixed/unknown", record_id=PREFIX + fingerprint(source, day),
                        occurred_at=at.isoformat(), granularity="daily_bucket"))
                    if not inp + out + cached + written + reasoning:
                        result.diagnostics["zero_token_client_days"] += 1
            except (ValueError, TypeError, KeyError, AttributeError):
                raise UsageError(f"invalid Tokscale contribution {number}; check day, client identity and five-bucket totals") from None
        if count(data["summary"]["totalTokens"]) != total:
            raise UsageError("Tokscale summary total does not match contributions")
        start, end = meta["dateRange"]["start"], meta["dateRange"]["end"]
        if rows and (start != min(seen_days) or end != max(seen_days)):
            raise UsageError("Tokscale date range does not match contributions")
    except UsageError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise UsageError("expected Tokscale 4.x graph --output JSON, not TUI/session or leaderboard exports") from None
    return result
