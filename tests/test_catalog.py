import json
import unittest

from agentbase.catalog import roles, skills


class CatalogTests(unittest.TestCase):
    def test_role_skill_references_and_discovery_metadata(self):
        catalog = skills()
        role_ids = [role["id"] for role in roles()]
        self.assertEqual(len(role_ids), len(set(role_ids)))
        for role in roles():
            with self.subTest(role=role["id"]):
                self.assertLessEqual(set(role["skills"]), set(catalog))
                for field in ("responsibility", "trigger", "excludes", "inputs", "outputs"):
                    self.assertTrue(role[field].strip())
        for name, body in catalog.items():
            with self.subTest(skill=name):
                _, metadata, instructions = body.split("---\n", 2)
                fields = dict(line.split(": ", 1) for line in metadata.strip().splitlines())
                self.assertEqual(fields["name"], name)
                self.assertTrue(fields["description"].strip())
                self.assertTrue(instructions.strip())
                # İki sağlayıcıya ortak skill'lerde sağlayıcıya özel alan sızmasını yakalar.
                self.assertEqual(set(fields), {"name", "description"})
                json.dumps(fields, ensure_ascii=False)
