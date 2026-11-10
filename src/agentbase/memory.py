"""Small durable notes and derived task summaries with source drift checks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

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
                raise AgentBaseError("Memory file exceeds 1 MB; review/archive it explicitly.")
            result[name] = path.read_bytes().decode("utf-8")
    return result


def index(root: Path) -> dict:
    path = confined(root, INDEX)
    value = read_json(path) if path.exists() else {"schema_version": 1, "entries": []}
    if value.get("schema_version") == 1 and set(value) == {"schema_version", "entries"}:
        # Eski kanıtlar korunur; kimliği olmayan notların sahipliği varsayılmaz.
        value = value | {"schema_version": 2, "managed_notes": []}
    if (set(value) != {"schema_version", "entries", "managed_notes"} or value["schema_version"] != 2
            or not isinstance(value["entries"], list) or not isinstance(value["managed_notes"], list)):
        raise AgentBaseError("Unsupported memory evidence schema.")
    for record in value["entries"]:
        if (not isinstance(record, dict) or set(record) != {"category", "file", "line", "sha256"} or
                record["category"] not in CATEGORIES or not isinstance(record["file"], str) or
                type(record["line"]) is not int or record["line"] < 1 or
                not isinstance(record["sha256"], str)):
            raise AgentBaseError("Invalid memory evidence entry.")
    seen = set()
    for item in value["managed_notes"]:
        if (not isinstance(item, dict) or set(item) != {"id", "category", "entry", "evidence"}
                or not isinstance(item["id"], str) or len(item["id"]) != 32
                or any(c not in "0123456789abcdef" for c in item["id"])
                or item["id"] in seen or item["category"] not in CATEGORIES
                or not isinstance(item["entry"], str) or not item["entry"].strip()
                or not isinstance(item["evidence"], dict) or item["evidence"] not in value["entries"]
                or item["evidence"]["category"] != item["category"]
                or f"<!-- agentbase-note:{item['id']} -->" not in item["entry"]):
            raise AgentBaseError("Invalid managed memory note.")
        seen.add(item["id"])
    return value


def append_note(root: Path, category: str, text: str, evidence: str,
                config: dict, current: dict, evidence_index: dict) -> dict:
    if category not in CATEGORIES or not text.strip():
        raise AgentBaseError("A supported category and nonempty note are required.")
    if len(text) > 2000:
        raise AgentBaseError("Keep each memory note within 2000 characters.")
    try:
        name, line_text = evidence.rsplit(":", 1)
        line = int(line_text)
    except (ValueError, TypeError) as exc:
        raise AgentBaseError("Evidence must be project-relative file:line.") from exc
    source, error = read_source(root, name, limits(config)["max_file_bytes"])
    if error or line < 1 or line > len(source.splitlines()):
        raise AgentBaseError("Evidence needs a readable, allowed source file and existing line.")
    stamp = datetime.now(UTC).date().isoformat()
    note_id = uuid4().hex
    entry = (f"\n<!-- agentbase-note:{note_id} -->\n"
             f"- {stamp}: {text.strip()} (evidence: `{name}:{line}`, sha256 `{digest(source)[:12]}`)\n")
    body = current.get(category, f"# {category.capitalize()}\n") + entry
    if sum(map(len, current.values())) - len(current.get(category, "")) + len(body) > limits(config)["memory_max_chars"]:
        raise AgentBaseError("Memory budget reached; use memory list, then prune/supersede --dry-run on explicit IDs.")
    record = {"category": category, "file": name, "line": line, "sha256": digest(source)}
    if record not in evidence_index["entries"]:
        evidence_index["entries"].append(record)
    if len(evidence_index["entries"]) > 500:
        raise AgentBaseError("Evidence index limit reached; use memory prune/supersede --dry-run.")
    current[category] = body
    evidence_index["managed_notes"].append({"id": note_id, "category": category, "entry": entry, "evidence": record})
    return record | {"id": note_id}


def note(root: Path, category: str, text: str, evidence: str) -> dict:
    with project_lock(root):
        current, evidence_index = notes(root), index(root)
        record = append_note(root, category, text, evidence, load_config(root), current, evidence_index)
        batch_write(root, {f".agentbase/memory/{category}.md": current[category], INDEX: json_text(evidence_index)})
    return record


def list_notes(root: Path) -> dict:
    current = notes(root)
    return {"notes": [{"id": item["id"], "category": item["category"], "entry": item["entry"],
                       "intact": current.get(item["category"], "").count(item["entry"]) == 1}
                      for item in index(root)["managed_notes"]],
            "untracked_notes": "Legacy and manual notes are preserved; only tracked intact IDs can be maintained."}


def maintain(root: Path, ids: list[str], reason: str, *, text: str | None = None,
             evidence: str | None = None, dry_run: bool = False) -> dict:
    if not ids or len(set(ids)) != len(ids) or not reason.strip():
        raise AgentBaseError("Select unique note IDs and provide a nonempty --reason.")
    if (text is None) != (evidence is None) or (text is not None and len(ids) != 1):
        raise AgentBaseError("Supersede needs one ID, replacement text and evidence.")
    with project_lock(root):
        config, current, evidence_index = load_config(root), notes(root), index(root)
        selected = [item for item in evidence_index["managed_notes"] if item["id"] in ids]
        if len(selected) != len(ids):
            raise AgentBaseError("Unknown note ID; use memory list. Legacy/manual notes are preserved.")
        for item in selected:
            category, entry = item["category"], item["entry"]
            if current.get(category, "").count(entry) != 1:
                raise AgentBaseError("Preserving edited, missing or ambiguous note; review it manually.")
            # Yalnızca kaydedilen tam blok çıkarılır; çevresindeki kullanıcı metni korunur.
            current[category] = current[category].replace(entry, "", 1)
        evidence_index["managed_notes"] = [item for item in evidence_index["managed_notes"] if item["id"] not in ids]
        for item in selected:
            record = item["evidence"]
            referenced = any(other["evidence"] == record for other in evidence_index["managed_notes"])
            # Eski/elle yazılmış notların başvuruları da kanıt kaydını yaşatır.
            referenced |= f"{record['file']}:{record['line']}" in current.get(record["category"], "")
            if not referenced and record in evidence_index["entries"]:
                evidence_index["entries"].remove(record)
        replacement = None
        if text is not None:
            replacement = append_note(root, selected[0]["category"], text, evidence, config, current, evidence_index)
        archive = {"schema_version": 1, "action": "supersede" if text is not None else "prune",
                   "reason": reason, "notes": selected, "replacement": replacement}
        archive_body = json_text(archive)
        archive_name = f".agentbase/memory/archive/{digest(archive_body)}.json"
        if confined(root, archive_name).exists():
            raise AgentBaseError("Archive collision; preserving existing archive.")
        changes = {f".agentbase/memory/{item['category']}.md": current[item["category"]] for item in selected}
        changes.update({archive_name: archive_body, INDEX: json_text(evidence_index)})
        result = {"dry_run": dry_run, "action": archive["action"], "selected": selected,
                  "archive": archive_name, "updated": list(changes), "replacement": replacement}
        if not dry_run:
            batch_write(root, changes)
    return result


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
            raise AgentBaseError("Derived state exceeds memory budget; review memory prune/supersede --dry-run or task artifacts.")
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
