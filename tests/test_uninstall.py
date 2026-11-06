import tempfile
import unittest
from pathlib import Path

from agentbase.fs import AgentBaseError
from agentbase.install import install, uninstall


class UninstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def files(self):
        return {p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()}

    def test_roundtrip_restores_user_instructions_byte_for_byte(self):
        # Kullanıcının kendi AGENTS.md içeriği init+uninstall sonrasında birebir aynı kalmalı.
        original = b"# Team rules\r\n\r\nRun our checks.\r\n"
        (self.root / "AGENTS.md").write_bytes(original)
        install(self.root)
        uninstall(self.root)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), original)

    def test_files_created_by_agentbase_are_removed_but_state_is_kept(self):
        install(self.root)
        uninstall(self.root)
        left = self.files()
        self.assertNotIn("AGENTS.md", left)  # Dosyayı AgentBase yaratmıştı.
        self.assertNotIn("CLAUDE.md", left)
        self.assertFalse(any(f.startswith((".codex/", ".claude/", ".agents/")) for f in left))
        self.assertIn(".agentbase/config.json", left)  # Kullanıcı durumu korunur.
        self.assertIn(".agentbase/memory/overview.md", left)

    def test_update_reinstalls_after_uninstall(self):
        install(self.root)
        uninstall(self.root)
        self.assertTrue(install(self.root, update=True)["changes"])
        self.assertIn("AGENTS.md", self.files())

    def test_purge_removes_everything_agentbase_owns(self):
        install(self.root)
        uninstall(self.root, purge=True)
        self.assertEqual(self.files(), set())
        self.assertFalse((self.root / ".agentbase").exists())

    def test_dry_run_has_no_effects(self):
        install(self.root)
        before = self.files()
        result = uninstall(self.root, purge=True, dry_run=True)
        self.assertTrue(result["changes"])
        self.assertEqual(self.files(), before)

    def test_locally_edited_managed_file_blocks_uninstall(self):
        install(self.root)
        policy = self.root / ".agentbase/policy.md"
        policy.write_text("my edit\n", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "Local managed edit"):
            uninstall(self.root)
        self.assertEqual(policy.read_text(encoding="utf-8"), "my edit\n")

    def test_not_initialized_is_an_error(self):
        with self.assertRaisesRegex(AgentBaseError, "Not initialized"):
            uninstall(self.root)


if __name__ == "__main__":
    unittest.main()
