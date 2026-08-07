"""Integridad de catalog/ respecto al Combined y project.json."""
from __future__ import annotations

import json
import unittest
from typing import Any, ClassVar

from catalog_lib import (
    ALL_KINGDOMS_REFERENCE_PATH,
    CATALOG_DIR,
    DEFAULT_GOALS_REFERENCE_PATH,
    JSON_PATH,
    LONG_GOALS_REFERENCE_PATH,
    SHORT_GOALS_REFERENCE_PATH,
    collect_availability_violations,
    load_project,
)


class CatalogFilesExistTests(unittest.TestCase):
    def test_core_catalog_files(self) -> None:
        required = [
            "project.json",
            "bingo_groups.json",
            "bingo_lineas.json",
            "goal_icons.json",
            "goal_tooltips.json",
            "goal_lists.json",
            "goals_referencia.json",
            "lunas-objetivos.json",
            "tags_inventario.json",
            "capturas_lunas.json",
            "regionales_zonas.json",
        ]
        for name in required:
            with self.subTest(name=name):
                path = CATALOG_DIR / name
                self.assertTrue(path.is_file(), f"Falta {path}")
                json.loads(path.read_text(encoding="utf-8"))

    def test_lockout_reference_boards(self) -> None:
        for path in (
            JSON_PATH,
            SHORT_GOALS_REFERENCE_PATH,
            DEFAULT_GOALS_REFERENCE_PATH,
            LONG_GOALS_REFERENCE_PATH,
            ALL_KINGDOMS_REFERENCE_PATH,
        ):
            with self.subTest(name=path.name):
                self.assertTrue(path.is_file())
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("objectives", data)


class GoalsReferenciaSyncTests(unittest.TestCase):
    combined: ClassVar[dict[str, Any]]
    ref: ClassVar[dict[str, Any]]
    combined_goals: ClassVar[set[str]]
    ref_goals: ClassVar[set[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.combined = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        cls.ref = json.loads(
            (CATALOG_DIR / "goals_referencia.json").read_text(encoding="utf-8")
        )
        cls.combined_goals = {o["goal"] for o in cls.combined["objectives"]}
        cls.ref_goals = {g["goal"] for g in cls.ref["goals"]}

    def test_counts_match(self) -> None:
        self.assertEqual(self.ref["n_goals"], len(self.ref["goals"]))
        self.assertEqual(len(self.combined_goals), self.ref["n_goals"])

    def test_same_goal_set(self) -> None:
        self.assertEqual(self.combined_goals, self.ref_goals)


class BingoGroupsSyncTests(unittest.TestCase):
    def test_group_count(self) -> None:
        data = json.loads((CATALOG_DIR / "bingo_groups.json").read_text(encoding="utf-8"))
        self.assertEqual(data["n_groups"], len(data["groups"]))
        self.assertGreater(data["n_groups"], 0)


class ProjectAndLunasTests(unittest.TestCase):
    def test_project_in_scope_count(self) -> None:
        project = load_project()
        self.assertEqual(project["n_in_scope_moons"], project["meta"]["in_scope_moon_count"])
        # 433 en lunas-objetivos + mushroom#39 in-scope fuera del catálogo de lunas
        self.assertEqual(project["n_in_scope_moons"], 434)

    def test_lunas_objetivos_count(self) -> None:
        data = json.loads((CATALOG_DIR / "lunas-objetivos.json").read_text(encoding="utf-8"))
        self.assertEqual(data["n_moons"], len(data["moons"]))
        self.assertEqual(data["n_moons"], 433)

    def test_no_availability_violations(self) -> None:
        self.assertEqual(collect_availability_violations(), [])


class GoalListsTests(unittest.TestCase):
    def test_lists_counts(self) -> None:
        data = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        lists = data["lists"]
        self.assertEqual(data["n_lists"], len(lists))
        item_total = sum(len(v) for v in lists.values())
        self.assertEqual(data["n_items"], item_total)


if __name__ == "__main__":
    unittest.main()
