"""Helpers de progression (apply_progression_accessibility)."""
from __future__ import annotations

import unittest

from apply_progression_accessibility import (
    FORK_LATE_KINGDOMS,
    FORK_MID_KINGDOMS,
    KINGDOM_BORDER_PROGRESSION,
    apply_objective,
    expand_zones_forward,
    goal_availability_rank,
    kingdom_for_weighting,
    kingdom_to_zone,
    mono_kingdom_progression,
    strip_moontype_from_regional_categories,
    unique_ascending,
    unique_progression,
    weighting_for_progression,
    weighting_kingdoms,
    weighting_progression,
)
from catalog_lib import STORY_ORDER, _CLOUD_KINGDOM

# Combos mono-reino: Lost=m y Metro=l (sin puente m,l).
ALLOWED_BORDER_COMBOS = {
    ("e",),
    ("m",),
    ("l",),
    ("e", "m"),
    ("l", "n"),
    ("n",),
}


class UniqueHelpersTests(unittest.TestCase):
    def test_unique_ascending(self) -> None:
        self.assertEqual(unique_ascending([3, 1, 2, 2]), [1, 2, 3])

    def test_unique_progression_orders_zones(self) -> None:
        self.assertEqual(unique_progression(["n", "e", "e", "l"]), ["e", "l", "n"])

    def test_unique_progression_fallback(self) -> None:
        self.assertEqual(unique_progression(["x", "y"]), ["m"])


class KingdomZoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ceilings = {"e": "sand", "m": "wooded", "l": "seaside", "n": "moon"}

    def test_cap_is_early(self) -> None:
        self.assertEqual(kingdom_to_zone("cap", STORY_ORDER, self.ceilings), "e")

    def test_metro_is_late(self) -> None:
        self.assertEqual(kingdom_to_zone("metro", STORY_ORDER, self.ceilings), "l")

    def test_cloud_kingdom_internal_slug_mid(self) -> None:
        self.assertEqual(
            kingdom_to_zone(_CLOUD_KINGDOM, STORY_ORDER, self.ceilings), "m"
        )

    def test_lost_is_mid_with_lost_ceiling(self) -> None:
        ceilings = {"e": "sand", "m": "lost", "l": "seaside", "n": "moon"}
        self.assertEqual(kingdom_to_zone("lost", STORY_ORDER, ceilings), "m")
        self.assertEqual(kingdom_to_zone("wooded", STORY_ORDER, ceilings), "m")
        self.assertEqual(kingdom_to_zone("metro", STORY_ORDER, ceilings), "l")

    def test_lost_is_late_with_wooded_ceiling(self) -> None:
        self.assertEqual(kingdom_to_zone("lost", STORY_ORDER, self.ceilings), "l")


class KingdomBorderProgressionTests(unittest.TestCase):
    def test_only_continuous_bridge_combos(self) -> None:
        for kingdom, prog in KINGDOM_BORDER_PROGRESSION.items():
            with self.subTest(kingdom=kingdom):
                self.assertEqual(tuple(prog), tuple(unique_progression(prog)))
                self.assertIn(tuple(prog), ALLOWED_BORDER_COMBOS)

    def test_bridge_cluster_sizes(self) -> None:
        by_combo: dict[tuple[str, ...], list[str]] = {}
        for kingdom, prog in KINGDOM_BORDER_PROGRESSION.items():
            by_combo.setdefault(tuple(prog), []).append(kingdom)
        self.assertEqual(sorted(by_combo[("e",)]), ["cap", "cascade"])
        self.assertEqual(sorted(by_combo[("e", "m")]), ["lake", "sand", "wooded"])
        self.assertEqual(sorted(by_combo[("m",)]), ["lost"])
        self.assertEqual(sorted(by_combo[("l",)]), ["metro"])
        self.assertEqual(
            sorted(by_combo[("l", "n")]),
            ["luncheon", "mushroom", "seaside", "snow"],
        )
        self.assertEqual(sorted(by_combo[("n",)]), ["bowser", "moon", "ruined"])

    def test_no_lone_invalid_borders(self) -> None:
        """Solo lost=m y metro=l como zona suelta; no otros m/l solos."""
        for kingdom, prog in KINGDOM_BORDER_PROGRESSION.items():
            with self.subTest(kingdom=kingdom):
                if kingdom == "lost":
                    self.assertEqual(prog, ["m"])
                elif kingdom == "metro":
                    self.assertEqual(prog, ["l"])
                else:
                    self.assertNotEqual(prog, ["m"])
                    self.assertNotEqual(prog, ["l"])


