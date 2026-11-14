import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentbase.cli import main


class FoundationCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def call(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--project", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_packs_full_cli_lifecycle(self):
        code, out, _ = self.call("packs", "list")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["packs"]), 7)
        self.assertEqual(self.call("init", "--pack", "core", "--provider", "both")[0], 0)
        self.assertEqual(self.call("packs", "add", "web", "--dry-run")[0], 0)
        self.assertFalse((self.root / ".claude/agents/agentbase-frontend-engineer.md").exists())
        self.assertEqual(self.call("packs", "add", "web")[0], 0)
        self.assertTrue((self.root / ".claude/agents/agentbase-frontend-engineer.md").exists())
        self.assertEqual(self.call("packs", "remove", "web")[0], 0)
        self.assertEqual(self.call("doctor")[0], 0)

    def test_usage_opt_in_import_reports_and_export(self):
        self.assertEqual(self.call("usage")[0], 2)
        self.assertEqual(self.call("usage", "configure", "--source", "codex-exec-v1")[0], 0)
        capture = {"schema_version": 1, "source": "codex-exec-v1", "timestamp": "2026-11-10T12:00:00Z",
                   "provider_version": "fixture", "project_id": "project", "session_id": "session", "event_id": "turn",
                   "event": {"type": "turn.completed", "usage": {"input_tokens": 25, "output_tokens": 3}}}
        path = self.root / "captures.json"
        path.write_text(json.dumps({"captures": [capture]}), encoding="utf-8")
        self.assertEqual(self.call("usage", "import", "--file", str(path))[0], 0)
        self.assertEqual(self.call("usage", "--json", "--today", "--timezone", "UTC")[0], 0)
        self.assertIn("Subscription quota: not available", self.call("usage")[1])
        self.assertEqual(self.call("usage", "export", "--format", "csv")[0], 0)
        self.assertEqual(self.call("usage", "delete", "--all")[0], 0)

    def test_skills_preserve_old_interface_and_review_options(self):
        self.assertTrue(json.loads(self.call("skills")[1])["skills"])
        self.assertEqual(self.call("skills", "search", "verify")[0], 0)
        self.assertEqual(self.call("skills", "audit")[0], 0)
        self.assertEqual(self.call("skills", "info", "missing")[0], 2)
        with patch("agentbase.registry.add", return_value={"dry_run": True}) as add:
            self.assertEqual(self.call("skills", "add", "https://github.com/e/r", "--path", "sample")[0], 0)
            self.assertTrue(add.call_args.kwargs["dry_run"])
            self.assertIsNone(add.call_args.kwargs["expected_plan"])

    def test_capture_stdin_and_native_probe_consent(self):
        self.call("usage", "configure", "--source", "claude-statusline-v1")
        event = json.dumps({"session_id": "fixture-session", "context_window": {"total_input_tokens": 12, "total_output_tokens": 3}})
        with patch("sys.stdin", io.StringIO(event)):
            code, out, _ = self.call("usage", "capture", "--source", "claude-statusline-v1", "--provider-version", "fixture", "--project-id", "fixture")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["imported"], 1)
        with patch("sys.stdin", io.StringIO("not json")):
            self.assertEqual(self.call("usage", "capture", "--source", "claude-statusline-v1", "--provider-version", "fixture", "--project-id", "fixture")[0], 2)
        self.assertEqual(self.call("eval", "capabilities", "--provider", "codex")[0], 2)

    def test_native_smoke_routes_modes_and_propagates_failure_without_launch_on_missing_consent(self):
        image = "sha256:" + "a" * 64
        self.assertEqual(self.call("eval", "native-smoke", "--provider", "codex", "--image", image)[0], 2)
        with patch("agentbase.native.mock_smoke", return_value={"ok": False, "origin": "mock", "provider_api_calls": 0}) as smoke:
            code, output, _ = self.call("eval", "native-smoke", "--provider", "claude", "--image", image, "--mode", "eval", "--consent")
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output)["origin"], "mock")
            self.assertEqual(smoke.call_args.kwargs, {"mode": "eval", "consent": True})

    def test_reconcile_cli_and_sandbox_default_refusal(self):
        self.call("init", "--provider", "codex")
        self.call("spec", "init", "health", "--title", "Health", "--request", "Add health", "--criterion", "Returns 200", "--scope", "src")
        self.assertEqual(self.call("spec", "tasks", "health", "--import")[0], 0)
        code, out, _ = self.call("spec", "reconcile", "health")
        self.assertEqual(code, 0)
        self.assertEqual(self.call("spec", "reconcile", "health", "--apply", "--plan-id", json.loads(out)["plan_id"])[0], 0)
        self.assertEqual(json.loads(self.call("spec", "evidence", "health")[1])["criteria"][0]["status"], "unverified")
        self.assertEqual(self.call("tasks", "sandbox", "R1", "--worker", "absent.json")[0], 2)

    def test_gateway_cli_validates_policy_and_requires_consent_for_real_docker(self):
        policy = {"schema_version": 1, "provider": "codex", "model": "fixture-model", "max_requests": 1,
                  "max_output_tokens": 16, "max_request_bytes": 2048, "max_response_bytes": 2048,
                  "timeout_seconds": 1, "lifetime_seconds": 10}
        path = self.root / "gateway.json"
        path.write_text(json.dumps(policy), encoding="utf-8")
        code, out, _ = self.call("gateway", "validate", "--file", str(path))
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["valid"])
        self.assertFalse(json.loads(out)["billing_cap_verified"])
        self.assertEqual(self.call("gateway", "self-test", "--image", "node@sha256:" + "a" * 64)[0], 2)


if __name__ == "__main__":
    unittest.main()
