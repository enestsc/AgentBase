import json
import unittest
from pathlib import Path

from agentbase.config import DEFAULT
from agentbase.tasks import validate_plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ExampleTests(unittest.TestCase):
    def test_example_plan_stays_valid(self):
        # Belgelerdeki örnek şema değişince sessizce eskimesin diye CI'da doğrulanır.
        plan = json.loads((EXAMPLES / "tasks.example.json").read_text(encoding="utf-8"))
        self.assertEqual(len(validate_plan(plan, DEFAULT)["tasks"]), 3)


if __name__ == "__main__":
    unittest.main()
