import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentbase import distribution, providers
from agentbase.fs import AgentBaseError

CLAUDE_HELP = "Usage: claude plugin eval [options]\n --max-cost-usd <usd>\n --concurrency <n>\n --no-publish\n --no-scaffold\n --mocks <mode>"


class ProviderTests(unittest.TestCase):
    def test_consent_unavailable_and_version_drift(self):
        with self.assertRaisesRegex(AgentBaseError, "consent"):
            providers.inspect("claude")
        with patch("agentbase.providers.shutil.which", return_value=None):
            with self.assertRaisesRegex(AgentBaseError, "unavailable"):
                providers.inspect("claude", consent=True)
        with patch("agentbase.providers.executable", return_value="trusted"), patch("agentbase.providers.invoke", return_value=(0, "unknown")):
            with self.assertRaisesRegex(AgentBaseError, "version"):
                providers.inspect("codex", consent=True)

    def test_claude_feature_detection_keeps_launch_and_hard_cap_disabled(self):
        replies = [(0, "2.1.310 (Claude Code)"), (0, CLAUDE_HELP), (0, "Usage: claude plugin validate [path]")]
        with patch("agentbase.providers.executable", return_value="trusted"), patch("agentbase.providers.invoke", side_effect=replies) as calls:
            result = providers.inspect("claude", consent=True)
        self.assertTrue(result["native_eval_available"])
        self.assertTrue(result["native_plugin_validator"])
        self.assertFalse(result["native_launch_enabled"])
        self.assertFalse(result["hard_spending_ceiling_verified"])
        self.assertEqual(result["model_sessions"], 0)
        self.assertTrue(all(c.args[1][-1] in {"--help", "--version"} for c in calls.call_args_list))

    def test_codex_does_not_invent_eval_or_plugin_validation(self):
        replies = [(0, "codex-cli 0.167.0-alpha.4.1"), (0, "Usage: codex exec [OPTIONS]\n --json --sandbox --ephemeral"), (0, "Commands:\n  list  List plugins\n  install Install plugins")]
        with patch("agentbase.providers.executable", return_value="trusted"), patch("agentbase.providers.invoke", side_effect=replies):
            result = providers.inspect("codex", consent=True)
        self.assertFalse(result["native_eval_available"])
        self.assertFalse(result["native_plugin_validator"])
        self.assertIn("--json", result["exec_features"])

    def test_native_validator_only_runs_after_canonical_integrity_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            distribution.build(root, "claude", "plugin")
            with patch("agentbase.providers.inspect", return_value={"native_plugin_validator": True, "version": "fixture"}), patch("agentbase.providers.executable", return_value="trusted"), patch("agentbase.providers.invoke", return_value=(0, "Valid")) as native:
                result = providers.validate_plugin(root, "claude", "plugin", consent=True)
                self.assertTrue(result["provider_validator_executed"])
                self.assertEqual(result["native_validation"], "passed")
                (root / "plugin/README.md").write_text("manual edit", encoding="utf-8")
                with self.assertRaises(AgentBaseError):
                    providers.validate_plugin(root, "claude", "plugin", consent=True)
                self.assertEqual(native.call_count, 1)


if __name__ == "__main__":
    unittest.main()
