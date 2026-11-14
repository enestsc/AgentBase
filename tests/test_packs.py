import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from agentbase import packs
from agentbase.fs import AgentBaseError
from agentbase.install import install, prepare


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_core_web_and_combinations_use_canonical_adapters(self):
        install(self.root, providers=["codex", "claude"], pack_ids=["web", "security"])
        state = packs.state(self.root)
        self.assertEqual(state["selected"], ["core", "security", "web"])
        self.assertTrue((self.root / ".codex/agents/agentbase-frontend-engineer.toml").exists())
        self.assertTrue((self.root / ".claude/agents/agentbase-security-reviewer.md").exists())
        self.assertFalse((self.root / ".codex/agents/agentbase-ai-ml-engineer.toml").exists())
        self.assertEqual(prepare(self.root, update=True), {})
        install(self.root, update=True)
        self.assertEqual(packs.state(self.root), state)

    def test_pack_removal_keeps_shared_files_and_user_content(self):
        install(self.root, providers=["claude"], pack_ids=["web"])
        (self.root / "app.py").write_text("user content")
        plan = packs.change(self.root, "web", remove=True)
        self.assertTrue(plan["dry_run"])
        packs.change(self.root, "web", remove=True, dry_run=False)
        self.assertFalse((self.root / ".claude/agents/agentbase-frontend-engineer.md").exists())
        self.assertTrue((self.root / ".claude/skills/agentbase-verify-change/SKILL.md").exists())
        self.assertEqual((self.root / "app.py").read_text(), "user content")

    def test_local_edits_block_addition_and_removal(self):
        install(self.root, providers=["codex"], pack_ids=["web"])
        path = self.root / ".codex/agents/agentbase-frontend-engineer.toml"
        path.write_text("local edit")
        with self.assertRaisesRegex(AgentBaseError, "Local managed edit"):
            packs.change(self.root, "web", remove=True, dry_run=False)
        self.assertEqual(path.read_text(), "local edit")

    def test_legacy_install_preserves_full_catalog(self):
        install(self.root, providers=["codex"])
        packs.change(self.root, "python", dry_run=False)
        self.assertTrue(packs.state(self.root)["legacy_catalog"])
        self.assertTrue((self.root / ".codex/agents/agentbase-ai-ml-engineer.toml").exists())

    def test_conflicts_unknown_dependencies_and_provider_mismatch(self):
        catalog = packs.catalog()
        catalog["web"]["conflicts"] = ["security"]
        with patch("agentbase.packs.catalog", return_value=catalog):
            with self.assertRaisesRegex(AgentBaseError, "Conflicting"):
                packs.resolve(["web", "security"], ["codex"])
        catalog["web"]["conflicts"] = []
        catalog["web"]["skills"] = ["missing"]
        with patch("agentbase.packs.catalog", return_value=catalog):
            with self.assertRaisesRegex(AgentBaseError, "unknown canonical"):
                packs.resolve(["web"], ["codex"])
        catalog["web"]["providers"] = ["claude"]
        with patch("agentbase.packs.catalog", return_value=catalog):
            with self.assertRaisesRegex(AgentBaseError, "support"):
                packs.resolve(["web"], ["codex"])

    def test_recommendations_are_local_and_dry_run_does_not_write(self):
        (self.root / "pyproject.toml").write_text("[project]")
        self.assertIn("python", packs.recommend(self.root)["recommendations"])
        install(self.root, pack_ids=["python"], dry_run=True)
        self.assertFalse((self.root / ".agentbase").exists())
        with self.assertRaises(AgentBaseError):
            packs.resolve(["missing"], ["codex"])

    def test_custom_pack_registration_and_combination(self):
        custom = deepcopy(packs.catalog()["python"])
        custom.update(id="my-python", name="My Python", agents=["backend-engineer"], skills=["agentbase-verify-change"])
        packs.register(self.root, custom, dry_run=True)
        self.assertFalse((self.root / ".agentbase").exists())
        packs.register(self.root, custom)
        install(self.root, providers=["codex"], pack_ids=["my-python", "security"])
        self.assertIn("my-python", packs.state(self.root)["selected"])
        self.assertEqual(prepare(self.root, update=True), {})
        with self.assertRaisesRegex(AgentBaseError, "shadow"):
            packs.register(self.root, packs.catalog()["core"])
        custom["skills"] = ["missing"]
        with self.assertRaisesRegex(AgentBaseError, "unknown canonical"):
            packs.register(self.root, custom)


if __name__ == "__main__":
    unittest.main()
