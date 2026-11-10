import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from agentbase.config import DEFAULT, load_config
from agentbase.context import retrieve
from agentbase.explain import project_report
from agentbase.fs import AgentBaseError, atomic_write, json_text
from agentbase.install import install
from agentbase.memory import INDEX, handoff, index, list_notes, maintain, note, sync_memory


class ContextMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        install(self.root)
        (self.root / "app.py").write_text("import service\n\ndef main():\n    return service.value\n", encoding="utf-8")
        (self.root / "service.py").write_text("value = 42\n", encoding="utf-8")

    def test_context_deduplicates_paths_and_content(self):
        (self.root / "copy.py").write_bytes((self.root / "app.py").read_bytes())
        result = retrieve(self.root, ["app.py", "app.py", "copy.py"], DEFAULT)
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual([s["reason"] for s in result["skipped"]], ["duplicate path", "duplicate content"])
        self.assertIn("not a provider", result["estimate_method"])

    def test_secret_binary_and_large_files_excluded(self):
        (self.root / ".env").write_text("SECRET=dont-read", encoding="utf-8")
        (self.root / "image.bin").write_bytes(b"x\0y")
        (self.root / "large.md").write_text("a" * 100_001, encoding="utf-8")
        result = retrieve(self.root, [".env", "image.bin", "large.md"], DEFAULT)
        self.assertEqual(result["files"], [])
        self.assertEqual(len(result["skipped"]), 3)
        self.assertNotIn("dont-read", json_text(result))

    def test_aggregate_context_budget(self):
        config = deepcopy(DEFAULT)
        config["context_overrides"] = {"max_document_bytes": 12}
        result = retrieve(self.root, ["service.py", "app.py"], config)
        self.assertEqual([f["path"] for f in result["files"]], ["service.py"])
        self.assertLessEqual(result["bytes"], 12)

    def test_python_evidence_and_import_graph(self):
        report, snapshot = project_report(self.root, DEFAULT)
        self.assertIn("app.py:1", report)
        self.assertIn("app.py:3", report)
        self.assertIn("```mermaid", report)
        self.assertIn("not proven runtime calls", report)
        self.assertIn("app.py", snapshot["files"])
        self.assertNotIn(".agentbase/policy.md", snapshot["files"])

    def test_js_lexical_edge_is_labeled_heuristic(self):
        (self.root / "view.ts").write_text("import {x} from './lib';\n", encoding="utf-8")
        (self.root / "lib.ts").write_text("export const x = 1;\n", encoding="utf-8")
        report, _ = project_report(self.root, DEFAULT)
        self.assertIn("JS/TS lexical import (heuristic)", report)
        self.assertIn("view.ts:1", report)

    def test_failed_parse_reported(self):
        (self.root / "bad.py").write_text("def ?", encoding="utf-8")
        report, _ = project_report(self.root, DEFAULT)
        self.assertIn("could not be parsed", report)

    def test_memory_note_evidence_and_drift(self):
        record = note(self.root, "decision", "Keep the service boundary explicit.", "app.py:1")
        self.assertEqual(record["file"], "app.py")
        before = (self.root / ".agentbase/memory/decision.md").read_bytes()
        (self.root / "app.py").write_text("# changed\n", encoding="utf-8")
        result = sync_memory(self.root, deep=True)
        self.assertEqual(result["drift"][0]["file"], "app.py")
        self.assertFalse(result["decisions_rewritten"])
        self.assertEqual(before, (self.root / ".agentbase/memory/decision.md").read_bytes())

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_prune_preview_preserves_every_file_then_archives_selected_only(self):
        first = note(self.root, "decision", "Old claim", "app.py:1")
        second = note(self.root, "decision", "Other claim", "service.py:1")
        path = self.root / ".agentbase/memory/decision.md"
        original = path.read_bytes()
        path.write_bytes(b"Manual prefix\r\n" + original + b"Manual suffix\r\n")
        before = self.snapshot()
        preview = maintain(self.root, [first["id"]], "outdated", dry_run=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(preview["selected"][0]["id"], first["id"])
        result = maintain(self.root, [first["id"]], "outdated")
        body = path.read_bytes()
        self.assertTrue(body.startswith(b"Manual prefix\r\n"))
        self.assertTrue(body.endswith(b"Manual suffix\r\n"))
        self.assertNotIn(b"Old claim", body)
        self.assertIn(b"Other claim", body)
        saved = index(self.root)
        self.assertEqual([n["id"] for n in saved["managed_notes"]], [second["id"]])
        self.assertEqual([e["file"] for e in saved["entries"]], ["service.py"])
        self.assertIn("Old claim", (self.root / result["archive"]).read_text(encoding="utf-8"))

    def test_shared_evidence_survives_until_last_note_is_pruned(self):
        a = note(self.root, "issue", "First", "app.py:1")
        b = note(self.root, "issue", "Second", "app.py:1")
        maintain(self.root, [a["id"]], "resolved")
        self.assertEqual(len(index(self.root)["entries"]), 1)
        maintain(self.root, [b["id"]], "resolved")
        self.assertEqual(index(self.root)["entries"], [])

    def test_supersede_replaces_evidence_and_preserves_original_in_archive(self):
        old = note(self.root, "decision", "Previous", "app.py:1")
        before = self.snapshot()
        maintain(self.root, [old["id"]], "changed", text="Current", evidence="service.py:1", dry_run=True)
        self.assertEqual(before, self.snapshot())
        result = maintain(self.root, [old["id"]], "changed", text="Current", evidence="service.py:1")
        self.assertNotEqual(result["replacement"]["id"], old["id"])
        self.assertEqual(index(self.root)["entries"][0]["file"], "service.py")
        self.assertEqual(len(index(self.root)["managed_notes"]), 1)
        self.assertIn("Previous", (self.root / result["archive"]).read_text(encoding="utf-8"))

    def test_invalid_replacement_or_edited_note_changes_nothing(self):
        old = note(self.root, "decision", "Previous", "app.py:1")
        before = self.snapshot()
        with self.assertRaises(AgentBaseError):
            maintain(self.root, [old["id"]], "changed", text="Current", evidence="missing.py:1")
        self.assertEqual(before, self.snapshot())
        path = self.root / ".agentbase/memory/decision.md"
        path.write_text(path.read_text().replace("Previous", "User edited"), encoding="utf-8")
        self.assertFalse(list_notes(self.root)["notes"][0]["intact"])
        before = self.snapshot()
        with self.assertRaisesRegex(AgentBaseError, "Preserving edited"):
            maintain(self.root, [old["id"]], "changed")
        self.assertEqual(before, self.snapshot())

    def test_legacy_index_and_manual_references_are_preserved(self):
        record = note(self.root, "issue", "Tracked", "app.py:1")
        data = index(self.root)
        legacy = {"schema_version": 1, "entries": data["entries"]}
        (self.root / INDEX).write_text(json_text(legacy), encoding="utf-8")
        self.assertEqual(list_notes(self.root)["notes"], [])
        fresh = note(self.root, "issue", "Fresh", "service.py:1")
        path = self.root / ".agentbase/memory/issue.md"
        path.write_bytes(path.read_bytes() + b"Manual reference service.py:1\r\n")
        maintain(self.root, [fresh["id"]], "changed")
        self.assertEqual(len(index(self.root)["entries"]), 2)
        self.assertIn(record["id"], path.read_text())

    def test_unknown_duplicate_ids_and_empty_reason_are_rejected(self):
        old = note(self.root, "issue", "Tracked", "app.py:1")
        before = self.snapshot()
        for ids, reason in ((["../escape"], "x"), ([old["id"], old["id"]], "x"), ([old["id"]], " ")):
            with self.subTest(ids=ids), self.assertRaises(AgentBaseError):
                maintain(self.root, ids, reason)
        self.assertEqual(before, self.snapshot())

    def test_archive_write_failure_rolls_back_note_and_index(self):
        old = note(self.root, "issue", "Tracked", "app.py:1")
        before = self.snapshot()

        def fail_archive(path, data):
            if path.parent.name == "archive":
                raise OSError("archive write failure")
            atomic_write(path, data)

        with patch("agentbase.fs.atomic_write", side_effect=fail_archive), self.assertRaises(OSError):
            maintain(self.root, [old["id"]], "changed")
        self.assertEqual(before, self.snapshot())

    def test_supersede_can_recover_full_budget_without_losing_old_note(self):
        old = note(self.root, "issue", "x" * 1800, "app.py:1")
        config = load_config(self.root)
        config["context_overrides"] = {"memory_max_chars": 1000}
        (self.root / ".agentbase/config.json").write_text(json_text(config), encoding="utf-8")
        maintain(self.root, [old["id"]], "shorter", text="Short", evidence="app.py:1")
        self.assertIn("Short", (self.root / ".agentbase/memory/issue.md").read_text())

    def test_memory_rejects_nonexistent_line_or_secret_evidence(self):
        for evidence in ("app.py:100", "app.py:0", "missing.py:1", ".env:1", "app.py"):
            with self.subTest(evidence=evidence), self.assertRaises(AgentBaseError):
                note(self.root, "decision", "A claim", evidence)

    def test_light_sync_does_not_generate_reports(self):
        result = sync_memory(self.root)
        self.assertEqual(result["mode"], "light")
        self.assertFalse((self.root / ".agentbase/reports").exists())
        self.assertIn("does not imply", (self.root / ".agentbase/memory/status.md").read_text())

    def test_memory_budget_preserves_old_notes(self):
        config = load_config(self.root)
        config["context_overrides"] = {"memory_max_chars": 100}
        (self.root / ".agentbase/config.json").write_text(json_text(config), encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "budget"):
            note(self.root, "decision", "x" * 100, "app.py:1")
        self.assertFalse((self.root / ".agentbase/memory/decision.md").exists())

    def test_handoff_is_bounded_and_marks_omissions(self):
        config = load_config(self.root)
        config["context_overrides"] = {"max_handoff_chars": 200}
        (self.root / ".agentbase/config.json").write_text(json_text(config), encoding="utf-8")
        body = handoff(self.root)
        self.assertLessEqual(len(body), 200)
        self.assertIn("omitted material", body)

    def test_deep_sync_preserves_unmarked_user_report(self):
        path = self.root / ".agentbase/reports/project.md"
        path.parent.mkdir()
        path.write_text("My manual documentation", encoding="utf-8")
        with self.assertRaisesRegex(AgentBaseError, "Preserving unmarked"):
            sync_memory(self.root, deep=True)
        self.assertFalse((self.root / ".agentbase/memory/status.md").exists())


if __name__ == "__main__":
    unittest.main()
