"""Export individuales: progressive_ranges lockout + catálogo."""
from __future__ import annotations

import json
import unittest
from typing import Any, ClassVar

from apply_progression_accessibility import (
    KINGDOM_BORDER_PROGRESSION,
    limiting_availability_for_threshold,
    progression_from_kingdom_availability,
)
from catalog_lib import CATALOG_DIR, ZONE_ORDER
from export_goals_individuales import (
    CURATED_ONLY_TEMPLATES,
    PROGRESSION_OVERRIDES,
    ZONE_GROUP_ID_SET,
    expand_goal,
    flatten_goals,
    group_id_for,
    is_kingdomless_group,
    progressions_for_entries,
    refine_multi_kingdom_progression,
    resolve_blank_progression,
    seal_full_pool_last_kingdom,
)


class ProgressionsForEntriesTests(unittest.TestCase):
    """Solape de intervalos lockout.live (GameEditor preview)."""

    def test_single_zone_broadcast(self) -> None:
        self.assertEqual(
            progressions_for_entries([4, 6, 8], ["e"]),
            [["e"], ["e"], ["e"]],
        )

    def test_equal_lengths_one_to_one(self) -> None:
        self.assertEqual(
            progressions_for_entries([1, 2, 3, 4], ["e", "m", "l", "n"]),
            [["e"], ["m"], ["l"], ["n"]],
        )

    def test_three_by_two_middle_overlap_both_zones(self) -> None:
        # Deep Woods style: e={0,1}, m={1,2} → medio en ambas
        self.assertEqual(
            progressions_for_entries([4, 6, 8], ["e", "m"]),
            [["e"], ["e", "m"], ["m"]],
        )

    def test_four_by_two_halves_no_blank(self) -> None:
        self.assertEqual(
            progressions_for_entries([12, 14, 16, 18], ["e", "m"]),
            [["e"], ["e"], ["m"], ["m"]],
        )

    def test_six_by_two_halves_no_blank(self) -> None:
        self.assertEqual(
            progressions_for_entries([1, 2, 3, 4, 5, 6], ["m", "l"]),
            [["m"], ["m"], ["m"], ["l"], ["l"], ["l"]],
        )

    def test_five_by_two_center_overlap(self) -> None:
        self.assertEqual(
            progressions_for_entries([1, 2, 3, 4, 5], ["l", "n"]),
            [["l"], ["l"], ["l", "n"], ["n"], ["n"]],
        )

    def test_empty_progression_all_blank(self) -> None:
        self.assertEqual(progressions_for_entries([1, 2], []), [[], []])

    def test_no_range_single_slot(self) -> None:
        self.assertEqual(progressions_for_entries(None, ["n"]), [["n"]])


class GroupIdTests(unittest.TestCase):
    def test_kingdom_with_progression(self) -> None:
        self.assertEqual(group_id_for("cap", "e"), "cap")

    def test_blanks(self) -> None:
        self.assertEqual(group_id_for("", "e"), "blank_reino")
        self.assertEqual(group_id_for("", "m"), "blank_reino")
        self.assertEqual(group_id_for("sand", ""), "blank_progresion")
        self.assertEqual(group_id_for("", ""), "blank_reino")
        self.assertEqual(group_id_for("", ["m", "l"]), "blank_reino")
        self.assertTrue(is_kingdomless_group("early"))
        self.assertTrue(is_kingdomless_group("blank_reino"))
        self.assertFalse(is_kingdomless_group("sand"))
        self.assertEqual(ZONE_GROUP_ID_SET, {"early", "mid", "late", "endgame"})


class SealFullPoolLastKingdomTests(unittest.TestCase):
    def test_special_seed_style_last_only(self) -> None:
        items = [
            {"kingdom": "lake"},
            {"kingdom": "wooded"},
            {"kingdom": "seaside"},
        ]
        self.assertEqual(
            seal_full_pool_last_kingdom(["", "", ""], [1, 2, 3], items),
            ["", "", "seaside"],
        )

    def test_no_seal_when_max_below_pool(self) -> None:
        items = [{"kingdom": "cap"}, {"kingdom": "metro"}, {"kingdom": "bowser"}]
        self.assertEqual(
            seal_full_pool_last_kingdom(["", ""], [2, 4], items),
            ["", ""],
        )

    def test_does_not_overwrite_existing_last(self) -> None:
        items = [{"kingdom": "wooded"}, {"kingdom": "luncheon"}]
        self.assertEqual(
            seal_full_pool_last_kingdom(
                ["wooded", "luncheon"], [1, 2], items
            ),
            ["wooded", "luncheon"],
        )


