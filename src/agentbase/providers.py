"""Explicit read-only native feature probes; never start inference or install plugins."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .fs import AgentBaseError

EXEC_FEATURES = {"--json", "--sandbox", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--output-schema"}
EVAL_FEATURES = {"--max-cost-usd", "--concurrency", "--no-publish", "--no-scaffold", "--mocks"}
PRINT_FEATURES = {"--print", "--output-format", "--input-format", "--settings", "--setting-sources", "--plugin-dir", "--strict-mcp-config", "--tools", "--max-budget-usd"}


def executable(provider: str, project: Path | None = None) -> str:
    if provider not in {"codex", "claude"}:
        raise AgentBaseError("Unsupported native provider.")
    found = shutil.which(provider)
    if (not found or Path(found).resolve().is_relative_to(Path.cwd().resolve())
            or project is not None and Path(found).resolve().is_relative_to(project.resolve())):
        raise AgentBaseError("Trusted host provider executable unavailable; project-local executables are refused.")
    return found


def invoke(binary: str, arguments: list[str]) -> tuple[int, str]:
    environment = {k: v for k, v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}}
    environment.update(NO_COLOR="1", DO_NOT_TRACK="1", OTEL_SDK_DISABLED="true",
                       DISABLE_TELEMETRY="1", DISABLE_AUTOUPDATER="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
    with tempfile.TemporaryDirectory(prefix="agentbase-native-probe-") as directory:
        try:
            result = subprocess.run([binary, *arguments], cwd=directory, env=environment,
                                    capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AgentBaseError("Native feature probe unavailable/timed out; no model session was requested.") from exc
    if len(result.stdout) + len(result.stderr) > 150_000:
        raise AgentBaseError("Native feature probe output exceeds limit.")
    return result.returncode, result.stdout.decode("utf-8", errors="replace")


def flags(text: str) -> set[str]:
    return set(re.findall(r"(?<![\w-])--[a-z][a-z-]+\b", text))


def inspect(provider: str, *, consent: bool = False, root: Path | None = None) -> dict:
    if not consent:
        raise AgentBaseError("Pass --consent for explicit native --version/--help probes; no inference is launched.")
    binary = executable(provider, root)
    code, version = invoke(binary, ["--version"])
    match = re.search(r"\b\d+\.\d+\.\d+(?:[-+.][a-zA-Z0-9.-]+)?", version)
    if code or not match:
        raise AgentBaseError("Native CLI did not report a recognizable version.")
    report = {"provider": provider, "version": match[0], "model_sessions": 0,
              "plugin_activation_verified": False, "native_launch_enabled": False,
              "launch_blocker": "Provider network/credential isolation and a bounded spending contract are not implemented; offline TaskRunner only."}
    if provider == "claude":
        code, help_text = invoke(binary, ["plugin", "eval", "--help"])
        supported = flags(help_text) if code == 0 and "claude plugin eval" in help_text else set()
        required = EVAL_FEATURES
        validation_code, validation = invoke(binary, ["plugin", "validate", "--help"])
        semantics = " ".join(help_text.split()).lower()
        budget = ("Native max-cost threshold is checked before launches; in-flight runs can overrun. Not a precise hard cap."
                  if "checked before" in semantics and "in flight" in semantics else
                  "Budget flag detected; exact enforcement semantics unverified for this version. No hard spending cap established.")
        return report | {"native_eval_available": required <= supported,
                         "eval_features": sorted(supported & required),
                         "native_plugin_validator": validation_code == 0 and "claude plugin validate" in validation,
                         "hard_spending_ceiling_verified": False,
                         "budget_semantics": budget}
    code, help_text = invoke(binary, ["exec", "--help"])
    supported = flags(help_text) if code == 0 and "codex exec" in help_text else set()
    plugin_code, plugin_help = invoke(binary, ["plugin", "--help"])
    validator = plugin_code == 0 and re.search(r"^\s+validate\s", plugin_help, re.M) is not None
    return report | {"native_eval_available": False, "native_plugin_validator": validator,
                     "exec_features": sorted(supported & EXEC_FEATURES),
                     "hard_spending_ceiling_verified": False,
                     "budget_semantics": "No supported hard spending cap or native eval command established by this adapter."}


def validate_plugin(root: Path, provider: str, output: str, *, consent: bool = False) -> dict:
    from .distribution import validate
    from .fs import confined
    # Verify the exact first-party canonical artifact before invoking native code.
    result = validate(root, output)
    if result["provider"] != provider:
        raise AgentBaseError("Plugin provider differs from the requested validator.")
    detected = inspect(provider, consent=consent, root=root)
    if not detected["native_plugin_validator"]:
        return result | {"native_validation": "unavailable", "provider_capabilities": detected}
    # The Codex adapter deliberately has no invented validator argument contract.
    if provider != "claude":
        return result | {"native_validation": "unsupported-command-contract", "provider_capabilities": detected}
    code, _ = invoke(executable(provider, root), ["plugin", "validate", str(confined(root, output))])
    return result | {"provider_validator_executed": True, "native_validation": "passed" if code == 0 else "failed",
                     "ok": code == 0, "provider_version": detected["version"], "runtime_verified": False}
