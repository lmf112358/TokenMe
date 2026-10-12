"""Import the documented ccusage unified daily JSON contract; never execute it."""
from datetime import datetime
import json
from pathlib import Path
import re

from .adapters import ScanResult
from .model import UsageError, fingerprint, normalize_usage, utc_offset


def import_ccusage(path, offset):
    tz = utc_offset(offset)
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("daily"), list):
        raise UsageError("expected ccusage daily --by-agent --json output")
    result = ScanResult("ccusage_import", files=1, available=True)
    seen = set()
    for row in data["daily"]:
        if not isinstance(row, dict):
            raise UsageError("ccusage daily row must be an object")
        day = row.get("period") or row.get("date")
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise UsageError("ccusage import needs daily YYYY-MM-DD periods")
        observed = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=tz).isoformat()
        agents = row.get("agents") or [row]
        if not isinstance(agents, list):
            raise UsageError("ccusage agents must be a list")
        for agent in agents:
            if not isinstance(agent, dict):
                raise UsageError("ccusage agent row must be an object")
            source = agent.get("agent")
            if not isinstance(source, str) or source == "all" or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", source):
                raise UsageError("ccusage JSON must contain per-agent rows; use --by-agent")
            key = (day, source)
            if key in seen:
                raise UsageError("duplicate ccusage agent/day bucket")
            seen.add(key)
            usage = {"input_tokens": agent.get("inputTokens"), "output_tokens": agent.get("outputTokens"),
                     "cached_input_tokens": agent.get("cacheReadTokens"),
                     "cache_write_input_tokens": agent.get("cacheCreationTokens"),
                     "total_tokens": agent.get("totalTokens")}
            if usage["total_tokens"] is None:
                raise UsageError("ccusage totalTokens required for accounting validation")
            result.records.append(normalize_usage(
                usage, input_semantics="exclusive", record_id=fingerprint("ccusage", source, day),
                source=source, provider="unknown", model="mixed/unknown", occurred_at=observed,
                granularity="daily_bucket"))
    return result
