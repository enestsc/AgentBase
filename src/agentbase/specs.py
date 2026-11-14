"""Editable Markdown specifications compiled into the existing task DAG schema."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from itertools import combinations
from pathlib import Path

from . import tasks
from .config import DEFAULT, load_config
from .fs import AgentBaseError, batch_write, confined, digest, json_text, project_lock, read_json

FENCE = re.compile(r"^```agentbase-spec\s*\n(.*?)^```\s*$", re.M | re.S)


definition = tasks.definition


def binding(spec_id: str, result: dict) -> dict:
    return {"schema_version": 1, "specification": location(spec_id), "sha256": result["traceability"]["sha256"],
            "definitions": {t["id"]: definition(t) for t in result["plan"]["tasks"]}}


def managed(root: Path, spec_id: str, suffix: str) -> dict:
    location(spec_id)
    name = f".agentbase/specs/{spec_id}.{suffix}.json"
    manifest = read_json(confined(root, f".agentbase/specs/{spec_id}.generated.json"))
    path = confined(root, name)
    if not path.is_file() or digest(path.read_bytes()) != manifest.get("files", {}).get(name):
        raise AgentBaseError("Preserving locally edited or missing active specification state; import a new milestone explicitly.")
    return read_json(path)


def location(spec_id: str) -> str:
    if not isinstance(spec_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", spec_id) or len(spec_id) > 64:
        raise AgentBaseError("Specification ID must be lowercase kebab-case (1..64 characters).")
    return f".agentbase/specs/{spec_id}.md"


def initialize(root: Path, spec_id: str, title: str, request: str, criteria: list[str], role: str,
               scope: str, *, dry_run: bool = False) -> dict:
    name = location(spec_id)
    spec = {"schema_version": 1, "id": spec_id, "title": title, "assumptions": [], "architecture_impact": [],
            "requirements": [{"id": "R1", "statement": request, "acceptance": criteria, "role": role,
                              "scope": [{"path": scope, "access": "write"}], "dependencies": [], "conflicts_with": []}]}
    compile_plan(spec)
    text = (f"# {title}\n\nStatus: proposed; review assumptions, architecture impact and acceptance criteria.\n\n"
            "The fenced block is the authoritative editable specification. Dependencies\n"
            "refer to requirement IDs. Contradictions require explicit resolution.\n\n"
            f"```agentbase-spec\n{json_text(spec)}```\n")
    if confined(root, name).exists():
        raise AgentBaseError("Existing specification preserved; edit it incrementally.")
    if not dry_run:
        with project_lock(root):
            if confined(root, name).exists():
                raise AgentBaseError("Existing specification preserved.")
            batch_write(root, {name: text})
    return {"path": name, "dry_run": dry_run, "status": "proposed", "content": text}


def read(root: Path, spec_id: str) -> tuple[dict, str]:
    path = confined(root, location(spec_id))
    if not path.is_file() or path.stat().st_size > 500_000:
        raise AgentBaseError("Expected a specification Markdown file under 500 KB.")
    text = path.read_text(encoding="utf-8")
    blocks = FENCE.findall(text)
    if len(blocks) != 1:
        raise AgentBaseError("Specification requires exactly one agentbase-spec fenced JSON object.")
    try:
        value = json.loads(blocks[0])
    except ValueError as exc:
        raise AgentBaseError("Invalid specification JSON.") from exc
    if not isinstance(value, dict) or value.get("id") != spec_id:
        raise AgentBaseError("Specification identity does not match its filename.")
    return value, digest(text)


def compile_plan(spec: dict, config: dict | None = None) -> dict:
    if (not isinstance(spec, dict) or set(spec) != {"schema_version", "id", "title", "assumptions", "architecture_impact", "requirements"}
            or spec["schema_version"] != 1):
        raise AgentBaseError("Unsupported specification schema.")
    location(spec["id"])
    if not isinstance(spec["title"], str) or not spec["title"].strip():
        raise AgentBaseError("Specification title required.")
    for field in ("assumptions", "architecture_impact"):
        tasks.string_list(spec[field], field)
    requirements = spec["requirements"]
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 100:
        raise AgentBaseError("Specification requires 1..100 explicit requirements.")
    plan = {"schema_version": 1, "tasks": []}
    for req in requirements:
        if not isinstance(req, dict) or set(req) != {"id", "statement", "acceptance", "role", "scope", "dependencies", "conflicts_with"}:
            raise AgentBaseError("Each requirement needs id, statement, acceptance, role, scope, dependencies and conflicts_with.")
        if not isinstance(req["id"], str) or not re.fullmatch(r"R[1-9][0-9]{0,2}", req["id"]):
            raise AgentBaseError("Requirement IDs must be R1..R999.")
        tasks.string_list(req["dependencies"], "requirement dependencies")
        tasks.string_list(req["conflicts_with"], "conflicts_with")
        if req["conflicts_with"]:
            raise AgentBaseError(f"Resolve declared contradictory requirements: {req['id']} -> {req['conflicts_with']}")
        plan["tasks"].append({"id": req["id"], "description": req["statement"], "role": req["role"],
                              "dependencies": req["dependencies"], "inputs": [location(spec["id"]) + "#" + req["id"]],
                              "outputs": [f"Implementation and acceptance evidence for {req['id']}"],
                              "scope": req["scope"], "resources": [], "acceptance": req["acceptance"],
                              "status": "pending", "verification": [], "blocking_reason": ""})
    plan = tasks.validate_plan(plan, config or DEFAULT)
    by_id = {t["id"]: t for t in plan["tasks"]}

    def ancestors(task_id):
        result, pending = set(), list(by_id[task_id]["dependencies"])
        while pending:
            item = pending.pop()
            if item not in result:
                result.add(item)
                pending.extend(by_id[item]["dependencies"])
        return result

    for left, right in combinations(plan["tasks"], 2):
        if tasks.conflicts(left, right) and left["id"] not in ancestors(right["id"]) and right["id"] not in ancestors(left["id"]):
            raise AgentBaseError("Ambiguous file ownership: add a dependency between " + left["id"] + " and " + right["id"])
    return plan


def generated_changes(root: Path, spec_id: str, contents: dict[str, str]) -> dict[str, str]:
    """Hash-track regenerable proposals so handwritten/edited output is preserved."""
    manifest = f".agentbase/specs/{spec_id}.generated.json"
    old = read_json(confined(root, manifest)) if confined(root, manifest).exists() else {"schema_version": 1, "files": {}}
    allowed = {f".agentbase/specs/{spec_id}.{suffix}.json" for suffix in ("plan", "trace", "active", "evidence")}
    if old.get("schema_version") != 1 or not isinstance(old.get("files"), dict) or set(old["files"]) - allowed:
        raise AgentBaseError("Invalid specification proposal manifest.")
    hashes = dict(old["files"])
    for name, content in contents.items():
        if name not in allowed:
            raise AgentBaseError("Invalid generated specification path.")
        path = confined(root, name)
        if path.exists() and (not path.is_file() or digest(path.read_bytes()) != hashes.get(name)):
            raise AgentBaseError("Preserving locally edited or unmanaged specification output: " + name)
        hashes[name] = digest(content)
    return contents | {manifest: json_text({"schema_version": 1, "files": hashes})}


def proposal(root: Path, spec_id: str, *, write: bool = False, import_tasks: bool = False) -> dict:
    def prepare():
        spec, spec_hash = read(root, spec_id)
        config = load_config(root) if confined(root, ".agentbase/config.json").exists() else DEFAULT
        plan = compile_plan(spec, config)
        trace = {"schema_version": 1, "specification": location(spec_id), "sha256": spec_hash,
                 "requirements": {r["id"]: {"task_id": r["id"], "acceptance": r["acceptance"], "test_evidence": "required in task handoff before completion"}
                                  for r in spec["requirements"]}}
        return {"plan": plan, "traceability": trace, "executes_tasks": False,
                "limitations": ["Deterministic compilation of explicit requirements; natural-language contradictions require human review."]}
    if import_tasks:
        # One lock/transaction covers spec hash, trace and the existing DAG store.
        with project_lock(root):
            result = prepare()
            if tasks.load_plan(root)["tasks"]:
                raise AgentBaseError("Existing task plan preserved; archive the previous milestone before importing specifications.")
            changes = generated_changes(root, spec_id, {f".agentbase/specs/{spec_id}.trace.json": json_text(result["traceability"]),
                                                       f".agentbase/specs/{spec_id}.active.json": json_text(binding(spec_id, result))})
            batch_write(root, changes | {tasks.PLAN: json_text(result["plan"])})
        return result | {"imported": True}
    if write:
        with project_lock(root):
            result = prepare()
            # Generated proposals are regenerable; handwritten Markdown stays intact.
            batch_write(root, generated_changes(root, spec_id, {f".agentbase/specs/{spec_id}.plan.json": json_text(result["plan"]),
                               f".agentbase/specs/{spec_id}.trace.json": json_text(result["traceability"])}))
        return result
    return prepare()


def reconcile(root: Path, spec_id: str, *, apply: bool = False, expected_plan: str | None = None) -> dict:
    """Merge owned, unstarted tasks into the existing DAG; preserve runtime evidence."""
    def prepare():
        result = proposal(root, spec_id)
        active = managed(root, spec_id, "active")
        if (set(active) != {"schema_version", "specification", "sha256", "definitions"} or active["schema_version"] != 1
                or active["specification"] != location(spec_id) or not isinstance(active["definitions"], dict)):
            raise AgentBaseError("Invalid specification active binding.")
        current = tasks.load_plan(root)
        current_by_id = {t["id"]: t for t in current["tasks"]}
        desired = {t["id"]: t for t in result["plan"]["tasks"]}
        owned = active["definitions"]
        added, updated, removed, unchanged = [], [], [], []
        for task_id, expected in owned.items():
            task = current_by_id.get(task_id)
            if task is None or definition(task) != expected:
                raise AgentBaseError("Local task definition/missing task preserved: " + task_id)
            if task_id in desired and definition(desired[task_id]) == expected:
                unchanged.append(task_id)
                continue
            if task["status"] != "pending" or task["verification"] or "handoff" in task:
                raise AgentBaseError("Started or evidenced task preserved; create a follow-up requirement: " + task_id)
            (updated if task_id in desired else removed).append(task_id)
        for task_id in desired.keys() - owned.keys():
            if task_id in current_by_id:
                raise AgentBaseError("Unmanaged task identity collision: " + task_id)
            added.append(task_id)
        merged = deepcopy(current)
        merged["tasks"] = [desired[t["id"]] if t["id"] in updated else t for t in current["tasks"] if t["id"] not in removed]
        merged["tasks"].extend(desired[k] for k in sorted(added))
        tasks.validate_plan(merged, load_config(root))
        diff = {"added": sorted(added), "updated": sorted(updated), "removed": sorted(removed), "unchanged": sorted(unchanged)}
        plan_id = digest(json_text({"active": active, "current": current, "desired": result, "changes": diff}))
        changes = generated_changes(root, spec_id, {f".agentbase/specs/{spec_id}.trace.json": json_text(result["traceability"]),
                                                   f".agentbase/specs/{spec_id}.active.json": json_text(binding(spec_id, result))})
        if apply:
            if expected_plan != plan_id:
                raise AgentBaseError("Review reconciliation, then use --apply --plan-id with its exact plan_id.")
            batch_write(root, changes | {tasks.PLAN: json_text(merged)})
        return result | {"plan": merged, "changes": diff, "plan_id": plan_id, "applied": apply}
    if not apply:
        return prepare()
    with project_lock(root):
        return prepare()


def evidence(root: Path, spec_id: str, mapping: dict | None = None) -> dict:
    """Bind explicit criterion-to-test mappings to existing handoff observations."""
    def prepare():
        result = proposal(root, spec_id)
        active = managed(root, spec_id, "active")
        if active["sha256"] != result["traceability"]["sha256"]:
            raise AgentBaseError("Specification changed; reconcile before attaching evidence.")
        plan = {t["id"]: t for t in tasks.load_plan(root)["tasks"]}
        for req_id, expected in active["definitions"].items():
            if req_id not in plan or definition(plan[req_id]) != expected:
                raise AgentBaseError("Active task definition changed; reconcile before reporting evidence.")
        state = {"schema_version": 1, "sha256": active["sha256"], "requirements": {}}
        path = f".agentbase/specs/{spec_id}.evidence.json"
        if mapping is not None:
            if set(mapping) != {"schema_version", "requirements"} or mapping["schema_version"] != 1 or not isinstance(mapping["requirements"], dict):
                raise AgentBaseError("Evidence mapping needs schema_version 1 and requirements object.")
            if set(mapping["requirements"]) - set(active["definitions"]):
                raise AgentBaseError("Evidence references unknown requirement.")
            for req_id, criteria in mapping["requirements"].items():
                task = plan[req_id]
                handoff = task.get("handoff")
                if not handoff:
                    raise AgentBaseError("Evidence requires a stored task handoff: " + req_id)
                tasks.validate_handoff(handoff, task, load_config(root))
                if not isinstance(criteria, list) or not criteria:
                    raise AgentBaseError("Evidence requires explicit criterion/test index mappings.")
                seen = set()
                for criterion in criteria:
                    if (not isinstance(criterion, dict) or set(criterion) != {"criterion", "tests"}
                            or not isinstance(criterion["criterion"], str) or criterion["criterion"] not in task["acceptance"]
                            or criterion["criterion"] in seen or not isinstance(criterion["tests"], list) or not criterion["tests"]
                            or any(type(i) is not int or not 0 <= i < len(handoff["tests"]) for i in criterion["tests"])):
                        raise AgentBaseError("Evidence criterion or handoff test index is invalid/duplicate.")
                    seen.add(criterion["criterion"])
                state["requirements"][req_id] = {"handoff_sha256": digest(json_text(handoff)), "criteria": criteria}
        elif confined(root, path).exists():
            state = managed(root, spec_id, "evidence")
        rows = []
        for req_id in active["definitions"]:
            task = plan.get(req_id)
            if task is None or definition(task) != active["definitions"][req_id]:
                raise AgentBaseError("Active task definition changed; reconcile before reporting evidence.")
            record = state["requirements"].get(req_id, {})
            valid = state["sha256"] == active["sha256"] and record.get("handoff_sha256") == digest(json_text(task.get("handoff")))
            by_criterion = {c["criterion"]: c["tests"] for c in record.get("criteria", [])} if valid else {}
            for criterion in task["acceptance"]:
                checks = [task["handoff"]["tests"][i] for i in by_criterion.get(criterion, [])]
                status = "reported-passed" if checks and all(c["status"] == "passed" for c in checks) else "unverified"
                rows.append({"requirement": req_id, "task_id": req_id, "criterion": criterion, "status": status, "tests": checks})
        if mapping is not None:
            batch_write(root, generated_changes(root, spec_id, {path: json_text(state)}))
        return {"sha256": active["sha256"], "criteria": rows, "test_execution_verified": False,
                "provenance": "Explicit mapping to stored host-reported handoff observations; AgentBase did not execute these tests."}
    if mapping is None:
        return prepare()
    with project_lock(root):
        return prepare()