class ExpandZonesTests(unittest.TestCase):
    def test_mono_kingdom_uses_border_progression(self) -> None:
        self.assertEqual(expand_zones_forward({"e"}, kingdoms={"sand"}), ["e", "m"])
        self.assertEqual(expand_zones_forward({"l"}, kingdoms={"snow"}), ["l", "n"])
        self.assertEqual(expand_zones_forward({"m"}, kingdoms={"lost"}), ["m"])
        self.assertEqual(expand_zones_forward({"l"}, kingdoms={"metro"}), ["l"])
        self.assertEqual(
            expand_zones_forward({"l"}, kingdoms={"seaside"}), ["l", "n"]
        )


class MonoKingdomProgressionTests(unittest.TestCase):
    def test_single_zone_kingdom(self) -> None:
        self.assertEqual(
            mono_kingdom_progression(
                "cap", goal="Cap Shop Moon", ranges=None, moons=[]
            ),
            ["e"],
        )

    def test_base_fixed_uses_first(self) -> None:
        moons = [{"kingdom": "sand", "disponibilidad": "base"}]
        self.assertEqual(
            mono_kingdom_progression(
                "sand", goal="Sand Shop Moon", ranges=None, moons=moons
            ),
            ["e"],
        )

    def test_mid_story_fixed_uses_second(self) -> None:
        moons = [{"kingdom": "metro", "name": "Celebrating in the Streets!", "disponibilidad": "mid_story"}]
        # Dump del reino + luna concreta: debe usar Festival mid_story → n.
        dump = [
            {"kingdom": "metro", "moon": 1, "name": "Pest", "disponibilidad": "base"},
            moons[0],
        ]
        self.assertEqual(
            mono_kingdom_progression(
                "metro",
                goal="Metro Festival Moon",
                ranges=None,
                moons=dump,
            ),
            ["l"],
        )

    def test_multi_range_splits_border(self) -> None:
        moons = [{"kingdom": "lost", "disponibilidad": "base"}]
        self.assertEqual(
            mono_kingdom_progression(
                "lost",
                goal="{{X}} Lost Moons",
                ranges=[12, 14, 16, 18],
                moons=moons,
            ),
            ["m"],
        )

    def test_warp_painting_skipped(self) -> None:
        self.assertIsNone(
            mono_kingdom_progression(
                "metro",
                goal="Metro Warp-Painting Moon",
                ranges=None,
                moons=[{"kingdom": "metro", "disponibilidad": "mid_story"}],
            )
        )


