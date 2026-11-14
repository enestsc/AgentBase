"""Hash-tracked installation with preflight conflict detection and managed blocks."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from . import __version__, packs
from .adapters import instruction_bodies, render
from .config import DEFAULT, load_config
from .fs import AgentBaseError, batch_write, confined, digest, json_text, project_lock, read_json

START = "<!-- agentbase:begin -->"
END = "<!-- agentbase:end -->"
MANIFEST = ".agentbase/manifest.json"
DISCOVERY = ".agentbase/discovery.json"


def discovery_mode(root: Path) -> str:
    if not confined(root, DISCOVERY).exists():
        return "native"
    value = read_json(confined(root, DISCOVERY))
    if set(value) != {"schema_version", "mode"} or value["schema_version"] != 1 or value["mode"] not in ("native", "plugin"):
        raise AgentBaseError("Invalid discovery mode state.")
    return value["mode"]


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


def prepare(root: Path, *, update: bool, providers: list[str] | None = None,
            pack_ids: list[str] | None = None, discovery: str | None = None) -> dict[str, str | None]:
    manifest_exists = confined(root, MANIFEST).exists()
    if update != manifest_exists:
        raise AgentBaseError("Already initialized; use update." if manifest_exists else "Not initialized; use init.")
    old = load_manifest(root)["files"] if update else {}
    config = load_config(root) if update else deepcopy(DEFAULT)
    if providers:
        config["providers"] = providers
    previous_packs = packs.state(root) if update else None
    selection = None
    if pack_ids is not None or previous_packs:
        selection = packs.resolve(pack_ids if pack_ids is not None else previous_packs["selected"], config["providers"],
                                  legacy=(previous_packs["legacy_catalog"] if previous_packs else update), root=root)
    generated = render(config["providers"], role_ids=selection["agents"] if selection else None,
                       skill_ids=selection["skills"] if selection else None)
    mode = discovery or (discovery_mode(root) if update else "native")
    if mode not in ("native", "plugin"):
        raise AgentBaseError("Discovery must be native or plugin.")
    if mode == "plugin":
        # Codex plugin custom-agent discovery is not assumed; its standalone
        # agents remain. Claude plugin agents and shared plugin skills are not
        # duplicated into the project-native discovery directories.
        generated = {n: body for n, body in generated.items() if not n.startswith((".agents/skills/", ".claude/skills/", ".claude/agents/"))}
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
    if selection and text_at(root, packs.STATE) != json_text(selection):
        if not update and confined(root, packs.STATE).exists():
            raise AgentBaseError("Existing pack state would be overwritten.")
        changes[packs.STATE] = json_text(selection)
    if discovery is not None or (update and confined(root, DISCOVERY).exists()):
        body = json_text({"schema_version": 1, "mode": mode})
        if not update and confined(root, DISCOVERY).exists():
            raise AgentBaseError("Existing discovery state preserved.")
        if text_at(root, DISCOVERY) != body:
            changes[DISCOVERY] = body
    manifest_body = json_text({"schema_version": 1, "version": __version__, "files": records})
    if text_at(root, MANIFEST) != manifest_body:
        changes[MANIFEST] = manifest_body  # Must be last: crash drift remains detectable.
    return changes


def prepare_uninstall(root: Path, *, purge: bool) -> dict[str, str | None]:
    """Yalnızca manifestteki yönetilen öğeleri geri alır; kullanıcı içeriğine dokunmaz."""
    if not confined(root, MANIFEST).exists():
        raise AgentBaseError("Not initialized; nothing to uninstall.")
    if purge and confined(root, ".agentbase/skills.lock.json").exists():
        from .registry import load
        if load(root)["skills"]:
            raise AgentBaseError("Remove installed third-party skills with `skills remove ID --apply` before purging their provenance lock.")
    old = load_manifest(root)["files"]
    changes: dict[str, str | None] = {}
    for name, record in old.items():
        content = text_at(root, name)
        if content is None:
            continue  # Zaten yok; geri alınacak bir şey kalmadı.
        if record["kind"] == "file":
            # Yerel düzenlenmiş yönetilen dosya silinirse kullanıcı emeği kaybolur; update ile aynı koruma.
            if digest(content.replace("\r\n", "\n")) != record["sha256"]:
                raise AgentBaseError(f"Local managed edit detected: {name}. Preserve/move the edit before uninstalling.")
            changes[name] = None
            continue
        parts = block_parts(content)
        if not parts:
            continue
        before, block, after = parts
        if digest(block.replace("\r\n", "\n")) != record["sha256"]:
            raise AgentBaseError(f"Local managed edit detected: {name}. Preserve/move the edit before uninstalling.")
        # install() boş dosyada "blok\n", dolu dosyada "\n\nblok\n" ekler; bunu birebir geri al.
        if before == "" and after.strip() == "":
            changes[name] = None  # Dosyayı AgentBase yaratmıştı ve başka içerik yok.
        elif before.endswith("\n\n") and after == "\n":
            changes[name] = before[:-2]
        else:
            changes[name] = before + after
    if purge:
        base = confined(root, ".agentbase")
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                if path.is_symlink():
                    raise AgentBaseError(f"Refusing linked project path: {path.name}")
                if path.is_file() and path.name != "write.lock":
                    changes[path.relative_to(root).as_posix()] = None
    else:
        # Durum (config/tasks/memory) korunur; boş manifest sonraki `update` ile yeniden kurulumu mümkün kılar.
        changes[MANIFEST] = json_text({"schema_version": 1, "version": __version__, "files": {}})
    return changes


def uninstall(root: Path, *, purge: bool = False, dry_run: bool = False) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise AgentBaseError("Project directory must already exist.")
    if dry_run:
        changes = prepare_uninstall(root, purge=purge)
    else:
        with project_lock(root):
            changes = prepare_uninstall(root, purge=purge)
            batch_write(root, changes)
            # Boşalan dizinleri temizle (yalnızca boş olanlar; rmdir doluysa hata verir, biz yutarız).
            for name in sorted((n for n, b in changes.items() if b is None), reverse=True):
                parent = confined(root, name).parent
                while parent != root and parent.is_dir():
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
        if purge:
            # write.lock kilidin içinde silinemediği için .agentbase en son, kilit kalkınca kaldırılır.
            try:
                confined(root, ".agentbase").rmdir()
            except OSError:
                pass
    return {"dry_run": dry_run, "purge": purge,
            "changes": [{"path": name, "action": "remove" if body is None else "write"}
                        for name, body in changes.items()]}


def install(root: Path, *, update: bool = False, providers: list[str] | None = None,
            dry_run: bool = False, pack_ids: list[str] | None = None, discovery: str | None = None) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise AgentBaseError("Project directory must already exist.")
    if dry_run:
        changes = prepare(root, update=update, providers=providers, pack_ids=pack_ids, discovery=discovery)
    else:
        with project_lock(root):
            changes = prepare(root, update=update, providers=providers, pack_ids=pack_ids, discovery=discovery)
            batch_write(root, changes)
    return {"dry_run": dry_run, "version": __version__,
            "dependency_availability": packs.dependencies(root, pack_ids or (packs.state(root) or {}).get("selected", [])),
            "changes": [{"path": name, "action": "remove" if body is None else "write"}
                        for name, body in changes.items()]}
