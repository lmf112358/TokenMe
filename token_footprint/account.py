"""Read documented account/usage/read through an existing authenticated Codex binary."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import queue
import subprocess
import threading
import time

from .model import UsageError, count


SUMMARY_FIELDS = ("lifetimeTokens", "peakDailyTokens", "longestRunningTurnSec", "currentStreakDays", "longestStreakDays")


def sanitize_account_usage(data):
    if not isinstance(data, dict):
        raise UsageError("account result must be an object")
    summary = data.get("summary") or {}
    if not isinstance(summary, dict):
        raise UsageError("account summary must be an object")
    clean_summary = {k: count(summary.get(k), k, True) for k in SUMMARY_FIELDS}
    raw_buckets = data.get("dailyUsageBuckets")
    daily = None
    if raw_buckets is not None:
        if not isinstance(raw_buckets, list):
            raise UsageError("daily buckets must be a list or null")
        buckets = {}
        for raw in raw_buckets:
            if not isinstance(raw, dict):
                raise UsageError("account daily bucket must be an object")
            day = date.fromisoformat(raw["startDate"]).isoformat()
            tokens = count(raw["tokens"])
            if day in buckets and buckets[day] != tokens:
                raise UsageError("conflicting account buckets")
            buckets[day] = tokens
        daily = [{"startDate": k, "tokens": v} for k, v in sorted(buckets.items())]
    # No account identifiers, thread titles or threadUsage are retained.
    return {"source": "codex_account", "evidence": "provider_response",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "summary": clean_summary, "dailyUsageBuckets": daily,
            "day_boundary": "provider_defined_unspecified",
            "scope": "Codex service account activity; exact product coverage not established",
            "merge_policy": "separate_from_local_ledger"}


def read_account_usage(executable, timeout=25):
    if timeout <= 0:
        raise UsageError("timeout must be positive")
    proc = subprocess.Popen([str(executable), "app-server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    messages = queue.Queue()

    def reader():
        for line in proc.stdout:
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    messages.put(obj)
            except ValueError:
                pass
        messages.put(None)

    worker = threading.Thread(target=reader, daemon=True)
    worker.start()
    deadline = time.monotonic() + timeout

    def send(message):
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def response(identifier):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise UsageError("account usage request timed out")
            try:
                obj = messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise UsageError("account usage request timed out") from exc
            if obj is None:
                raise UsageError("Codex app-server exited before replying")
            if obj.get("id") != identifier:
                continue
            if "error" in obj:
                # Avoid printing potentially sensitive upstream error payloads.
                code = obj["error"].get("code", "unknown")
                raise UsageError(f"account usage unavailable (RPC code {code}); check client version and login")
            return obj.get("result")

    try:
        send({"method": "initialize", "id": 0,
              "params": {"clientInfo": {"name": "token_footprint", "title": "Token Footprint", "version": "0.1.0"},
                         "capabilities": {"experimentalApi": True}}})
        response(0)
        send({"method": "initialized", "params": {}})
        send({"method": "account/usage/read", "id": 1})
        return sanitize_account_usage(response(1))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        worker.join(timeout=1)
        proc.stdin.close()
        proc.stdout.close()
