import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from agentbase.adapters import render
from agentbase.catalog import roles, skills
from agentbase.cli import doctor
from agentbase.fs import AgentBaseError, atomic_write, batch_write, confined, project_lock
from agentbase.install import END, START, install


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_init_preserves_existing_instructions_byte_for_byte_outside_block(self):
        original = b"# Team rules\r\n\r\nRun our checks.\r\n"
        (self.root / "AGENTS.md").write_bytes(original)
        result = install(self.root)
        self.assertTrue(result["changes"])
        self.assertTrue((self.root / "AGENTS.md").read_bytes().startswith(original))
        self.assertIn("@AGENTS.md", (self.root / "CLAUDE.md").read_text())
        self.assertTrue(doctor(self.root)["ok"])

    def test_dry_run_has_no_filesystem_effects(self):
        result = install(self.root, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_update_is_idempotent_and_keeps_project_memory_and_config(self):
        install(self.root)
        memory = self.root / ".agentbase/memory/overview.md"
        memory.write_text("# Our reviewed memory\n", encoding="utf-8")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(install(self.root, update=True)["changes"], [])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_user_instruction_edits_outside_block_survive_update(self):
        install(self.root)
        path = self.root / "AGENTS.md"
        path.write_text("User prefix\n" + path.read_text() + "\nUser suffix\n", encoding="utf-8")
        install(self.root, update=True)
        self.assertTrue(path.read_text().startswith("User prefix\n"))
        self.assertTrue(path.read_text().endswith("User suffix\n"))

    def test_upgrade_discovers_new_delivery_skills_and_preserves_user_work(self):
        new = {"agentbase-prepare-release", "agentbase-changelog", "agentbase-pr-summary"}
        old = {name: body for name, body in skills().items() if name not in new}
        with patch("agentbase.adapters.skills", return_value=old):
            install(self.root)
        memory = self.root / ".agentbase/memory/overview.md"
        memory.write_bytes(b"User knowledge\r\n")
        preview = install(self.root, update=True, dry_run=True)
        for name in new:
            for prefix in (".agents", ".claude"):
                path = f"{prefix}/skills/{name}/SKILL.md"
                self.assertIn(path, [change["path"] for change in preview["changes"]])
                self.assertFalse((self.root / path).exists())
        install(self.root, update=True)
        for name in new:
            self.assertEqual((self.root / f".agents/skills/{name}/SKILL.md").read_text(encoding="utf-8"), skills()[name])
        self.assertEqual(memory.read_bytes(), b"User knowledge\r\n")
        self.assertEqual(install(self.root, update=True)["changes"], [])

    def test_full_file_conflict_prevents_all_updates(self):
        install(self.root)
        path = self.root / ".agentbase/policy.md"
        path.write_text("local edit", encoding="utf-8")
        before = (self.root / ".agentbase/manifest.json").read_bytes()
        with self.assertRaisesRegex(AgentBaseError, "Local managed edit"):
            install(self.root, update=True)
        self.assertEqual(path.read_text(), "local edit")
        self.assertEqual(before, (self.root / ".agentbase/manifest.json").read_bytes())
        self.assertFalse((self.root / ".agentbase/write.lock").exists())

    def test_block_edit_detected(self):
        install(self.root)
        path = self.root / "AGENTS.md"
        path.write_text(path.read_text().replace("sequential", "parallel"), encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "Local managed edit"):
            install(self.root, update=True)

    def test_managed_missing_file_detected(self):
        install(self.root)
        (self.root / ".agentbase/policy.md").unlink()
        with self.assertRaisesRegex(AgentBaseError, "missing"):
            install(self.root, update=True)

    def test_unmanaged_collision_not_overwritten(self):
        path = self.root / ".codex/agents/agentbase-architect.toml"
        path.parent.mkdir(parents=True)
        path.write_text("user config", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "collision"):
            install(self.root)
        self.assertEqual(path.read_text(), "user config")
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_malformed_markers_not_overwritten(self):
        (self.root / "AGENTS.md").write_text(END + START, encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "Malformed"):
            install(self.root)

    def test_provider_specific_install(self):
        install(self.root, providers=["claude"])
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / ".codex").exists())
        self.assertIn("Orchestrator", (self.root / "CLAUDE.md").read_text())

    def test_native_formats_and_shared_content(self):
        generated = render(["codex", "claude"])
        for role in roles():
            name = "agentbase-" + role["id"]
            native = tomllib.loads(generated[f".codex/agents/{name}.toml"])
            self.assertEqual(native["name"], name)
            self.assertEqual(native["model"], role["model_recommendations"]["codex"]["model"])
            self.assertEqual(native["model_reasoning_effort"],
                             role["model_recommendations"]["codex"]["model_reasoning_effort"])
            self.assertEqual(native["developer_instructions"], generated[f".agentbase/roles/{role['id']}.md"])
            claude = generated[f".claude/agents/{name}.md"]
            self.assertTrue(claude.endswith(native["developer_instructions"]))
            for key, value in role["model_recommendations"]["claude"].items():
                self.assertIn(f"\n{key}: {value}\n", claude)
            self.assertNotIn("tools: Agent", claude)

    def test_model_recommendations_match_role_complexity(self):
        generated = render(["codex", "claude"])
        for role in roles():
            codex, claude = (role["model_recommendations"][key] for key in ("codex", "claude"))
            if role["id"] in {"architect", "security-reviewer"}:
                self.assertEqual((codex["model"], codex["model_reasoning_effort"]), ("gpt-6.1-sol", "high"))
                self.assertEqual(claude, {"model": "opus", "effort": "high"})
            elif role["access"] == "read":
                self.assertEqual((codex["model"], codex["model_reasoning_effort"]), ("gpt-6-luna", "low"))
                self.assertEqual(claude, {"model": "haiku", "effort": "low"})
        for name, content in skills().items():
            self.assertTrue(content.startswith(f"---\nname: {name}\ndescription: "))
            self.assertEqual(content, generated[f".agents/skills/{name}/SKILL.md"])
            self.assertEqual(content, generated[f".claude/skills/{name}/SKILL.md"])

    def test_installed_project_does_not_receive_source_or_tests(self):
        install(self.root)
        names = [p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file()]
        self.assertFalse(any(name.endswith(".py") or name.startswith("tests/") for name in names))

    def test_lock_prevents_second_writer(self):
        with project_lock(self.root):
            with self.assertRaisesRegex(AgentBaseError, "writer active"):
                install(self.root)
        self.assertFalse((self.root / ".agentbase/write.lock").exists())

    def test_batch_rolls_back_ordinary_io_failure(self):
        (self.root / "one.txt").write_text("before", encoding="utf-8")
        original = atomic_write
        calls = 0

        def fail_second(path, content):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated write failure")
            original(path, content)

        with patch("agentbase.fs.atomic_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                batch_write(self.root, {"one.txt": "after", "two.txt": "new"})
        self.assertEqual((self.root / "one.txt").read_text(), "before")
        self.assertFalse((self.root / "two.txt").exists())

    def test_unsafe_paths_rejected(self):
        for value in ("../outside", "/absolute", "C:/Windows/file", "a/../b", "a\\b", "CON.txt", "a/*", "a/b."):
            with self.subTest(value=value), self.assertRaises(AgentBaseError):
                confined(self.root, value)

    def test_linked_directory_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.root / ".agentbase").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("OS does not permit symlink creation")
            with self.assertRaisesRegex(AgentBaseError, "linked"):
                install(self.root)
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
