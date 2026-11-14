import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agentbase import receipts, specs, tasks
from agentbase.cli import main
from agentbase.fs import AgentBaseError, digest, json_text
from agentbase.install import install


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        install(self.root, providers=["codex"])
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("VALUE = 1\n", encoding="utf-8")
        specs.initialize(self.root, "health", "Health", "Check health", ["Returns ok"], "backend-engineer", "src")
        specs.proposal(self.root, "health", import_tasks=True)
        tasks.sync(self.root)
        tasks.transition(self.root, "R1", "running")

    def run_check(self, code="print('private output')", **kwargs):
        return receipts.execute(self.root, "R1", [sys.executable, "-c", code], ["src"], consent=True, **kwargs)

    def change_task(self, **fields):
        plan = tasks.load_plan(self.root)
        plan["tasks"][0].update(fields)
        (self.root / tasks.PLAN).write_text(json_text(plan), encoding="utf-8")

    def test_real_success_binds_without_raw_output_or_argv_and_preserves_state(self):
        before = (self.root / tasks.PLAN).read_bytes()
        result = self.run_check()
        report = receipts.report(self.root, result["receipt_id"])
        self.assertTrue(result["ok"])
        self.assertTrue(report["fresh"])
        self.assertFalse(report["authenticated"])
        self.assertFalse(report["acceptance_verified"])
        self.assertEqual(report["receipt"]["result"]["exit_code"], 0)
        self.assertNotIn("private output", json_text(report))
        self.assertEqual((self.root / tasks.PLAN).read_bytes(), before)
        self.assertEqual(specs.definition(tasks.load_plan(self.root)["tasks"][0]), report["receipt"]["task_sha256"])

    def test_consent_and_running_writer_required_before_launch(self):
        with patch("agentbase.receipts.collect") as launch:
            with self.assertRaisesRegex(AgentBaseError, "consent"):
                receipts.execute(self.root, "R1", [sys.executable], ["src"])
            for task_id in ("missing", "R1"):
                if task_id == "R1":
                    self.change_task(status="ready")
                with self.assertRaisesRegex(AgentBaseError, "running writer"):
                    receipts.execute(self.root, task_id, [sys.executable], ["src"], consent=True)
            self.change_task(status="running", role="codebase-explorer", scope=[{"path": "src", "access": "read"}])
            with self.assertRaisesRegex(AgentBaseError, "running writer"):
                self.run_check()
            launch.assert_not_called()

    def test_argv_timeout_pythonpath_and_sources_fail_closed(self):
        with patch("agentbase.receipts.collect") as launch:
            for argv in ([], ["python"], [sys.executable, "bad\0arg"], [sys.executable, "a" * 32001]):
                with self.assertRaises(AgentBaseError):
                    receipts.execute(self.root, "R1", argv, ["src"], consent=True)
            for timeout in (0, 301, True):
                with self.assertRaises(AgentBaseError):
                    self.run_check(timeout=timeout)
            with self.assertRaises(AgentBaseError):
                self.run_check(pythonpath=["tests"])
            task = tasks.load_plan(self.root)["tasks"][0]
            for sources in ([], ["../else"], ["src", "src"], ["src", "src/app.py"], ["docs"], [".env"]):
                with self.assertRaises((AgentBaseError, OSError)):
                    receipts.source_snapshot(self.root, task, sources)
            launch.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows implicit batch launcher boundary")
    def test_windows_exe_alias_to_batch_is_refused_after_resolution(self):
        alias = self.root / "launcher.exe"
        original = Path.resolve
        for extension in (".cmd", ".bat"):
            target = self.root / ("launcher" + extension)
            def resolve(path, strict=False, *, target=target):
                return target if path == alias else original(path, strict=strict)
            with patch.object(Path, "resolve", resolve), patch("agentbase.receipts.collect") as launch:
                with self.assertRaisesRegex(AgentBaseError, "Resolved Windows"):
                    receipts.execute(self.root, "R1", [str(alias)], ["src"], consent=True)
                launch.assert_not_called()

    def test_selected_directory_content_addition_and_deletion_become_stale(self):
        result = self.run_check()
        source = self.root / "src/app.py"
        source.write_text("VALUE = 2\n", encoding="utf-8")
        self.assertFalse(receipts.report(self.root, result["receipt_id"])["fresh"])
        source.write_text("VALUE = 1\n", encoding="utf-8")
        self.assertTrue(receipts.report(self.root, result["receipt_id"])["fresh"])
        extra = self.root / "src/new.py"
        extra.write_text("new = True", encoding="utf-8")
        self.assertFalse(receipts.report(self.root, result["receipt_id"])["fresh"])
        extra.unlink()
        source.unlink()
        self.assertFalse(receipts.report(self.root, result["receipt_id"])["fresh"])

    def test_task_resource_and_executable_drift(self):
        result = self.run_check()
        self.change_task(resources=[{"name": "database", "access": "write"}])
        self.assertIn("task-definition-changed", receipts.report(self.root, result["receipt_id"])["stale"])
        original = receipts.file_hash
        with patch("agentbase.receipts.file_hash", side_effect=lambda p, limit=128000000:
                   "a" * 64 if p == Path(sys.executable).resolve() else original(p, limit)):
            self.assertIn("executable-changed", receipts.report(self.root, result["receipt_id"])["stale"])

    def test_definition_move_preserves_old_hash_and_excludes_runtime_state(self):
        task = tasks.load_plan(self.root)["tasks"][0]
        expected = digest(json_text({k: v for k, v in task.items() if k not in {"status", "verification", "blocking_reason", "handoff"}}))
        self.assertEqual(tasks.definition(task), expected)
        self.assertEqual(specs.definition(task | {"status": "review", "verification": ["observation"]}), expected)

    def test_source_change_or_loss_during_execution_never_passes(self):
        result = self.run_check("from pathlib import Path; Path('src/app.py').write_text('changed')")
        self.assertFalse(result["ok"])
        self.assertIn("sources-changed-during-run", result["stale"])
        result = self.run_check("from pathlib import Path; Path('src/app.py').unlink()")
        self.assertFalse(result["ok"])
        self.assertFalse(receipts.report(self.root, result["receipt_id"])["ok"])

    def test_real_nonzero_timeout_and_output_overflow(self):
        result = self.run_check("raise SystemExit(7)")
        self.assertFalse(result["ok"])
        self.assertEqual(result["result"]["exit_code"], 7)
        result = self.run_check("import time; time.sleep(10)", timeout=1)
        self.assertEqual(result["result"]["status"], "timeout")
        with patch("agentbase.receipts.OUTPUT_LIMIT", 1000):
            result = self.run_check("import sys; sys.stdout.write('x' * 10000)")
        self.assertEqual(result["result"]["status"], "output-limit")
        self.assertEqual(result["result"]["output"]["stdout"]["bytes_hashed"], 1000)

    def test_minimal_environment_and_explicit_pythonpath(self):
        with patch.dict(os.environ, {"AGENTBASE_RECEIPT_TEST_SECRET": "secret", "PYTHONPATH": "evil"}):
            result = self.run_check("import os,app; assert app.VALUE == 1; assert 'AGENTBASE_RECEIPT_TEST_SECRET' not in os.environ", pythonpath=["src"])
        self.assertTrue(result["ok"])

    def test_edited_or_missing_managed_artifacts_are_preserved_before_launch(self):
        result = self.run_check()
        path = self.root / result["receipt"]
        path.write_text("manual edit", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "edited/missing"):
            receipts.report(self.root, result["receipt_id"])
        with patch("agentbase.receipts.collect") as launch:
            with self.assertRaises(AgentBaseError):
                self.run_check()
            launch.assert_not_called()
        (self.root / receipts.MANIFEST).unlink()
        with self.assertRaisesRegex(AgentBaseError, "without a managed"):
            self.run_check()
        self.assertEqual(path.read_text(), "manual edit")

    def test_source_size_secret_and_link_refusals(self):
        task = tasks.load_plan(self.root)["tasks"][0]
        (self.root / "src/.env").write_text("secret", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "sensitive"):
            receipts.source_snapshot(self.root, task, ["src"])
        (self.root / "src/.env").unlink()
        (self.root / "src/large.py").write_bytes(b"x" * 1000001)
        with self.assertRaises(AgentBaseError):
            receipts.source_snapshot(self.root, task, ["src"])
        (self.root / "src/large.py").unlink()
        try:
            (self.root / "src/link.py").symlink_to(self.root / "src/app.py")
        except OSError:
            return  # Size/secret checks still executed on Windows without symlink privileges.
        with self.assertRaisesRegex(AgentBaseError, "linked"):
            receipts.source_snapshot(self.root, task, ["src"])

    def test_manifest_changes_during_check_are_preserved(self):
        self.run_check()
        code = "from pathlib import Path; Path('.agentbase/receipts/manifest.json').write_text('operator edit')"
        with self.assertRaises(AgentBaseError):
            self.run_check(code)
        self.assertEqual((self.root / receipts.MANIFEST).read_text(), "operator edit")

    def test_incomplete_pipe_collection_never_passes(self):
        class RetainedPipeThread:
            ident = 1

            def __init__(self, **kwargs):
                pass

            def start(self):
                pass

            def join(self, timeout):
                pass

        process = Mock(returncode=0, stdout=io.BytesIO(), stderr=io.BytesIO())
        process.poll.return_value = 0
        with patch("agentbase.receipts.threading.Thread", RetainedPipeThread), patch("agentbase.receipts.subprocess.Popen", return_value=process):
            result = self.run_check("pass")
        self.assertFalse(result["ok"])
        self.assertEqual(result["result"]["status"], "output-incomplete")

    def test_cli_literal_argv_and_failed_check_exit_status(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--project", str(self.root), "tasks", "test", "R1", "--source", "src", "--consent",
                         "--argv", sys.executable, "-c", "raise SystemExit(9)"])
        self.assertEqual(code, 1, err.getvalue())
        result = json.loads(out.getvalue())
        self.assertEqual(result["result"]["exit_code"], 9)
        with self.assertRaises(AgentBaseError):
            receipts.report(self.root, "../invalid")
