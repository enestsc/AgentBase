"""Validated DAG state, deterministic scheduling and cooperative ownership claims."""

from __future__ import annotations

import re
from copy import deepcopy
from itertools import combinations
from pathlib import Path

from .catalog import roles
from .config import limits, load_config
from .fs import AgentBaseError, batch_write, confined, json_text, project_lock, read_json, relative

PLAN = ".agentbase/tasks.json"
ACTIVE = {"running", "review"}
TRANSITIONS = {
    "pending": {"ready", "blocked"}, "ready": {"running", "blocked"},
    "running": {"review", "blocked", "failed"},
    "review": {"completed", "running", "blocked", "failed"},
    "blocked": {"pending"}, "failed": {"pending"}, "completed": set(),
}
TASK_FIELDS = {"id", "description", "role", "dependencies", "inputs", "outputs", "scope",
               "resources", "acceptance", "status", "verification", "blocking_reason"}


def string_list(value: object, label: str, *, nonempty: bool = False) -> None:
    if (not isinstance(value, list) or (nonempty and not value) or
            any(not isinstance(s, str) or not s.strip() for s in value)):
        raise AgentBaseError(f"{label} must be {'a nonempty' if nonempty else 'a'} string list.")


def claims(task: dict) -> list[tuple[str, str, str]]:
    return [("file", relative(s["path"], root_scope=True).casefold(), s["access"]) for s in task["scope"]] + [
        ("resource", s["name"].casefold(), s["access"]) for s in task["resources"]]


def overlap(a: str, b: str) -> bool:
    return a == "." or b == "." or a == b or a.startswith(b + "/") or b.startswith(a + "/")


def conflicts(a: dict, b: dict) -> list[str]:
    return sorted({f"{kind}:{left} <> {right}" for kind, left, access in claims(a)
                   for kind2, right, access2 in claims(b)
                   if kind == kind2 and "write" in (access, access2) and
                   (overlap(left, right) if kind == "file" else left == right)})


def is_writer(task: dict) -> bool:
    return any(access == "write" for _, _, access in claims(task))


def compatible(a: dict, b: dict) -> bool:
    # Deliberately conservative: v1 does not verify isolated worktrees or runtimes.
    return not conflicts(a, b) and not is_writer(a) and not is_writer(b)


def validate_plan(value: dict, config: dict | None = None) -> dict:
    if set(value) != {"schema_version", "tasks"} or value.get("schema_version") != 1 or not isinstance(value["tasks"], list):
        raise AgentBaseError("Task plan requires schema_version 1 and tasks array.")
    tasks = value["tasks"]
    if len(tasks) > 1000:
        raise AgentBaseError("Task plan exceeds 1000 tasks; archive a completed milestone first.")
    role_map = {r["id"]: r for r in roles()}
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict) or set(task) != TASK_FIELDS:
            raise AgentBaseError(f"Each task needs exactly these fields: {', '.join(sorted(TASK_FIELDS))}")
        task_id = task["id"]
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", task_id):
            raise AgentBaseError("Task ID must be a portable identifier (1..64 characters).")
        if task_id in by_id:
            raise AgentBaseError(f"Duplicate task ID: {task_id}")
        by_id[task_id] = task
        if not isinstance(task["description"], str) or not task["description"].strip():
            raise AgentBaseError(f"{task_id}: description required.")
        if not isinstance(task["role"], str) or task["role"] not in role_map:
            raise AgentBaseError(f"{task_id}: unknown role.")
        if not isinstance(task["status"], str) or task["status"] not in TRANSITIONS:
            raise AgentBaseError(f"{task_id}: invalid status.")
        for field in ("dependencies", "inputs", "outputs", "acceptance", "verification"):
            string_list(task[field], f"{task_id}.{field}", nonempty=field in ("inputs", "outputs", "acceptance"))
        if len(set(task["dependencies"])) != len(task["dependencies"]):
            raise AgentBaseError(f"{task_id}: duplicate dependency.")
        if not isinstance(task["blocking_reason"], str):
            raise AgentBaseError(f"{task_id}: blocking_reason must be a string.")
        if task["status"] in ("blocked", "failed") and not task["blocking_reason"].strip():
            raise AgentBaseError(f"{task_id}: blocked/failed state requires a reason.")
        if task["status"] == "completed" and not task["verification"]:
            raise AgentBaseError(f"{task_id}: completion requires observed verification evidence.")
        for field, key in (("scope", "path"), ("resources", "name")):
            if not isinstance(task[field], list) or (field == "scope" and not task[field]):
                raise AgentBaseError(f"{task_id}: scope must be nonempty; resources must be an array.")
            seen = set()
            for claim in task[field]:
                if (not isinstance(claim, dict) or set(claim) != {key, "access"} or
                        claim["access"] not in ("read", "write") or
                        not isinstance(claim[key], str) or not claim[key].strip()):
                    raise AgentBaseError(f"{task_id}: invalid {field} claim.")
                name = relative(claim[key], root_scope=True) if key == "path" else claim[key]
                if name.casefold() in seen:
                    raise AgentBaseError(f"{task_id}: duplicate {field} claim.")
                seen.add(name.casefold())
        if role_map[task["role"]]["access"] == "read" and is_writer(task):
            raise AgentBaseError(f"{task_id}: read-only role cannot own write claims.")
    for task in tasks:
        if any(dep not in by_id for dep in task["dependencies"]):
            raise AgentBaseError(f"{task['id']}: dependency does not exist.")
    # Kahn traversal avoids recursion limits on large valid plans.
    remaining = {task["id"]: set(task["dependencies"]) for task in tasks}
    while remaining:
        ready = sorted(key for key, deps in remaining.items() if not deps)
        if not ready:
            raise AgentBaseError("Circular task dependencies detected.")
        for key in ready:
            del remaining[key]
        for deps in remaining.values():
            deps.difference_update(ready)
    for task in tasks:
        if task["status"] in {"ready", "running", "review", "completed"} and not dependencies_done(task, by_id):
            raise AgentBaseError(f"{task['id']}: dependencies are not completed.")
    active = [task for task in tasks if task["status"] in ACTIVE]
    for a, b in combinations(active, 2):
        if not compatible(a, b):
            raise AgentBaseError(f"Incompatible active claims: {a['id']} and {b['id']} ({conflicts(a, b) or 'writers are serialized'}).")
    if config:
        count = config["execution"]["max_concurrency"]
        if len(active) > count:
            raise AgentBaseError("Active tasks exceed configured concurrency.")
    return deepcopy(value)


