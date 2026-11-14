import io
import json
import shutil
import subprocess
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from agentbase import gateway
from agentbase.fs import AgentBaseError
from agentbase.runner import docker_environment

POLICY = {"schema_version": 1, "provider": "codex", "model": "fixture-model", "max_requests": 2,
          "max_output_tokens": 128, "max_request_bytes": 2048, "max_response_bytes": 2048,
          "timeout_seconds": 1, "lifetime_seconds": 10}
IMAGE = "node@sha256:" + "a" * 64


class GatewayTests(unittest.TestCase):
    def test_policy_is_bounded_and_rejects_arbitrary_upstreams_or_credentials(self):
        self.assertEqual(gateway.policy(POLICY), POLICY)
        for bad in (POLICY | {"credential": "not-allowed"}, POLICY | {"upstream": "http://evil"},
                    POLICY | {"max_requests": True}, POLICY | {"provider": []}, POLICY | {"timeout_seconds": 20}):
            with self.assertRaises(AgentBaseError):
                gateway.policy(bad)

    def test_session_requires_consent_and_never_discovers_credentials(self):
        session = gateway.GatewaySession(IMAGE)
        with patch("agentbase.gateway.DockerTaskRunner", side_effect=AssertionError("must not invoke Docker")):
            with self.assertRaisesRegex(AgentBaseError, "consent"):
                session.start(POLICY, "synthetic-credential-only")
            with self.assertRaisesRegex(AgentBaseError, "credential is invalid"):
                session.start(POLICY, "short", consent=True)
        self.assertNotIn("credential", vars(session))
        self.assertGreaterEqual(len(session.capability), 32)

    def test_network_must_be_local_and_internal(self):
        valid = {"Internal": True, "Driver": "bridge", "Scope": "local", "Ingress": False}
        gateway.verify_network(valid)
        for key, value in (("Internal", False), ("Driver", "overlay"), ("Scope", "swarm")):
            with self.assertRaises(AgentBaseError):
                gateway.verify_network(valid | {key: value})

    def test_failed_start_cleans_container_network_and_never_puts_key_in_arguments(self):
        session = gateway.GatewaySession(IMAGE)
        calls = []
        existing = {"container": False, "network": False}

        class Engine:
            def connect(self):
                pass

            def command(self, args, timeout=10):
                calls.append(args)
                if args[:2] == ["network", "create"]:
                    existing["network"] = True
                elif args[:2] == ["network", "inspect"]:
                    return json.dumps({"Internal": True, "Driver": "bridge", "Scope": "local", "Ingress": False})
                elif args[0] == "create":
                    existing["container"] = True
                elif args[:2] == ["network", "connect"]:
                    raise AgentBaseError("fixture connect failure")
                elif args[:2] == ["container", "ls"]:
                    return session.name if existing["container"] else ""
                elif args[0] == "rm":
                    existing["container"] = False
                elif args[:2] == ["network", "ls"]:
                    return session.network if existing["network"] else ""
                elif args[:2] == ["network", "rm"]:
                    existing["network"] = False
                return ""

        credential = "synthetic-provider-secret-not-a-real-key"
        with patch("agentbase.gateway.DockerTaskRunner", return_value=Engine()), patch("agentbase.gateway.subprocess.Popen") as process:
            with self.assertRaisesRegex(AgentBaseError, "fixture connect failure"):
                session.start(POLICY, credential, consent=True)
        process.assert_not_called()
        self.assertEqual(existing, {"container": False, "network": False})
        self.assertNotIn(credential, json.dumps(calls))
        self.assertFalse(Path(session.temporary.name).exists())

    def test_bootstrap_uses_stdin_not_environment_files_or_command_line(self):
        session = gateway.GatewaySession(IMAGE)
        calls, sources = [], {}
        existing = {"container": False, "network": False}

        class Engine:
            executable, endpoint = "trusted-docker", "unix:///fixture"

            def connect(self):
                pass

            def command(self, args, timeout=10):
                calls.append(args)
                if args[:2] == ["network", "create"]:
                    existing["network"] = True
                elif args[:2] == ["network", "inspect"]:
                    return json.dumps({"Internal": True, "Driver": "bridge", "Scope": "local", "Ingress": False})
                elif args[0] == "create":
                    existing["container"] = True
                    for i, arg in enumerate(args):
                        if arg == "--mount":
                            item = dict(p.split("=", 1) for p in args[i + 1].split(",") if "=" in p)
                            sources[item["target"]] = item["source"]
                elif args[0] == "inspect":
                    return json.dumps({"HostConfig": {"NetworkMode": "bridge", "ReadonlyRootfs": True, "Privileged": False,
                        "IpcMode": "private", "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
                        "Memory": 128 * 1024 * 1024, "MemorySwap": 128 * 1024 * 1024, "PidsLimit": 32,
                        "NanoCpus": 500_000_000, "PublishAllPorts": False, "LogConfig": {"Type": "none"},
                        "Mounts": [{"Type": "bind", "ReadOnly": True, "Target": target, "Source": source} for target, source in sources.items()]},
                        "Config": {"User": "65534:65534", "Entrypoint": ["/usr/bin/env"]},
                        "NetworkSettings": {"Networks": {"bridge": {}, session.network: {}}}})
                elif args[:2] == ["container", "ls"]:
                    return session.name if existing["container"] else ""
                elif args[0] == "rm":
                    existing["container"] = False
                elif args[:2] == ["network", "ls"]:
                    return session.network if existing["network"] else ""
                elif args[:2] == ["network", "rm"]:
                    existing["network"] = False
                return ""

        class Process:
            stdin = io.BytesIO()
            stdout = io.BytesIO(b'{"ready":true}\n')
            stderr = io.BytesIO()

            def wait(self, timeout):
                return 0

        credential = "synthetic-provider-secret-not-a-real-key"
        with patch("agentbase.gateway.DockerTaskRunner", return_value=Engine()), patch("agentbase.gateway.subprocess.Popen", return_value=Process()) as process:
            try:
                result = session.start(POLICY, credential, consent=True)
                bootstrap = json.loads(session.process.stdin.getvalue())
                self.assertEqual(bootstrap["credential"], credential)
                self.assertEqual(bootstrap["capability"], session.capability)
                self.assertNotIn(credential, json.dumps(result))
                self.assertNotIn(credential, json.dumps(process.call_args.args))
                self.assertNotIn(credential, json.dumps(process.call_args.kwargs))
                self.assertNotIn(credential, json.dumps(calls))
                for source in sources.values():
                    self.assertNotIn(credential, Path(source).read_text(encoding="utf-8"))
            finally:
                session.stop()
        self.assertEqual(existing, {"container": False, "network": False})

    def test_container_needs_private_network_mounts_nonroot_and_no_logs_ports(self):
        sources = {"/program/gateway.cjs": "fixture-script", "/program/gateway-policy.json": "fixture-policy"}
        value = {"HostConfig": {"NetworkMode": "bridge", "ReadonlyRootfs": True, "Privileged": False, "IpcMode": "private",
            "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"], "Memory": 128 * 1024 * 1024,
            "MemorySwap": 128 * 1024 * 1024, "PidsLimit": 32, "NanoCpus": 500_000_000,
            "PortBindings": {}, "PublishAllPorts": False, "LogConfig": {"Type": "none"},
            "Mounts": [{"Type": "bind", "Source": source, "Target": target, "ReadOnly": True} for target, source in sources.items()]},
            "Config": {"User": "65534:65534", "Entrypoint": ["/usr/bin/env"]},
            "NetworkSettings": {"Networks": {"bridge": {}, "private-fixture": {}}}}
        gateway.verify_container(value, "private-fixture", sources)
        for key, bad in (("ReadonlyRootfs", False), ("PortBindings", {"8787/tcp": [{}]}), ("Privileged", True),
                         ("Memory", 0), ("LogConfig", {"Type": "json-file"})):
            observed = deepcopy(value)
            observed["HostConfig"][key] = bad
            with self.assertRaises(AgentBaseError):
                gateway.verify_container(observed, "private-fixture", sources)

    @unittest.skipUnless(shutil.which("node"), "Optional Node runtime unavailable; Docker gateway stays optional")
    def test_gateway_protocol_with_synthetic_credentials_and_no_provider(self):
        binary = Path(shutil.which("node")).resolve()
        root = Path(__file__).resolve().parents[1]
        if binary.is_relative_to(root):
            self.skipTest("Project-local Node executable is not a trusted test runtime")
        result = subprocess.run([str(binary), "--test", str(root / "tests/gateway_protocol.cjs")],
                                env=docker_environment(), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# pass 20", result.stdout)
        self.assertEqual(json.loads(json.dumps(POLICY)), POLICY)


if __name__ == "__main__":
    unittest.main()
