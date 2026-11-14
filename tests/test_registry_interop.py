import importlib.util
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from test_registry import MIT, SKILL, URL, response

from agentbase import dependencies, registry
from agentbase.fs import AgentBaseError, atomic_write
from agentbase.skill_security import licenses, metadata


class InteropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixtures(self):
        staged = []
        for name in ("sample", "second"):
            files = {f"{name}/SKILL.md": SKILL.replace(b"sample", name.encode()), "LICENSE": MIT}
            with patch("agentbase.registry.download", side_effect=response(files=files)):
                record, selected = registry.fetch(URL)
            record["targets"] = ["codex", "claude"]
            staged.append((record, selected))
        exported = {"schema_version": 1, "skills": {r["id"]: deepcopy(r) for r, _ in staged}, "history": {}}
        return exported, staged

    def test_multi_restore_is_one_batch_and_repeated_restore_preserves_other_skills(self):
        exported, staged = self.fixtures()
        with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)):
            preview = registry.restore(self.root, exported)
        self.assertFalse((self.root / registry.LOCK).exists())
        with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)), patch("agentbase.registry.batch_write", wraps=registry.batch_write) as batch:
            registry.restore(self.root, exported, dry_run=False, expected_plan=preview["plan_id"])
        self.assertEqual(batch.call_count, 1)
        self.assertEqual(set(registry.load(self.root)["skills"]), {"sample", "second"})
        self.assertTrue(registry.audit(self.root)["ok"])
        subset = exported | {"skills": {"sample": exported["skills"]["sample"]}}
        fresh = deepcopy(staged[0])
        fresh[0]["installed_at"] = "2026-11-14T00:00:00+00:00"
        with patch("agentbase.registry.fetch", return_value=fresh):
            preview = registry.restore(self.root, subset)
            registry.restore(self.root, subset, dry_run=False, expected_plan=preview["plan_id"])
        self.assertIn("second", registry.load(self.root)["skills"])
        self.assertEqual(registry.load(self.root)["history"], {})
        self.assertEqual(registry.load(self.root)["skills"]["sample"]["requested_ref"], "HEAD")

    def test_all_sources_validated_before_first_write(self):
        exported, staged = self.fixtures()
        with patch("agentbase.registry.fetch", side_effect=[staged[0], AgentBaseError("network fixture")]):
            with self.assertRaisesRegex(AgentBaseError, "network fixture"):
                registry.restore(self.root, exported, dry_run=False)
        self.assertEqual(list(self.root.iterdir()), [])
        staged[1][0]["hashes"]["SKILL.md"] = "0" * 64
        with patch("agentbase.registry.fetch", side_effect=staged):
            with self.assertRaisesRegex(AgentBaseError, "hashes"):
                registry.restore(self.root, exported)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_multi_restore_io_failure_rolls_back_both_and_lock(self):
        exported, staged = self.fixtures()
        with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)):
            preview = registry.restore(self.root, exported)
        calls = 0

        def fail(path, data):
            nonlocal calls
            calls += 1
            if calls == 8:
                raise OSError("second skill write fixture")
            atomic_write(path, data)

        with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)), patch("agentbase.fs.atomic_write", side_effect=fail):
            with self.assertRaises(OSError):
                registry.restore(self.root, exported, dry_run=False, expected_plan=preview["plan_id"])
        self.assertFalse((self.root / registry.LOCK).exists())
        self.assertFalse(any(p.is_file() for p in self.root.rglob("*")))
        with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)):
            retry = registry.restore(self.root, exported)
        self.assertEqual(retry["conflicts"], [])
        self.assertEqual(retry["plan_id"], preview["plan_id"])

    def test_batch_conflict_prevents_every_install(self):
        exported, staged = self.fixtures()
        (self.root / ".agents/skills/second").mkdir(parents=True)
        with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)):
            preview = registry.restore(self.root, exported)
        with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)):
            with self.assertRaisesRegex(AgentBaseError, "conflicts"):
                registry.restore(self.root, exported, dry_run=False, expected_plan=preview["plan_id"])
        self.assertFalse((self.root / ".agents/skills/sample").exists())
        self.assertFalse((self.root / registry.LOCK).exists())

    def test_restore_missing_ack_and_stale_plan_prevent_all_writes(self):
        exported, staged = self.fixtures()
        staged[1][0]["findings"] = [{"id": "fixture", "rule": "script", "severity": "high", "file": "SKILL.md", "evidence": "fixture", "action": "Review"}]
        with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)):
            preview = registry.restore(self.root, exported)
        for expected, message in ((preview["plan_id"], "acknowledge"), ("wrong", "plan-id")):
            with patch("agentbase.registry.fetch", side_effect=deepcopy(staged)):
                with self.assertRaisesRegex(AgentBaseError, message):
                    registry.restore(self.root, exported, dry_run=False, expected_plan=expected)
        self.assertFalse((self.root / registry.LOCK).exists())

    def test_offline_curated_sources_and_no_executable_dependency_checks(self):
        self.assertEqual(registry.search("superpowers")["sources"][0]["id"], "superpowers")
        with patch("subprocess.run", side_effect=AssertionError("never execute")):
            result = dependencies.inspect(["Python 3.11+", "skill:sample", "skill:absent", "python-dist:agentbase-fixture-absent", "tool:absent-fixture", "unknown tool"], installed_skills=["sample"])
        self.assertEqual([r["status"] for r in result], ["available", "available", "missing", "missing", "missing", "unknown"])

    def test_license_matrix_keeps_restrictions_and_mixed_licenses_unresolved(self):
        for spdx in ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "CC0-1.0"):
            with self.subTest(spdx=spdx):
                self.assertEqual(licenses({"LICENSE": f"SPDX-License-Identifier: {spdx}".encode()}, "sample")["status"], "identified")
        for text in (b"SPDX-License-Identifier: MIT OR Apache-2.0", MIT + b"\nNoncommercial", b"SPDX-License-Identifier: Proprietary"):
            self.assertEqual(licenses({"LICENSE": text}, "sample")["status"], "unresolved")
        self.assertEqual(licenses({"LICENSE": MIT, "sample/LICENSE": b"SPDX-License-Identifier: ISC"}, "sample")["status"], "unresolved")

    @unittest.skipUnless(importlib.util.find_spec("yaml"), "optional PyYAML not installed")
    def test_optional_yaml_syntax_and_security(self):
        text = "---\nname: sample\ndescription: >+\n    Use when testing\n    samples.\nmetadata: {author: 'Test', version: '1.0'}\n---\nReview files."
        self.assertEqual(metadata(text, parser="pyyaml")["metadata"]["version"], "1.0")
        for fragment in ("name: sample\nname: sample", "name: !!python/object/apply:os.system ['bad']", "name: &n sample", "name: sample\nmetadata: {version: 1}", "name: sample\nmetadata: {x: {y: z}}"):
            with self.subTest(fragment=fragment), self.assertRaises(AgentBaseError):
                metadata("---\n" + fragment + "\ndescription: Test\n---\nBody", parser="pyyaml")

    def test_metadata_type_and_empty_validation(self):
        for old, new in (("Use when testing samples.", "'  '"), ("description:", "compatibility: ''\ndescription:")):
            with self.assertRaises(AgentBaseError):
                metadata(SKILL.decode().replace(old, new))
