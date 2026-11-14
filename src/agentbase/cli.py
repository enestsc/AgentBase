"""Public CLI. Structured output is JSON except for human-oriented reports."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tomllib
from pathlib import Path

from . import __version__, distribution, evaluation, gateway, local, memory, native, packs, receipts, registry, runner, specs, tasks, usage
from . import providers as native_providers
from .catalog import role_prompt, roles, skills
from .config import DEFAULT, limits, load_config, validate_config
from .context import retrieve
from .explain import project_report, report_changes
from .fs import AgentBaseError, batch_write, confined, json_text, project_lock, read_json
from .install import install, load_manifest, prepare, uninstall
from .intelligence import index_changes


def parser() -> argparse.ArgumentParser:
    app = argparse.ArgumentParser(prog="agentbase", description="Provider-native workflows and safe local coordination.")
    app.add_argument("--version", action="version", version=__version__)
    app.add_argument("--project", type=Path, default=Path.cwd(), help="Existing project root (default: current directory)")
    commands = app.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Install minimal project integration; preserve existing instructions")
    init.add_argument("--provider", choices=("codex", "claude", "both"), default="both")
    init.add_argument("--dry-run", action="store_true")
    init.add_argument("--pack", action="append", help="Bundled or registered custom pack ID")
    init.add_argument("--discovery", choices=("native", "plugin"), help="Plugin mode avoids duplicate bundled skills/Claude agents")
    update = commands.add_parser("update", help="Regenerate managed files after upgrading the CLI")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--discovery", choices=("native", "plugin"))
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
    skill = commands.add_parser("skills", help="Canonical catalog and pinned, reviewed GitHub imports")
    sc = skill.add_subparsers(dest="skill_command")
    search = sc.add_parser("search")
    search.add_argument("query", nargs="?", default="")
    for name in ("list", "audit", "export"):
        sc.add_parser(name)
    info = sc.add_parser("info")
    info.add_argument("id")
    for name in ("add", "update", "rollback", "restore"):
        sub = sc.add_parser(name)
        sub.add_argument("source", type=Path if name == "restore" else str)
        sub.add_argument("--apply", action="store_true", help="Apply exactly the previously reviewed --plan-id")
        sub.add_argument("--dry-run", action="store_true")
        sub.add_argument("--plan-id")
        sub.add_argument("--acknowledge", action="append", default=[], metavar="FINDING_ID")
        if name in {"add", "update"}:
            sub.add_argument("--ref", default="HEAD" if name == "add" else None)
        if name != "rollback":
            sub.add_argument("--yaml-parser", choices=("stdlib", "pyyaml"), default="stdlib")
        if name == "add":
            sub.add_argument("--path")
            sub.add_argument("--provider", choices=("codex", "claude", "both"), default="both")
    sub = sc.add_parser("remove")
    sub.add_argument("id")
    sub.add_argument("--apply", action="store_true")
    sub.add_argument("--dry-run", action="store_true")
    pack = commands.add_parser("packs", help="Canonical versioned selections and deterministic recommendations")
    pc = pack.add_subparsers(dest="pack_command", required=True)
    for name in ("list", "recommend"):
        pc.add_parser(name)
    for name in ("info", "add", "remove"):
        sub = pc.add_parser(name)
        sub.add_argument("id")
        if name != "info":
            sub.add_argument("--dry-run", action="store_true")
    register = pc.add_parser("register", help="Register a custom selection of canonical roles/skills; executes nothing")
    register.add_argument("--file", type=Path, required=True)
    register.add_argument("--dry-run", action="store_true")
    us = commands.add_parser("usage", help="Opt-in local usage imports; no credential or session scraping")
    period = us.add_mutually_exclusive_group()
    period.add_argument("--today", action="store_true")
    period.add_argument("--week", action="store_true")
    us.add_argument("--provider", choices=("codex", "claude"))
    group = us.add_mutually_exclusive_group()
    group.add_argument("--by-agent", action="store_true")
    group.add_argument("--by-skill", action="store_true")
    us.add_argument("--json", action="store_true")
    us.add_argument("--timezone", default="local", help="local, UTC or installed IANA timezone")
    uc = us.add_subparsers(dest="usage_command")
    setup = uc.add_parser("configure")
    setup.add_argument("--source", choices=sorted(usage.SOURCES), action="append", default=[])
    setup.add_argument("--retention-days", type=int, default=30)
    ingest = uc.add_parser("import")
    ingest.add_argument("--file", type=Path, required=True, help="JSON object containing captures array")
    capture = uc.add_parser("capture", help="Read one documented JSON event from stdin; no provider launch or raw storage")
    capture.add_argument("--source", choices=sorted(usage.SOURCES), required=True)
    capture.add_argument("--provider-version", required=True)
    capture.add_argument("--project-id", required=True, help="Opaque project identifier")
    capture.add_argument("--session-id")
    capture.add_argument("--event-id", help="Required stable request/turn identity for incremental counters")
    export = uc.add_parser("export")
    export.add_argument("--format", choices=("json", "csv"), default="json")
    delete = uc.add_parser("delete")
    delete.add_argument("--before")
    delete.add_argument("--all", action="store_true")
    spec = commands.add_parser("spec", help="Compile explicit Markdown requirements into the existing task DAG")
    sp = spec.add_subparsers(dest="spec_command", required=True)
    si = sp.add_parser("init")
    si.add_argument("id")
    si.add_argument("--title", required=True)
    si.add_argument("--request", required=True)
    si.add_argument("--criterion", action="append", required=True)
    si.add_argument("--role", choices=[r["id"] for r in roles()], default="backend-engineer")
    si.add_argument("--scope", required=True, help="Explicit project-relative write scope")
    si.add_argument("--dry-run", action="store_true")
    for name in ("validate", "plan", "tasks"):
        sub = sp.add_parser(name)
        sub.add_argument("id")
        if name == "plan":
            sub.add_argument("--write", action="store_true")
        if name == "tasks":
            sub.add_argument("--import", dest="import_tasks", action="store_true")
    reconcile = sp.add_parser("reconcile", help="Review incremental changes to owned, unstarted tasks")
    reconcile.add_argument("id")
    reconcile.add_argument("--apply", action="store_true")
    reconcile.add_argument("--plan-id")
    evidence = sp.add_parser("evidence", help="Map acceptance criteria to stored host-reported handoff tests")
    evidence.add_argument("id")
    evidence.add_argument("--file", type=Path)
    ev = commands.add_parser("eval", help="Offline validation or grading explicitly supplied observations")
    ec = ev.add_subparsers(dest="eval_command", required=True)
    for name in ("list", "validate", "report"):
        ec.add_parser(name)
    capabilities = ec.add_parser("capabilities", help="Explicit native version/features probe; no model calls")
    capabilities.add_argument("--provider", choices=("codex", "claude"), required=True)
    capabilities.add_argument("--consent", action="store_true")
    capabilities.add_argument("--image", help="Probe an explicitly trusted immutable local image with network disabled")
    smoke = ec.add_parser("native-smoke", help="Network-disabled native CLI with synthetic API only; no real keys or model calls")
    smoke.add_argument("--provider", choices=("codex", "claude"), required=True)
    smoke.add_argument("--image", required=True, help="Explicitly trusted preinstalled immutable native CLI + Node image")
    smoke.add_argument("--consent", action="store_true")
    smoke.add_argument("--mode", choices=("print", "eval"), default="print", help="Claude eval uses one fixed regex case; all API replies stay synthetic")
    er = ec.add_parser("run")
    er.add_argument("--suite", type=Path)
    er.add_argument("--observations", type=Path)
    plugin = commands.add_parser("plugins", help="Generate and statically validate optional native distributions")
    plc = plugin.add_subparsers(dest="plugin_command", required=True)
    pb = plc.add_parser("build")
    pb.add_argument("--provider", choices=("codex", "claude"), required=True)
    pb.add_argument("--output", required=True, help="Project-relative output directory; existing files preserved")
    pb.add_argument("--dry-run", action="store_true")
    pv = plc.add_parser("validate")
    pv.add_argument("--output", required=True)
    pv.add_argument("--native", action="store_true", help="Also run an available supported native static validator")
    pv.add_argument("--consent", action="store_true")
    gw = commands.add_parser("gateway", help="Validate bounded gateway policy or explicitly test local Docker isolation; no provider launch")
    gc = gw.add_subparsers(dest="gateway_command", required=True)
    gv = gc.add_parser("validate")
    gv.add_argument("--file", type=Path, required=True)
    gs = gc.add_parser("self-test", help="Dummy-key Docker probe; no valid provider requests, downloads or host ports")
    gs.add_argument("--image", required=True, help="Trusted preinstalled pinned Node image")
    gs.add_argument("--consent", action="store_true")
    context = commands.add_parser("context", help="Retrieve explicitly selected files within a context budget")
    context.add_argument("paths", nargs="+")
    explain = commands.add_parser("explain", help="Generate an evidence-backed structural map; no model calls")
    explain.add_argument("--write", action="store_true", help="Write the marked .agentbase/reports/project.md")
    explain.add_argument("--feature", help="Lexical feature matches plus one-hop static import neighbors; no runtime inference")
    task = commands.add_parser("tasks", help="Validate, schedule and transition a dependency DAG")
    tc = task.add_subparsers(dest="task_command", required=True)
    for name in ("validate", "import"):
        sub = tc.add_parser(name)
        sub.add_argument("--file", required=name == "import", type=Path)
    for name in ("show", "ready", "sync"):
        tc.add_parser(name)
    check = tc.add_parser("test", help="Execute explicit trusted HOST argv and record local hashes; no sandbox")
    check.add_argument("id")
    check.add_argument("--source", action="append", required=True)
    check.add_argument("--pythonpath", action="append", default=[])
    check.add_argument("--timeout", type=int, default=60)
    check.add_argument("--consent", action="store_true")
    check.add_argument("--argv", nargs=argparse.REMAINDER, required=True, help="Last option: absolute trusted executable then literal arguments")
    receipt = tc.add_parser("receipt", help="Report freshness of a managed local host execution record")
    receipt.add_argument("id")
    sandbox = tc.add_parser("sandbox", help="Run a trusted pinned offline worker in local Linux Docker; proposals only")
    sandbox.add_argument("id")
    sandbox.add_argument("--worker", required=True, type=Path)
    sandbox.add_argument("--context", action="append", default=[])
    sandbox.add_argument("--consent", action="store_true")
    hv = tc.add_parser("validate-handoff", help="Validate a worker handoff against its current task scope")
    hv.add_argument("--file", required=True, type=Path)
    trans = tc.add_parser("transition")
    trans.add_argument("id")
    trans.add_argument("status", choices=list(tasks.TRANSITIONS))
    trans.add_argument("--evidence", action="append")
    trans.add_argument("--reason", default="")
    trans.add_argument("--handoff-file", type=Path)
    mem = commands.add_parser("memory", help="Evidence-backed notes, state synchronization and handoff")
    mc = mem.add_subparsers(dest="memory_command", required=True)
    note = mc.add_parser("note")
    note.add_argument("category", choices=memory.CATEGORIES)
    note.add_argument("--text", required=True)
    note.add_argument("--evidence", required=True, help="Project-relative file:line")
    ms = mc.add_parser("sync")
    ms.add_argument("--deep", action="store_true")
    mc.add_parser("handoff")
    mc.add_parser("list", help="List tracked note IDs; manual and legacy notes are preserved")
    for name in ("prune", "supersede"):
        sub = mc.add_parser(name)
        sub.add_argument("--id", required=True, action="append" if name == "prune" else "store")
        sub.add_argument("--reason", required=True)
        sub.add_argument("--dry-run", action="store_true")
        if name == "supersede":
            sub.add_argument("--text", required=True)
            sub.add_argument("--evidence", required=True)
    loc = commands.add_parser("local", help="Explicit opt-in loopback Ollama proposal; no file mutations")
    loc.add_argument("action", choices=("summarize", "classify", "models"))
    loc.add_argument("--input")
    loc.add_argument("--consent", action="store_true")
    loc.add_argument("--fallback", action="store_true", help="Return host-review guidance on unavailable/incompatible local inference")
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
        plan = tasks.load_plan(root)
        legacy = [t["id"] for t in plan["tasks"] if t["status"] == "completed" and "handoff" not in t]
        if legacy:
            warnings.append("Legacy completed tasks lack validated handoffs: " + ", ".join(legacy))
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
    if not root.is_dir():
        raise AgentBaseError("Project directory must already exist.")
    # Harici plan doğrulaması bağımsızdır; proje işlemleri önce kurulum ister.
    standalone_plan = args.command == "tasks" and args.task_command == "validate" and args.file
    if args.command in {"explain", "context", "memory", "tasks"} and not standalone_plan:
        if not confined(root, ".agentbase/config.json").is_file():
            raise AgentBaseError("Project is not initialized; first run `agentbase init` (önce `agentbase init` çalıştır).")
    if args.command == "init":
        providers = ["codex", "claude"] if args.provider == "both" else [args.provider]
        return install(root, providers=providers, dry_run=args.dry_run, pack_ids=args.pack, discovery=args.discovery)
    if args.command == "update":
        return install(root, update=True, dry_run=args.dry_run, discovery=args.discovery)
    if args.command == "uninstall":
        return uninstall(root, purge=args.purge, dry_run=args.dry_run)
    if args.command == "doctor":
        return doctor(root)
    if args.command == "roles":
        return role_prompt(next(r for r in roles() if r["id"] == args.role)) if args.role else {
            "orchestrator": "The primary host session", "roles": roles()}
    if args.command == "skills":
        if args.skill_command is None:
            return {"skills": list(skills())}
        if args.skill_command == "search":
            result = registry.search(args.query)
            result["installed"] = [r for n, r in registry.load(root)["skills"].items() if args.query.casefold() in n.casefold()]
            return result
        if args.skill_command == "list":
            return {"canonical": list(skills()), "installed": registry.load(root)["skills"]}
        if args.skill_command == "audit":
            return registry.audit(root)
        if args.skill_command == "export":
            return registry.load(root)
        if args.skill_command == "info":
            if args.id in skills():
                return {"id": args.id, "trust": "official-agentbase", "content": skills()[args.id]}
            record = registry.load(root)["skills"].get(args.id)
            if not record:
                raise AgentBaseError("Unknown skill.")
            return record | {"modified_files": registry.modifications(root, record), "trust": "unreviewed-community"}
        if args.skill_command == "remove":
            return registry.remove(root, args.id, dry_run=not args.apply or args.dry_run)
        options = {"dry_run": not args.apply or args.dry_run, "acknowledgements": args.acknowledge,
                   "expected_plan": args.plan_id}
        if args.skill_command == "add":
            targets = ["codex", "claude"] if args.provider == "both" else [args.provider]
            return registry.add(root, args.source, ref=args.ref, path=args.path, targets=targets, yaml_parser=args.yaml_parser, **options)
        if args.skill_command == "update":
            return registry.update(root, args.source, ref=args.ref, yaml_parser=args.yaml_parser, **options)
        if args.skill_command == "rollback":
            return registry.rollback(root, args.source, **options)
        return registry.restore(root, read_json(args.source), yaml_parser=args.yaml_parser, **options)
    if args.command == "packs":
        if args.pack_command == "list":
            return {"packs": packs.catalog(root), "installed": packs.state(root)}
        if args.pack_command == "register":
            return packs.register(root, read_json(args.file), dry_run=args.dry_run)
        if args.pack_command == "info":
            if args.id not in packs.catalog(root):
                raise AgentBaseError("Unknown pack.")
            return packs.catalog(root)[args.id] | {"dependency_availability": packs.dependencies(root, [args.id])}
        if args.pack_command == "recommend":
            return packs.recommend(root)
        return packs.change(root, args.id, remove=args.pack_command == "remove", dry_run=args.dry_run)
    if args.command == "usage":
        if args.usage_command == "capture":
            body = sys.stdin.read(1_000_001)
            if len(body.encode("utf-8")) > 1_000_000:
                raise AgentBaseError("Capture exceeds 1 MB.")
            try:
                event = json.loads(body)
            except ValueError as exc:
                raise AgentBaseError("Capture stdin requires one JSON object; raw input is not saved.") from exc
            return usage.capture_event(root, args.source, event, provider_version=args.provider_version,
                                       project_id=args.project_id, session_id=args.session_id, event_id=args.event_id)
        if args.usage_command == "configure":
            return usage.configure(root, args.source, retention_days=args.retention_days)
        if args.usage_command == "import":
            return usage.ingest(root, read_json(args.file).get("captures"))
        if args.usage_command == "export":
            return usage.export(root, csv_format=args.format == "csv")
        if args.usage_command == "delete":
            return usage.delete(root, before=args.before, all_data=args.all)
        report = usage.report(root, period="today" if args.today else "week" if args.week else None,
                              provider=args.provider, by="agent_id" if args.by_agent else "skill_id" if args.by_skill else "model",
                              timezone=args.timezone)
        return report if args.json else usage.render_table(report)
    if args.command == "spec":
        if args.spec_command == "reconcile":
            return specs.reconcile(root, args.id, apply=args.apply, expected_plan=args.plan_id)
        if args.spec_command == "evidence":
            return specs.evidence(root, args.id, read_json(args.file) if args.file else None)
        if args.spec_command == "init":
            return specs.initialize(root, args.id, args.title, args.request, args.criterion, args.role, args.scope, dry_run=args.dry_run)
        if args.spec_command == "validate":
            value, sha = specs.read(root, args.id)
            return {"valid": True, "tasks": len(specs.compile_plan(value)["tasks"]), "sha256": sha}
        return specs.proposal(root, args.id, write=args.spec_command == "plan" and args.write,
                              import_tasks=args.spec_command == "tasks" and args.import_tasks)
    if args.command == "eval":
        if args.eval_command == "native-smoke":
            return native.mock_smoke(root, args.provider, args.image, mode=args.mode, consent=args.consent)
        if args.eval_command == "capabilities":
            if args.image:
                return native.inspect_image(root, args.provider, args.image, consent=args.consent)
            return native_providers.inspect(args.provider, consent=args.consent, root=root)
        if args.eval_command == "list":
            return {"suites": ["static", "supplied-observations"], "live_provider_execution": False, "paid_evals": "disabled"}
        if args.eval_command == "validate":
            return evaluation.validate(root)
        if args.eval_command == "report":
            return evaluation.report(root)
        return evaluation.run(root, args.suite, args.observations)
    if args.command == "plugins":
        if args.plugin_command == "validate":
            if args.native:
                result = distribution.validate(root, args.output)
                return native_providers.validate_plugin(root, result["provider"], args.output, consent=args.consent)
            return distribution.validate(root, args.output)
        return distribution.build(root, args.provider, args.output, dry_run=args.dry_run)
    if args.command == "gateway":
        if args.gateway_command == "validate":
            return {"valid": True, "policy": gateway.policy(read_json(args.file)), "provider_calls": 0,
                    "billing_cap_verified": False}
        return gateway.self_test(args.image, consent=args.consent)
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
        if args.task_command == "test":
            return receipts.execute(root, args.id, args.argv, args.source, consent=args.consent,
                                    timeout=args.timeout, pythonpath=args.pythonpath)
        if args.task_command == "receipt":
            return receipts.report(root, args.id)
        if args.task_command == "sandbox":
            if not args.consent:
                raise AgentBaseError("Review the worker policy and pass --consent for explicit offline execution.")
            with project_lock(root):
                plan = tasks.load_plan(root)
                task = next((t for t in plan["tasks"] if t["id"] == args.id), None)
                if task is None:
                    raise AgentBaseError("Unknown task.")
                return runner.DockerTaskRunner().run(root, task, args.context, read_json(args.worker), consent=args.consent)
        if args.task_command == "validate-handoff":
            value = read_json(args.file)
            target = next((t for t in tasks.load_plan(root)["tasks"] if t["id"] == value.get("task_id")), None)
            if target is None:
                raise AgentBaseError("Unknown handoff task_id.")
            tasks.validate_handoff(value, target, load_config(root))
            return {"valid": True, "task_id": target["id"], "checks_executed": False}
        if args.task_command == "validate":
            config = load_config(root) if confined(root, ".agentbase/config.json").exists() else DEFAULT
            plan = tasks.validate_plan(read_json(args.file), config) if args.file else tasks.load_plan(root)
            return {"valid": True, "tasks": len(plan["tasks"]), "legacy_completed_without_handoff":
                    [t["id"] for t in plan["tasks"] if t["status"] == "completed" and "handoff" not in t]}
        if args.task_command == "import":
            return tasks.import_plan(root, read_json(args.file))
        if args.task_command == "sync":
            return tasks.sync(root)
        if args.task_command == "transition":
            return tasks.transition(root, args.id, args.status, evidence=args.evidence, reason=args.reason,
                                    handoff=read_json(args.handoff_file) if args.handoff_file else None)
        plan = tasks.load_plan(root)
        return {"ready": tasks.schedule(plan, load_config(root)), "launches_workers": False} if args.task_command == "ready" else plan
    if args.command == "context":
        return retrieve(root, args.paths, load_config(root))
    if args.command == "explain":
        if args.write:
            with project_lock(root):
                report, evidence = project_report(root, load_config(root), feature=args.feature)
                batch_write(root, report_changes(root, report) | index_changes(evidence["structural"]))
            return {"written": ".agentbase/reports/project.md"}
        return project_report(root, load_config(root), feature=args.feature)[0]
    if args.command == "memory":
        if args.memory_command == "list":
            return memory.list_notes(root)
        if args.memory_command in {"prune", "supersede"}:
            replace = args.memory_command == "supersede"
            return memory.maintain(root, [args.id] if replace else args.id, args.reason,
                                   text=args.text if replace else None,
                                   evidence=args.evidence if replace else None, dry_run=args.dry_run)
        if args.memory_command == "sync":
            return memory.sync_memory(root, deep=args.deep)
        if args.memory_command == "note":
            return memory.note(root, args.category, args.text, args.evidence)
        return memory.handoff(root)
    if args.command == "local":
        config = load_config(root)
        if args.action == "models":
            return local.discover(config, consent=args.consent)
        if not args.input:
            raise AgentBaseError("Local summarize/classify requires --input.")
        return local.assist(root, config, args.action, args.input, consent=args.consent, fallback=args.fallback)
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
