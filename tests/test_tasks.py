import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from agentbase.config import DEFAULT
from agentbase.fs import AgentBaseError
from agentbase.install import install
from agentbase.tasks import conflicts, import_plan, load_plan, schedule, sync, transition, validate_plan


def task(name="contract", deps=None, path="src/api.py", access="read", role="architect"):
    return {"id": name, "description": "Define a usable contract", "role": role,
            "dependencies": deps or [], "inputs": ["Requirement"], "outputs": ["Accepted contract"],
            "scope": [{"path": path, "access": access}], "resources": [],
            "acceptance": ["Contract matches the requirement"], "status": "pending",
            "verification": [], "blocking_reason": ""}


def plan(*items):
    return {"schema_version": 1, "tasks": list(items)}


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        install(self.root)

    def complete(self, name):
        transition(self.root, name, "running")
        transition(self.root, name, "review")
        transition(self.root, name, "completed", evidence=["Contract inspected: criteria met"])

    def test_real_dependency_lifecycle(self):
        import_plan(self.root, plan(task(), task("backend", ["contract"], access="write", role="backend-engineer")))
        self.assertEqual(schedule(load_plan(self.root), DEFAULT), ["contract"])
        with self.assertRaises(AgentBaseError):
            transition(self.root, "backend", "running")
        sync(self.root)
        self.complete("contract")
        self.assertEqual(load_plan(self.root)["tasks"][1]["status"], "pending")
        sync(self.root)
        self.assertEqual(schedule(load_plan(self.root), DEFAULT), ["backend"])

    def test_completion_requires_review_and_evidence(self):
        import_plan(self.root, plan(task()))
        sync(self.root)
        transition(self.root, "contract", "running")
        with self.assertRaisesRegex(AgentBaseError, "Invalid transition"):
            transition(self.root, "contract", "completed", evidence=["checked"])
        transition(self.root, "contract", "review")
        with self.assertRaisesRegex(AgentBaseError, "evidence"):
            transition(self.root, "contract", "completed")
        self.assertEqual(load_plan(self.root)["tasks"][0]["status"], "review")

    def test_cycle_and_self_dependency_rejected(self):
        for value in (plan(task("a", ["b"]), task("b", ["a"])), plan(task("a", ["a"]))):
            with self.assertRaisesRegex(AgentBaseError, "Circular"):
                validate_plan(value)

    def test_missing_and_duplicate_dependencies_rejected(self):
        for value in (plan(task("a", ["missing"])), plan(task("a"), task("b", ["a", "a"]))):
            with self.assertRaises(AgentBaseError):
                validate_plan(value)

    def test_duplicate_id_and_unknown_role_rejected(self):
        for value in (plan(task(), task()), plan(task(role="general-implementer"))):
            with self.assertRaises(AgentBaseError):
                validate_plan(value)

    def test_read_only_role_cannot_claim_writer_scope(self):
        with self.assertRaisesRegex(AgentBaseError, "read-only role"):
            validate_plan(plan(task(access="write")))

    def test_directory_and_case_collisions(self):
        a = task(path="src", access="write", role="backend-engineer")
        b = task("b", path="SRC/api.py")
        self.assertTrue(conflicts(a, b))
        b["scope"][0]["path"] = "src_other/api.py"
        self.assertFalse(conflicts(a, b))
        a["scope"][0]["path"] = "."
        self.assertTrue(conflicts(a, b))

    def test_resource_conflicts(self):
        a, b = task(), task("b")
        a["resources"] = [{"name": "TEST-DB", "access": "write"}]
        b["resources"] = [{"name": "test-db", "access": "read"}]
        self.assertTrue(conflicts(a, b))

    def test_safe_parallel_readers_are_deterministic(self):
        config = deepcopy(DEFAULT)
        config["execution"] = {"mode": "safe-parallel", "max_concurrency": 2}
        self.assertEqual(schedule(plan(task("c"), task("b"), task("a")), config), ["a", "b"])

    def test_writer_serializes_even_disjoint_paths(self):
        config = deepcopy(DEFAULT)
        config["execution"] = {"mode": "safe-parallel", "max_concurrency": 3}
        a = task("a", path="server", access="write", role="backend-engineer")
        b = task("b", path="client", access="write", role="frontend-engineer")
        self.assertEqual(schedule(plan(b, a), config), ["a"])

    def test_running_and_review_tasks_hold_slots(self):
        import_plan(self.root, plan(task("a"), task("b")))
        sync(self.root)
        transition(self.root, "a", "running")
        transition(self.root, "a", "review")
        self.assertEqual(schedule(load_plan(self.root), DEFAULT), [])
        with self.assertRaisesRegex(AgentBaseError, "concurrency"):
            transition(self.root, "b", "running")

    def test_blocked_requires_reason_and_retry_clears_evidence(self):
        import_plan(self.root, plan(task()))
        with self.assertRaisesRegex(AgentBaseError, "reason"):
            transition(self.root, "contract", "blocked")
        transition(self.root, "contract", "blocked", reason="Missing approved contract", evidence=["Old observation"])
        transition(self.root, "contract", "pending")
        item = load_plan(self.root)["tasks"][0]
        self.assertEqual(item["verification"], [])
        self.assertEqual(item["blocking_reason"], "")

    def test_nonempty_plan_cannot_be_replaced(self):
        import_plan(self.root, plan(task()))
        with self.assertRaisesRegex(AgentBaseError, "preserved"):
            import_plan(self.root, plan(task("other")))

    def test_completed_with_unsatisfied_dependencies_rejected(self):
        a, b = task("a"), task("b", ["a"])
        b.update(status="completed", verification=["claimed checked"])
        with self.assertRaisesRegex(AgentBaseError, "dependencies"):
            validate_plan(plan(a, b))

    def test_malformed_fields_and_traversal_rejected(self):
        cases = [task(path="../escape"), task(path="src/**"), task()]
        cases[-1]["inputs"] = "not a list"
        for value in cases:
            with self.assertRaises(AgentBaseError):
                validate_plan(plan(value))


if __name__ == "__main__":
    unittest.main()
