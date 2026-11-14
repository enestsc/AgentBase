"""Install our locally built wheel in a temporary venv and exercise offline CLI flows."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True, help="Trusted, locally built AgentBase wheel")
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="agentbase-package-smoke-") as temporary:
        base = Path(temporary)
        environment = base / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        binaries = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        executable = binaries / ("agentbase.exe" if os.name == "nt" else "agentbase")
        env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
        subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
                       check=True, capture_output=True, text=True, env=env)
        root = base / "project"
        root.mkdir()
        (root / "app.py").write_text("def health():\n    return {'status': 'ok'}\n", encoding="utf-8")
        observations = []

        def call(*command, stdin=None, expected=0):
            result = subprocess.run([str(executable), "--project", str(root), *command], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=30, input=stdin)
            if result.returncode != expected:
                raise RuntimeError(f"CLI failed (exit {result.returncode}): {command!r}\n{result.stdout}\n{result.stderr}")
            observations.append({"command": list(command), "status": "passed"})
            return json.loads(result.stdout if result.stdout.strip() else result.stderr)

        call("init", "--provider", "both", "--pack", "python", "--pack", "security")
        if not call("doctor")["ok"]:
            raise RuntimeError("Installed-package doctor failed")
        call("packs", "add", "documentation")
        call("packs", "remove", "documentation")
        call("update", "--discovery", "plugin")
        call("doctor")
        call("update", "--discovery", "native")
        call("skills", "audit")
        policy_file = root / "gateway-policy.json"
        policy_file.write_text(json.dumps({"schema_version": 1, "provider": "codex", "model": "fixture-model",
            "max_requests": 1, "max_output_tokens": 128, "max_request_bytes": 2048, "max_response_bytes": 2048,
            "timeout_seconds": 1, "lifetime_seconds": 10}), encoding="utf-8")
        call("gateway", "validate", "--file", str(policy_file))
        for provider in ("codex", "claude"):
            error = call("eval", "native-smoke", "--provider", provider, "--image", "sha256:" + "a" * 64, expected=2)
            if "consent" not in error.get("error", ""):
                raise RuntimeError("Installed native probe must fail before Docker without consent")
        if not call("skills", "search", "superpowers")["sources"]:
            raise RuntimeError("Packaged curated sources missing")
        call("usage", "configure", "--source", "codex-exec-v1", "--source", "claude-statusline-v1")
        event = json.dumps({"session_id": "smoke", "context_window": {"total_input_tokens": 12, "total_output_tokens": 1}})
        call("usage", "capture", "--source", "claude-statusline-v1", "--provider-version", "package-smoke-fixture", "--project-id", "smoke", stdin=event)
        duplicate = call("usage", "capture", "--source", "claude-statusline-v1", "--provider-version", "package-smoke-fixture", "--project-id", "smoke", stdin=event)
        if duplicate["duplicates"] != 1:
            raise RuntimeError("Snapshot deduplication failed")
        call("usage", "--json", "--timezone", "UTC")
        call("spec", "init", "health", "--title", "Health", "--request", "Verify health response",
             "--criterion", "Health returns ok", "--scope", "app.py")
        call("spec", "validate", "health")
        call("spec", "tasks", "health", "--import")
        plan = call("spec", "reconcile", "health")
        call("spec", "reconcile", "health", "--apply", "--plan-id", plan["plan_id"])
        call("spec", "evidence", "health")
        call("tasks", "validate")
        call("tasks", "sync")
        call("tasks", "transition", "R1", "running")
        refused = call("tasks", "test", "R1", "--source", "app.py", "--argv", sys.executable,
                       "-c", "raise SystemExit(0)", expected=2)
        if "consent" not in refused.get("error", ""):
            raise RuntimeError("Host receipt execution must require explicit consent")
        receipt = call("tasks", "test", "R1", "--source", "app.py", "--consent", "--argv", sys.executable,
                       "-c", "raise SystemExit(0)")
        fresh = call("tasks", "receipt", receipt["receipt_id"])
        if not fresh["fresh"] or fresh["authenticated"] or fresh["acceptance_verified"]:
            raise RuntimeError("Installed receipt provenance/freshness failed")
        (root / "app.py").write_text("def health():\n    return {'status': 'changed'}\n", encoding="utf-8")
        stale = call("tasks", "receipt", receipt["receipt_id"], expected=1)
        if stale["fresh"]:
            raise RuntimeError("Installed receipt must become stale after source change")
        call("explain", "--write")
        call("explain", "--write", "--feature", "health")
        call("eval", "run")
        for provider in ("codex", "claude"):
            call("plugins", "build", "--provider", provider, "--output", "packages/" + provider)
            call("plugins", "validate", "--output", "packages/" + provider)
        call("memory", "note", "decision", "--text", "Smoke project health response is static", "--evidence", "app.py:1")
        call("memory", "sync")
        call("uninstall", "--dry-run")
        print(json.dumps({"ok": True, "wheel": wheel.name, "checks": observations,
                          "network": False, "model_sessions": 0}, indent=2))


if __name__ == "__main__":
    main()
