import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agentbase import distribution, evaluation, specs, tasks
from agentbase.fs import AgentBaseError
from agentbase.install import discovery_mode, install, prepare


class AdvancedFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def initialize_spec(self):
        return specs.initialize(self.root, "health", "Health API", "Add a health endpoint", ["GET /health returns 200"], "backend-engineer", "src")

    def test_spec_trace_and_import_use_existing_engine(self):
        install(self.root, providers=["codex"])
        self.initialize_spec()
        result = specs.proposal(self.root, "health", write=True)
        self.assertEqual(result["plan"]["tasks"][0]["status"], "pending")
        self.assertIn("R1", result["traceability"]["requirements"])
        specs.proposal(self.root, "health", import_tasks=True)
        self.assertEqual(tasks.load_plan(self.root)["tasks"], result["plan"]["tasks"])
        tasks.transition(self.root, "R1", "ready")
        tasks.transition(self.root, "R1", "running")
        with self.assertRaisesRegex(AgentBaseError, "handoff"):
            tasks.transition(self.root, "R1", "review")
        with self.assertRaisesRegex(AgentBaseError, "preserved"):
            specs.proposal(self.root, "health", import_tasks=True)

    def test_spec_acceptance_cycles_contradictions_ownership(self):
        self.initialize_spec()
        value, _ = specs.read(self.root, "health")
        missing = deepcopy(value)
        missing["requirements"][0]["acceptance"] = []
        with self.assertRaises(AgentBaseError):
            specs.compile_plan(missing)
        second = deepcopy(value["requirements"][0]) | {"id": "R2"}
        value["requirements"].append(second)
        with self.assertRaisesRegex(AgentBaseError, "ownership"):
            specs.compile_plan(value)
        second["dependencies"] = ["R1"]
        self.assertEqual(len(specs.compile_plan(value)["tasks"]), 2)
        value["requirements"][0]["dependencies"] = ["R2"]
        with self.assertRaisesRegex(AgentBaseError, "Circular"):
            specs.compile_plan(value)
        value["requirements"][0]["dependencies"] = ["missing"]
        with self.assertRaisesRegex(AgentBaseError, "does not exist"):
            specs.compile_plan(value)
        value["requirements"][0]["conflicts_with"] = ["R2"]
        with self.assertRaisesRegex(AgentBaseError, "contradictory"):
            specs.compile_plan(value)

    def test_incremental_spec_updates_change_hash_not_dag_until_import(self):
        self.initialize_spec()
        first = specs.proposal(self.root, "health")
        path = self.root / specs.location("health")
        path.write_text(path.read_text() + "\nReviewed architecture impact.\n", encoding="utf-8")
        second = specs.proposal(self.root, "health")
        self.assertNotEqual(first["traceability"]["sha256"], second["traceability"]["sha256"])
        self.assertFalse((self.root / tasks.PLAN).exists())
        with self.assertRaisesRegex(AgentBaseError, "preserved"):
            self.initialize_spec()

    def test_spec_readonly_ownership_and_malformed_json(self):
        self.initialize_spec()
        value, _ = specs.read(self.root, "health")
        value["requirements"][0]["role"] = "code-reviewer"
        with self.assertRaisesRegex(AgentBaseError, "read-only"):
            specs.compile_plan(value)
        (self.root / specs.location("health")).write_text("# empty", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "exactly one"):
            specs.read(self.root, "health")

    def test_generated_spec_output_preserves_local_edits(self):
        self.initialize_spec()
        specs.proposal(self.root, "health", write=True)
        path = self.root / ".agentbase/specs/health.trace.json"
        path.write_text("handwritten trace", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "Preserving locally edited"):
            specs.proposal(self.root, "health", write=True)
        self.assertEqual(path.read_text(), "handwritten trace")

    def test_static_eval_and_supplied_observation_grading(self):
        result = evaluation.run(self.root)
        self.assertTrue(result["ok"])
        self.assertEqual(evaluation.report(self.root), result)
        suite = {"schema_version": 1, "cases": [{"id": "fix", "prompt": "Fix parser bug", "expected_role": "debugger",
            "required_skills": ["agentbase-verify-change"], "forbidden_skills": ["agentbase-prepare-release"],
            "required_tools": ["tests"], "forbidden_tools": ["publish"], "expected_files": ["src/parser.py"]}]}
        observed = {"schema_version": 1, "origin": "mock", "observations": [{"id": "fix", "role": "debugger",
            "skills": ["agentbase-verify-change"], "tools": ["tests"], "changed_files": ["src/parser.py"],
            "evidence": ["fixture assertion"], "result": "passed"}]}
        result = evaluation.grade(suite, observed)
        self.assertTrue(result["ok"])
        self.assertEqual(result["origin"], "mock")
        self.assertFalse(result["runtime_behavior_verified"])
        observed["observations"][0]["skills"].append("agentbase-prepare-release")
        observed["observations"][0]["tools"].append("publish")
        result = evaluation.grade(suite, observed)
        self.assertFalse(result["ok"])
        self.assertIn("activated forbidden_tools", result["checks"][0]["failures"])
        with self.assertRaisesRegex(AgentBaseError, "both"):
            evaluation.run(self.root, Path("missing"))

    def test_reproducible_plugin_layout_and_local_modifications(self):
        for provider in ("codex", "claude"):
            with self.subTest(provider=provider):
                output = "packages/" + provider
                preview = distribution.build(self.root, provider, output, dry_run=True)
                self.assertTrue(preview["dry_run"])
                self.assertFalse((self.root / output).exists())
                distribution.build(self.root, provider, output)
                self.assertTrue(distribution.validate(self.root, output)["ok"])
                self.assertEqual(distribution.build(self.root, provider, output)["written"], 0)
                self.assertTrue((self.root / output / f".{provider}-plugin/plugin.json").is_file())
                lock = json.loads((self.root / output / "package.lock.json").read_text())
                self.assertEqual(lock["provider"], provider)
                (self.root / output / "README.md").write_text("local changes")
                with self.assertRaisesRegex(AgentBaseError, "differs"):
                    distribution.build(self.root, provider, output)
                with self.assertRaises(AgentBaseError):
                    distribution.validate(self.root, output)

    def test_plugin_discovery_preserves_cli_state_without_duplicate_skills(self):
        install(self.root, providers=["codex", "claude"], discovery="plugin")
        self.assertEqual(discovery_mode(self.root), "plugin")
        self.assertFalse((self.root / ".agents/skills").exists())
        self.assertFalse((self.root / ".claude/agents").exists())
        self.assertTrue((self.root / ".codex/agents/agentbase-debugger.toml").is_file())
        self.assertTrue((self.root / ".agentbase/tasks.json").is_file())
        self.assertEqual(prepare(self.root, update=True), {})
        install(self.root, update=True, discovery="native")
        self.assertTrue((self.root / ".claude/skills/agentbase-verify-change/SKILL.md").exists())
        install(self.root, update=True, discovery="plugin")
        self.assertFalse((self.root / ".claude/skills/agentbase-verify-change/SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
