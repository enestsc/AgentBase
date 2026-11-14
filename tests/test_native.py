import json
import shutil
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentbase import native
from agentbase.fs import AgentBaseError
from agentbase.runner import docker_environment, remove_owned_container

IMAGE = "sha256:" + "a" * 64


def boundary():
    return {"HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True, "Privileged": False, "IpcMode": "private",
            "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"], "Memory": 1024 * 1024 * 1024,
            "MemorySwap": 1024 * 1024 * 1024, "PidsLimit": 64, "NanoCpus": 1_000_000_000, "PublishAllPorts": False,
            "LogConfig": {"Type": "local", "Config": {"max-size": "256k", "max-file": "1", "compress": "false"}}},
            "Config": {"User": "65534:65534", "Entrypoint": ["/usr/bin/env"]},
            "NetworkSettings": {"Networks": {"none": {}}}}


class NativeProbeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.gettempdir()) / "agentbase-native-unit-project"
        self.engine = MagicMock()
        self.engine.executable = str(Path(tempfile.gettempdir()) / "trusted-docker")

    def test_consent_invalid_image_and_provider_are_refused_before_execution(self):
        with patch("agentbase.native.DockerTaskRunner", side_effect=AssertionError("no execution")):
            with self.assertRaisesRegex(AgentBaseError, "consent"):
                native.inspect_image(self.root, "codex", IMAGE)
            with self.assertRaisesRegex(AgentBaseError, "Unsupported"):
                native.inspect_image(self.root, "unknown", IMAGE, consent=True)
            with self.assertRaisesRegex(AgentBaseError, "sha256"):
                native.inspect_image(self.root, "codex", "image:latest", consent=True)

    def test_boundary_rejects_host_network_mounts_and_missing_resource_caps(self):
        native.verify_probe_boundary(boundary())
        for key, value in (("NetworkMode", "bridge"), ("Mounts", [{"Source": "project"}]), ("Privileged", True),
                           ("Memory", 0), ("PidsLimit", 0), ("ReadonlyRootfs", False)):
            observed = deepcopy(boundary())
            observed["HostConfig"][key] = value
            with self.assertRaises(AgentBaseError):
                native.verify_probe_boundary(observed)

    def test_only_literal_version_help_commands_and_pinned_images_are_accepted(self):
        for provider, arguments, image in (("codex", ["exec", "paid prompt"], IMAGE),
                                           ("claude", ["--print", "paid prompt"], IMAGE),
                                           ("codex", ["--version"], "mutable:tag")):
            with self.assertRaises(AgentBaseError):
                native.probe_command(self.engine, image, provider, arguments)
        self.engine.command.assert_not_called()

    def test_failed_boundary_verification_cleans_before_native_start(self):
        with patch("agentbase.native.verify_probe_boundary", side_effect=AgentBaseError("fixture boundary failure")), patch("agentbase.native.remove_owned_container") as cleanup:
            self.engine.command.return_value = "{}"
            with self.assertRaisesRegex(AgentBaseError, "fixture boundary failure"):
                native.probe_command(self.engine, IMAGE, "codex", ["--version"])
        cleanup.assert_called_once()
        self.assertTrue(all(call.args[0][0] != "start" for call in self.engine.command.call_args_list))

    def test_codex_image_contract_does_not_invent_native_eval_or_validator(self):
        responses = [(0, "codex-cli 0.169.0"), (0, "Usage: codex exec [OPTIONS]\n--json --sandbox --ephemeral --ignore-user-config"),
                     (0, "Commands:\n  install Install plugin\n  list List plugins")]
        with patch("agentbase.native.DockerTaskRunner", return_value=self.engine), patch("agentbase.native.probe_command", side_effect=responses):
            result = native.inspect_image(self.root, "codex", IMAGE, consent=True)
        self.assertEqual(result["version"], "0.169.0")
        self.assertEqual(result["model_sessions"], 0)
        self.assertFalse(result["native_eval_available"])
        self.assertFalse(result["native_plugin_validator"])
        self.assertFalse(result["native_launch_enabled"])

    def test_claude_image_flags_and_missing_features_are_version_specific(self):
        responses = [(0, "2.1.310 (Claude Code)"), (0, "Usage: claude\n--print --tools --settings --max-budget-usd"),
                     (0, "Usage: claude plugin eval\n--no-publish --no-scaffold --mocks --concurrency --max-cost-usd"),
                     (0, "Usage: claude plugin validate [path]")]
        with patch("agentbase.native.DockerTaskRunner", return_value=self.engine), patch("agentbase.native.probe_command", side_effect=responses):
            result = native.inspect_image(self.root, "claude", IMAGE, consent=True)
        self.assertTrue(result["native_eval_available"])
        self.assertTrue(result["native_plugin_validator"])
        self.assertIn("--print", result["print_features"])
        self.assertFalse(result["hard_spending_ceiling_verified"])

    def test_missing_executable_never_advances_to_help_or_a_provider_session(self):
        with patch("agentbase.native.DockerTaskRunner", return_value=self.engine), patch("agentbase.native.probe_command", return_value=(127, "")) as probe:
            result = native.inspect_image(self.root, "claude", IMAGE, consent=True)
        self.assertFalse(result["available"])
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(result["model_sessions"], 0)

    def test_cleanup_cannot_target_arbitrary_containers(self):
        with self.assertRaisesRegex(AgentBaseError, "namespace"):
            remove_owned_container(self.engine, "unrelated-user-container")
        self.engine.command.assert_not_called()

    def test_synthetic_probe_rejects_eval_for_codex_without_running_commands(self):
        with patch("agentbase.native.inspect_image", side_effect=AssertionError("no probe")):
            with self.assertRaisesRegex(AgentBaseError, "requires Claude"):
                native.mock_smoke(self.root, "codex", IMAGE, mode="eval", consent=True)

    def test_explicit_program_mounts_are_readonly_and_no_other_paths_are_permitted(self):
        sources = {"/program/native-mock.cjs": "fixture-script"}
        observed = boundary()
        observed["HostConfig"]["Mounts"] = [{"Type": "bind", "Target": "/program/native-mock.cjs", "Source": "fixture-script", "ReadOnly": True}]
        native.verify_probe_boundary(observed, sources)
        for key, bad in (("ReadOnly", False), ("Target", "/host"), ("Source", "user-home"), ("Type", "volume")):
            altered = deepcopy(observed)
            altered["HostConfig"]["Mounts"][0][key] = bad
            with self.assertRaises(AgentBaseError):
                native.verify_probe_boundary(altered, sources)
        observed["NetworkSettings"]["Networks"]["bridge"] = {}
        with self.assertRaises(AgentBaseError):
            native.verify_probe_boundary(observed, sources)

    def test_mock_output_allowlist_discards_native_trace_and_requires_consistent_metrics(self):
        metrics = {"attempted_requests": 1, "successful_requests": 1, "rejected_requests": 0,
                   "upstream_failures": 0, "bytes_sent": 100, "bytes_received": 100}
        output = {"schema_version": 1, "provider": "claude", "mode": "print", "origin": "mock", "exit_code": 0,
                  "marker_verified": True, "fixture_requests": 1, "gateway_metrics": metrics, "output_overflow": False,
                  "provider_api_calls": 0, "actual_model_behavior_verified": False, "canonical_plugin_discovered": True,
                  "raw_trace": "must not survive", "eval_evidence": None}
        contract = {"available": True, "version": "fixture", "native_eval_available": True}
        with patch("agentbase.native.inspect_image", return_value=contract), patch("agentbase.native.DockerTaskRunner", return_value=self.engine):
            with patch("agentbase.native._container_command", return_value=(0, json.dumps(output))) as command:
                result = native.mock_smoke(self.root, "claude", IMAGE, consent=True)
            self.assertTrue(result["ok"])
            self.assertNotIn("must not survive", json.dumps(result))
            self.assertEqual(len(command.call_args.kwargs["sources"]), 4)
            self.assertFalse((self.root / ".agentbase").exists())
            for changed in (output | {"provider_api_calls": 1}, output | {"fixture_requests": 0},
                            output | {"gateway_metrics": metrics | {"raw-secret": 0}}, output | {"exit_code": True}):
                with patch("agentbase.native._container_command", return_value=(0, json.dumps(changed))):
                    with self.assertRaises(AgentBaseError):
                        native.mock_smoke(self.root, "claude", IMAGE, consent=True)
            with patch("agentbase.native._container_command", return_value=(0, json.dumps(output | {"mode": "eval"}))):
                self.assertFalse(native.mock_smoke(self.root, "claude", IMAGE, mode="eval", consent=True)["ok"])

    @unittest.skipUnless(shutil.which("node"), "Optional Node runtime unavailable")
    def test_synthetic_fixtures_have_no_provider_calls_or_arbitrary_commands(self):
        binary = Path(shutil.which("node")).resolve()
        root = Path(__file__).resolve().parents[1]
        if binary.is_relative_to(root):
            self.skipTest("Project-local Node is not a trusted test runtime")
        result = subprocess.run([str(binary), "--test", str(root / "tests/native_protocol.cjs")],
                                env=docker_environment(), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# pass 4", result.stdout)


if __name__ == "__main__":
    unittest.main()