def dependencies_done(task: dict, by_id: dict) -> bool:
    return all(by_id[dep]["status"] == "completed" for dep in task["dependencies"])


def load_plan(root: Path) -> dict:
    return validate_plan(read_json(confined(root, PLAN)), load_config(root))


def schedule(plan: dict, config: dict) -> list[str]:
    plan = validate_plan(plan, config)
    tasks = plan["tasks"]
    by_id = {task["id"]: task for task in tasks}
    selected = [task for task in tasks if task["status"] in ACTIVE]
    result = []
    for task in sorted(tasks, key=lambda t: t["id"]):
        if len(selected) >= config["execution"]["max_concurrency"]:
            break
        if task["status"] not in ("pending", "ready") or not dependencies_done(task, by_id):
            continue
        if all(compatible(task, active) for active in selected):
            selected.append(task)
            result.append(task["id"])
    return result


def import_plan(root: Path, plan: dict) -> dict:
    with project_lock(root):
        if load_plan(root)["tasks"]:
            raise AgentBaseError("Existing nonempty task plan is preserved. Archive it explicitly before importing another milestone.")
        checked = validate_plan(plan, load_config(root))
        if any(task["status"] != "pending" for task in checked["tasks"]):
            raise AgentBaseError("Import only pending tasks; record transitions through the CLI.")
        batch_write(root, {PLAN: json_text(checked)})
    return checked


def sync(root: Path) -> dict:
    with project_lock(root):
        plan = load_plan(root)
        by_id = {task["id"]: task for task in plan["tasks"]}
        for task in plan["tasks"]:
            if task["status"] == "pending" and dependencies_done(task, by_id):
                task["status"] = "ready"
        batch_write(root, {PLAN: json_text(plan)})
    return plan


def transition(root: Path, task_id: str, status: str, *, evidence: list[str] | None = None,
               reason: str = "") -> dict:
    with project_lock(root):
        config = load_config(root)
        plan = load_plan(root)
        by_id = {task["id"]: task for task in plan["tasks"]}
        if task_id not in by_id:
            raise AgentBaseError(f"Unknown task: {task_id}")
        task = by_id[task_id]
        if status not in TRANSITIONS[task["status"]]:
            raise AgentBaseError(f"Invalid transition: {task['status']} -> {status}; use tasks sync to promote pending tasks.")
        if evidence:
            if sum(map(len, evidence)) > limits(config)["max_handoff_chars"]:
                raise AgentBaseError("Evidence exceeds the handoff budget; reference an artifact instead.")
            task["verification"].extend(evidence)
        task["status"] = status
        task["blocking_reason"] = reason if status in ("blocked", "failed") else ""
        if status == "pending":
            task["verification"] = []  # A retry needs fresh evidence.
        validate_plan(plan, config)
        batch_write(root, {PLAN: json_text(plan)})
    return task
