import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agentbase.cli import main
from agentbase.config import DEFAULT
from agentbase.explain import MARKER, REPORT, project_report


class ExplainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Küçük proje: a.py -> b.py içe aktarması grafikte bir kenar üretmeli.
        (self.root / "a.py").write_text("import b\n\ndef run():\n    return b.VALUE\n", encoding="utf-8")
        (self.root / "b.py").write_text("VALUE = 1\n\nclass Thing:\n    pass\n", encoding="utf-8")

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--project", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def init_project(self):
        # explain yapılandırmayı okur; bu yüzden proje önce init ile hazırlanır.
        self.assertEqual(self.cli("init")[0], 0)

    def test_project_report_finds_symbols_and_import_edge(self):
        report, evidence = project_report(self.root, DEFAULT)
        self.assertTrue(report.startswith(MARKER))
        self.assertIn("function `run`", report)
        self.assertIn("class `Thing`", report)
        self.assertIn("`a.py:1` → `b.py`", report)
        self.assertTrue({"a.py", "b.py"} <= set(evidence["files"]))

    def test_report_is_deterministic(self):
        self.assertEqual(project_report(self.root, DEFAULT), project_report(self.root, DEFAULT))

    def test_explain_without_write_is_read_only(self):
        self.init_project()
        code, out, _ = self.cli("explain")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith(MARKER))
        self.assertFalse((self.root / REPORT).exists())

    def test_explain_on_uninitialized_project_exits_2(self):
        bare = tempfile.TemporaryDirectory()
        self.addCleanup(bare.cleanup)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--project", bare.name, "explain"])
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(err.getvalue()))

    def test_explain_write_second_run_is_idempotent(self):
        self.init_project()
        code, out, _ = self.cli("explain", "--write")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"written": REPORT})
        path = self.root / REPORT
        first = path.read_bytes()
        self.assertTrue(first.startswith(MARKER.encode()))
        # Rapor kendi çıktısını envantere katmamalı; aksi halde her yazım farklı olurdu.
        code, _, _ = self.cli("explain", "--write")
        self.assertEqual(code, 0)
        self.assertEqual(first, path.read_bytes())

    def test_explain_write_refuses_to_overwrite_unmarked_report(self):
        self.init_project()
        path = self.root / REPORT
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# hand written\n", encoding="utf-8")
        code, _, err = self.cli("explain", "--write")
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(err))
        self.assertEqual(path.read_text(encoding="utf-8"), "# hand written\n")


if __name__ == "__main__":
    unittest.main()
