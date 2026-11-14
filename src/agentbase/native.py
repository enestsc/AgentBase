"""Network-disabled native CLI contract probes in trusted immutable local images.

No provider credentials, project mounts, model requests, CLI installation or image
pulls. A successful probe establishes flags/version, not model activation.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from . import distribution
from .catalog import asset
from .fs import AgentBaseError
from .providers import EVAL_FEATURES, EXEC_FEATURES, PRINT_FEATURES, flags
from .runner import DockerTaskRunner, policy, remove_owned_container


def verify_probe_boundary(value: dict, sources: dict[str, str] | None = None) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("HostConfig"), dict) or not isinstance(value.get("Config"), dict):
        raise AgentBaseError("Native probe container boundary unavailable.")
    host, config = value["HostConfig"], value["Config"]
    settings = value.get("NetworkSettings")
    if not isinstance(settings, dict):
        raise AgentBaseError("Native probe network metadata is unavailable.")
    networks = settings.get("Networks", {})
    if not isinstance(networks, dict) or set(networks) != {"none"} or not isinstance(host.get("CapDrop"), list) or not isinstance(host.get("SecurityOpt"), list):
        raise AgentBaseError("Native probe network/capability metadata is invalid.")
    mounts = host.get("Mounts", [])
    expected = sources or {}
    if (not isinstance(mounts, list) or any(not isinstance(m, dict) for m in mounts)
            or len(mounts) != len(expected)
            or {m.get("Target"): m.get("Source") for m in mounts if m.get("Type") == "bind" and m.get("ReadOnly") is True} != expected):
        raise AgentBaseError("Native probe permits only its explicit read-only first-party program files.")
    if (host.get("NetworkMode") != "none" or host.get("ReadonlyRootfs") is not True or host.get("Privileged") is not False
            or host.get("Binds") or host.get("PortBindings") or config.get("Volumes")
            or host.get("PublishAllPorts") is not False
            or host.get("LogConfig") != {"Type": "local", "Config": {"max-size": "256k", "max-file": "1", "compress": "false"}}
            or config.get("User") != "65534:65534" or config.get("Entrypoint") != ["/usr/bin/env"]
            or "ALL" not in (host.get("CapDrop") or []) or "no-new-privileges" not in (host.get("SecurityOpt") or [])
            or host.get("PidMode") not in ("", None) or host.get("IpcMode") != "private"
            or host.get("Memory") != 1024 * 1024 * 1024 or host.get("MemorySwap") != 1024 * 1024 * 1024
            or host.get("PidsLimit") != 64 or host.get("NanoCpus") != 1_000_000_000):
        raise AgentBaseError("Docker did not confirm a network-disabled, credential-free native probe boundary.")


def probe_command(engine: DockerTaskRunner, image: str, provider: str, arguments: list[str]) -> tuple[int, str]:
    allowed = {"codex": [["--version"], ["exec", "--help"], ["plugin", "--help"]],
               "claude": [["--version"], ["--help"], ["plugin", "eval", "--help"], ["plugin", "validate", "--help"]]}
    if provider not in allowed or arguments not in allowed[provider]:
        raise AgentBaseError("Native contract probes permit only known --version/--help commands.")
    return _container_command(engine, image, ["/usr/local/bin/" + provider, *arguments])


def _container_command(engine: DockerTaskRunner, image: str, command: list[str], *, sources: dict[str, str] | None = None,
                       timeout: int = 15) -> tuple[int, str]:
    """Internal literal commands only; callers never supply user prompts/scripts."""
    policy({"schema_version": 1, "provider": "deterministic", "image": image, "entrypoint": "/usr/bin/env",
            "arguments": [], "timeout_seconds": 15, "memory_mb": 1024, "pids": 64})
    name = "agentbase-native-probe-" + uuid4().hex
    attempted = False
    try:
        attempted = True
        arguments = ["create", "--pull=never", "--name", name, "--network=none", "--read-only", "--user=65534:65534",
                        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--init", "--no-healthcheck",
                        "--memory=1024m", "--memory-swap=1024m", "--pids-limit=64", "--cpus=1", "--ulimit=nofile=256:256",
                        "--log-driver=local", "--log-opt=max-size=256k", "--log-opt=max-file=1", "--log-opt=compress=false",
                        "--tmpfs=/tmp:rw,nosuid,nodev,size=64m,uid=65534,gid=65534", "--workdir=/tmp"]
        for target, source in (sources or {}).items():
            arguments += ["--mount", f"type=bind,source={source},target={target},readonly"]
        arguments += ["--entrypoint=/usr/bin/env", image, "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp",
                        "CODEX_HOME=/tmp/codex", "CLAUDE_CONFIG_DIR=/tmp/claude", "DISABLE_AUTOUPDATER=1", "DISABLE_TELEMETRY=1",
                        "OTEL_SDK_DISABLED=true", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1", *command]
        engine.command(arguments)
        try:
            observed = json.loads(engine.command(["inspect", "--format", "{{json .}}", name]))
        except ValueError as exc:
            raise AgentBaseError("Native probe inspection is invalid.") from exc
        verify_probe_boundary(observed, sources)
        deadline = time.monotonic() + timeout
        engine.command(["start", name], 10)
        code = engine.command(["wait", name], max(0.01, deadline - time.monotonic())).strip()
        if not code.isdigit() or not 0 <= int(code) <= 255:
            raise AgentBaseError("Native probe exit status unavailable.")
        return int(code), engine.command(["logs", name])
    finally:
        if attempted:
            remove_owned_container(engine, name)


def mock_smoke(root: Path, provider: str, image: str, *, mode: str = "print", consent: bool = False) -> dict:
    """Exercise native protocol decoding against a fixed synthetic loopback API."""
    if mode not in {"print", "eval"} or mode == "eval" and provider != "claude":
        raise AgentBaseError("Synthetic native eval requires Claude; supported modes are print/eval.")
    contract = inspect_image(root, provider, image, consent=consent)
    if not contract["available"]:
        raise AgentBaseError("Native executable unavailable; synthetic protocol probe not launched.")
    if mode == "eval" and not contract.get("native_eval_available"):
        raise AgentBaseError("Required native eval flags are unavailable; synthetic eval not launched.")
    engine = DockerTaskRunner()
    if Path(engine.executable).resolve().is_relative_to(root.resolve()):
        raise AgentBaseError("Project-local Docker executables are refused.")
    engine.connect()
    with tempfile.TemporaryDirectory(prefix="agentbase-native-mock-") as temporary:
        directory = Path(temporary)
        directory.chmod(0o700)
        sources = {}
        programs = {name: asset(name) for name in ("native-mock.cjs", "gateway.cjs", "gateway-policy.json")}
        if provider == "claude":
            programs["native-plugin.json"] = json.dumps(distribution.files("claude"))
        for name, content in programs.items():
            path = directory / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o644)
            source = str(path.resolve())
            if any(c in source for c in (",", "\r", "\n")):
                raise AgentBaseError("Native probe temporary path contains a Docker mount separator.")
            sources["/program/" + name] = source
        code, raw = _container_command(engine, image, ["/usr/local/bin/node", "/program/native-mock.cjs", provider, mode],
                                       sources=sources, timeout=65)
    try:
        result = json.loads(raw)
        if (code != 0 or not isinstance(result, dict) or type(result.get("schema_version")) is not int or result["schema_version"] != 1
                or result.get("provider") != provider or result.get("origin") != "mock"
                or result.get("mode") != mode
                or type(result.get("provider_api_calls")) is not int or result["provider_api_calls"] != 0
                or result.get("actual_model_behavior_verified") is not False):
            raise ValueError
    except (ValueError, RecursionError) as exc:
        raise AgentBaseError("Synthetic native probe output invalid; no raw native output was retained.") from exc
    metrics = result.get("gateway_metrics")
    metric_names = {"attempted_requests", "successful_requests", "rejected_requests", "upstream_failures", "bytes_sent", "bytes_received"}
    if (not isinstance(metrics, dict) or set(metrics) != metric_names or any(type(v) is not int or not 0 <= v <= 2_000_000 for v in metrics.values())
            or type(result.get("fixture_requests")) is not int or not 0 <= result["fixture_requests"] <= 2
            or type(result.get("exit_code")) not in (int, type(None))
            or result["exit_code"] is not None and not 0 <= result["exit_code"] <= 255
            or not 0 <= metrics["successful_requests"] <= metrics["attempted_requests"] <= 2
            or metrics["successful_requests"] != result["fixture_requests"]):
        raise AgentBaseError("Synthetic native probe metrics are invalid.")
    # Return an explicit allowlist: native stdout/stderr and traces stay discarded.
    passed = (result.get("exit_code") == 0 and result.get("marker_verified") is True and result.get("output_overflow") is False
              and result["fixture_requests"] == 1 and metrics["upstream_failures"] == 0)
    evidence = result.get("eval_evidence")
    if mode == "eval" and evidence is not None:
        if (not isinstance(evidence, dict) or set(evidence) != {"cases_total", "cases_passed", "score_is_one", "run_error"}
                or type(evidence["cases_total"]) is not int or evidence["cases_total"] not in (0, 1)
                or type(evidence["cases_passed"]) is not int or evidence["cases_passed"] not in (0, 1)
                or type(evidence["score_is_one"]) is not bool or type(evidence["run_error"]) is not bool):
            raise AgentBaseError("Synthetic eval evidence is invalid.")
    if mode == "eval":
        passed = passed and evidence == {"cases_total": 1, "cases_passed": 1, "score_is_one": True, "run_error": False}
    if provider == "claude" and mode == "print":
        passed = passed and result.get("canonical_plugin_discovered") is True
    return {"ok": passed, "provider": provider, "image": image, "version": contract["version"], "mode": mode, "origin": "mock", "passed": passed,
            "exit_code": result["exit_code"], "marker_verified": result.get("marker_verified") is True,
            "fixture_requests": result["fixture_requests"], "gateway_metrics": metrics, "provider_api_calls": 0,
            "canonical_plugin_discovered": result.get("canonical_plugin_discovered") is True,
            "eval_evidence": evidence if mode == "eval" else None,
            "actual_model_behavior_verified": False, "host_files_changed": [], "provider_credentials": 0,
            "boundary": "network-disabled container; loopback synthetic API; first-party program mounts only",
            "note": "Fixture token counts are synthetic. This does not measure plugin effectiveness, provider usage or cost."}


def inspect_image(root: Path, provider: str, image: str, *, consent: bool = False) -> dict:
    if not consent:
        raise AgentBaseError("Pass --consent for network-disabled version/help probes in a trusted pinned image.")
    if provider not in {"codex", "claude"}:
        raise AgentBaseError("Unsupported native probe provider.")
    policy({"schema_version": 1, "provider": "deterministic", "image": image, "entrypoint": "/usr/bin/env",
            "arguments": [], "timeout_seconds": 15, "memory_mb": 1024, "pids": 64})
    engine = DockerTaskRunner()
    if Path(engine.executable).resolve().is_relative_to(root.resolve()):
        raise AgentBaseError("Project-local Docker executables are refused.")
    engine.connect()
    engine.command(["image", "inspect", "--format", "{{.Id}}", image], 5)
    code, version = probe_command(engine, image, provider, ["--version"])
    match = re.search(r"\b\d+\.\d+\.\d+(?:[-+.][a-zA-Z0-9.-]+)?", version)
    if code or not match:
        return {"provider": provider, "image": image, "available": False, "reason": "trusted native executable/version unavailable",
                "model_sessions": 0, "native_launch_enabled": False}
    result = {"provider": provider, "image": image, "version": match[0], "available": True,
              "origin": "network-disabled-container-probe", "model_sessions": 0, "native_launch_enabled": False,
              "project_mounts": 0, "provider_credentials": 0, "runtime_behavior_verified": False}
    if provider == "codex":
        code, text = probe_command(engine, image, provider, ["exec", "--help"])
        supported = flags(text) if code == 0 and "codex exec" in text else set()
        plugin_code, plugin_help = probe_command(engine, image, provider, ["plugin", "--help"])
        return result | {"exec_features": sorted(supported & EXEC_FEATURES),
                         "native_eval_available": False,
                         "native_plugin_validator": plugin_code == 0 and re.search(r"^\s+validate\s", plugin_help, re.M) is not None}
    code, general_help = probe_command(engine, image, provider, ["--help"])
    general = flags(general_help) if code == 0 else set()
    eval_code, eval_help = probe_command(engine, image, provider, ["plugin", "eval", "--help"])
    supported = flags(eval_help) if eval_code == 0 and "claude plugin eval" in eval_help else set()
    validator_code, validator_help = probe_command(engine, image, provider, ["plugin", "validate", "--help"])
    required = EVAL_FEATURES
    return result | {"print_features": sorted(general & PRINT_FEATURES),
                     "eval_features": sorted(supported & required), "native_eval_available": required <= supported,
                     "native_plugin_validator": validator_code == 0 and "claude plugin validate" in validator_help,
                     "hard_spending_ceiling_verified": False}
