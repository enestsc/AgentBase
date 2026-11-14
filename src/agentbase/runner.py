"""Opt-in offline Docker worker boundary. Never launches cloud providers or pulls images.

Workers receive bounded snapshots and return untrusted proposals. Host integration
and DAG review remain explicit; a container is not a separate virtual machine.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from . import tasks
from .context import read_source
from .fs import AgentBaseError, digest, json_text, relative


def docker_environment() -> dict[str, str]:
    """Host Docker transport configuration only; no provider credentials."""
    return {k: v for k, v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}}


def remove_owned_container(engine, name: str) -> None:
    if not re.fullmatch(r"agentbase-(?:worker|gateway|native-probe)-[a-f0-9]{32}(?:-probe)?", name):
        raise AgentBaseError("Refusing cleanup outside the generated AgentBase container namespace.")
    query = ["container", "ls", "--all", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}"]
    present = engine.command(query).strip()
    if present == name:
        engine.command(["rm", "--force", "--volumes", name])
        if engine.command(query).strip():
            raise AgentBaseError("Owned container removal was not verified.")
    elif present:
        raise AgentBaseError("Unexpected owned container cleanup identity.")


class TaskRunner(Protocol):
    def run(self, root: Path, task: dict, context: list[str], configuration: dict, *, consent: bool = False) -> dict: ...


def policy(value: dict) -> dict:
    required = {"schema_version", "provider", "image", "entrypoint", "arguments", "timeout_seconds", "memory_mb", "pids"}
    if not isinstance(value, dict) or set(value) != required or value["schema_version"] != 1:
        raise AgentBaseError("Worker policy requires exactly schema_version, provider, image, entrypoint, arguments, timeout_seconds, memory_mb, pids.")
    if value["provider"] != "deterministic":
        raise AgentBaseError("Only offline deterministic workers are supported; cloud-provider credential/network isolation is not implemented.")
    if not isinstance(value["image"], str) or not re.fullmatch(r"(?:[a-z0-9][a-z0-9./:_-]*@)?sha256:[a-f0-9]{64}", value["image"]):
        raise AgentBaseError("Use a trusted preinstalled repository@sha256 digest or full local sha256 image ID.")
    if not isinstance(value["entrypoint"], str) or not re.fullmatch(r"/[A-Za-z0-9/_.-]+", value["entrypoint"]):
        raise AgentBaseError("Worker entrypoint must be an absolute in-image executable path.")
    if (not isinstance(value["arguments"], list) or len(value["arguments"]) > 30
            or any(not isinstance(a, str) or len(a) > 10_000 or "\0" in a for a in value["arguments"])):
        raise AgentBaseError("Worker arguments must be bounded literal strings.")
    for key, low, high in (("timeout_seconds", 1, 300), ("memory_mb", 32, 4096), ("pids", 4, 128)):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise AgentBaseError(f"Worker {key} must be {low}..{high}.")
    return dict(value)


def snapshot(root: Path, task: dict, names: list[str]) -> dict:
    if len(names) > 50:
        raise AgentBaseError("Worker context is limited to 50 explicit files.")
    files, size = {}, 0
    for raw in names:
        name = relative(raw)
        if name in files:
            raise AgentBaseError("Duplicate worker context path.")
        if not any(kind == "file" and (scope == "." or name.casefold() == scope or name.casefold().startswith(scope + "/"))
                   for kind, scope, _ in tasks.claims(task)):
            raise AgentBaseError("Worker context lies outside the task's declared file scope.")
        text, error = read_source(root, name, 100_000)
        if error:
            raise AgentBaseError("Worker context refused: " + error)
        size += len(text.encode("utf-8"))
        if size > 500_000:
            raise AgentBaseError("Worker context exceeds 500 KB.")
        files[name] = {"text": text, "sha256": digest(text)}
    return {"schema_version": 1, "task": task, "files": files,
            "contract": "Return one JSON object with handoff (existing AgentBase schema) and files (path -> proposed UTF-8 text or null). No direct host changes."}


class DockerTaskRunner:
    """Offline-only implementation; local Linux Docker daemon is the trust boundary."""

    def __init__(self):
        self.executable = shutil.which("docker")
        if not self.executable:
            raise AgentBaseError("Docker unavailable; keep work in the active host. No alternative provider launched.")
        if Path(self.executable).resolve().is_relative_to(Path.cwd().resolve()):
            raise AgentBaseError("Refusing a project-local Docker executable; use a trusted host installation.")
        self.endpoint = None

    def command(self, arguments: list[str], timeout: float = 10) -> str:
        environment = docker_environment()
        prefix = [self.executable] + (["--host", self.endpoint] if self.endpoint else [])
        try:
            result = subprocess.run([*prefix, *arguments], env=environment, capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AgentBaseError("Docker unavailable, permission denied or timed out; no host task files changed.") from exc
        if result.returncode:
            diagnostic = result.stderr.decode("utf-8", errors="replace")[:600] if arguments[0] in {"create", "start"} else "Check the local daemon and trusted image availability."
            raise AgentBaseError(f"Docker {arguments[0]} failed; no host task files changed. {diagnostic}")
        if len(result.stdout) > 1_100_000:
            raise AgentBaseError("Docker worker output exceeds the 1 MB bound.")
        try:
            return result.stdout.decode("utf-8")
        except UnicodeError as exc:
            raise AgentBaseError("Worker output is not UTF-8.") from exc

    def connect(self):
        endpoint = self.command(["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], 5).strip()
        if not (endpoint.startswith("unix:///") or endpoint in {"npipe:////./pipe/docker_engine", "npipe:////./pipe/dockerDesktopLinuxEngine"}):
            raise AgentBaseError("Remote Docker contexts are refused; input snapshots must stay on a local daemon.")
        self.endpoint = endpoint
        if self.command(["version", "--format", "{{.Server.Os}}"], 5).strip() != "linux":
            raise AgentBaseError("This worker boundary requires Linux containers; no host subprocess fallback.")

    def run(self, root: Path, task: dict, context: list[str], configuration: dict, *, consent: bool = False) -> dict:
        configured = policy(configuration)
        if Path(self.executable).resolve().is_relative_to(root.resolve()):
            raise AgentBaseError("Refusing a project-local Docker executable.")
        if not consent:
            raise AgentBaseError("Review the trusted pinned image/entrypoint and pass --consent to execute the offline worker.")
        if task.get("status") != "running":
            raise AgentBaseError("Claim/start the task through the existing DAG before executing an offline worker.")
        request = snapshot(root, task, context)
        self.connect()
        # No inspect output is retained or exposed; image presence does not grant trust.
        self.command(["image", "inspect", "--format", "{{.Id}}", configured["image"]], 5)
        name = "agentbase-worker-" + uuid4().hex
        with tempfile.TemporaryDirectory(prefix="agentbase-worker-") as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            file = directory / "request.json"
            file.write_text(json_text(request), encoding="utf-8")
            # Container uid must read this snapshot; the parent remains owner-only
            # on POSIX. Windows inherits the user's temp-directory ACL.
            file.chmod(0o644)
            source = str(file.resolve())
            if any(c in source for c in (",", "\n", "\r")):
                raise AgentBaseError("Worker temporary path cannot contain Docker mount separators.")
            args = ["create", "--pull=never", "--name", name, "--network=none", "--read-only", "--cap-drop=ALL",
                    "--security-opt=no-new-privileges", "--user=65534:65534", "--init", "--no-healthcheck",
                    "--pids-limit", str(configured["pids"]), "--memory", f"{configured['memory_mb']}m",
                    "--memory-swap", f"{configured['memory_mb']}m", "--cpus=1", "--ulimit=nofile=128:128",
                    "--ulimit=fsize=8388608:8388608", "--log-driver=local", "--log-opt=max-size=1m", "--log-opt=max-file=1", "--log-opt=compress=false",
                    "--tmpfs=/work:rw,nosuid,nodev,size=32m,uid=65534,gid=65534", "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m,uid=65534,gid=65534",
                    "--mount", f"type=bind,source={source},target=/input/request.json,readonly", "--workdir=/work",
                    "--entrypoint=/usr/bin/env", configured["image"], "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp",
                    configured["entrypoint"], *configured["arguments"]]
            created = False
            cleanup_failed = False
            try:
                created = True
                self.command(args)
                try:
                    observed = json.loads(self.command(["inspect", "--format", "{{json .}}", name]))
                except ValueError as exc:
                    raise AgentBaseError("Docker boundary configuration could not be verified.") from exc
                verify_boundary(observed, source, configured)
                deadline = time.monotonic() + configured["timeout_seconds"]
                self.command(["start", name], min(10, configured["timeout_seconds"]))
                code = self.command(["wait", name], max(0.01, deadline - time.monotonic())).strip()
                if code != "0":
                    raise AgentBaseError("Isolated worker exited unsuccessfully; no host task files changed.")
                raw = self.command(["logs", name])
                try:
                    value = json.loads(raw)
                except (ValueError, RecursionError) as exc:
                    raise AgentBaseError("Isolated worker returned invalid JSON; output is untrusted and was not applied.") from exc
                result = validate_result(value, task, request)
            finally:
                if created:
                    try:
                        remove_owned_container(self, name)
                    except AgentBaseError:
                        cleanup_failed = True
                if cleanup_failed:
                    raise AgentBaseError("Worker cleanup could not be verified. Inspect container " + name + "; no host integration was performed.")
        return result | {"provider": "deterministic", "image": configured["image"], "host_files_changed": [],
                         "boundary": "local Linux Docker; no network, non-root, dropped capabilities, bounded memory/PIDs/tmpfs; not a VM",
                         "task_state_changed": False, "trusted": False}


def verify_boundary(value: dict, source: str, configured: dict) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("HostConfig"), dict) or not isinstance(value.get("Config"), dict):
        raise AgentBaseError("Docker boundary configuration is invalid; worker not started.")
    host, config = value.get("HostConfig", {}), value.get("Config", {})
    mounts = host.get("Mounts", [])
    if (not isinstance(mounts, list) or any(not isinstance(m, dict) for m in mounts)
            or not isinstance(host.get("CapDrop"), list) or not isinstance(host.get("SecurityOpt"), list)):
        raise AgentBaseError("Docker mounts/permissions could not be verified; worker not started.")
    if (host.get("NetworkMode") != "none" or host.get("ReadonlyRootfs") is not True or host.get("Privileged") is not False
            or host.get("PidMode") not in ("", None) or host.get("IpcMode") != "private"
            or "ALL" not in host.get("CapDrop", []) or "no-new-privileges" not in host.get("SecurityOpt", [])
            or host.get("Memory") != configured["memory_mb"] * 1024 * 1024 or host.get("PidsLimit") != configured["pids"]
            or host.get("NanoCpus") != 1_000_000_000 or config.get("User") != "65534:65534" or config.get("Volumes")
            or len(mounts) != 1 or mounts[0].get("Type") != "bind" or mounts[0].get("Source") != source
            or mounts[0].get("Target") != "/input/request.json" or mounts[0].get("ReadOnly") is not True):
        raise AgentBaseError("Docker did not confirm the required offline filesystem/process/resource boundary; worker not started.")


def validate_result(value: dict, task: dict, request: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"handoff", "files"} or not isinstance(value["files"], dict) or len(value["files"]) > 100:
        raise AgentBaseError("Worker result requires a handoff and bounded proposed files mapping.")
    tasks.validate_handoff(value["handoff"], task)
    if set(value["files"]) != set(value["handoff"]["changed_files"]):
        raise AgentBaseError("Worker proposal files do not match handoff changed_files.")
    seen = set()
    for name, content in value["files"].items():
        relative(name)
        if name.casefold() in seen or content is not None and (not isinstance(content, str) or len(content.encode("utf-8")) > 100_000):
            raise AgentBaseError("Invalid or colliding proposed file.")
        seen.add(name.casefold())
    return {"handoff": value["handoff"], "proposed_files": value["files"],
            "input_hashes": {n: f["sha256"] for n, f in request["files"].items()},
            "note": "Review and test proposals in the host; worker test observations are not authenticated. No automatic task completion or file integration."}
