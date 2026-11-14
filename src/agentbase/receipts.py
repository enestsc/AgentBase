"""Explicit trusted host checks; local drift records, never sandbox or attestation."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from . import tasks
from .context import EXCLUDED_DIRS, sensitive
from .fs import AgentBaseError, batch_write, confined, digest, json_text, project_lock, read_json, relative

DIRECTORY = ".agentbase/receipts"
MANIFEST = DIRECTORY + "/manifest.json"
OUTPUT_LIMIT = 1_000_000


def file_hash(path: Path, limit: int = 128_000_000) -> str:
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > limit:
        raise AgentBaseError("Receipt input must be a bounded regular file.")
    hasher, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            size += len(chunk)
            if size > limit:
                raise AgentBaseError("Receipt input grew beyond its byte limit.")
            hasher.update(chunk)
    return hasher.hexdigest()


def source_snapshot(root: Path, task: dict, names: list[str]) -> dict:
    if not isinstance(names, list) or not 1 <= len(names) <= 50:
        raise AgentBaseError("Select 1..50 explicit source files/directories.")
    selected = [relative(n) for n in names]
    if len({n.casefold() for n in selected}) != len(selected):
        raise AgentBaseError("Duplicate source roots.")
    files, seen, total, visited = {}, set(), 0, 0

    def visit(name: str, depth: int = 0):
        nonlocal total, visited
        visited += 1
        if visited > 5000 or depth > 50:
            raise AgentBaseError("Source inventory exceeds entry/depth limits.")
        if sensitive(name) or any(p.casefold() in EXCLUDED_DIRS for p in name.split("/")):
            raise AgentBaseError("Excluded or sensitive receipt source.")
        if name.casefold() in seen:
            raise AgentBaseError("Overlapping or case-colliding receipt sources.")
        seen.add(name.casefold())
        if not any(kind == "file" and tasks.overlap(scope, name.casefold()) and
                   (scope == "." or name.casefold() == scope or name.casefold().startswith(scope + "/"))
                   for kind, scope, _ in tasks.claims(task)):
            raise AgentBaseError("Receipt source lies outside task scope.")
        path = confined(root, name)
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode):
            children = []
            for child in path.iterdir():
                if len(children) >= 5000:
                    raise AgentBaseError("Source directory exceeds entry limit.")
                children.append(child)
            for child in sorted(children, key=lambda p: p.name):
                if child.name.casefold() not in EXCLUDED_DIRS:
                    visit(name + "/" + child.name, depth + 1)
        elif stat.S_ISREG(mode):
            size = path.stat().st_size
            total += size
            if len(files) >= 2000 or total > 16_000_000:
                raise AgentBaseError("Receipt source exceeds 2000 files / 16 MB.")
            files[name] = {"sha256": file_hash(path, 1_000_000), "bytes": size}
        else:
            raise AgentBaseError("Receipt sources must be regular files/directories.")

    for name in selected:
        visit(name)
    if not files:
        raise AgentBaseError("Receipt source inventory is empty.")
    return {"roots": selected, "files": files}


def manifest(root: Path) -> dict:
    path = confined(root, MANIFEST)
    if not path.exists():
        directory = confined(root, DIRECTORY)
        if directory.exists() and any(directory.iterdir()):
            raise AgentBaseError("Preserving receipt files without a managed manifest.")
        return {"schema_version": 1, "files": {}}
    value = read_json(path)
    if (set(value) != {"schema_version", "files"} or type(value["schema_version"]) is not int
            or value["schema_version"] != 1 or not isinstance(value["files"], dict) or len(value["files"]) > 1000):
        raise AgentBaseError("Invalid receipt manifest.")
    for name, sha in value["files"].items():
        if (not re.fullmatch(re.escape(DIRECTORY) + r"/[a-f0-9]{32}\.json", name)
                or not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha)
                or file_hash(confined(root, name), 2_000_000) != sha):
            raise AgentBaseError("Preserving edited/missing managed receipt.")
    return value


def collect(argv: list[str], root: Path, environment: dict, timeout: int) -> dict:
    """Hash bounded pipe prefixes. Only the direct child is terminated on failure."""
    stop = threading.Event()
    streams = {}
    start = time.monotonic()
    process = subprocess.Popen(argv, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)

    def drain(label, stream):
        hasher, size = hashlib.sha256(), 0
        complete = False
        try:
            while True:
                chunk = stream.read1(65536)
                if not chunk:
                    complete = True
                    break
                kept = chunk[:max(0, OUTPUT_LIMIT - size)]
                size += len(kept)
                hasher.update(kept)
                if len(kept) != len(chunk):
                    stop.set()
                    break
        except OSError:
            stop.set()
        finally:
            streams[label] = {"sha256": hasher.hexdigest(), "bytes_hashed": size, "complete": complete}
            stream.close()

    threads = [threading.Thread(target=drain, args=(label, stream), daemon=True)
               for label, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
    timed_out = False
    try:
        for thread in threads:
            thread.start()
        while process.poll() is None:
            timed_out = time.monotonic() - start >= timeout
            if timed_out or stop.wait(0.01):
                break
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=0.5)
    # A descendant can retain pipe handles. Never wait indefinitely or call that passed.
    output = {label: streams.get(label, {"sha256": None, "bytes_hashed": 0, "complete": False})
              for label in ("stdout", "stderr")}
    status = ("timeout" if timed_out else "output-limit" if stop.is_set() else
              "output-incomplete" if not all(v["complete"] for v in output.values()) else
              "passed" if process.returncode == 0 else "failed")
    return {"status": status, "exit_code": process.returncode, "duration_seconds": round(time.monotonic() - start, 6),
            "output": output, "descendant_cleanup_verified": False}


def execute(root: Path, task_id: str, argv: list[str], sources: list[str], *, consent: bool = False,
            timeout: int = 60, pythonpath: list[str] | None = None) -> dict:
    if not consent:
        raise AgentBaseError("Review explicit argv and pass --consent: trusted HOST execution has filesystem/network rights; no sandbox.")
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 100 or
            any(not isinstance(a, str) or "\0" in a or len(a) > 10000 for a in argv) or sum(map(len, argv)) > 32000):
        raise AgentBaseError("Use bounded literal argv with an absolute trusted executable.")
    executable = Path(argv[0])
    if not executable.is_absolute() or (os.name == "nt" and executable.suffix.lower() != ".exe"):
        raise AgentBaseError("Use an absolute native executable; Windows script launchers are refused.")
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise AgentBaseError("Host test timeout must be 1..300 seconds.")
    executable = executable.resolve(strict=True)
    if os.name == "nt" and executable.suffix.lower() != ".exe":
        raise AgentBaseError("Resolved Windows executable must be native .exe; script targets are refused.")
    argv = [str(executable), *argv[1:]]
    with project_lock(root):
        current = tasks.load_plan(root)
        task = next((t for t in current["tasks"] if t["id"] == task_id), None)
        if task is None or task["status"] != "running" or not tasks.is_writer(task):
            raise AgentBaseError("Host checks require an existing running writer task in the canonical DAG.")
        owned = manifest(root)
        if len(owned["files"]) >= 1000:
            raise AgentBaseError("Receipt store is full; preserve/archive this milestone explicitly.")
        before = source_snapshot(root, task, sources)
        executable_sha = file_hash(executable)
        paths = [relative(n) for n in (pythonpath or [])]
        if len(paths) > 20:
            raise AgentBaseError("Select at most 20 explicit Python import directories.")
        for name in paths:
            if not confined(root, name).is_dir() or not any(name == n or name.startswith(n + "/") for n in before["roots"]):
                raise AgentBaseError("Python import paths must be directories within selected source roots.")
        environment = {k.upper(): v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        environment["PATH"] = str(executable.parent) + os.pathsep + (
            str(Path(environment.get("SYSTEMROOT", r"C:\Windows")) / "System32") if os.name == "nt" else "/usr/bin:/bin")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        if paths:
            environment["PYTHONPATH"] = os.pathsep.join(str(confined(root, name)) for name in paths)
        started = datetime.now(UTC).isoformat()
        result = collect(argv, root, environment, timeout)
        stale = []
        try:
            if source_snapshot(root, task, sources) != before:
                stale.append("sources-changed-during-run")
            if file_hash(executable) != executable_sha:
                stale.append("executable-changed-during-run")
            after_task = next((t for t in tasks.load_plan(root)["tasks"] if t["id"] == task_id), None)
            if after_task is None or tasks.definition(after_task) != tasks.definition(task) or after_task["status"] != "running":
                stale.append("task-changed-during-run")
        except (AgentBaseError, OSError):
            stale.append("bindings-unreadable-after-run")
        if manifest(root) != owned:
            raise AgentBaseError("Preserving receipt manifest changed during host execution.")
        receipt_id = uuid4().hex
        record = {"schema_version": 1, "id": receipt_id, "task_id": task_id, "task_sha256": tasks.definition(task),
                  "sources": before, "executable": str(executable), "executable_sha256": executable_sha,
                  "argv_sha256": digest(json_text(argv)), "pythonpath": paths, "timeout_seconds": timeout,
                  "started_at": started, "stale_at_recording": stale, "result": result,
                  "provenance": "local-host-execution; unauthenticated; explicit source subset; not a sandbox"}
        name = f"{DIRECTORY}/{receipt_id}.json"
        if confined(root, name).exists():
            raise AgentBaseError("Preserving existing untracked receipt path.")
        content = json_text(record)
        owned["files"][name] = digest(content)
        batch_write(root, {name: content, MANIFEST: json_text(owned)})
        return {"ok": result["status"] == "passed" and not stale, "receipt_id": receipt_id,
                "receipt": name, "result": result, "stale": stale, "task_state_changed": False}


def report(root: Path, receipt_id: str) -> dict:
    if not isinstance(receipt_id, str) or not re.fullmatch(r"[a-f0-9]{32}", receipt_id):
        raise AgentBaseError("Invalid receipt ID.")
    with project_lock(root):
        name = f"{DIRECTORY}/{receipt_id}.json"
        if name not in manifest(root)["files"]:
            raise AgentBaseError("Unknown managed receipt.")
        record = read_json(confined(root, name))
        stale = list(record["stale_at_recording"])
        task = next((t for t in tasks.load_plan(root)["tasks"] if t["id"] == record["task_id"]), None)
        if task is None or tasks.definition(task) != record["task_sha256"]:
            stale.append("task-definition-changed")
        try:
            if task is None or source_snapshot(root, task, record["sources"]["roots"]) != record["sources"]:
                stale.append("sources-changed")
            if file_hash(Path(record["executable"])) != record["executable_sha256"]:
                stale.append("executable-changed")
        except (AgentBaseError, OSError):
            stale.append("bindings-unreadable")
        return {"ok": record["result"]["status"] == "passed" and not stale,
                "fresh": not stale, "stale": stale, "receipt": record, "authenticated": False,
                "acceptance_verified": False, "task_state_changed": False}
