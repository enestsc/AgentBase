"""Public CLI. Structured output is JSON except for human-oriented reports."""

from __future__ import annotations

import argparse
import shutil
import sys
import tomllib
from pathlib import Path

from . import __version__, local, memory, tasks
from .catalog import role_prompt, roles, skills
from .config import DEFAULT, limits, load_config, validate_config
from .context import retrieve
from .explain import project_report, report_changes
from .fs import AgentBaseError, batch_write, confined, json_text, project_lock, read_json
from .install import install, load_manifest, prepare, uninstall


def parser() -> argparse.ArgumentParser:
    app = argparse.ArgumentParser(prog="agentbase", description="Provider-native workflows and safe local coordination.")
    app.add_argument("--version", action="version", version=__version__)
    app.add_argument("--project", type=Path, default=Path.cwd(), help="Existing project root (default: current directory)")
    commands = app.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Install minimal project integration; preserve existing instructions")
    init.add_argument("--provider", choices=("codex", "claude", "both"), default="both")
    init.add_argument("--dry-run", action="store_true")
    update = commands.add_parser("update", help="Regenerate managed files after upgrading the CLI")
    update.add_argument("--dry-run", action="store_true")
    remove = commands.add_parser("uninstall", help="Remove AgentBase-managed files and blocks; user content is preserved")
    remove.add_argument("--dry-run", action="store_true")
    remove.add_argument("--purge", action="store_true", help="Also delete .agentbase state (config, tasks, memory, reports)")
    commands.add_parser("doctor", help="Offline configuration, ownership and installation diagnostics")
    configure = commands.add_parser("configure", help="Change validated context/execution settings")
    configure.add_argument("--profile", choices=("minimal", "balanced", "deep"))
    configure.add_argument("--mode", choices=("sequential", "safe-parallel"))
    configure.add_argument("--max-concurrency", type=int)
    role = commands.add_parser("roles", help="List roles or show a canonical role")
    role.add_argument("--role", choices=[r["id"] for r in roles()])
    commands.add_parser("skills", help="List available progressively loaded skills")
    context = commands.add_parser("context", help="Retrieve explicitly selected files within a context budget")
    context.add_argument("paths", nargs="+")
    explain = commands.add_parser("explain", help="Generate an evidence-backed structural map; no model calls")
    explain.add_argument("--write", action="store_true", help="Write the marked .agentbase/reports/project.md")
    task = commands.add_parser("tasks", help="Validate, schedule and transition a dependency DAG")
    tc = task.add_subparsers(dest="task_command", required=True)
    for name in ("validate", "import"):
        sub = tc.add_parser(name)
        sub.add_argument("--file", required=name == "import", type=Path)
    for name in ("show", "ready", "sync"):
        tc.add_parser(name)
    trans = tc.add_parser("transition")
    trans.add_argument("id")
    trans.add_argument("status", choices=list(tasks.TRANSITIONS))
    trans.add_argument("--evidence", action="append")
    trans.add_argument("--reason", default="")
    mem = commands.add_parser("memory", help="Evidence-backed notes, state synchronization and handoff")
    mc = mem.add_subparsers(dest="memory_command", required=True)
    note = mc.add_parser("note")
    note.add_argument("category", choices=memory.CATEGORIES)
    note.add_argument("--text", required=True)
    note.add_argument("--evidence", required=True, help="Project-relative file:line")
    ms = mc.add_parser("sync")
    ms.add_argument("--deep", action="store_true")
    mc.add_parser("handoff")
    loc = commands.add_parser("local", help="Explicit opt-in loopback Ollama proposal; no file mutations")
    loc.add_argument("action", choices=("summarize", "classify"))
    loc.add_argument("--input", required=True)
    loc.add_argument("--consent", action="store_true")
    return app