class RefineMultiKingdomProgressionTests(unittest.TestCase):
    def test_border_by_availability(self) -> None:
        self.assertEqual(
            progression_from_kingdom_availability("luncheon", "base"), "l"
        )
        self.assertEqual(
            progression_from_kingdom_availability("luncheon", "mid_story"), "n"
        )
        self.assertEqual(
            progression_from_kingdom_availability("wooded", "base"), "e"
        )
        self.assertEqual(
            progression_from_kingdom_availability("lost", "world_peace"), "m"
        )

    def test_fire_bro_style_refine(self) -> None:
        items = [
            {"kingdom": "wooded", "disponibilidad": "base"},
            {"kingdom": "luncheon", "disponibilidad": "base"},
        ]
        self.assertEqual(
            refine_multi_kingdom_progression(
                kingdom="luncheon",
                prog="n",
                template="{{X}} Fire Bro Moon[[s]]",
                goal_text="2 Fire Bro Moons",
                threshold=2,
                items=items,
                multi_kingdom=True,
                weighted=False,
            ),
            "l",
        )

    def test_npc_lake_uses_limiting_moon(self) -> None:
        """2 NPC Lake: easiest 2 include world_peace → m."""
        items = [
            {"kingdom": "lake", "disponibilidad": "world_peace"},
            {"kingdom": "lake", "disponibilidad": "base"},
            {"kingdom": "metro", "disponibilidad": "mid_story"},
            {"kingdom": "snow", "disponibilidad": "world_peace"},
        ]
        self.assertEqual(
            limiting_availability_for_threshold(
                items, 2, "lake", multi_kingdom=True
            ),
            "world_peace",
        )
        # Mono: también wp (las 2 del reino).
        self.assertEqual(
            limiting_availability_for_threshold(
                items, 2, "lake", multi_kingdom=False
            ),
            "world_peace",
        )
        self.assertEqual(
            refine_multi_kingdom_progression(
                kingdom="lake",
                prog="e",
                template="{{X}} NPC Moons",
                goal_text="2 NPC Moons",
                threshold=2,
                items=items,
                multi_kingdom=True,
                weighted=False,
            ),
            "m",
        )

    def test_mono_kingdom_uses_easiest_n(self) -> None:
        """Mono: umbral alcanzable solo con base → 1ª zona (ignora orden JSON)."""
        items = (
            [{"kingdom": "lake", "disponibilidad": "world_peace"}] * 3
            + [{"kingdom": "lake", "disponibilidad": "base"}] * 20
        )
        self.assertEqual(
            refine_multi_kingdom_progression(
                kingdom="lake",
                prog="m",
                template="{{X}} Lake Moons",
                goal_text="12 Lake Moons",
                threshold=12,
                items=items,
                multi_kingdom=False,
                weighted=False,
            ),
            "e",
        )

    def test_mono_kingdom_keeps_lockout(self) -> None:
        items = [{"kingdom": "luncheon", "disponibilidad": "base"}] * 24
        self.assertEqual(
            refine_multi_kingdom_progression(
                kingdom="luncheon",
                prog="n",
                template="{{X}} Luncheon Moons",
                goal_text="22 Luncheon Moons",
                threshold=22,
                items=items,
                multi_kingdom=False,
                weighted=False,
            ),
            "l",
        )


class ResolveBlankProgressionTests(unittest.TestCase):
    def test_overlap_empty_fills_first_border_zone(self) -> None:
        # El expand a varias zonas ocurre antes; aquí solo relleno de fija/vacío.
        self.assertEqual(
            resolve_blank_progression(
                "wooded",
                "",
                goal_text="6 Deep Woods Moons",
                template_prog=["e", "m"],
                n_range=3,
                template_has_mapped_prog=True,
            ),
            ("wooded", "e"),
        )

    def test_fixed_fill_first(self) -> None:
        self.assertEqual(
            resolve_blank_progression(
                "sand",
                "",
                goal_text="Sand Shop Moon",
                template_prog=["e", "m"],
                n_range=0,
                template_has_mapped_prog=False,
            ),
            ("sand", "e"),
        )

    def test_fixed_delayed_last(self) -> None:
        self.assertEqual(
            resolve_blank_progression(
                "sand",
                "",
                goal_text="Sand Warp-Painting Moon",
                template_prog=["m", "l"],
                n_range=0,
                template_has_mapped_prog=False,
            ),
            ("sand", "m"),
        )

    def test_sphynx_not_delayed_first_zone(self) -> None:
        self.assertEqual(
            resolve_blank_progression(
                "wooded",
                "",
                goal_text="Correct Wooded Sphynx Question",
                template_prog=["m", "l"],
                n_range=0,
                template_has_mapped_prog=False,
            ),
            ("wooded", "m"),
        )

    def test_moon_rock_like_talkatoo_first_zone(self) -> None:
        """Moon Rock = llegar; misma zona temprana que Talkatoo."""
        self.assertEqual(
            resolve_blank_progression(
                "lake",
                "",
                goal_text="Lake Moon Rock",
                template_prog=["e", "m"],
                n_range=0,
                template_has_mapped_prog=False,
            ),
            ("lake", "e"),
        )

    def test_warp_intersection(self) -> None:
        self.assertEqual(
            resolve_blank_progression(
                "sand",
                "",
                goal_text="Sand Warp-Painting Moon",
                template_prog=["m", "l"],
                n_range=0,
                template_has_mapped_prog=False,
            ),
            ("sand", "m"),
        )

    def test_no_intersection_blank_ambos(self) -> None:
        self.assertEqual(
            resolve_blank_progression(
                "cap",
                "",
                goal_text="Cap Something",
                template_prog=["l", "n"],
                n_range=0,
                template_has_mapped_prog=False,
            ),
            ("", ""),
        )


