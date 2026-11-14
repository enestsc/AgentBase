"""Opt-in local, allowlisted usage imports. No prompts, credentials or telemetry upload.

Adapters accept explicitly captured documented messages inside a versioned capture
envelope. Capture metadata is user supplied, not scraped from private session files.
"""

from __future__ import annotations

import csv
import io
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .fs import AgentBaseError, batch_write, confined, digest, json_text, project_lock, read_json

CONFIG = ".agentbase/usage/config.json"
DATA = ".agentbase/usage/records.json"
SOURCES = {"codex-exec-v1", "codex-app-server-v1", "claude-api-request-v1", "claude-statusline-v1"}
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "cache_creation_tokens", "reasoning_tokens")


def timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone missing")
        return result.astimezone(UTC)
    except (ValueError, AttributeError, OverflowError) as exc:
        raise AgentBaseError("Usage timestamps must be ISO 8601 with an explicit timezone.") from exc


def identifier(value: object, field: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or any(ord(c) < 32 for c in value):
        raise AgentBaseError(f"Invalid usage {field}; use short opaque identifiers, never private text.")
    return value


def number(value: object, field: str, *, integer: bool = True) -> int | float | None:
    if value is None:
        return None
    if type(value) not in ({int} if integer else {int, float}) or not 0 <= value <= 10**15 or not math.isfinite(value):
        raise AgentBaseError(f"Invalid nonnegative usage metric: {field}")
    return value


def configure(root: Path, sources: list[str], *, retention_days: int = 30) -> dict:
    if set(sources) - SOURCES or type(retention_days) is not int or not 1 <= retention_days <= 3650:
        raise AgentBaseError("Choose supported usage sources and retention 1..3650 days.")
    value = {"schema_version": 1, "sources": sorted(set(sources)), "retention_days": retention_days}
    with project_lock(root):
        batch_write(root, {CONFIG: json_text(value)})
        private(root)
    return value | {"collection": "explicit imports only", "upload": False}


def private(root: Path) -> None:
    # POSIX owner-only permissions. Windows inherits the project ACL: documented,
    # never represented as a private ACL guarantee. Users must protect their checkout.
    for name, mode in [(".agentbase/usage", 0o700), (CONFIG, 0o600), (DATA, 0o600)]:
        path = confined(root, name)
        if path.exists():
            path.chmod(mode)


def settings(root: Path) -> dict:
    if not confined(root, CONFIG).is_file():
        raise AgentBaseError("Usage is disabled. Opt in with `agentbase usage configure --source SOURCE`.")
    value = read_json(confined(root, CONFIG))
    if (value.get("schema_version") != 1 or not isinstance(value.get("sources"), list)
            or any(s not in SOURCES for s in value["sources"]) or type(value.get("retention_days")) is not int
            or not 1 <= value["retention_days"] <= 3650):
        raise AgentBaseError("Invalid usage configuration.")
    return value


def records(root: Path) -> list[dict]:
    if not confined(root, DATA).exists():
        return []
    value = read_json(confined(root, DATA))
    if value.get("schema_version") != 1 or not isinstance(value.get("records"), list):
        raise AgentBaseError("Unsupported usage data schema.")
    for record in value["records"]:
        if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
            raise AgentBaseError("Invalid usage record fields.")
        timestamp(record["timestamp"])
        for key in TOKEN_FIELDS:
            number(record[key], key)
    return value["records"]


RECORD_FIELDS = {"id", "source", "provider", "provider_version", "project_id", "session_id", "event_id",
                 "timestamp", "model", "agent_id", "skill_id", "correlation_id", "reliability", "kind",
                 "estimated_cost_usd", "billed_usd", "context_tokens", "context_capacity", "duration_ms", "tool_calls",
                 "provenance", *TOKEN_FIELDS}


def normalize(envelope: dict) -> dict:
    if (not isinstance(envelope, dict) or envelope.get("schema_version") != 1
            or not isinstance(envelope.get("source"), str) or envelope["source"] not in SOURCES):
        raise AgentBaseError("Expected schema_version 1 usage capture envelope and supported source.")
    source = envelope["source"]
    provider = "codex" if source.startswith("codex") else "claude"
    event = envelope.get("event")
    if not isinstance(event, dict):
        raise AgentBaseError("Usage capture requires an event object.")
    record = dict.fromkeys(RECORD_FIELDS)
    record.update(source=source, provider=provider, reliability="provider-reported", kind="increment",
                  provenance="explicit user-authorized capture; adapter v1")
    for key in ("session_id", "event_id", "project_id", "provider_version"):
        record[key] = identifier(envelope.get(key), key, required=True)
    record["timestamp"] = timestamp(envelope.get("timestamp")).isoformat()
    record["model"] = identifier(envelope.get("model"), "model")
    # Attribution is permitted only with an explicit AgentBase correlation contract.
    correlation = envelope.get("agentbase_correlation")
    if correlation is not None:
        if not isinstance(correlation, dict):
            raise AgentBaseError("Invalid explicit correlation.")
        record["correlation_id"] = identifier(correlation.get("id"), "correlation id", required=True)
        record["agent_id"] = identifier(correlation.get("agent_id"), "agent id")
        record["skill_id"] = identifier(correlation.get("skill_id"), "skill id")
    usage = {}
    if source == "codex-exec-v1":
        if event.get("type") != "turn.completed" or not isinstance(event.get("usage"), dict):
            raise AgentBaseError("Expected Codex exec turn.completed with usage.")
        usage = event["usage"]
        usage = usage | {"reasoning_tokens": usage.get("reasoning_output_tokens")}
    elif source == "codex-app-server-v1":
        params = event.get("params", {})
        if event.get("method") != "thread/tokenUsage/updated" or not isinstance(params, dict):
            raise AgentBaseError("Expected Codex App Server token usage notification.")
        token_usage = params.get("tokenUsage", {})
        total = token_usage.get("total") if isinstance(token_usage, dict) else None
        if not isinstance(total, dict) or params.get("threadId") != record["session_id"]:
            raise AgentBaseError("Expected cumulative tokenUsage.total and matching threadId.")
        usage = {dest: total.get(src) for src, dest in [("inputTokens", "input_tokens"), ("outputTokens", "output_tokens"),
                  ("cachedInputTokens", "cached_input_tokens"), ("cacheWriteInputTokens", "cache_creation_tokens"),
                  ("reasoningOutputTokens", "reasoning_tokens")]}
        record["context_capacity"] = number(token_usage.get("modelContextWindow"), "modelContextWindow")
        record["kind"] = "cumulative"
    elif source == "claude-api-request-v1":
        # A decoded OTel api_request attributes object, not an OTLP transport parser.
        if event.get("event.name") != "api_request":
            raise AgentBaseError("Expected Claude Code api_request attributes.")
        if event.get("session.id") not in {None, record["session_id"]}:
            raise AgentBaseError("Claude event session does not match capture.")
        usage = {dest: event.get(src) for src, dest in [("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                  ("cache_read_tokens", "cached_input_tokens"), ("cache_creation_tokens", "cache_creation_tokens")]}
        record["model"] = identifier(event.get("model", record["model"]), "model")
        record["estimated_cost_usd"] = number(event.get("cost_usd"), "cost_usd", integer=False)
        record["duration_ms"] = number(event.get("duration_ms"), "duration_ms")
        if event.get("request_id") is not None:
            record["event_id"] = identifier(event["request_id"], "request_id", required=True)
        # Provider-native attribution is evidence when non-redacted. Generic
        # redaction placeholders cannot identify an AgentBase role or skill.
        for src, dest in (("agent.name", "agent_id"), ("skill.name", "skill_id")):
            if event.get(src) not in (None, "custom", "third-party"):
                record[dest] = identifier(event[src], dest)
    else:
        # Statusline token fields describe context occupancy, not session consumption.
        if event.get("session_id") != record["session_id"]:
            raise AgentBaseError("Statusline session_id does not match capture.")
        context, cost = event.get("context_window", {}), event.get("cost", {})
        if not isinstance(context, dict) or not isinstance(cost, dict):
            raise AgentBaseError("Invalid statusline context/cost.")
        inp = number(context.get("total_input_tokens"), "context input")
        out = number(context.get("total_output_tokens"), "context output")
        record["context_tokens"] = inp + out if inp is not None and out is not None else None
        record["context_capacity"] = number(context.get("context_window_size"), "context capacity")
        record["estimated_cost_usd"] = number(cost.get("total_cost_usd"), "estimated cost", integer=False)
        record["duration_ms"] = number(cost.get("total_duration_ms"), "duration")
        model = event.get("model", {})
        if isinstance(model, dict):
            record["model"] = identifier(model.get("id", record["model"]), "model")
        record["kind"] = "context-snapshot"
    for key in TOKEN_FIELDS:
        record[key] = number(usage.get(key), key)
    # No provider offers actual billing/plan quota in these events.
    record["id"] = digest(json_text([source, record["project_id"], record["session_id"], record["event_id"]]))
    return record


def capture_event(root: Path, source: str, event: dict, *, provider_version: str, project_id: str,
                  session_id: str | None = None, event_id: str | None = None, now: datetime | None = None) -> dict:
    """Explicit stdin integration; no provider launch, private logs, or raw storage."""
    if source not in settings(root)["sources"]:
        raise AgentBaseError("This usage source is not opted in.")
    if not isinstance(event, dict):
        raise AgentBaseError("Capture requires a supported JSON event object.")
    if source == "claude-statusline-v1":
        session_id = session_id or event.get("session_id")
    elif source == "codex-app-server-v1" and isinstance(event.get("params"), dict):
        session_id = session_id or event["params"].get("threadId")
    if source in {"codex-exec-v1", "claude-api-request-v1"} and event_id is None:
        raise AgentBaseError("Incremental captures require an explicit stable --event-id; repeated equal counters may be different requests.")
    envelope = {"schema_version": 1, "source": source, "event": event, "provider_version": provider_version,
                "project_id": project_id, "session_id": session_id, "event_id": event_id or "observation",
                "timestamp": (now or datetime.now(UTC)).isoformat()}
    normalized = normalize(envelope)
    observation = event_id is None
    if observation:
        envelope["event_id"] = digest(json_text({k: normalized[k] for k in sorted(normalized) if k not in {"id", "event_id", "timestamp"}}))
    return ingest(root, [envelope], now=now, observation_identity=observation)


def ingest(root: Path, captures: list[dict], *, now: datetime | None = None, observation_identity: bool = False) -> dict:
    if not isinstance(captures, list) or len(captures) > 10_000:
        raise AgentBaseError("Import at most 10000 capture envelopes.")
    normalized = [normalize(c) for c in captures]
    with project_lock(root):
        config = settings(root)
        if {r["source"] for r in normalized} - set(config["sources"]):
            raise AgentBaseError("This usage source is not opted in.")
        existing = {r["id"]: r for r in records(root)}
        added = 0
        for record in normalized:
            if record["id"] in existing:
                prior = existing[record["id"]]
                if observation_identity:
                    prior = prior | {"timestamp": record["timestamp"]}
                if prior != record:
                    raise AgentBaseError("Usage event ID reused with different data; import rejected.")
                continue
            existing[record["id"]] = record
            added += 1
        cutoff = (now or datetime.now(UTC)) - timedelta(days=config["retention_days"])
        kept = [r for r in existing.values() if timestamp(r["timestamp"]) >= cutoff]
        body = json_text({"schema_version": 1, "records": sorted(kept, key=lambda r: (r["timestamp"], r["id"]))})
        if len(body.encode("utf-8")) > 3_900_000:
            raise AgentBaseError("Usage store nearing 4 MB; export and delete older data before importing.")
        batch_write(root, {DATA: body})
        private(root)
    return {"imported": added, "duplicates": len(normalized) - added, "retained": len(kept), "raw_events_saved": False}


def zone(value: str):
    if value == "UTC":
        return UTC
    if value == "local":
        return datetime.now().astimezone().tzinfo
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise AgentBaseError("Timezone unavailable; use UTC/local or install system timezone data.") from exc


def report(root: Path, *, period: str | None = None, provider: str | None = None, by: str = "model",
           timezone: str = "local", now: datetime | None = None) -> dict:
    config = settings(root)
    tz = zone(timezone)
    current = (now or datetime.now(UTC)).astimezone(tz)
    cutoff = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        cutoff -= timedelta(days=6)
    retention = current.astimezone(UTC) - timedelta(days=config["retention_days"])
    raw = [r for r in records(root) if r["source"] in config["sources"] and timestamp(r["timestamp"]) >= retention]
    # Only overlapping consumption streams compete. Context observations have
    # separate semantics and can coexist with request-token counters.
    sessions = {}
    for r in raw:
        if r["kind"] != "context-snapshot":
            sessions.setdefault((r["provider"], r["project_id"], r["session_id"]), set()).add(r["source"])
    ambiguous = {k for k, s in sessions.items() if len(s) > 1}
    warnings = []
    if ambiguous:
        warnings.append("Multiple sources for the same session: excluded from totals to prevent double counting.")
    rows, groups, daily = [], {}, {}
    cumulative, unallocated = {}, []
    for r in sorted(raw, key=lambda r: (r["timestamp"], r["id"])):
        key = (r["provider"], r["project_id"], r["session_id"])
        if (key in ambiguous and r["kind"] != "context-snapshot") or (provider and r["provider"] != provider):
            continue
        delta = dict(r)
        if r["kind"] == "cumulative":
            previous = cumulative.get(key)
            for field in TOKEN_FIELDS:
                v, p = r[field], previous[field] if previous else None
                # First cumulative sample has no reliable period allocation. Keep
                # snapshot exported but require two observations to form a delta.
                delta[field] = v - p if v is not None and p is not None and v >= p else None
                if v is not None and p is not None and v < p:
                    warnings.append("Counter decreased; delta unknown until next valid sample.")
            cumulative[key] = r
            if not previous or not r["correlation_id"] or previous["correlation_id"] != r["correlation_id"]:
                delta.update(agent_id=None, skill_id=None, correlation_id=None)
            elif any(previous[field] != r[field] for field in ("agent_id", "skill_id", "model")):
                delta.update(agent_id=None, skill_id=None, correlation_id=None)
            if previous and timestamp(previous["timestamp"]).astimezone(tz).date() != timestamp(r["timestamp"]).astimezone(tz).date():
                delta["cross_day"] = True
                if not period or timestamp(r["timestamp"]).astimezone(tz) >= cutoff:
                    unallocated.append({"provider": r["provider"], "project_id": r["project_id"], "session_id": r["session_id"],
                                        "from": previous["timestamp"], "to": r["timestamp"],
                                        "tokens": {f: delta[f] for f in TOKEN_FIELDS}})
                    warnings.append("Cross-day cumulative intervals have unknown daily allocation; inspect unallocated_intervals.")
                if period and timestamp(previous["timestamp"]).astimezone(tz) < cutoff:
                    for field in TOKEN_FIELDS:
                        delta[field] = None
        if period and timestamp(r["timestamp"]).astimezone(tz) < cutoff:
            continue
        rows.append(delta)
        group = delta.get(by) or "unattributed"
        groups.setdefault(group, []).append(delta)
        day = timestamp(r["timestamp"]).astimezone(tz).date().isoformat()
        daily.setdefault(day, []).append(delta | dict.fromkeys(TOKEN_FIELDS) if delta.get("cross_day") else delta)

    def totals(values):
        return {field: {"known_total": sum(r[field] for r in values if r[field] is not None) if any(r[field] is not None for r in values) else None,
                        "unknown_records": sum(r[field] is None for r in values)} for field in TOKEN_FIELDS}

    request_costs = [r["estimated_cost_usd"] for r in rows if r["kind"] == "increment"]
    snapshots = {}
    for r in rows:
        if r["kind"] == "context-snapshot":
            snapshots[(r["project_id"], r["session_id"])] = {key: r[key] for key in (
                "provider", "project_id", "session_id", "timestamp", "model", "context_tokens", "context_capacity",
                "estimated_cost_usd", "duration_ms")}
    return {"records": len(rows), "timezone": timezone, "period": period or "retained", "totals": totals(rows),
            "by": by, "groups": {k: totals(v) for k, v in groups.items()}, "daily": {k: totals(v) for k, v in daily.items()},
            "providers": {p: totals([r for r in rows if r["provider"] == p]) for p in sorted({r["provider"] for r in rows})},
            "projects": {p: totals([r for r in rows if r["project_id"] == p]) for p in sorted({r["project_id"] for r in rows})},
            "estimated_request_cost_usd": {"known_total": sum(v for v in request_costs if v is not None) if any(v is not None for v in request_costs) else None,
                                           "unknown_records": sum(v is None for v in request_costs)},
            "latest_session_context": list(snapshots.values()),
            "unallocated_intervals": unallocated,
            "warnings": sorted(set(warnings + ["Missing values are unknown. Attribution requires explicit correlation; no token savings baseline measured."])),
            "subscription_remaining": "not available", "actual_billed_amount": None,
            "cost_note": "Provider estimates are exported separately; context snapshots are not consumed tokens."}


def render_table(value: dict) -> str:
    lines = [f"Usage ({value['period']}, {value['timezone']})", f"{value['by']:<28} {'input known':>14} {'output known':>14} {'unknown records':>16}"]
    for name, metrics in value["groups"].items():
        inp, out = metrics["input_tokens"], metrics["output_tokens"]
        lines.append(f"{name:<28} {str(inp['known_total']):>14} {str(out['known_total']):>14} {max(inp['unknown_records'], out['unknown_records']):>16}")
    cost = value["estimated_request_cost_usd"]
    return "\n".join([*lines, f"Estimated request cost, known subtotal USD: {cost['known_total']} (unknown records: {cost['unknown_records']})",
                      *value["warnings"], "Subscription quota: not available"]) + "\n"


def export(root: Path, *, csv_format: bool = False) -> str | dict:
    config = settings(root)
    cutoff = datetime.now(UTC) - timedelta(days=config["retention_days"])
    values = [r for r in records(root) if r["source"] in config["sources"] and timestamp(r["timestamp"]) >= cutoff]
    if not csv_format:
        return {"schema_version": 1, "records": values}
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=sorted(RECORD_FIELDS))
    writer.writeheader()
    # Keep untrusted identifiers from becoming formulas when opened in a spreadsheet.
    writer.writerows({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
                      for key, value in record.items()} for record in values)
    return output.getvalue()


def delete(root: Path, *, before: str | None = None, all_data: bool = False) -> dict:
    if not before and not all_data:
        raise AgentBaseError("Specify --before timezone-aware timestamp or --all to delete local usage data.")
    with project_lock(root):
        settings(root)
        old = records(root)
        kept = [r for r in old if timestamp(r["timestamp"]) >= timestamp(before)] if before and not all_data else []
        batch_write(root, {DATA: json_text({"schema_version": 1, "records": kept})})
        private(root)
    return {"deleted": len(old) - len(kept), "retained": len(kept)}
