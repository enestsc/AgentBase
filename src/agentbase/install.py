"""Hash-tracked installation with preflight conflict detection and managed blocks."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from . import __version__
from .adapters import instruction_bodies, render
from .config import DEFAULT, load_config
from .fs import AgentBaseError, batch_write, confined, digest, json_text, project_lock, read_json

START = "<!-- agentbase:begin -->"
END = "<!-- agentbase:end -->"
MANIFEST = ".agentbase/manifest.json"


def text_at(root: Path, name: str) -> str | None:
    path = confined(root, name)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise AgentBaseError(f"Expected text file under 2 MB: {name}")
    return path.read_bytes().decode("utf-8")


def block_parts(text: str) -> tuple[str, str, str] | None:
    if START not in text and END not in text:
        return None
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise AgentBaseError("Malformed/duplicate AgentBase instruction markers; repair manually.")
    start, end = text.index(START), text.index(END) + len(END)
    return text[:start], text[start:end], text[end:]


def owned_path(name: str, kind: str) -> bool:
    if kind == "block":
        return name in ("AGENTS.md", "CLAUDE.md")
    return kind == "file" and bool(re.fullmatch(
        r"(?:\.agentbase/policy\.md|\.agentbase/roles/[a-z0-9-]+\.md|"
        r"\.codex/agents/agentbase-[a-z0-9-]+\.toml|"
        r"\.(?:agents|claude)/skills/agentbase-[a-z0-9-]+/SKILL\.md|"
        r"\.claude/agents/agentbase-[a-z0-9-]+\.md)", name))


def load_manifest(root: Path) -> dict:
    value = read_json(confined(root, MANIFEST))
    if set(value) != {"schema_version", "version", "files"} or value["schema_version"] != 1:
        raise AgentBaseError("Unsupported manifest schema; no automatic migration is available.")
    if not isinstance(value["files"], dict) or not isinstance(value["version"], str):
        raise AgentBaseError("Invalid manifest.")
    for name, record in value["files"].items():
        if (not isinstance(record, dict) or set(record) != {"kind", "sha256"} or
                not owned_path(name, record.get("kind")) or
                not isinstance(record.get("sha256"), str) or
                not re.fullmatch(r"[a-f0-9]{64}", record["sha256"])):
            raise AgentBaseError(f"Invalid managed manifest entry: {name}")
    return value


def prepare(root: Path, *, update: bool, providers: list[str] | None = None) -> dict[str, str | None]:
    manifest_exists = confined(root, MANIFEST).exists()
    if update != manifest_exists:
        raise AgentBaseError("Already initialized; use update." if manifest_exists else "Not initialized; use init.")
    old = load_manifest(root)["files"] if update else {}
    config = load_config(root) if update else deepcopy(DEFAULT)
    if providers:
        config["providers"] = providers
    generated = render(config["providers"])
    blocks = instruction_bodies(config["providers"])
    desired = {name: ("file", body) for name, body in generated.items()}
    desired.update({name: ("block", f"{START}\n{body.rstrip()}\n{END}") for name, body in blocks.items()})
    current = {name: text_at(root, name) for name in sorted(set(desired) | set(old))}
    # Verify every old managed item before planning any writes or removals.
    for name, record in old.items():
        content = current[name]
        if content is None:
            raise AgentBaseError(f"Managed file missing: {name}; restore it before update.")
        if record["kind"] == "block":
            parts = block_parts(content)
            content = parts[1] if parts else ""
        # Tolerate CRLF conversion (Windows editors, git autocrlf).
        if digest(content.replace("\r\n", "\n")) != record["sha256"]:
            raise AgentBaseError(f"Local managed edit detected: {name}. Preserve/move the edit and restore the generated version before updating.")
    changes = {}
    records = {}
    for name, (kind, body) in desired.items():
        existing = current[name]
        if name not in old and existing is not None:
            if kind == "file" or block_parts(existing):
                raise AgentBaseError(f"Unmanaged file/marker collision: {name}")
        if kind == "block":
            parts = block_parts(existing) if existing is not None else None
            if parts:
                content = parts[0] + body + parts[2]
            else:
                content = (existing or "") + ("\n\n" if existing else "") + body + "\n"
        else:
            content = body
        records[name] = {"kind": kind, "sha256": digest(body)}
        if content != existing:
            changes[name] = content
    for name, record in old.items():
        if name in desired:
            continue
        if record["kind"] == "block":
            parts = block_parts(current[name])
            changes[name] = parts[0] + parts[2]
        else:
            changes[name] = None
    if not update:
        seeds = {
            ".agentbase/config.json": json_text(config),
            ".agentbase/tasks.json": json_text({"schema_version": 1, "tasks": []}),
            ".agentbase/memory/overview.md": "# Project overview\n\nNo project-specific overview recorded yet.\n",
        }
        for name, body in seeds.items():
            if confined(root, name).exists():
                raise AgentBaseError(f"Existing project state would be overwritten: {name}")
            changes[name] = body
    manifest_body = json_text({"schema_version": 1, "version": __version__, "files": records})
    if text_at(root, MANIFEST) != manifest_body:
        changes[MANIFEST] = manifest_body  # Must be last: crash drift remains detectable.
    return changes


def install(root: Path, *, update: bool = False, providers: list[str] | None = None,
            dry_run: bool = False) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise AgentBaseError("Project directory must already exist.")
    if dry_run:
        changes = prepare(root, update=update, providers=providers)
    else:
        with project_lock(root):
            changes = prepare(root, update=update, providers=providers)
            batch_write(root, changes)
    return {"dry_run": dry_run, "version": __version__,
            "changes": [{"path": name, "action": "remove" if body is None else "write"}
                        for name, body in changes.items()]}