class GoalsIndividualesCatalogTests(unittest.TestCase):
    data: ClassVar[dict[str, Any]]
    groups: ClassVar[list[dict[str, Any]]]
    goals: ClassVar[list[dict[str, Any]]]

    @classmethod
    def setUpClass(cls) -> None:
        path = CATALOG_DIR / "goals_individuales.json"
        cls.data = json.loads(path.read_text(encoding="utf-8"))
        cls.groups = cls.data["groups"]
        cls.goals = flatten_goals(cls.groups)

    def test_file_counts(self) -> None:
        primary = [gr for gr in self.groups if gr["id"] not in ZONE_GROUP_ID_SET]
        self.assertEqual(self.data["n_goals"], len(self.goals))
        self.assertEqual(self.data["n_groups"], len(self.groups))
        self.assertEqual(
            self.data["n_goals"],
            sum(int(gr["n_goals"]) for gr in primary),
        )
        self.assertGreater(self.data["n_goals"], 0)
        # Sin contadores derivados en cabecera (salen de groups[]).
        for key in (
            "n_blank_ambos",
            "n_blank_reino",
            "n_blank_progresion",
            "n_blank_kingdom",
            "n_blank_progression",
            "n_with_kingdom",
            "n_with_progression",
        ):
            self.assertNotIn(key, self.data)

    def test_blank_reino_not_in_kingdom_groups(self) -> None:
        blank_reino = next(g for g in self.groups if g["id"] == "blank_reino")
        blank_names = {r["goal"] for r in blank_reino["goals"]}
        for gr in self.groups:
            if is_kingdomless_group(gr["id"]):
                continue
            overlap = blank_names & {r["goal"] for r in gr["goals"]}
            self.assertFalse(overlap, f"{gr['id']}: {sorted(overlap)}")

    def test_zone_groups_present(self) -> None:
        ids = {gr["id"] for gr in self.groups}
        for zid in ("early", "mid", "late", "endgame"):
            self.assertIn(zid, ids)
            gr = next(g for g in self.groups if g["id"] == zid)
            letter = {"early": "e", "mid": "m", "late": "l", "endgame": "n"}[zid]
            has_kingdom = False
            has_blank = False
            for row in gr["goals"]:
                self.assertIn("kingdom", row)
                prog = row["progression"]
                letters = (
                    list(prog)
                    if isinstance(prog, list)
                    else ([prog] if prog else [])
                )
                self.assertIn(letter, letters)
                if row["kingdom"]:
                    has_kingdom = True
                else:
                    has_blank = True
            self.assertTrue(has_kingdom, f"{zid}: faltan goals de reino")
            self.assertTrue(has_blank, f"{zid}: faltan goals blank/globales")

    def test_blank_reino_keeps_globals(self) -> None:
        blank = next(g for g in self.groups if g["id"] == "blank_reino")
        names = {r["goal"] for r in blank["goals"]}
        self.assertIn("3 8-Bit Moons", names)
        self.assertIn("3 Total Multi-Moons", names)
        self.assertIn("3 Broodal Fights", names)

    def test_groups_alpha_and_counts(self) -> None:
        ids = [gr["id"] for gr in self.groups]
        self.assertEqual(ids, sorted(ids))
        ordens = [gr["orden"] for gr in self.groups]
        self.assertEqual(ordens, list(range(1, len(self.groups) + 1)))
        for gr in self.groups:
            with self.subTest(id=gr["id"]):
                self.assertEqual(gr["n_goals"], len(gr["goals"]))
                self.assertGreater(gr["n_goals"], 0)

    def test_compact_goal_fields_by_group(self) -> None:
        for gr in self.groups:
            gid = gr["id"]
            for row in gr["goals"]:
                with self.subTest(group=gid, goal=row.get("goal")):
                    self.assertIn("goal", row)
                    self.assertNotIn("orden", row)
                    self.assertIn("lockout", row)
                    lockout = row["lockout"]
                    if isinstance(lockout, list):
                        self.assertGreaterEqual(len(lockout), 2)
                        for z in lockout:
                            self.assertIn(z, ZONE_ORDER)
                    else:
                        self.assertIsInstance(lockout, str)
                    if is_kingdomless_group(gid):
                        self.assertIn("kingdom", row)
                        self.assertIn("progression", row)
                        self.assertIsInstance(row["kingdom"], str)
                        prog = row["progression"]
                        if gid == "blank_reino":
                            self.assertEqual(row["kingdom"], "")
                            if isinstance(prog, list):
                                self.assertGreaterEqual(len(prog), 2)
                                for z in prog:
                                    self.assertIn(z, ZONE_ORDER)
                            else:
                                self.assertIsInstance(prog, str)
                                # Puede ser "" (antes blank_ambos).
                        elif gid == "blank_progresion":
                            self.assertTrue(row["kingdom"])
                            self.assertEqual(prog, "")
                        elif gid in ZONE_GROUP_ID_SET:
                            letter = {
                                "early": "e",
                                "mid": "m",
                                "late": "l",
                                "endgame": "n",
                            }[gid]
                            letters = (
                                list(prog)
                                if isinstance(prog, list)
                                else ([prog] if prog else [])
                            )
                            self.assertIn(letter, letters)
                        else:
                            self.fail(f"grupo blank/zona inesperado: {gid}")
                    else:
                        self.assertNotIn("kingdom", row)
                        self.assertIn("progression", row)
                        prog = row["progression"]
                        if isinstance(prog, list):
                            self.assertGreaterEqual(len(prog), 2)
                            for z in prog:
                                self.assertIn(z, ZONE_ORDER)
                        else:
                            self.assertTrue(prog)

    def test_required_fields_and_orden(self) -> None:
        n = len(self.goals)
        ordens = []
        for row in self.goals:
            with self.subTest(orden=row.get("orden"), goal=row.get("goal")):
                for field in (
                    "orden",
                    "goal",
                    "kingdom",
                    "progression",
                    "lockout",
                ):
                    self.assertIn(field, row)
                self.assertIsInstance(row["goal"], str)
                self.assertTrue(row["goal"].strip())
                self.assertIsInstance(row["kingdom"], str)
                prog = row["progression"]
                if isinstance(prog, list):
                    self.assertGreaterEqual(len(prog), 2)
                    for z in prog:
                        self.assertIn(z, ZONE_ORDER)
                else:
                    self.assertIsInstance(prog, str)
                    if prog:
                        self.assertIn(prog, ZONE_ORDER)
                lockout = row["lockout"]
                if isinstance(lockout, list):
                    self.assertGreaterEqual(len(lockout), 2)
                    for z in lockout:
                        self.assertIn(z, ZONE_ORDER)
                else:
                    self.assertIsInstance(lockout, str)
                    if lockout:
                        self.assertIn(lockout, ZONE_ORDER)
                ordens.append(row["orden"])
        # orden solo en flatten de tests; en JSON el orden es posición en goals[].
        self.assertEqual(sorted(ordens), list(range(1, n + 1)))

    def test_deep_woods_and_lake_moons_mapping(self) -> None:
        by_goal = {row["goal"]: row for row in self.goals}
        # Deep Woods: todo base → e (sin overlap de progressive_ranges).
        self.assertEqual(by_goal["4 Deep Woods Moons"]["progression"], "e")
        self.assertEqual(by_goal["6 Deep Woods Moons"]["kingdom"], "wooded")
        self.assertEqual(by_goal["6 Deep Woods Moons"]["progression"], "e")
        self.assertEqual(by_goal["8 Deep Woods Moons"]["progression"], "e")
        # Lake: base_n≥18 → todos Early.
        self.assertEqual(by_goal["12 Lake Moons"]["progression"], "e")
        self.assertEqual(by_goal["14 Lake Moons"]["progression"], "e")
        self.assertEqual(by_goal["16 Lake Moons"]["progression"], "e")
        self.assertEqual(by_goal["18 Lake Moons"]["progression"], "e")

    def test_total_multi_moons_four_zone_mapping(self) -> None:
        """3×4 dejaba todo blank; range [3,6,9,12] → e/m/l/n limpio."""
        by_goal = {row["goal"]: row for row in self.goals}
        self.assertEqual(by_goal["3 Total Multi-Moons"]["progression"], "e")
        self.assertEqual(by_goal["6 Total Multi-Moons"]["progression"], "m")
        self.assertEqual(by_goal["9 Total Multi-Moons"]["progression"], "l")
        self.assertEqual(by_goal["12 Total Multi-Moons"]["progression"], "n")
        for g in (
            "3 Total Multi-Moons",
            "6 Total Multi-Moons",
            "9 Total Multi-Moons",
            "12 Total Multi-Moons",
        ):
            self.assertEqual(by_goal[g]["kingdom"], "")

    def test_blank_progresion_policy_samples(self) -> None:
        by_goal = {row["goal"]: row for row in self.goals}
        # Deep Woods: avail base → e (ya no overlap 3×2).
        woods6 = next(
            r for r in self.goals if r["goal"] == "6 Deep Woods Moons"
        )
        self.assertEqual(woods6["kingdom"], "wooded")
        self.assertEqual(woods6["progression"], "e")
        # Dorrie: lake/e; seaside base/l; seaside+wp/n.
        self.assertEqual(by_goal["1 Dorrie Moon"]["kingdom"], "lake")
        self.assertEqual(by_goal["1 Dorrie Moon"]["progression"], "e")
        dorrie2 = [
            r for r in self.goals if r["goal"] == "2 Dorrie Moons"
        ]
        self.assertEqual(len(dorrie2), 1)
        self.assertEqual(dorrie2[0]["kingdom"], "seaside")
        self.assertEqual(dorrie2[0]["progression"], "l")
        self.assertEqual(by_goal["3 Dorrie Moons"]["kingdom"], "seaside")
        self.assertEqual(by_goal["3 Dorrie Moons"]["progression"], "n")
        # Luncheon Turnip: todo alcanzable en base → l.
        turnip2 = next(
            r
            for r in self.goals
            if r["goal"] == "2 Luncheon Golden Turnip Moons"
        )
        self.assertEqual(turnip2["kingdom"], "luncheon")
        self.assertEqual(turnip2["progression"], "l")
        # Shiny Rock: cascade/e, wooded base/e, moon/n.
        shiny = {
            r["goal"]: r
            for r in self.goals
            if r["goal"]
            in {
                "1 Shiny Rock Moon",
                "2 Shiny Rock Moons",
                "3 Shiny Rock Moons",
                "4 Shiny Rock Moons",
            }
        }
        self.assertEqual(shiny["1 Shiny Rock Moon"]["kingdom"], "cascade")
        self.assertEqual(shiny["1 Shiny Rock Moon"]["progression"], "e")
        self.assertEqual(shiny["2 Shiny Rock Moons"]["kingdom"], "wooded")
        self.assertEqual(shiny["2 Shiny Rock Moons"]["progression"], "e")
        self.assertEqual(shiny["3 Shiny Rock Moons"]["kingdom"], "wooded")
        self.assertEqual(shiny["3 Shiny Rock Moons"]["progression"], "e")
        self.assertEqual(shiny["4 Shiny Rock Moons"]["kingdom"], "moon")
        self.assertEqual(shiny["4 Shiny Rock Moons"]["progression"], "n")
        # Paraguas Fauna/Flora/Nature: sin reino → grupos de zona.
        self.assertEqual(by_goal["3 Fauna Moons"]["kingdom"], "")
        self.assertEqual(by_goal["2 Flora Moons"]["kingdom"], "")
        self.assertEqual(by_goal["5 Nature Moons"]["kingdom"], "")
        # Sin reino + progression vacía → blank_reino (lockout puede tener zonas).
        broodal3 = [r for r in self.goals if r["goal"] == "3 Broodal Fights"]
        self.assertEqual(len(broodal3), 1)
        self.assertEqual(broodal3[0]["kingdom"], "")
        self.assertEqual(broodal3[0]["progression"], "")
        self.assertEqual(broodal3[0]["lockout"], ["e", "m"])
        self.assertNotIn(
            "blank_ambos", {gr["id"] for gr in self.groups}
        )
        # Special Seed: 1/2 zona mid; 3 (=pool) → seaside/l.
        seeds = {
            r["goal"]: r
            for r in self.goals
            if r["goal"]
            in {
                "1 Special Seed Moon",
                "2 Special Seed Moons",
                "3 Special Seed Moons",
            }
        }
        self.assertEqual(seeds["1 Special Seed Moon"]["kingdom"], "")
        self.assertEqual(seeds["1 Special Seed Moon"]["progression"], "m")
        self.assertEqual(seeds["2 Special Seed Moons"]["kingdom"], "")
        self.assertEqual(seeds["2 Special Seed Moons"]["progression"], "m")
        self.assertEqual(seeds["3 Special Seed Moons"]["kingdom"], "seaside")
        self.assertEqual(seeds["3 Special Seed Moons"]["progression"], "l")
        # Rocket Flower: 2/4 blank zona; 6 (=pool) → moon/n.
        rockets = {
            r["goal"]: r
            for r in self.goals
            if r["goal"]
            in {
                "2 Rocket Flower Moons",
                "4 Rocket Flower Moons",
                "6 Rocket Flower Moons",
            }
        }
        self.assertEqual(rockets["2 Rocket Flower Moons"]["kingdom"], "")
        self.assertEqual(rockets["2 Rocket Flower Moons"]["progression"], "l")
        self.assertEqual(rockets["4 Rocket Flower Moons"]["kingdom"], "")
        self.assertEqual(rockets["4 Rocket Flower Moons"]["progression"], "n")
        self.assertEqual(rockets["6 Rocket Flower Moons"]["kingdom"], "moon")
        self.assertEqual(rockets["6 Rocket Flower Moons"]["progression"], "n")
        # blank_reino no se duplica en grupos de reino (Outfit Door).
        outfit2 = [
            r for r in self.goals if r["goal"] == "2 Outfit Door Moons"
        ]
        self.assertEqual(len(outfit2), 1)
        self.assertEqual(outfit2[0]["kingdom"], "")
        self.assertEqual(outfit2[0]["progression"], "e")
        # Global Ground Pound (pool multi-reino) → blank_reino, no sand/wooded/…
        gp7 = [r for r in self.goals if r["goal"] == "7 Ground Pound Moons"]
        self.assertEqual(len(gp7), 1)
        self.assertEqual(gp7[0]["kingdom"], "")
        self.assertEqual(gp7[0]["progression"], "m")
        self.assertEqual(by_goal["2 Sand Ground Pound Moons"]["kingdom"], "sand")
        # Lake base → Early (no Mid del techo).
        self.assertEqual(by_goal["2 Ledge Grab Moons"]["kingdom"], "lake")
        self.assertEqual(by_goal["2 Ledge Grab Moons"]["progression"], "e")
        self.assertEqual(by_goal["2 Wooden Crate Moons"]["kingdom"], "lake")
        self.assertEqual(by_goal["2 Wooden Crate Moons"]["progression"], "e")
        # Multi-reino: avail→borde.
        self.assertEqual(by_goal["1 Fire Bro Moon"]["kingdom"], "wooded")
        self.assertEqual(by_goal["1 Fire Bro Moon"]["progression"], "e")
        self.assertEqual(by_goal["2 Fire Bro Moons"]["kingdom"], "luncheon")
        self.assertEqual(by_goal["2 Fire Bro Moons"]["progression"], "l")
        self.assertEqual(by_goal["3 Cactus/Tree Moons"]["kingdom"], "wooded")
        self.assertEqual(by_goal["3 Cactus/Tree Moons"]["progression"], "e")
        # Cheep: catálogo m/l/l; página Lockout 3×2 → m / [m,l] / l.
        self.assertEqual(by_goal["2 Cheep Cheep Moons"]["kingdom"], "lake")
        self.assertEqual(by_goal["2 Cheep Cheep Moons"]["progression"], "m")
        self.assertEqual(by_goal["2 Cheep Cheep Moons"]["lockout"], "m")
        self.assertEqual(by_goal["4 Cheep Cheep Moons"]["kingdom"], "seaside")
        self.assertEqual(by_goal["4 Cheep Cheep Moons"]["progression"], "l")
        self.assertEqual(
            by_goal["4 Cheep Cheep Moons"]["lockout"], ["m", "l"]
        )
        self.assertEqual(by_goal["6 Cheep Cheep Moons"]["kingdom"], "seaside")
        self.assertEqual(by_goal["6 Cheep Cheep Moons"]["progression"], "l")
        self.assertEqual(by_goal["6 Cheep Cheep Moons"]["lockout"], "l")
        # Lake Moons: Combined solo e → página = catálogo.
        self.assertEqual(by_goal["12 Lake Moons"]["progression"], "e")
        self.assertEqual(by_goal["12 Lake Moons"]["lockout"], "e")
        self.assertEqual(by_goal["18 Lake Moons"]["lockout"], "e")
        # 2 NPC Lake: 1ª base (e) + 2ª wp (m) → limitante m.
        self.assertEqual(by_goal["2 NPC Moons"]["kingdom"], "lake")
        self.assertEqual(by_goal["2 NPC Moons"]["progression"], "m")
        # Lost = solo Mid; Metro día = solo Late (sin puente m,l).
        self.assertEqual(by_goal["3 Lost Butterfly Moons"]["progression"], "m")
        self.assertEqual(by_goal["12 Lost Moons"]["progression"], "m")
        self.assertEqual(by_goal["14 Lost Moons"]["progression"], "m")
        self.assertEqual(by_goal["16 Lost Moons"]["progression"], "m")
        self.assertEqual(by_goal["18 Lost Moons"]["progression"], "m")
        self.assertEqual(by_goal["2 Lost Checkpoints"]["progression"], "m")
        self.assertEqual(by_goal["3 Lost Checkpoints"]["progression"], "m")
        self.assertEqual(by_goal["2 Lost Trapeetle Moons"]["progression"], "m")
        self.assertEqual(by_goal["5 Lost Tropical Wiggler Moons"]["progression"], "m")
        # Mono 2 zonas: base fija → 1ª; mid/wp fija → 2ª.
        self.assertEqual(by_goal["Sand Shop Moon"]["progression"], "e")
        self.assertEqual(by_goal["Wooded Captain Toad Moon"]["progression"], "m")
        self.assertEqual(by_goal["Sand Captain Toad Moon"]["progression"], "m")
        self.assertEqual(by_goal["Snow Shop Moon"]["progression"], "l")
        self.assertEqual(by_goal["1 Metro Multi-Moon"]["kingdom"], "lost")
        self.assertEqual(by_goal["1 Metro Multi-Moon"]["progression"], "m")
        self.assertEqual(by_goal["2 Metro Multi-Moons"]["kingdom"], "metro")
        self.assertEqual(by_goal["2 Metro Multi-Moons"]["progression"], "l")
        # Metro noche (lost): todo Mid; pintura #51 en pool Night.
        self.assertEqual(by_goal["2 Metro Night Moons"]["kingdom"], "lost")
        self.assertEqual(by_goal["2 Metro Night Moons"]["progression"], "m")
        self.assertEqual(by_goal["4 Metro Night Moons"]["kingdom"], "lost")
        self.assertEqual(by_goal["4 Metro Night Moons"]["progression"], "m")
        self.assertEqual(by_goal["6 Metro Night Moons"]["kingdom"], "lost")
        self.assertEqual(by_goal["6 Metro Night Moons"]["progression"], "m")
        self.assertEqual(by_goal["1 Metro Girder Moon"]["kingdom"], "lost")
        self.assertEqual(by_goal["1 Metro Girder Moon"]["progression"], "m")
        self.assertEqual(by_goal["2 Metro Girder Moons"]["progression"], "m")
        self.assertEqual(by_goal["3 Metro Girder Moons"]["progression"], "m")
        self.assertEqual(by_goal["Metro Shop Moon"]["kingdom"], "lost")
        self.assertEqual(by_goal["Metro Shop Moon"]["progression"], "m")
        self.assertEqual(by_goal["Metro City Hall Moon"]["kingdom"], "lost")
        self.assertEqual(by_goal["Metro City Hall Moon"]["progression"], "m")
        self.assertEqual(by_goal["Metro Moon Rock"]["kingdom"], "lost")
        self.assertEqual(by_goal["Metro Moon Rock"]["progression"], "m")
        # Metro Checkpoints: 3/5 night → lost/m; 7/9 día → metro/l.
        self.assertEqual(by_goal["3 Metro Checkpoints"]["kingdom"], "lost")
        self.assertEqual(by_goal["3 Metro Checkpoints"]["progression"], "m")
        self.assertEqual(by_goal["5 Metro Checkpoints"]["kingdom"], "lost")
        self.assertEqual(by_goal["5 Metro Checkpoints"]["progression"], "m")
        self.assertEqual(by_goal["7 Metro Checkpoints"]["kingdom"], "metro")
        self.assertEqual(by_goal["7 Metro Checkpoints"]["progression"], "l")
        self.assertEqual(by_goal["9 Metro Checkpoints"]["kingdom"], "metro")
        self.assertEqual(by_goal["9 Metro Checkpoints"]["progression"], "l")
        # Misma luna #51 Night → lost/m (no sand de entrada).
        self.assertEqual(by_goal["Metro Warp-Painting Moon"]["kingdom"], "lost")
        self.assertEqual(by_goal["Metro Warp-Painting Moon"]["progression"], "m")
        # Pinturas con varias entradas → blank_reino + progression de entrada.
        for g, zones in (
            ("Sand Warp-Painting Moon", ["m", "l"]),
            ("Luncheon Warp-Painting Moon", ["m", "l"]),
            ("Lake Warp-Painting Moon", ["m", "l"]),
            ("Wooded Warp-Painting Moon", ["m", "l"]),
            ("Cascade Warp-Painting Moon", ["l", "n"]),
        ):
            row = by_goal[g]
            self.assertEqual(row["kingdom"], "", g)
            self.assertEqual(row["progression"], zones, g)
        # Mushroom: entrada única Luncheon → luncheon/l (base).
        self.assertEqual(
            by_goal["Mushroom Warp-Painting Moon"]["kingdom"], "luncheon"
        )
        self.assertEqual(by_goal["Mushroom Warp-Painting Moon"]["progression"], "l")
        # Critter: cascade wp→e (solo e); sand wp→m; lost→m.
        self.assertEqual(by_goal["2 Critter Moons"]["kingdom"], "sand")
        self.assertEqual(by_goal["2 Critter Moons"]["progression"], "m")
        self.assertEqual(by_goal["3 Critter Moons"]["progression"], "m")
        # Lurker/Rumble: sand#52 base→e; sand#23 wp→m (tras sync orden).
        self.assertEqual(by_goal["1 Lurker/Rumble Moon"]["kingdom"], "sand")
        self.assertEqual(by_goal["1 Lurker/Rumble Moon"]["progression"], "e")
        self.assertEqual(by_goal["2 Lurker/Rumble Moons"]["kingdom"], "sand")
        self.assertEqual(by_goal["2 Lurker/Rumble Moons"]["progression"], "m")
        # Levers: sand 8-bit/e; sand Moe-Eye wp→m; wooded/e; metro/l.
        self.assertEqual(by_goal["Activate 2 Levers"]["kingdom"], "sand")
        self.assertEqual(by_goal["Activate 2 Levers"]["progression"], "e")
        self.assertEqual(by_goal["Activate 3 Levers"]["kingdom"], "sand")
        self.assertEqual(by_goal["Activate 3 Levers"]["progression"], "m")
        self.assertEqual(by_goal["Activate 4 Levers"]["progression"], "e")
        self.assertEqual(by_goal["Activate 5 Levers"]["progression"], "l")
        # GP Switches: seaside TC1 Late (l), no overlap l,n.
        self.assertEqual(
            by_goal["Activate 3 Ground-Pound Switches"]["progression"], "l"
        )
        self.assertEqual(
            by_goal["Activate 3 Ground-Pound Switches"]["kingdom"], "seaside"
        )
        # Hint Art Seaside/Snow: luna base → l (no n del puente).
        self.assertEqual(by_goal["Seaside Hint Art Moon"]["progression"], "l")
        self.assertEqual(by_goal["Snow Hint Art Moon"]["progression"], "l")
        # Glydon: m / l / n (Combined m,l,n; lost puente a Late).
        self.assertEqual(by_goal["1 Glydon Moon"]["progression"], "m")
        self.assertEqual(by_goal["2 Glydon Moons"]["progression"], "l")
        self.assertEqual(by_goal["3 Glydon Moons"]["progression"], "n")
        # Regionals (lista sin avail): progression = emparejado Combined, no e falso.
        # Sand Ice: Ice Cave 4 → e; 8/11 templo → m.
        self.assertEqual(by_goal["4 Sand Ice Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["8 Sand Ice Regional Coins"]["progression"], "m")
        self.assertEqual(by_goal["11 Sand Ice Regional Coins"]["progression"], "m")
        self.assertEqual(by_goal["4 Sand Jaxi Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["8 Sand Jaxi Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["12 Sand Jaxi Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["5 Sand Ruins Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["10 Sand Ruins Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["15 Sand Ruins Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["45 Sand Regional Coins"]["progression"], "e")
        # Totales de reino: Regional = mismo progression que Moons.
        self.assertEqual(by_goal["30 Lake Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["45 Seaside Regional Coins"]["progression"], "l")
        self.assertEqual(by_goal["30 Luncheon Regional Coins"]["progression"], "l")
        self.assertEqual(by_goal["45 Luncheon Regional Coins"]["progression"], "l")
        self.assertEqual(by_goal["20 Snow Regional Coins"]["progression"], "l")
        self.assertEqual(by_goal["35 Snow Regional Coins"]["progression"], "n")
        self.assertEqual(by_goal["50 Wooded Regional Coins"]["progression"], "e")
        self.assertEqual(by_goal["65 Wooded Regional Coins"]["progression"], "m")
        self.assertEqual(
            by_goal["10 Snow Shiveria Regional Coins"]["progression"], "l"
        )
        self.assertEqual(
            by_goal["30 Snow Shiveria Regional Coins"]["progression"], "l"
        )
        # Fijas rellenadas.
        self.assertEqual(by_goal["Lake Moon Rock"]["progression"], "e")
        self.assertEqual(by_goal["Lake Talkatoo"]["progression"], "e")
        # Destructible: sand/e; wooded mid/wp→m; lost/m.
        self.assertEqual(by_goal["1 Destructible Block Moons"]["progression"], "e")
        self.assertEqual(by_goal["3 Destructible Block Moons"]["progression"], "m")
        self.assertEqual(by_goal["5 Destructible Block Moons"]["progression"], "m")
        # Spark Pylon curado: cap/metro (Bowser fuera; no hace falta la 5ª).
        self.assertEqual(by_goal["2 Spark Pylon Moons"]["kingdom"], "cap")
        self.assertEqual(by_goal["2 Spark Pylon Moons"]["progression"], "e")
        self.assertEqual(by_goal["4 Spark Pylon Moons"]["kingdom"], "metro")
        self.assertEqual(by_goal["4 Spark Pylon Moons"]["progression"], "l")
        # Seed Moon NTT: siempre sand/e.
        self.assertEqual(
            by_goal["1 Seed Moon (No Time Travel)"]["kingdom"], "sand"
        )
        self.assertEqual(
            by_goal["1 Seed Moon (No Time Travel)"]["progression"], "e"
        )
        # Rabbit: max(range) < pool → sin reino (grupo de zona).
        rabbit = {
            r["goal"]: r
            for r in self.goals
            if r["goal"]
            in {
                "1 Rabbit Chase Moon",
                "3 Rabbit Chase Moons",
                "5 Rabbit Chase Moons",
            }
        }
        for g, row in rabbit.items():
            self.assertEqual(row["kingdom"], "", g)
            self.assertTrue(row["progression"], g)

    def test_mono_kingdom_progression_in_border(self) -> None:
        """Si hay reino y progression no blank, debe caber en el puente del reino.

        Excluye templates curados (kingdom/progression override independiente).
        """
        curated_names: set[str] = set()
        for template in CURATED_ONLY_TEMPLATES | frozenset(PROGRESSION_OVERRIDES):
            # Umbrales tipicos 1..40 + el template sin expandir por si acaso.
            curated_names.add(template)
            for n in range(1, 41):
                curated_names.add(expand_goal(template, n))

        for row in self.goals:
            kingdom = row["kingdom"]
            prog = row["progression"]
            if not kingdom or not prog:
                continue
            if row["goal"] in curated_names:
                continue
            border = KINGDOM_BORDER_PROGRESSION.get(kingdom)
            if not border:
                continue
            zones = prog if isinstance(prog, list) else [prog]
            with self.subTest(goal=row["goal"]):
                for z in zones:
                    self.assertIn(z, border)


if __name__ == "__main__":
    unittest.main()
