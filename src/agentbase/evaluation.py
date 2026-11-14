"""Offline catalog validation and evidence grading, separate from model execution."""

from __future__ import annotations

from pathlib import Path

from . import packs, registry, tasks
from .catalog import roles, skills
from .fs import AgentBaseError, batch_write, confined, json_text, project_lock, read_json
from .skill_security import metadata

REPORT = ".agentbase/evaluations/latest.json"


def validate(root: Path) -> dict:
    checks = []
    for name, text in skills().items():
        metadata(text, name)
        checks.append({"id": "skill:" + name, "status": "passed", "kind": "static"})
    for name, pack in packs.catalog(root).items():
        packs.resolve([name], pack["providers"], root=root)
        checks.append({"id": "pack:" + name, "status": "passed", "kind": "static"})
    installed = registry.audit(root)
    checks.append({"id": "installed-integrity", "status": "passed" if installed["ok"] else "failed", "kind": "static"})
    return {"schema_version": 1, "ok": installed["ok"], "level": "static", "checks": checks,
            "provider_calls": 0, "runtime_behavior_verified": False}


def grade(suite: dict, observations: dict) -> dict:
    """Grade caller-supplied observations; never claim that this ran a provider."""
    if suite.get("schema_version") != 1 or not isinstance(suite.get("cases"), list) or not suite["cases"]:
        raise AgentBaseError("Evaluation suite requires schema_version 1 and nonempty cases.")
    if observations.get("schema_version") != 1 or observations.get("origin") not in {"mock", "provider-capture", "manual"}:
        raise AgentBaseError("Observations require origin mock/provider-capture/manual and schema_version 1.")
    actual = observations.get("observations")
    if not isinstance(actual, list):
        raise AgentBaseError("observations must be an array.")
    by_id = {}
    for value in actual:
        if not isinstance(value, dict) or not isinstance(value.get("id"), str) or value["id"] in by_id:
            raise AgentBaseError("Observation IDs must be unique strings.")
        by_id[value["id"]] = value
    results, seen = [], set()
    known_roles, known_skills = {r["id"] for r in roles()}, set(skills())
    for case in suite["cases"]:
        required = {"id", "prompt", "expected_role", "required_skills", "forbidden_skills", "required_tools", "forbidden_tools", "expected_files"}
        if not isinstance(case, dict) or set(case) != required or not isinstance(case["id"], str) or case["id"] in seen:
            raise AgentBaseError("Invalid/duplicate evaluation case.")
        seen.add(case["id"])
        if case["expected_role"] not in known_roles | {None}:
            raise AgentBaseError("Unknown evaluation role.")
        for field in ("required_skills", "forbidden_skills", "required_tools", "forbidden_tools", "expected_files"):
            tasks.string_list(case[field], field)
        if (set(case["required_skills"]) | set(case["forbidden_skills"])) - known_skills:
            raise AgentBaseError("Unknown evaluation skill.")
        if set(case["required_skills"]) & set(case["forbidden_skills"]) or set(case["required_tools"]) & set(case["forbidden_tools"]):
            raise AgentBaseError("Contradictory evaluation expectations.")
        observation = by_id.get(case["id"])
        failures = []
        if observation is None:
            failures.append("missing observation")
        else:
            for field in ("skills", "tools", "changed_files", "evidence"):
                tasks.string_list(observation.get(field), "observation." + field)
            if observation.get("role") != case["expected_role"]:
                failures.append("role mismatch")
            for actual_key, required_key, forbidden_key in (("skills", "required_skills", "forbidden_skills"), ("tools", "required_tools", "forbidden_tools")):
                if set(case[required_key]) - set(observation[actual_key]):
                    failures.append("missing " + required_key)
                if set(case[forbidden_key]) & set(observation[actual_key]):
                    failures.append("activated " + forbidden_key)
            if set(case["expected_files"]) != set(observation["changed_files"]):
                failures.append("unexpected changed files")
            if not observation["evidence"] or observation.get("result") != "passed":
                failures.append("correctness evidence missing/failed")
        results.append({"id": case["id"], "status": "failed" if failures else "passed", "failures": failures})
    if set(by_id) - seen:
        raise AgentBaseError("Observations include cases outside this suite.")
    return {"schema_version": 1, "ok": all(r["status"] == "passed" for r in results), "level": "observation-grading",
            "origin": observations["origin"], "checks": results, "provider_calls": 0,
            "runtime_behavior_verified": False, "note": "Grades supplied evidence only; no provider session executed or independently authenticated."}


def run(root: Path, suite_file: Path | None = None, observations_file: Path | None = None) -> dict:
    if bool(suite_file) != bool(observations_file):
        raise AgentBaseError("Supply both --suite and --observations, or neither for static validation.")
    result = grade(read_json(suite_file), read_json(observations_file)) if suite_file else validate(root)
    with project_lock(root):
        batch_write(root, {REPORT: json_text(result)})
    return result


def report(root: Path) -> dict:
    return read_json(confined(root, REPORT))
