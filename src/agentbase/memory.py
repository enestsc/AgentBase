"""Small durable notes and derived task summaries with source drift checks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import limits, load_config
from .context import read_source
from .explain import project_report, report_changes
from .fs import AgentBaseError, batch_write, confined, digest, json_text, project_lock, read_json
from .tasks import load_plan

CATEGORIES = ("overview", "decision", "milestone", "issue", "question", "relationship")
INDEX = ".agentbase/memory/evidence.json"
STATE = ".agentbase/memory/status.md"


def notes(root: Path) -> dict[str, str]:
    result = {}
    for name in (*CATEGORIES, "status"):
        path = confined(root, f".agentbase/memory/{name}.md")
        if path.exists():
            if path.stat().st_size > 1_000_000:
                raise AgentBaseError("Memory file exceeds 1 MB; curate/archive it manually.")
            result[name] = path.read_text(encoding="utf-8")
    return result


def index(root: Path) -> dict:
    path = confined(root, INDEX)
    value = read_json(path) if path.exists() else {"schema_version": 1, "entries": []}
    if set(value) != {"schema_version", "entries"} or value["schema_version"] != 1 or not isinstance(value["entries"], list):
        raise AgentBaseError("Unsupported memory evidence schema.")
    for record in value["entries"]:
        if (not isinstance(record, dict) or set(record) != {"category", "file", "line", "sha256"} or
                record["category"] not in CATEGORIES or not isinstance(record["file"], str) or
                type(record["line"]) is not int or record["line"] < 1 or
                not isinstance(record["sha256"], str)):
            raise AgentBaseError("Invalid memory evidence entry.")
    return value


def note(root: Path, category: str, text: str, evidence: str) -> dict:
    if category not in CATEGORIES or not text.strip():
        raise AgentBaseError("A supported category and nonempty note are required.")
    if len(text) > 2000:
        raise AgentBaseError("Keep each memory note within 2000 characters.")
    try:
        name, line_text = evidence.rsplit(":", 1)
        line = int(line_text)
    except (ValueError, TypeError) as exc:
        raise AgentBaseError("Evidence must be project-relative file:line.") from exc
    with project_lock(root):
        config = load_config(root)
        source, error = read_source(root, name, limits(config)["max_file_bytes"])
        if error or line < 1 or line > len(source.splitlines()):
            raise AgentBaseError("Evidence needs a readable, allowed source file and existing line.")
        current = notes(root)
        stamp = datetime.now(timezone.utc).date().isoformat()
        entry = f"\n- {stamp}: {text.strip()} (evidence: `{name}:{line}`, sha256 `{digest(source)[:12]}`)\n"
        body = current.get(category, f"# {category.capitalize()}\n") + entry
        if sum(map(len, current.values())) - len(current.get(category, "")) + len(body) > limits(config)["memory_max_chars"]:
            raise AgentBaseError("Memory budget reached; curate superseded notes before adding more.")
        evidence_index = index(root)
        record = {"category": category, "file": name, "line": line, "sha256": digest(source)}
        if record not in evidence_index["entries"]:
            evidence_index["entries"].append(record)
        if len(evidence_index["entries"]) > 500:
            raise AgentBaseError("Evidence index limit reached; curate stale entries first.")
        batch_write(root, {f".agentbase/memory/{category}.md": body, INDEX: json_text(evidence_index)})
    return record


def state_text(plan: dict) -> str:
    lines = ["# Current task state", "", "Derived from .agentbase/tasks.json; evidence is recorded by the host, not independently executed.", ""]
    for task in plan["tasks"]:
        lines.append(f"- {task['id']} [{task['status']}]: {task['description']}")
        if task["blocking_reason"]:
            lines.append("  Reason: " + task["blocking_reason"])
        for evidence in task["verification"]:
            lines.append("  Evidence: " + evidence)
    if not plan["tasks"]:
        lines.append("No coordinated tasks recorded. This does not imply that the project is complete.")
    return "\n".join(lines) + "\n"


def sync_memory(root: Path, *, deep: bool = False) -> dict:
    with project_lock(root):
        config = load_config(root)
        state = state_text(load_plan(root))
        current = notes(root)
        if sum(len(v) for k, v in current.items() if k != "status") + len(state) > limits(config)["memory_max_chars"]:
            raise AgentBaseError("Derived state exceeds memory budget; curate/archive completed work first.")
        changes = {STATE: state}
        drift = []
        if deep:
            for record in index(root)["entries"]:
                source, error = read_source(root, record["file"], limits(config)["max_file_bytes"])
                if error or digest(source) != record["sha256"]:
                    drift.append({"file": record["file"], "line": record["line"],
                                  "reason": error or "file hash changed; review semantic claim"})
            report, snapshot = project_report(root, config)
            changes.update(report_changes(root, report))
            changes[".agentbase/reports/evidence.json"] = json_text(snapshot)
            changes[".agentbase/reports/drift.json"] = json_text({"schema_version": 1, "drift": drift})
        batch_write(root, changes)
    return {"mode": "deep" if deep else "light", "updated": list(changes), "drift": drift,
            "decisions_rewritten": False}


def handoff(root: Path) -> str:
    config = load_config(root)
    parts = ["# Session handoff", "", state_text(load_plan(root)),
             "Next read: .agentbase/memory/overview.md, relevant source and current verification artifacts.", ""]
    for name, content in notes(root).items():
        if name != "status":
            parts.append(content)
    body = "\n".join(parts)
    cap = limits(config)["max_handoff_chars"]
    suffix = "\n[Handoff budget reached; omitted material requires selective retrieval.]\n"
    return body if len(body) <= cap else body[:max(0, cap - len(suffix))] + suffix[:cap]
