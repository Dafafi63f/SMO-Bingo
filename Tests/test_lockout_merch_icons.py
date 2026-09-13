"""Tests del mapeo lockout souvenirs/stickers."""
from __future__ import annotations

import unittest
from pathlib import Path

from lockout_merch_icons import (
    SOUVENIR_GAME_COUNT,
    SOUVENIR_GOAL_LIST_ICON_ID_LISTS,
    SOUVENIR_KINGDOM_FILE,
    SOUVENIR_MISSING_ID_LISTS,
    STICKER_GAME_COUNT,
    all_sticker_icons,
    collect_goal_lists_icon_mismatches,
    naive_souvenir_icon,
    souvenir_icon,
    souvenir_kingdom_icon,
    sticker_icon,
    sticker_kingdom,
)


class LockoutMerchIconsTests(unittest.TestCase):
    def test_combined_stickers_rotation_within_limit(self) -> None:
        import json

        combined = json.loads(
            next(
                (Path(__file__).resolve().parents[1] / "Bingos").glob(
                    "Super Mario Odyssey-Combined-*.json"
                )
            ).read_text(encoding="utf-8")
        )
        from lockout_merch_icons import MERCH_ROTATION_ICON_LIMIT, goal_list_sticker_icons

        obj = next(o for o in combined["objectives"] if o.get("goal") == "{{X}} Stickers")
        self.assertEqual(obj["icons"], goal_list_sticker_icons())
        self.assertEqual(len(obj["icons"]), MERCH_ROTATION_ICON_LIMIT)
        self.assertNotIn("smo/sticker17.webp", obj["icons"])

    def test_sticker_icons_one_to_one(self) -> None:
        self.assertEqual(len(all_sticker_icons()), STICKER_GAME_COUNT)
        for n in range(1, STICKER_GAME_COUNT + 1):
            self.assertEqual(sticker_icon(n), f"smo/sticker{n}.webp")

    def test_souvenir_missing_have_no_icon(self) -> None:
        for id_list in SOUVENIR_MISSING_ID_LISTS:
            self.assertIsNone(souvenir_icon(id_list))

    def test_known_souvenir_item_icons(self) -> None:
        self.assertEqual(souvenir_icon(11), "smo/souvenir6.webp")  # Potted Palm
        self.assertEqual(souvenir_icon(22), "smo/souvenir11.webp")  # Jizo
        self.assertEqual(souvenir_icon(4), "smo/souvenir2.webp")  # Triceratops

    def test_souvenir_kingdom_slot_icons(self) -> None:
        self.assertEqual(souvenir_kingdom_icon("cap"), "smo/souvenir1.webp")
        self.assertEqual(souvenir_kingdom_icon("sand"), "smo/souvenir3.webp")
        self.assertEqual(souvenir_kingdom_icon("lost"), "smo/souvenir6.webp")
        self.assertEqual(souvenir_kingdom_icon("bowser"), "smo/souvenir11.webp")
        self.assertEqual(len(SOUVENIR_KINGDOM_FILE), 11)

    def test_souvenir_goal_list_icon_tiers(self) -> None:
        import json

        from catalog_lib import CATALOG_DIR

        data = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        by_id = {
            int(entry["id_list"]): entry
            for entry in (data.get("lists") or {}).get("souvenirs") or []
            if isinstance(entry, dict)
        }
        cheap = {1, 5, 7, 11, 17}
        expensive = {4, 10, 14, 16, 20, 22}
        for id_list in cheap:
            self.assertEqual(by_id[id_list]["regional"], 5)
            self.assertIn("icon", by_id[id_list])
        for id_list in expensive:
            self.assertEqual(by_id[id_list]["regional"], 25)
            self.assertIn("icon", by_id[id_list])

    def test_naive_souvenir_pattern_differs(self) -> None:
        for id_list in (4, 6, 11, 22):
            self.assertNotEqual(souvenir_icon(id_list), naive_souvenir_icon(id_list))

    def test_goal_lists_sticker_icons(self) -> None:
        mismatches = [
            m
            for m in collect_goal_lists_icon_mismatches()
            if m.startswith("stickers ")
        ]
        self.assertEqual(mismatches, [])

    def test_postgame_stickers_not_in_goal_lists(self) -> None:
        import json

        from catalog_lib import CATALOG_DIR
        from lockout_merch_icons import STICKER_POSTGAME_ID_LISTS

        data = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        id_lists = {
            int(entry["id_list"])
            for entry in (data.get("lists") or {}).get("stickers") or []
            if isinstance(entry, dict)
        }
        self.assertEqual(id_lists, set(range(1, 12)))
        self.assertFalse(id_lists & STICKER_POSTGAME_ID_LISTS)

    def test_goal_lists_souvenir_icons(self) -> None:
        mismatches = [
            m
            for m in collect_goal_lists_icon_mismatches()
            if m.startswith("souvenirs ")
        ]
        self.assertEqual(mismatches, [])

    def test_souvenirs_one_icon_per_kingdom_in_goal_lists(self) -> None:
        import json

        from catalog_lib import CATALOG_DIR

        data = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        entries = [
            entry
            for entry in (data.get("lists") or {}).get("souvenirs") or []
            if isinstance(entry, dict) and "icon" in entry
        ]
        self.assertEqual(
            {int(entry["id_list"]) for entry in entries},
            set(SOUVENIR_GOAL_LIST_ICON_ID_LISTS),
        )
        kingdoms = [str(entry["kingdom"]) for entry in entries]
        self.assertEqual(len(kingdoms), len(set(kingdoms)))

    def test_souvenirs_missing_lockout_have_no_icon_in_goal_lists(self) -> None:
        import json

        from catalog_lib import CATALOG_DIR

        data = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        by_id = {
            int(entry["id_list"]): entry
            for entry in (data.get("lists") or {}).get("souvenirs") or []
            if isinstance(entry, dict)
        }
        for id_list in SOUVENIR_MISSING_ID_LISTS:
            if id_list in SOUVENIR_GOAL_LIST_ICON_ID_LISTS:
                continue
            self.assertNotIn("icon", by_id[id_list])
        for id_list in range(1, SOUVENIR_GAME_COUNT + 1):
            if id_list in SOUVENIR_MISSING_ID_LISTS:
                self.assertIsNone(souvenir_icon(id_list))


if __name__ == "__main__":
    unittest.main()
