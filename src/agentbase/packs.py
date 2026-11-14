"""Versioned selections from the canonical catalog; no extra context injection."""

from __future__ import annotations

import re
from pathlib import Path

from .catalog import asset, roles, skills
from .dependencies import inspect as inspect_dependencies
from .fs import AgentBaseError, batch_write, confined, json_text, project_lock, read_json

STATE = ".agentbase/packs.json"


def catalog(root: Path | None = None) -> dict:
    import json
    result = json.loads(asset("packs.json"))
    if root is not None:
        directory = confined(root, ".agentbase/pack-catalog")
        if directory.is_dir():
            candidates = list(directory.glob("*.json"))
            if len(candidates) > 100:
                raise AgentBaseError("Custom pack catalog exceeds 100 manifests.")
            for path in sorted(candidates):
                manifest = read_json(confined(root, path.relative_to(root).as_posix()))
                validate_manifest(manifest)
                if manifest["id"] in result or path.stem != manifest["id"]:
                    raise AgentBaseError("Custom pack identity collision.")
                result[manifest["id"]] = manifest
    return result


def validate_manifest(value: dict) -> None:
    fields = {"id", "name", "description", "version", "providers", "agents", "skills", "optional_dependencies",
              "required_tools", "project_types", "conflicts", "impact", "license"}
    if not isinstance(value, dict) or set(value) != fields:
        raise AgentBaseError("Pack requires exactly the canonical manifest fields; inspect `packs info core`.")
    for key in ("id", "name", "description", "version", "impact", "license"):
        if not isinstance(value[key], str) or not 1 <= len(value[key]) <= 2000:
            raise AgentBaseError("Invalid pack string: " + key)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value["id"]) or len(value["id"]) > 64:
        raise AgentBaseError("Pack ID must be portable kebab-case.")
    for key in ("providers", "agents", "skills", "optional_dependencies", "required_tools", "project_types", "conflicts"):
        if (not isinstance(value[key], list) or len(value[key]) > 100
                or any(not isinstance(v, str) or not v.strip() or len(v) > 2000 for v in value[key])):
            raise AgentBaseError("Invalid pack string array: " + key)
    if not value["providers"] or set(value["providers"]) - {"codex", "claude"}:
        raise AgentBaseError("Invalid pack providers.")
    if set(value["agents"]) - {r["id"] for r in roles()} or set(value["skills"]) - set(skills()):
        raise AgentBaseError("Pack references unknown canonical dependencies.")


def register(root: Path, value: dict, *, dry_run: bool = False) -> dict:
    validate_manifest(value)
    if value["id"] in catalog():
        raise AgentBaseError("Custom packs cannot shadow bundled packs.")
    name = f".agentbase/pack-catalog/{value['id']}.json"
    body = json_text(value)

    def prepare():
        available = catalog(root)
        if value["id"] not in available and len(available) >= len(catalog()) + 100:
            raise AgentBaseError("Custom pack catalog exceeds 100 manifests.")
        target = confined(root, name)
        if target.exists() and (not target.is_file() or target.read_text(encoding="utf-8") != body):
            raise AgentBaseError("Existing custom manifest preserved; edit it explicitly or use a new pack ID.")
        if not dry_run:
            batch_write(root, {name: body})
        return {"path": name, "dry_run": dry_run, "installed": False, "note": "Registered selection only; use init --pack or packs add explicitly."}
    if dry_run:
        return prepare()
    with project_lock(root):
        return prepare()


def resolve(selected: list[str], providers: list[str], *, legacy: bool = False, root: Path | None = None) -> dict:
    available = catalog(root)
    names = sorted(set(["core", *selected]))
    if set(names) - set(available):
        raise AgentBaseError("Unknown pack: " + ", ".join(sorted(set(names) - set(available))))
    role_ids, skill_ids = set(), set()
    for name in names:
        pack = available[name]
        if set(providers) - set(pack["providers"]):
            raise AgentBaseError(f"Pack {name} does not support selected providers.")
        if set(pack["conflicts"]) & set(names):
            raise AgentBaseError(f"Conflicting packs: {name}")
        role_ids.update(pack["agents"])
        skill_ids.update(pack["skills"])
    known_roles = {r["id"]: r for r in roles()}
    if role_ids - set(known_roles) or skill_ids - set(skills()):
        raise AgentBaseError("Pack references an unknown canonical agent or skill.")
    # A role's on-demand skills are its dependencies, never injected automatically.
    for role_id in role_ids:
        skill_ids.update(known_roles[role_id]["skills"])
    if legacy:
        role_ids.update(known_roles)
        skill_ids.update(skills())
    return {"schema_version": 1, "selected": names, "versions": {n: available[n]["version"] for n in names},
            "legacy_catalog": legacy, "agents": sorted(role_ids), "skills": sorted(skill_ids)}


def state(root: Path) -> dict | None:
    if not confined(root, STATE).exists():
        return None
    value = read_json(confined(root, STATE))
    if (value.get("schema_version") != 1 or not isinstance(value.get("selected"), list)
            or any(not isinstance(n, str) for n in value["selected"]) or type(value.get("legacy_catalog")) is not bool):
        raise AgentBaseError("Invalid pack state.")
    return value


def dependencies(root: Path, selected: list[str]) -> dict:
    available = catalog(root)
    return {name: {key: inspect_dependencies(available[name][key]) for key in ("required_tools", "optional_dependencies")}
            for name in sorted(set(["core", *selected]))}


def recommend(root: Path) -> dict:
    recommendations = {"core": ["minimal coordination"]}
    for path, pack in [("pyproject.toml", "python"), ("requirements.txt", "python"),
                       ("package.json", "web"), ("pom.xml", "web"),
                       ("Dockerfile", "devops"), (".github/workflows", "devops")]:
        if confined(root, path).exists():
            recommendations.setdefault(pack, []).append(path)
    return {"recommendations": recommendations, "automatic_installation": False, "remote_analysis": False}


def change(root: Path, name: str, *, remove: bool = False, dry_run: bool = True) -> dict:
    from .install import install
    current = state(root)
    names = current["selected"] if current else []
    if name not in catalog(root):
        raise AgentBaseError("Unknown pack.")
    if remove and (name == "core" or name not in names):
        raise AgentBaseError("Core is required; only an installed optional pack can be removed.")
    selected = [n for n in names if n != name] if remove else sorted(set([*names, name]))
    return install(root, update=True, dry_run=dry_run, pack_ids=selected)
