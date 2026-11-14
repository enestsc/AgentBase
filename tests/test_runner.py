import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentbase import runner
from agentbase.fs import AgentBaseError

IMAGE = "example/worker@sha256:" + "a" * 64
DOCKER = str(Path(tempfile.gettempdir()) / "agentbase-fixture-docker")
POLICY = {"schema_version": 1, "provider": "deterministic", "image": IMAGE, "entrypoint": "/usr/bin/worker",
          "arguments": [], "timeout_seconds": 2, "memory_mb": 128, "pids": 16}
TASK = {"id": "T1", "description": "Inspect source", "role": "backend-engineer", "dependencies": [],
        "inputs": ["source"], "outputs": ["proposal"], "scope": [{"path": "src", "access": "write"}], "resources": [],
        "acceptance": ["Check source"], "status": "running", "verification": [], "blocking_reason": ""}
HANDOFF = {"schema_version": 1, "task_id": "T1", "result": "Fixture check", "changed_files": [], "decisions": [],
           "tests": [{"command": "fixture", "status": "not-run", "outcome": "unit-test fixture"}], "failures": [], "risks": [], "artifacts": []}


def boundary(source):
    return {"HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False, "IpcMode": "private",
                           "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"], "Memory": 128 * 1024 * 1024,
                           "PidsLimit": 16, "NanoCpus": 1_000_000_000,
                           "Mounts": [{"Type": "bind", "Source": source, "Target": "/input/request.json", "ReadOnly": True}]},
            "Config": {"User": "65534:65534"}}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "src/a.py").write_text("print('safe')", encoding="utf-8")
        self.commands = []

    def engine(self, *, malformed=False, timeout=False):
        def command(args, seconds=10):
            self.commands.append(args)
            if args[0] == "context":
                return "unix:///var/run/docker.sock"
            if args[0] == "version":
                return "linux"
            if args[0] == "create":
                self.name = args[args.index("--name") + 1]
                self.removed = False
                mount = args[args.index("--mount") + 1]
                self.source = mount.split("source=", 1)[1].split(",target=", 1)[0]
                return "fixture"
            if args[0] == "inspect":
                return json.dumps(boundary(self.source))
            if args[0] == "wait":
                if timeout:
                    raise AgentBaseError("timed out")
                return "0"
            if args[0] == "logs":
                return "invalid" if malformed else json.dumps({"handoff": HANDOFF, "files": {}})
            if args[0] == "container":
                return "" if self.removed else self.name
            if args[0] == "rm":
                self.removed = True
            return ""
        return command

    def run_worker(self, **options):
        with patch("agentbase.runner.shutil.which", return_value=DOCKER), patch.object(runner.DockerTaskRunner, "command", side_effect=self.engine(**options)):
            return runner.DockerTaskRunner().run(self.root, TASK, ["src/a.py"], POLICY, consent=True)

    def test_default_refusals_and_no_provider_fallback(self):
        self.assertEqual(runner.policy(POLICY | {"image": "sha256:" + "a" * 64})["image"], "sha256:" + "a" * 64)
        for bad in (POLICY | {"provider": "codex"}, POLICY | {"image": "example:latest"}, POLICY | {"pids": True}):
            with self.assertRaises(AgentBaseError):
                runner.policy(bad)
        with patch("agentbase.runner.shutil.which", return_value=None):
            with self.assertRaisesRegex(AgentBaseError, "active host"):
                runner.DockerTaskRunner()
        with patch("agentbase.runner.shutil.which", return_value=DOCKER):
            worker = runner.DockerTaskRunner()
            with self.assertRaisesRegex(AgentBaseError, "consent"):
                worker.run(self.root, TASK, [], POLICY)
            with self.assertRaisesRegex(AgentBaseError, "Claim/start"):
                worker.run(self.root, TASK | {"status": "pending"}, [], POLICY, consent=True)

    def test_real_boundary_flags_and_structured_proposal(self):
        result = self.run_worker()
        create = next(c for c in self.commands if c[0] == "create")
        for flag in ("--network=none", "--read-only", "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pull=never"):
            self.assertIn(flag, create)
        self.assertIn("-i", create)  # env -i: image/host environment is not inherited by worker
        self.assertEqual(result["host_files_changed"], [])
        self.assertFalse(result["trusted"])
        self.assertEqual(result["handoff"], HANDOFF)
        self.assertTrue(any(c[:2] == ["rm", "--force"] for c in self.commands))

    def test_invalid_output_and_timeout_cleanup_the_entire_container(self):
        for options in ({"malformed": True}, {"timeout": True}):
            self.commands = []
            with self.assertRaises(AgentBaseError):
                self.run_worker(**options)
            self.assertTrue(any(c[:2] == ["rm", "--force"] for c in self.commands))
        self.assertEqual((self.root / "src/a.py").read_text(), "print('safe')")

    def test_remote_context_and_non_linux_daemon_fail_closed(self):
        for replies in (["ssh://host"], ["unix:///var/run/docker.sock", "windows"]):
            with patch("agentbase.runner.shutil.which", return_value=DOCKER), patch.object(runner.DockerTaskRunner, "command", side_effect=replies):
                with self.assertRaises(AgentBaseError):
                    runner.DockerTaskRunner().connect()

    def test_daemon_must_confirm_boundary_before_worker_start(self):
        value = boundary("fixture")
        runner.verify_boundary(value, "fixture", POLICY)
        for key, bad in (("NetworkMode", "host"), ("Privileged", True), ("ReadonlyRootfs", False), ("Memory", 0), ("PidsLimit", 0)):
            observed = boundary("fixture")
            observed["HostConfig"][key] = bad
            with self.assertRaisesRegex(AgentBaseError, "worker not started"):
                runner.verify_boundary(observed, "fixture", POLICY)

    def test_context_and_proposed_files_must_obey_scope(self):
        (self.root / "outside.txt").write_text("private", encoding="utf-8")
        for path in ("outside.txt", "../escape", "src/.env"):
            with self.assertRaises(AgentBaseError):
                runner.snapshot(self.root, TASK, [path])
        request = runner.snapshot(self.root, TASK, ["src/a.py"])
        with self.assertRaisesRegex(AgentBaseError, "outside"):
            runner.validate_result({"handoff": HANDOFF | {"changed_files": ["outside.txt"]}, "files": {"outside.txt": "bad"}}, TASK, request)
        with self.assertRaisesRegex(AgentBaseError, "match"):
            runner.validate_result({"handoff": HANDOFF, "files": {"src/a.py": "bad"}}, TASK, request)


if __name__ == "__main__":
    unittest.main()
