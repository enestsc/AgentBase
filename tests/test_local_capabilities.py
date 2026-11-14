import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from agentbase import local
from agentbase.config import DEFAULT, validate_config
from agentbase.fs import AgentBaseError


def responses():
    return [{"models": [{"name": "fixture:latest", "size": 1000}]},
            {"capabilities": ["completion"], "model_info": {"general.architecture": "fixture", "fixture.context_length": 8192}},
            {"models": []}]


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "note.txt").write_text("Engineering note", encoding="utf-8")
        self.config = deepcopy(DEFAULT)
        self.config["local_model"].update(enabled=True, model="fixture:latest")

    def test_old_configuration_receives_optional_limits(self):
        old = deepcopy(DEFAULT)
        old["local_model"] = {k: old["local_model"][k] for k in ("enabled", "endpoint", "model", "timeout_seconds", "max_input_chars")}
        validated = validate_config(old)
        self.assertEqual(validated["local_model"]["context_tokens"], 4096)
        self.assertNotIn("context_tokens", old["local_model"])

    def test_discovery_requires_consent_and_does_not_infer_or_download(self):
        with patch("agentbase.local.api", return_value=responses()[0]) as api:
            with self.assertRaisesRegex(AgentBaseError, "consent"):
                local.discover(self.config, consent=False)
            api.assert_not_called()
            result = local.discover(self.config, consent=True)
        self.assertFalse(result["inference"])
        self.assertFalse(result["downloads"])
        self.assertEqual(api.call_args.args[1], "tags")

    def test_installed_model_capacity_and_memory_preflight(self):
        with patch("agentbase.local.api", side_effect=responses()):
            result = local.preflight(self.config, consent=True)
        self.assertEqual(result["context_capacity"], 8192)
        self.assertIn("no OS memory cap", result["memory_note"])
        for values in ([{"models": []}],
                       [{"models": [{"name": "fixture:latest", "size": 10**12}]}],
                       [responses()[0], {"capabilities": ["embedding"], "model_info": {}}],
                       [responses()[0], responses()[1] | {"remote_host": "remote"}],
                       [responses()[0], {"capabilities": ["completion"], "model_info": {}}],
                       responses()[:2] + [{"models": [{"name": "other", "size": 99_000_000_000}]}]):
            with self.subTest(values=values), patch("agentbase.local.api", side_effect=values), self.assertRaises(AgentBaseError):
                local.preflight(self.config, consent=True)

    def test_request_sets_structured_context_generation_and_unload_limits(self):
        _, payload = local.prepare_request(self.root, self.config, "summarize", "note.txt", consent=True)
        self.assertEqual(payload["options"], {"num_ctx": 4096, "num_predict": 512})
        self.assertEqual(payload["keep_alive"], 0)
        self.assertIsInstance(payload["format"], dict)

    def test_structured_validation_and_explicit_fallback(self):
        proposal = {"summary": "A note", "topics": ["docs"], "role": "documentation-engineer", "uncertainties": []}
        self.assertEqual(local.validate_proposal(proposal), proposal)
        for bad in (proposal | {"role": []}, proposal | {"execute": "script"}, proposal | {"summary": ""}, proposal | {"topics": [4]}):
            with self.assertRaises(AgentBaseError):
                local.validate_proposal(bad)
        with patch("agentbase.local.api", side_effect=AgentBaseError("unavailable")), patch("agentbase.local.request") as inference:
            result = local.assist(self.root, self.config, "summarize", "note.txt", consent=True, fallback=True)
        inference.assert_not_called()
        self.assertTrue(result["fallback"])
        self.assertEqual(result["files_changed"], [])
        self.assertIsNone(result["proposal"])
        self.assertNotIn("Engineering note", json.dumps(result))

    def test_invalid_limits_rejected(self):
        for key, value in (("context_tokens", 0), ("max_model_bytes", True), ("max_output_tokens", 99999), ("structured", "yes")):
            config = deepcopy(self.config)
            config["local_model"][key] = value
            with self.assertRaises(AgentBaseError):
                validate_config(config)


if __name__ == "__main__":
    unittest.main()