def doctor(root: Path) -> dict:
    issues, warnings = [], []
    config = load_config(root)
    manifest = load_manifest(root)
    try:
        pending = prepare(root, update=True)
        if pending:
            warnings.append("Generated content differs from this CLI; run update --dry-run after reviewing version changes.")
    except AgentBaseError as exc:
        issues.append(str(exc))
    try:
        tasks.load_plan(root)
    except AgentBaseError as exc:
        issues.append(str(exc))
    for name, record in manifest["files"].items():
        if name.endswith(".toml") and record["kind"] == "file":
            try:
                tomllib.loads(confined(root, name).read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                issues.append(f"Invalid native TOML: {name}: {exc}")
    if confined(root, "AGENTS.override.md").exists():
        warnings.append("AGENTS.override.md may shadow the root AGENTS.md bootstrap in Codex.")
    if confined(root, ".agentbase/write.lock").exists():
        warnings.append("A writer lock exists; inspect the PID if no AgentBase command is active.")
    if config["local_model"]["enabled"]:
        local.endpoint_url(config["local_model"]["endpoint"])
        warnings.append("Local model enabled; calls still require --consent. Ollama server locality is user-managed.")
    return {"ok": not issues, "version": __version__, "installed_version": manifest["version"],
            "issues": issues, "warnings": warnings, "context_limits": limits(config),
            "native_executables": {p: bool(shutil.which(p)) for p in config["providers"]},
            "runtime_note": "Discovery/permissions/concurrency must be verified in the host. No native model session was executed."}


def run(args: argparse.Namespace) -> dict | str:
    root = args.project.resolve()
    if args.command == "init":
        providers = ["codex", "claude"] if args.provider == "both" else [args.provider]
        return install(root, providers=providers, dry_run=args.dry_run)
    if args.command == "update":
        return install(root, update=True, dry_run=args.dry_run)
    if args.command == "uninstall":
        return uninstall(root, purge=args.purge, dry_run=args.dry_run)
    if args.command == "doctor":
        return doctor(root)
    if args.command == "roles":
        return role_prompt(next(r for r in roles() if r["id"] == args.role)) if args.role else {
            "orchestrator": "The primary host session", "roles": roles()}
    if args.command == "skills":
        return {"skills": list(skills())}
    if args.command == "configure":
        with project_lock(root):
            config = load_config(root)
            if args.profile:
                config["context_profile"] = args.profile
            if args.mode:
                config["execution"]["mode"] = args.mode
            if args.max_concurrency is not None:
                config["execution"]["max_concurrency"] = args.max_concurrency
            validate_config(config)
            tasks.validate_plan(read_json(confined(root, tasks.PLAN)), config)
            batch_write(root, {".agentbase/config.json": json_text(config)})
        return config
    if args.command == "tasks":
        if args.task_command == "validate":
            config = load_config(root) if confined(root, ".agentbase/config.json").exists() else DEFAULT
            plan = tasks.validate_plan(read_json(args.file), config) if args.file else tasks.load_plan(root)
            return {"valid": True, "tasks": len(plan["tasks"])}
        if args.task_command == "import":
            return tasks.import_plan(root, read_json(args.file))
        if args.task_command == "sync":
            return tasks.sync(root)
        if args.task_command == "transition":
            return tasks.transition(root, args.id, args.status, evidence=args.evidence, reason=args.reason)
        plan = tasks.load_plan(root)
        return {"ready": tasks.schedule(plan, load_config(root)), "launches_workers": False} if args.task_command == "ready" else plan
    if args.command == "context":
        return retrieve(root, args.paths, load_config(root))
    if args.command == "explain":
        if args.write:
            with project_lock(root):
                report, _ = project_report(root, load_config(root))
                batch_write(root, report_changes(root, report))
            return {"written": ".agentbase/reports/project.md"}
        return project_report(root, load_config(root))[0]
    if args.command == "memory":
        if args.memory_command == "sync":
            return memory.sync_memory(root, deep=args.deep)
        if args.memory_command == "note":
            return memory.note(root, args.category, args.text, args.evidence)
        return memory.handoff(root)
    if args.command == "local":
        config = load_config(root)
        url, payload = local.prepare_request(root, config, args.action, args.input, consent=args.consent)
        print(f"Sending reviewed input {args.input!r} to {url}, model {payload['model']!r} (proposal only).", file=sys.stderr)
        return local.request(url, payload, config["local_model"]["timeout_seconds"])
    raise AgentBaseError("Unknown command.")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = run(args)
        print(result if isinstance(result, str) else json_text(result), end="" if isinstance(result, str) and result.endswith("\n") else "\n")
        return 1 if isinstance(result, dict) and result.get("ok") is False else 0
    except (AgentBaseError, OSError, UnicodeError) as exc:
        print(json_text({"error": str(exc)}), file=sys.stderr, end="")
        return 2
    except KeyboardInterrupt:
        print("Interrupted; inspect doctor and task state before resuming.", file=sys.stderr)
        return 130
