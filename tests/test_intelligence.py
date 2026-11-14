import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentbase import intelligence
from agentbase.config import DEFAULT
from agentbase.context import inventory
from agentbase.explain import project_report
from agentbase.fs import AgentBaseError, batch_write


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "a.py").write_text("import b\nclass A:\n    def run(self):\n        return b.work()\n", encoding="utf-8")

    def index(self):
        source = inventory(self.root, DEFAULT)
        result = intelligence.analyze_source(source, intelligence.load_index(self.root))
        batch_write(self.root, intelligence.index_changes(result))
        return result

    def test_unchanged_files_reuse_facts_and_new_dependencies_resolve_without_reparse(self):
        first = self.index()
        self.assertEqual(first["cache"]["parsed"], 1)
        self.assertEqual(first["edges"], [])
        (self.root / "b.py").write_text("def work():\n    return 1\n", encoding="utf-8")
        with patch("agentbase.intelligence.file_facts", wraps=intelligence.file_facts) as parser:
            second = self.index()
        self.assertEqual(parser.call_count, 1)
        self.assertEqual(second["cache"], {"parsed": 1, "reused": 1, "removed": 0})
        self.assertEqual(second["edges"][0]["target"], "b.py")
        self.assertIn("A.run", {s["name"] for s in second["symbols"]})
        self.assertEqual(second["calls"][0]["callee"], "b.work")
        (self.root / "b.py").unlink()
        third = self.index()
        self.assertEqual(third["edges"], [])
        self.assertEqual(third["cache"]["removed"], 1)

    def test_changes_reparse_only_changed_file_and_cache_does_not_store_source(self):
        self.index()
        (self.root / "a.py").write_text("# PRIVATE_SOURCE_TEXT\ndef changed():\n    pass\n", encoding="utf-8")
        result = self.index()
        self.assertEqual(result["cache"]["parsed"], 1)
        self.assertNotIn("PRIVATE_SOURCE_TEXT", (self.root / intelligence.INDEX).read_text())
        with patch("agentbase.intelligence.file_facts", side_effect=AssertionError("unchanged file must not reparse")):
            self.index()

    def test_feature_query_and_diagram_cite_only_current_static_evidence(self):
        (self.root / "b.py").write_text("def work():\n    pass\n", encoding="utf-8")
        (self.root / "unrelated.py").write_text("def other():\n    pass\n", encoding="utf-8")
        report, evidence = project_report(self.root, DEFAULT, feature="A.run")
        self.assertEqual(evidence["files"], {})
        report, evidence = project_report(self.root, DEFAULT, feature="class A")
        self.assertEqual(set(evidence["files"]), {"a.py", "b.py"})
        self.assertIn("```mermaid", report)
        self.assertIn("runtime dispatch unverified", report)
        self.assertNotIn("unrelated.py", report)
        self.assertFalse((self.root / intelligence.INDEX).exists())

    def test_corrupt_cache_is_preserved_and_invalid_python_is_labeled(self):
        self.index()
        path = self.root / intelligence.INDEX
        path.write_text('{"engine":"manual"}', encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "Preserving"):
            self.index()
        self.assertEqual(path.read_text(), '{"engine":"manual"}')
        facts = intelligence.file_facts("broken.py", "def invalid(")
        self.assertTrue(facts["errors"])
        self.assertEqual(facts["symbols"], [])


if __name__ == "__main__":
    unittest.main()