class WeightingTests(unittest.TestCase):
    def test_fork_mid_lake_wooded_lower_than_sand(self) -> None:
        self.assertEqual(FORK_MID_KINGDOMS, frozenset({"lake", "wooded"}))
        self.assertEqual(
            weighting_for_progression(["e", "m"], kingdoms={"sand"}), 100
        )
        self.assertEqual(
            weighting_for_progression(["e", "m"], kingdoms={"lake"}), 70
        )
        self.assertEqual(
            weighting_for_progression(["e", "m"], kingdoms={"wooded"}), 70
        )

    def test_fork_late_luncheon_lower_than_snow(self) -> None:
        self.assertEqual(FORK_LATE_KINGDOMS, frozenset({"luncheon", "mushroom"}))
        self.assertEqual(
            weighting_for_progression(["l", "n"], kingdoms={"snow"}), 95
        )
        self.assertEqual(
            weighting_for_progression(["l", "n"], kingdoms={"seaside"}), 95
        )
        self.assertEqual(
            weighting_for_progression(["l", "n"], kingdoms={"luncheon"}), 75
        )

    def test_availability_penalty_within_bridge(self) -> None:
        self.assertEqual(
            weighting_for_progression(
                ["e", "m"], kingdoms={"sand"}, availability_rank=0
            ),
            100,
        )
        self.assertEqual(
            weighting_for_progression(
                ["e", "m"], kingdoms={"sand"}, availability_rank=1
            ),
            90,
        )
        self.assertEqual(
            weighting_for_progression(
                ["e", "m"], kingdoms={"sand"}, availability_rank=2
            ),
            80,
        )
        # Lake base sigue por debajo de Sand mid (fork Mid).
        self.assertEqual(
            weighting_for_progression(
                ["e", "m"], kingdoms={"lake"}, availability_rank=0
            ),
            70,
        )
        self.assertGreater(
            weighting_for_progression(
                ["e", "m"], kingdoms={"sand"}, availability_rank=1
            ),
            weighting_for_progression(
                ["e", "m"], kingdoms={"lake"}, availability_rank=0
            ),
        )

    def test_globals_skip_availability_penalty(self) -> None:
        self.assertEqual(
            weighting_for_progression(
                ["e", "m", "l", "n"], availability_rank=2
            ),
            55,
        )

    def test_bridge_weights(self) -> None:
        self.assertEqual(weighting_for_progression(["m", "l"]), 100)
        self.assertEqual(weighting_for_progression(["l", "n"]), 95)
        self.assertEqual(weighting_for_progression(["n"]), 60)
        self.assertEqual(
            weighting_for_progression(["e", "m", "l", "n"]), 55
        )

    def test_revisit_maps_to_next_kingdom(self) -> None:
        cap = {"kingdom": "cap", "moon": 1, "availability": "revisit"}
        lost = {"kingdom": "lost", "moon": 13, "availability": "revisit"}
        self.assertEqual(kingdom_for_weighting(cap), "sand")
        self.assertEqual(kingdom_for_weighting(lost), "metro")
        # Cap/Cascade base/wp también pesan con Sand.
        self.assertEqual(
            kingdom_for_weighting(
                {"kingdom": "cascade", "moon": 1, "availability": "base"}
            ),
            "sand",
        )
        ks = weighting_kingdoms(
            {"range": [1]}, [lost], fallback={"lost"}
        )
        self.assertEqual(ks, {"metro"})
        self.assertEqual(
            weighting_progression(["m", "l"], {"range": [1]}, [lost], ks),
            ["l"],
        )
        self.assertEqual(
            weighting_for_progression(["l"], kingdoms={"metro"}), 100
        )

    def test_goal_availability_rank_min_range(self) -> None:
        moons = [
            {"kingdom": "sand", "moon": 1, "availability": "base"},
            {"kingdom": "sand", "moon": 2, "availability": "base"},
            {"kingdom": "sand", "moon": 3, "availability": "mid_story"},
            {"kingdom": "sand", "moon": 4, "availability": "world_peace"},
        ]
        self.assertEqual(
            goal_availability_rank({"range": [2, 4]}, moons), 0
        )
        self.assertEqual(
            goal_availability_rank({"range": [3, 4]}, moons), 1
        )
        self.assertEqual(
            goal_availability_rank({"range": [4]}, moons), 2
        )
        self.assertEqual(
            goal_availability_rank({"goal": "Sand Moon Rock"}, []), 0
        )
        self.assertEqual(
            goal_availability_rank(
                {"goal": "Sand Moon Rock"},
                [{"kingdom": "sand", "moon": 1, "availability": "base"}],
            ),
            0,
        )
        self.assertEqual(
            goal_availability_rank({"goal": "Sand Talkatoo"}, []), 0
        )
        self.assertEqual(
            goal_availability_rank(
                {"goal": "Lake Hint Art Moon"},
                [
                    {
                        "kingdom": "lake",
                        "moon": 1,
                        "availability": "world_peace",
                    }
                ],
            ),
            2,
        )
        self.assertEqual(
            goal_availability_rank(
                {"goal": "Seaside Hint Art Moon"},
                [{"kingdom": "seaside", "moon": 1, "availability": "base"}],
            ),
            0,
        )


class ProgressionOverrideFixedGoalsTests(unittest.TestCase):
    """Overrides multi-zona deben aplicarse también sin range."""

    def test_fixed_warp_and_story_use_full_bridge(self) -> None:
        cases = {
            "Metro Warp-Painting Moon": ["m"],
            "Cascade Warp-Painting Moon": ["l", "n"],
            "Lake Hint Art Moon": ["m"],
            "Defeat Bowser in Cloud Kingdom": ["m"],
            "Correct Wooded Sphynx Question": ["e"],
        }
        for goal, expected in cases.items():
            with self.subTest(goal=goal):
                prog, rng = apply_objective(
                    goal,
                    {"goal": goal},
                    goal_moons={},
                    story_order=list(STORY_ORDER),
                    ceilings={"e": "sand", "m": "lost", "l": "seaside", "n": "moon"},
                )
                self.assertEqual(prog, expected)
                self.assertIsNone(rng)


class RegionalCategoriesTests(unittest.TestCase):
    def test_strip_moontype_from_regional(self) -> None:
        obj = {
            "goal": "{{X}} 8-Bit Regional Coins",
            "board_categories": ["regionalcoins", "moontype"],
            "line_categories": ["regionalcoins", "moontype"],
        }
        self.assertTrue(strip_moontype_from_regional_categories(obj))
        self.assertEqual(obj["board_categories"], ["regionalcoins"])
        self.assertEqual(obj["line_categories"], ["regionalcoins"])

    def test_strip_moontype_ignores_non_regional(self) -> None:
        obj = {
            "goal": "{{X}} 8-Bit Moons",
            "board_categories": ["moontype"],
            "line_categories": ["moontype"],
        }
        self.assertFalse(strip_moontype_from_regional_categories(obj))
        self.assertEqual(obj["board_categories"], ["moontype"])


if __name__ == "__main__":
    unittest.main()
