"""Helpers de progression (apply_progression_accessibility)."""
from __future__ import annotations

import unittest

from apply_progression_accessibility import (
    expand_zones_forward,
    kingdom_to_zone,
    pair_progression,
    unique_ascending,
    unique_progression,
)
from catalog_lib import STORY_ORDER, ZONE_ORDER


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

    def test_cloud_forced_mid(self) -> None:
        self.assertEqual(kingdom_to_zone("cloud", STORY_ORDER, self.ceilings), "m")


class ExpandAndPairTests(unittest.TestCase):
    def test_mono_kingdom_uses_border_progression(self) -> None:
        self.assertEqual(expand_zones_forward({"e"}, kingdoms={"sand"}), ["e", "m"])
        self.assertEqual(expand_zones_forward({"l"}, kingdoms={"snow"}), ["l"])

    def test_pair_progression_extremes(self) -> None:
        self.assertEqual(pair_progression("e", "l", 2), ["e", "l"])
        self.assertEqual(pair_progression("e", "n", 4), ZONE_ORDER)


if __name__ == "__main__":
    unittest.main()
