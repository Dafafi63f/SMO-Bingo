"""Integridad del Combined (fuente de verdad)."""
from __future__ import annotations

import json
import unittest
from typing import Any, ClassVar

from catalog_lib import JSON_PATH, ZONE_ORDER, load_active_combined_objectives


REQUIRED_FIELDS = (
    "goal",
    "progression",
    "orden",
    "board_categories",
    "line_categories",
    "icons",
)


class CombinedIntegrityTests(unittest.TestCase):
    data: ClassVar[dict[str, Any]]
    objectives: ClassVar[list[dict[str, Any]]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        cls.objectives = cls.data["objectives"]

    def test_combined_file_exists(self) -> None:
        self.assertTrue(JSON_PATH.is_file(), f"Falta {JSON_PATH.name}")

    def test_has_objectives(self) -> None:
        self.assertGreaterEqual(len(self.objectives), 1)

    def test_goals_unique(self) -> None:
        goals = [o["goal"] for o in self.objectives]
        self.assertEqual(len(goals), len(set(goals)))

    def test_required_fields(self) -> None:
        for obj in self.objectives:
            with self.subTest(goal=obj.get("goal")):
                for field in REQUIRED_FIELDS:
                    self.assertIn(field, obj)
                self.assertIsInstance(obj["goal"], str)
                self.assertTrue(obj["goal"].strip())

    def test_range_when_present_is_ascending_ints(self) -> None:
        """Goals binarias (Moon Rock, Talkatoo, …) no llevan range."""
        for obj in self.objectives:
            if "range" not in obj:
                continue
            with self.subTest(goal=obj["goal"]):
                values = obj["range"]
                self.assertIsInstance(values, list)
                self.assertGreaterEqual(len(values), 1)
                self.assertTrue(all(isinstance(v, int) for v in values))
                self.assertEqual(values, sorted(values))

    def test_progression_zones_valid(self) -> None:
        allowed = set(ZONE_ORDER)
        for obj in self.objectives:
            with self.subTest(goal=obj["goal"]):
                prog = obj["progression"]
                self.assertIsInstance(prog, list)
                self.assertGreaterEqual(len(prog), 1)
                self.assertTrue(set(prog) <= allowed)
                # Sin duplicados y en orden de zona
                self.assertEqual(prog, [z for z in ZONE_ORDER if z in prog])

    def test_orden_is_permutation_1_to_n(self) -> None:
        n = len(self.objectives)
        ordens = [o["orden"] for o in self.objectives]
        self.assertEqual(sorted(ordens), list(range(1, n + 1)))

    def test_active_loader_matches_file(self) -> None:
        active = load_active_combined_objectives()
        self.assertEqual(len(active), len(self.objectives))
        self.assertEqual(
            {o["goal"] for o in active},
            {o["goal"] for o in self.objectives},
        )


if __name__ == "__main__":
    unittest.main()
