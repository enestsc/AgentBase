"""Explicit credential-isolating Docker gateway; no credential discovery or inference.

The first-party sidecar receives an explicitly supplied key through stdin. Model
workers can join only its internal network and use a run-scoped capability.
Native provider/eval launch remains separately gated; this module starts no model.
"""

from __future__ import annotations

import json
import os
import queue
import re
import secrets
import subprocess
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from .catalog import asset
from .fs import AgentBaseError
from .runner import DockerTaskRunner, docker_environment, remove_owned_container
from .runner import policy as worker_policy


def policy(value: dict) -> dict:
    specification = json.loads(asset("gateway-policy.json"))
    if (not isinstance(value, dict) or set(value) != set(specification["fields"]) or type(value["schema_version"]) is not int
            or value["schema_version"] != 1 or not isinstance(value["provider"], str) or value["provider"] not in specification["targets"]
            or not isinstance(value["model"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}", value["model"])):
        raise AgentBaseError("Invalid gateway schema/provider/model; use the documented bounded policy.")
    for key, (low, high) in specification["limits"].items():
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise AgentBaseError(f"Gateway {key} must be {low}..{high}.")
    if value["timeout_seconds"] > value["lifetime_seconds"]:
        raise AgentBaseError("Gateway request timeout must fit its lifetime.")
    return dict(value)


def verify_network(value: dict) -> None:
    if (not isinstance(value, dict) or value.get("Internal") is not True or value.get("Driver") != "bridge"
            or value.get("Scope") != "local" or value.get("Ingress") is not False):
        raise AgentBaseError("Docker did not confirm a local internal gateway network.")


def verify_container(value: dict, network: str, sources: dict[str, str]) -> None:
    if not isinstance(value, dict):
        raise AgentBaseError("Invalid gateway container inspection.")
    host, config = value.get("HostConfig"), value.get("Config")
    settings = value.get("NetworkSettings")
    if not isinstance(settings, dict):
        raise AgentBaseError("Gateway network metadata unavailable.")
    networks = settings.get("Networks", {})
    if not isinstance(host, dict) or not isinstance(config, dict) or not isinstance(networks, dict):
        raise AgentBaseError("Invalid gateway boundary metadata.")
    mounts = host.get("Mounts", [])
    if not isinstance(mounts, list) or any(not isinstance(m, dict) for m in mounts):
        raise AgentBaseError("Invalid gateway mount metadata.")
    expected = {target: source for target, source in sources.items()}
    actual = {m.get("Target"): m.get("Source") for m in mounts if m.get("Type") == "bind" and m.get("ReadOnly") is True}
    if (set(networks) != {"bridge", network} or host.get("NetworkMode") != "bridge"
            or host.get("ReadonlyRootfs") is not True or host.get("Privileged") is not False
            or host.get("PidMode") not in (None, "") or host.get("IpcMode") != "private"
            or "ALL" not in (host.get("CapDrop") or []) or "no-new-privileges" not in (host.get("SecurityOpt") or [])
            or host.get("Memory") != 128 * 1024 * 1024 or host.get("MemorySwap") != 128 * 1024 * 1024
            or host.get("PidsLimit") != 32 or host.get("NanoCpus") != 500_000_000
            or host.get("PortBindings") or host.get("PublishAllPorts") is not False
            or config.get("User") != "65534:65534" or config.get("Volumes")
            or config.get("Entrypoint") != ["/usr/bin/env"] or host.get("LogConfig", {}).get("Type") != "none"
            or len(mounts) != len(expected) or actual != expected):
        raise AgentBaseError("Docker did not confirm credential/network isolation; gateway not started.")


class GatewaySession:
    """One short-lived, policy-bound credential sidecar. Call stop in finally."""

    def __init__(self, image: str):
        checked = worker_policy({"schema_version": 1, "provider": "deterministic", "image": image,
                                 "entrypoint": "/usr/local/bin/node", "arguments": [], "timeout_seconds": 10, "memory_mb": 128, "pids": 32})
        self.image = checked["image"]
        suffix = uuid4().hex
        self.name = "agentbase-gateway-" + suffix
        self.network = "agentbase-private-" + suffix
        self.capability = secrets.token_urlsafe(32)
        self.base_url = "http://gateway:8787"
        self.engine = None
        self.process = None
        self.temporary = None
        self.network_attempted = self.container_attempted = False
        self.started = False

    def start(self, configuration: dict, credential: str, *, consent: bool = False) -> dict:
        checked = policy(configuration)
        if not consent:
            raise AgentBaseError("Explicit --consent is required before creating a credential gateway.")
        if self.engine is not None:
            raise AgentBaseError("Gateway session cannot be reused.")
        if not isinstance(credential, str) or not re.fullmatch(r"[\x21-\x7e]{16,4096}", credential) or credential == self.capability:
            raise AgentBaseError("Explicit gateway credential is invalid; no credential files or environment were read.")
        self.engine = DockerTaskRunner()
        self.engine.connect()
        self.engine.command(["image", "inspect", "--format", "{{.Id}}", self.image], 5)
        self.temporary = tempfile.TemporaryDirectory(prefix="agentbase-gateway-")
        try:
            directory = Path(self.temporary.name)
            directory.chmod(0o700)
            sources = {}
            for name in ("gateway.cjs", "gateway-policy.json"):
                path = directory / name
                path.write_text(asset(name), encoding="utf-8")
                path.chmod(0o644)
                source = str(path.resolve())
                if any(c in source for c in (",", "\r", "\n")):
                    raise AgentBaseError("Gateway temporary path contains a Docker mount separator.")
                sources["/program/" + name] = source
            self.network_attempted = True
            self.engine.command(["network", "create", "--internal", "--driver", "bridge", "--label", "agentbase.gateway=" + self.name, self.network])
            verify_network(json.loads(self.engine.command(["network", "inspect", "--format", "{{json .}}", self.network])))
            arguments = ["create", "--pull=never", "--interactive", "--name", self.name, "--network=bridge", "--read-only",
                         "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--init", "--no-healthcheck",
                         "--memory=128m", "--memory-swap=128m", "--pids-limit=32", "--cpus=0.5", "--ulimit=nofile=128:128",
                         "--log-driver=none", "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=8m,uid=65534,gid=65534"]
            for target, source in sources.items():
                arguments += ["--mount", f"type=bind,source={source},target={target},readonly"]
            arguments += ["--entrypoint=/usr/bin/env", self.image, "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp",
                          "/usr/local/bin/node", "/program/gateway.cjs"]
            self.container_attempted = True
            self.engine.command(arguments)
            self.engine.command(["network", "connect", "--alias", "gateway", self.network, self.name])
            observed = json.loads(self.engine.command(["inspect", "--format", "{{json .}}", self.name]))
            verify_container(observed, self.network, sources)
            prefix = [self.engine.executable, "--host", self.engine.endpoint]
            self.process = subprocess.Popen([*prefix, "start", "--attach", "--interactive", self.name],
                                            env=docker_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            ready = queue.Queue(maxsize=1)
            def first_line():
                try:
                    ready.put(self.process.stdout.readline(1024))
                except OSError:
                    ready.put(b"")
            def discard_diagnostics():
                try:
                    while self.process.stderr.read(4096):
                        pass
                except OSError:
                    pass
            threading.Thread(target=first_line, daemon=True).start()
            threading.Thread(target=discard_diagnostics, daemon=True).start()
            bootstrap = json.dumps({"policy": checked, "credential": credential, "capability": self.capability}, separators=(",", ":")).encode() + b"\n"
            self.process.stdin.write(bootstrap)
            self.process.stdin.flush()
            del bootstrap
            try:
                line = ready.get(timeout=10)
                if json.loads(line) != {"ready": True}:
                    raise ValueError
            except (queue.Empty, ValueError, UnicodeError) as exc:
                raise AgentBaseError("Gateway bootstrap was not confirmed; no provider request was launched by AgentBase.") from exc
            self.started = True
            return {"started": True, "provider": checked["provider"], "model": checked["model"],
                    "credential_files": 0, "host_ports": 0, "model_calls_launched": 0,
                    "limits": {k: checked[k] for k in checked if k.startswith("max_") or k.endswith("_seconds")},
                    "budget_note": "Protocol limits, not an exact billing/subscription cap; upstream may continue after disconnect."}
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        errors = []
        if self.process is not None and self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        if self.engine is not None:
            if self.container_attempted:
                try:
                    remove_owned_container(self.engine, self.name)
                except AgentBaseError:
                    errors.append(self.name)
            if self.network_attempted:
                try:
                    names = self.engine.command(["network", "ls", "--filter", "name=^" + self.network + "$", "--format", "{{.Name}}"])
                    if names.strip() == self.network:
                        self.engine.command(["network", "rm", self.network])
                        if self.engine.command(["network", "ls", "--filter", "name=^" + self.network + "$", "--format", "{{.Name}}"]).strip():
                            raise AgentBaseError("Gateway network still present.")
                    elif names.strip():
                        raise AgentBaseError("Unexpected network identity.")
                except AgentBaseError:
                    errors.append(self.network)
        if self.process is not None:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            for stream in (self.process.stdout, self.process.stderr):
                if stream is not None:
                    stream.close()
        if self.temporary is not None:
            self.temporary.cleanup()
        self.started = False
        if errors:
            raise AgentBaseError("Gateway cleanup could not be verified; inspect owned resources: " + ", ".join(errors))

    def __enter__(self):
        if not self.started:
            raise AgentBaseError("Start the explicitly consented gateway before entering its scope.")
        return self

    def __exit__(self, *_):
        self.stop()


def self_test(image: str, *, consent: bool = False) -> dict:
    """Local Docker proof using a dummy key; deliberately makes no valid API call."""
    if not consent:
        raise AgentBaseError("Pass --consent to run the local synthetic Docker gateway self-test; no model is called.")
    credential = "agentbase-fixture-provider-secret-only-in-sidecar"
    configuration = {"schema_version": 1, "provider": "codex", "model": "fixture-model-never-called", "max_requests": 1,
                     "max_output_tokens": 16, "max_request_bytes": 2048, "max_response_bytes": 2048,
                     "timeout_seconds": 1, "lifetime_seconds": 20}
    session = GatewaySession(image)
    try:
        report = session.start(configuration, credential, consent=True)
        engine = session.engine
        observed = engine.command(["inspect", "--format", "{{json .}}", session.name])
        if credential in observed or credential in json.dumps(report):
            raise AgentBaseError("Synthetic credential appeared in Docker configuration or public report.")
        for file in Path(session.temporary.name).iterdir():
            if credential in file.read_text(encoding="utf-8"):
                raise AgentBaseError("Synthetic credential appeared in a bootstrap file.")
        worker = session.name + "-probe"
        attempted = False
        try:
            attempted = True
            engine.command(["create", "--pull=never", "--interactive", "--name", worker, "--network", session.network,
                            "--read-only", "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--init",
                            "--memory=128m", "--memory-swap=128m", "--pids-limit=32", "--cpus=0.5", "--no-healthcheck", "--log-driver=none",
                            "--entrypoint=/usr/bin/env", image, "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp",
                            "/usr/local/bin/node", "-e", asset("gateway-probe.cjs")])
            state = json.loads(engine.command(["inspect", "--format", "{{json .}}", worker]))
            if (set(state["NetworkSettings"]["Networks"]) != {session.network} or state["HostConfig"].get("Mounts")
                    or state["HostConfig"]["ReadonlyRootfs"] is not True or state["HostConfig"]["PortBindings"]):
                raise AgentBaseError("Probe worker network/mount isolation was not confirmed.")
            try:
                result = subprocess.run([engine.executable, "--host", engine.endpoint, "start", "--attach", "--interactive", worker],
                                        input=json.dumps({"capability": session.capability}).encode(), env=docker_environment(),
                                        capture_output=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise AgentBaseError("Gateway probe unavailable or timed out; no valid API request was made.") from exc
            if result.returncode or credential.encode() in result.stdout or credential.encode() in result.stderr:
                raise AgentBaseError("Gateway probe failed or exposed a synthetic credential.")
            try:
                observations = json.loads(result.stdout)
            except (ValueError, UnicodeError) as exc:
                raise AgentBaseError("Invalid synthetic gateway probe output.") from exc
            if (observations.get("provider_calls") != 0 or len(observations.get("checks", [])) != 7
                    or any(c["status"] != "passed" for c in observations["checks"])):
                raise AgentBaseError("Gateway boundary smoke assertions failed.")
        finally:
            if attempted:
                remove_owned_container(engine, worker)
        observations["checks"].extend([
            {"command": "provider credential absent from Docker config/report", "status": "passed"},
            {"command": "provider credential absent from bootstrap files", "status": "passed"}])
    finally:
        session.stop()
    expiring = GatewaySession(image)
    try:
        expiring.start(configuration | {"lifetime_seconds": 1}, credential, consent=True)
        if expiring.engine.command(["wait", expiring.name], 4).strip() != "0":
            raise AgentBaseError("Gateway lifetime did not terminate the credential process cleanly.")
    finally:
        expiring.stop()
    return {"ok": True, **observations, "gateway_and_network_removed": True, "lifetime_expiry_verified": True,
            "image_pulls": 0, "origin": "synthetic-offline-probe"}
