"""Validated DAG state, deterministic scheduling and cooperative ownership claims."""

from __future__ import annotations

import re
from copy import deepcopy
from itertools import combinations
from pathlib import Path

from .catalog import roles
from .config import DEFAULT, limits, load_config
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
HANDOFF_FIELDS = {"schema_version", "task_id", "result", "changed_files", "decisions",
                  "tests", "failures", "risks", "artifacts"}


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


def validate_handoff(value: dict, task: dict, config: dict | None = None, *, completed: bool = False) -> dict:
    if not isinstance(value, dict) or set(value) != HANDOFF_FIELDS or type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise AgentBaseError("Handoff requires schema_version 1 and fields: " + ", ".join(sorted(HANDOFF_FIELDS)))
    if value["task_id"] != task["id"]:
        raise AgentBaseError("Handoff task_id does not match the target task.")
    if not isinstance(value["result"], str) or not value["result"].strip():
        raise AgentBaseError("Handoff result must describe the observed outcome.")
    for field in ("changed_files", "decisions", "failures", "risks", "artifacts"):
        string_list(value[field], "handoff." + field)
    seen = set()
    for name in value["changed_files"]:
        name = relative(name).casefold()
        if name in seen:
            raise AgentBaseError("Duplicate changed file in handoff.")
        seen.add(name)
        if not any(access == "write" and (scope == "." or name == scope or name.startswith(scope + "/"))
                   for kind, scope, access in claims(task) if kind == "file"):
            raise AgentBaseError("Handoff changed file is outside the task's write scope.")
    if not isinstance(value["tests"], list) or not value["tests"]:
        raise AgentBaseError("Handoff tests must include observations or explicit not-run checks.")
    for check in value["tests"]:
        if (not isinstance(check, dict) or set(check) != {"command", "status", "outcome"}
                or not isinstance(check["status"], str) or check["status"] not in {"passed", "failed", "not-run"}
                or any(not isinstance(check[key], str) or not check[key].strip() for key in ("command", "outcome"))):
            raise AgentBaseError("Each handoff test needs command, status (passed/failed/not-run), and observed outcome or reason.")
    if completed and (value["failures"] or any(check["status"] == "failed" for check in value["tests"])
                      or not any(check["status"] == "passed" for check in value["tests"])):
        raise AgentBaseError("Completion handoff needs an observed passed check and no unresolved failures.")
    if len(json_text(value)) > limits(config or DEFAULT)["max_handoff_chars"]:
        raise AgentBaseError("Handoff exceeds the configured character budget; reference concise artifacts.")
    return deepcopy(value)


def validate_plan(value: dict, config: dict | None = None) -> dict:
    if set(value) != {"schema_version", "tasks"} or value.get("schema_version") != 1 or not isinstance(value["tasks"], list):
        raise AgentBaseError("Task plan requires schema_version 1 and tasks array.")
    tasks = value["tasks"]
    if len(tasks) > 1000:
        raise AgentBaseError("Task plan exceeds 1000 tasks; archive a completed milestone first.")
    role_map = {r["id"]: r for r in roles()}
    by_id = {}
    for task in tasks:
        if not isinstance(task, dict) or set(task) not in (TASK_FIELDS, TASK_FIELDS | {"handoff"}):
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
        if "handoff" in task:
            if task["status"] not in {"review", "completed"}:
                raise AgentBaseError("Stored handoffs belong only to review/completed tasks.")
            validate_handoff(task["handoff"], task, config, completed=task["status"] == "completed")
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
               reason: str = "", handoff: dict | None = None) -> dict:
    with project_lock(root):
        config = load_config(root)
        plan = load_plan(root)
        by_id = {task["id"]: task for task in plan["tasks"]}
        if task_id not in by_id:
            raise AgentBaseError(f"Unknown task: {task_id}")
        task = by_id[task_id]
        if status not in TRANSITIONS[task["status"]]:
            raise AgentBaseError(f"Invalid transition: {task['status']} -> {status}; use tasks sync to promote pending tasks.")
        if handoff is not None:
            if status not in {"review", "completed"}:
                raise AgentBaseError("Supply a handoff only for review/completed transitions.")
            task["handoff"] = validate_handoff(handoff, task, config, completed=status == "completed")
        if status in {"review", "completed"}:
            if "handoff" not in task:
                raise AgentBaseError("Review/completion requires a validated handoff; supply --handoff-file FILE.")
            validate_handoff(task["handoff"], task, config, completed=status == "completed")
        else:
            # Yeniden çalışma eski devirle tamamlanamasın; yeni gözlem kaydedilmelidir.
            task.pop("handoff", None)
        if status == "running" and task["status"] == "review":
            task["verification"] = []
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
