import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agentbase import specs, tasks
from agentbase.fs import AgentBaseError, json_text
from agentbase.install import install


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        install(self.root, providers=["codex"])
        specs.initialize(self.root, "health", "Health", "Add health", ["Returns 200"], "backend-engineer", "src")
        specs.proposal(self.root, "health", import_tasks=True)

    def edit(self, transform):
        spec, _ = specs.read(self.root, "health")
        transform(spec)
        (self.root / specs.location("health")).write_text("# Health\n```agentbase-spec\n" + json_text(spec) + "```\n", encoding="utf-8")

    def apply(self):
        preview = specs.reconcile(self.root, "health")
        return specs.reconcile(self.root, "health", apply=True, expected_plan=preview["plan_id"])

    def review(self):
        tasks.transition(self.root, "R1", "ready")
        tasks.transition(self.root, "R1", "running")
        handoff = {"schema_version": 1, "task_id": "R1", "result": "Health test observed", "changed_files": ["src/health.py"],
                   "decisions": [], "tests": [{"command": "python -m unittest tests.test_health", "status": "passed", "outcome": "fixture: 1 test passed"}],
                   "failures": [], "risks": [], "artifacts": []}
        tasks.transition(self.root, "R1", "review", handoff=handoff)

    def test_update_pending_preserves_unmanaged_tasks_and_plan_is_exact(self):
        current = tasks.load_plan(self.root)
        other = deepcopy(current["tasks"][0]) | {"id": "manual", "scope": [{"path": "docs", "access": "write"}]}
        current["tasks"].append(other)
        (self.root / tasks.PLAN).write_text(json_text(current), encoding="utf-8")
        self.edit(lambda s: s["requirements"][0].update(statement="Add better health"))
        preview = specs.reconcile(self.root, "health")
        self.assertEqual(preview["changes"]["updated"], ["R1"])
        self.assertEqual(tasks.load_plan(self.root), current)
        with self.assertRaisesRegex(AgentBaseError, "plan-id"):
            specs.reconcile(self.root, "health", apply=True, expected_plan="stale")
        self.apply()
        final = tasks.load_plan(self.root)["tasks"]
        self.assertEqual(final[1], other)
        self.assertEqual(final[0]["description"], "Add better health")

    def test_completed_task_and_handoff_preserved_when_adding_requirement(self):
        self.review()
        tasks.transition(self.root, "R1", "completed", evidence=["Observed fixture test"])
        old = tasks.load_plan(self.root)["tasks"][0]
        def add(spec):
            spec["requirements"].append(deepcopy(spec["requirements"][0]) | {"id": "R2", "statement": "Add readiness", "dependencies": ["R1"]})
        self.edit(add)
        result = self.apply()
        self.assertEqual(result["changes"]["added"], ["R2"])
        self.assertEqual(tasks.load_plan(self.root)["tasks"][0], old)
        self.assertEqual(tasks.load_plan(self.root)["tasks"][1]["status"], "pending")

    def test_started_task_and_manual_definition_edits_are_preserved(self):
        self.review()
        self.edit(lambda s: s["requirements"][0].update(acceptance=["New acceptance"]))
        before = (self.root / tasks.PLAN).read_bytes()
        with self.assertRaisesRegex(AgentBaseError, "follow-up"):
            self.apply()
        self.assertEqual((self.root / tasks.PLAN).read_bytes(), before)
        current = json.loads(before)
        current["tasks"][0]["description"] = "Manual change"
        (self.root / tasks.PLAN).write_text(json_text(current), encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "Local task"):
            specs.reconcile(self.root, "health")

    def test_source_or_runtime_changes_invalidate_preview(self):
        self.edit(lambda s: s["requirements"][0].update(statement="New description"))
        preview = specs.reconcile(self.root, "health")
        tasks.transition(self.root, "R1", "ready")
        with self.assertRaises(AgentBaseError):
            specs.reconcile(self.root, "health", apply=True, expected_plan=preview["plan_id"])

    def test_criterion_handoff_evidence_is_explicit_and_stale_after_spec_change(self):
        self.review()
        mapping = {"schema_version": 1, "requirements": {"R1": [{"criterion": "Returns 200", "tests": [0]}]}}
        report = specs.evidence(self.root, "health", mapping)
        self.assertEqual(report["criteria"][0]["status"], "reported-passed")
        self.assertFalse(report["test_execution_verified"])
        self.assertEqual(report, specs.evidence(self.root, "health"))
        self.edit(lambda s: s["assumptions"].append("Reviewed deployment"))
        with self.assertRaisesRegex(AgentBaseError, "reconcile"):
            specs.evidence(self.root, "health")
        self.apply()
        self.assertEqual(specs.evidence(self.root, "health")["criteria"][0]["status"], "unverified")

    def test_mapping_needs_handoff_and_preserves_edited_artifacts(self):
        mapping = {"schema_version": 1, "requirements": {"R1": [{"criterion": "Returns 200", "tests": [0]}]}}
        with self.assertRaisesRegex(AgentBaseError, "handoff"):
            specs.evidence(self.root, "health", mapping)
        self.review()
        bad = deepcopy(mapping)
        bad["requirements"]["R1"][0]["tests"] = [99]
        with self.assertRaisesRegex(AgentBaseError, "invalid"):
            specs.evidence(self.root, "health", bad)
        specs.evidence(self.root, "health", mapping)
        path = self.root / ".agentbase/specs/health.evidence.json"
        path.write_text("manual artifact", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "locally edited"):
            specs.evidence(self.root, "health", mapping)
        self.assertEqual(path.read_text(), "manual artifact")


if __name__ == "__main__":
    unittest.main()
