import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agentbase.cli import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, *argv):
        # Gerçek stdout/stderr'e sızmasın diye yakalanır; çıkış kodu ve çıktılar döner.
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--project", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def run_json(self, *argv):
        code, out, err = self.run_cli(*argv)
        return code, json.loads(out), err

    def test_init_dry_run_writes_nothing(self):
        code, data, _ = self.run_json("init", "--dry-run")
        self.assertEqual(code, 0)
        self.assertTrue(data["dry_run"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_project_does_not_create_directories(self):
        path = self.root / "missing"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--project", str(path), "usage", "configure", "--source", "codex-exec-v1"])
        self.assertEqual(code, 2)
        self.assertFalse(path.exists())

    def test_init_then_doctor_is_ok(self):
        code, data, _ = self.run_json("init")
        self.assertEqual(code, 0)
        self.assertTrue(data["changes"])
        self.assertTrue((self.root / "AGENTS.md").exists())
        code, report, _ = self.run_json("doctor")
        self.assertEqual(code, 0)
        self.assertIs(report["ok"], True)
        self.assertEqual(report["issues"], [])

    def test_roles_and_skills_listings(self):
        code, data, _ = self.run_json("roles")
        self.assertEqual(code, 0)
        self.assertTrue(data["roles"])
        role_id = data["roles"][0]["id"]
        # --role çıktısı JSON değil, insan okuyabilir rol istemidir (düz metin).
        code, text, _ = self.run_cli("roles", "--role", role_id)
        self.assertEqual(code, 0)
        self.assertIn(data["roles"][0]["title"], text)
        code, data, _ = self.run_json("skills")
        self.assertEqual(code, 0)
        self.assertTrue(data["skills"])

    def test_configure_safe_parallel_persists(self):
        self.run_cli("init")
        code, config, _ = self.run_json("configure", "--mode", "safe-parallel", "--max-concurrency", "2")
        self.assertEqual(code, 0)
        self.assertEqual(config["execution"], {"mode": "safe-parallel", "max_concurrency": 2})
        saved = json.loads((self.root / ".agentbase/config.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["execution"]["mode"], "safe-parallel")

    def test_configure_invalid_combination_exits_2_and_keeps_config(self):
        self.run_cli("init")
        path = self.root / ".agentbase/config.json"
        before = path.read_bytes()
        # sequential + eşzamanlılık 3 geçersiz: doğrulama diske yazmadan önce reddetmeli.
        code, out, err = self.run_cli("configure", "--max-concurrency", "3")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("error", json.loads(err))
        self.assertEqual(before, path.read_bytes())

    def test_update_on_uninitialized_project_exits_2_with_json_error(self):
        code, out, err = self.run_cli("update")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(json.loads(err)["error"])

    def test_project_commands_require_init_without_creating_state(self):
        for argv in (("explain",), ("explain", "--write"), ("context", "README.md"),
                     ("memory", "handoff"), ("memory", "sync"),
                     ("memory", "list"), ("memory", "prune", "--id", "x", "--reason", "x", "--dry-run"),
                     ("memory", "supersede", "--id", "x", "--reason", "x", "--text", "x", "--evidence", "x:1"),
                     ("memory", "note", "issue", "--text", "x", "--evidence", "x:1"),
                     ("tasks", "show"), ("tasks", "ready"), ("tasks", "sync"),
                     ("tasks", "validate"), ("tasks", "import", "--file", "missing.json"),
                     ("tasks", "transition", "x", "ready"), ("tasks", "validate-handoff", "--file", "missing.json")):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("first run `agentbase init`", json.loads(err)["error"])
                self.assertEqual(list(self.root.iterdir()), [])

    def test_external_plan_validation_needs_no_init(self):
        plan = self.root / "plan.json"
        plan.write_text('{"schema_version": 1, "tasks": []}', encoding="utf-8")
        code, result, _ = self.run_json("tasks", "validate", "--file", str(plan))
        self.assertEqual(code, 0)
        self.assertTrue(result["valid"])
        self.assertFalse((self.root / ".agentbase").exists())

    def test_memory_maintenance_cli(self):
        self.run_cli("init")
        (self.root / "app.py").write_text("value = 1\n", encoding="utf-8")
        code, record, _ = self.run_json("memory", "note", "issue", "--text", "Old", "--evidence", "app.py:1")
        self.assertEqual(code, 0)
        code, listing, _ = self.run_json("memory", "list")
        self.assertEqual(listing["notes"][0]["id"], record["id"])
        code, preview, _ = self.run_json("memory", "prune", "--id", record["id"], "--reason", "resolved", "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / preview["archive"]).exists())
        code, result, _ = self.run_json("memory", "supersede", "--id", record["id"], "--reason", "changed",
                                        "--text", "New", "--evidence", "app.py:1")
        self.assertEqual(code, 0)
        code, result, _ = self.run_json("memory", "prune", "--id", result["replacement"]["id"], "--reason", "resolved")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / result["archive"]).exists())

    def test_task_handoff_validation_and_completion_cli(self):
        self.run_cli("init")
        examples = Path(__file__).resolve().parents[1] / "examples"
        code, _, _ = self.run_json("tasks", "import", "--file", str(examples / "tasks.example.json"))
        self.assertEqual(code, 0)
        self.run_cli("tasks", "sync")
        self.run_cli("tasks", "transition", "api-design", "running")
        code, _, err = self.run_cli("tasks", "transition", "api-design", "review")
        self.assertEqual(code, 2)
        self.assertIn("--handoff-file", json.loads(err)["error"])
        value = json.loads((examples / "handoff.example.json").read_text(encoding="utf-8"))
        path = self.root / "handoff.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        code, data, _ = self.run_json("tasks", "validate-handoff", "--file", str(path))
        self.assertEqual(code, 0)
        self.assertFalse(data["checks_executed"])
        code, _, _ = self.run_cli("tasks", "transition", "api-design", "review", "--handoff-file", str(path))
        self.assertEqual(code, 0)
        code, _, _ = self.run_cli("tasks", "transition", "api-design", "completed", "--evidence", "claim")
        self.assertEqual(code, 2)
        value["tests"][0].update(status="passed", outcome="Fixture: acceptance compared against proposal")
        path.write_text(json.dumps(value), encoding="utf-8")
        code, data, _ = self.run_json("tasks", "transition", "api-design", "completed", "--evidence", "Fixture observation",
                                     "--handoff-file", str(path))
        self.assertEqual(code, 0)
        self.assertEqual(data["handoff"]["task_id"], "api-design")
        value["task_id"] = "unknown"
        path.write_text(json.dumps(value), encoding="utf-8")
        code, _, err = self.run_cli("tasks", "validate-handoff", "--file", str(path))
        self.assertEqual(code, 2)
        self.assertIn("Unknown handoff task_id", json.loads(err)["error"])

    def test_legacy_completion_is_reported_without_fabricating_handoff(self):
        self.run_cli("init")
        examples = Path(__file__).resolve().parents[1] / "examples"
        value = json.loads((examples / "tasks.example.json").read_text(encoding="utf-8"))
        value["tasks"][0].update(status="completed", verification=["Legacy observation"])
        path = self.root / ".agentbase/tasks.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        before = path.read_bytes()
        code, data, _ = self.run_json("tasks", "validate")
        self.assertEqual(code, 0)
        self.assertEqual(data["legacy_completed_without_handoff"], ["api-design"])
        code, data, _ = self.run_json("doctor")
        self.assertEqual(code, 0)
        self.assertTrue(any("Legacy completed tasks" in warning for warning in data["warnings"]))
        self.assertEqual(path.read_bytes(), before)

    def test_doctor_reports_issue_with_exit_1_when_managed_file_is_corrupted(self):
        self.run_cli("init")
        # Yönetilen tam dosya elle bozulunca doctor bunu sorun sayıp 1 ile çıkmalı.
        (self.root / ".agentbase/policy.md").write_text("local edit", encoding="utf-8")
        code, report, _ = self.run_json("doctor")
        self.assertEqual(code, 1)
        self.assertIs(report["ok"], False)
        self.assertTrue(report["issues"])


if __name__ == "__main__":
    unittest.main()
