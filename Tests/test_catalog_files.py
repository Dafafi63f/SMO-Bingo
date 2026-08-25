"""Integridad de Catalog/ respecto al Combined y project.json."""
from __future__ import annotations

import json
import unittest
from collections import Counter
from typing import Any, ClassVar

from catalog_lib import (
    ALL_KINGDOMS_REFERENCE_PATH,
    CATALOG_DIR,
    DEFAULT_GOALS_REFERENCE_PATH,
    JSON_PATH,
    LONG_GOALS_REFERENCE_PATH,
    SHORT_GOALS_REFERENCE_PATH,
    STORY_ORDER,
    collect_availability_violations,
    load_project,
)
from goal_list_lib import (
    collect_disponibilidad_list_violations,
    collect_goal_lists_referencia_mismatches,
    collect_location_field_violations,
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
            "goals_individuales.json",
            "lunas-objetivos.json",
            "tags_inventario.json",
            "capturas_lunas.json",
            "zonas_reino.json",
            "zonas_inventario.json",
        ]
        for name in required:
            with self.subTest(name=name):
                path = CATALOG_DIR / name
                self.assertTrue(path.is_file(), f"Falta {path}")
                json.loads(path.read_text(encoding="utf-8"))

    def test_bingo_lineas_goal_cat_counts(self) -> None:
        data = json.loads((CATALOG_DIR / "bingo_lineas.json").read_text(encoding="utf-8"))
        self.assertEqual(
            data["n_goals"], data["n_goals_1_cat"] + data["n_goals_2_cats"]
        )
        self.assertNotIn("n_goals_bad_cats", data)
        hits: Counter[str] = Counter()
        for group in data["groups"]:
            for obj in group["objectives"]:
                hits[str(obj["goal"])] += 1
        self.assertEqual(data["n_goals"], len(hits))
        self.assertEqual(data["n_goals_1_cat"], sum(1 for n in hits.values() if n == 1))
        self.assertEqual(data["n_goals_2_cats"], sum(1 for n in hits.values() if n == 2))
        self.assertTrue(all(n in (1, 2) for n in hits.values()))

    def test_zonas_inventario_alpha_by_zone(self) -> None:
        """Vista de revisión: zones[] en alfa (zone, kingdom); ≥3 por zona."""
        data = json.loads((CATALOG_DIR / "zonas_inventario.json").read_text(encoding="utf-8"))
        self.assertEqual(data["n_zones"], len(data["zones"]))
        self.assertEqual(data["n_total"], sum(z["n_total"] for z in data["zones"]))
        keys = [(z["zone"], z["kingdom"]) for z in data["zones"]]
        self.assertEqual(keys, sorted(keys, key=lambda zk: (zk[0].lower(), zk[1])))
        self.assertEqual([z["orden"] for z in data["zones"]], list(range(1, data["n_zones"] + 1)))
        for z in data["zones"]:
            with self.subTest(zone=z["zone"], kingdom=z["kingdom"]):
                self.assertGreaterEqual(z["n_total"], 3)
                self.assertEqual(z["n_total"], len(z["list"]))
                self.assertEqual(sum(z["by_source"].values()), z["n_total"])
                self.assertEqual(list(z["by_source"]), sorted(z["by_source"]))
                for it in z["list"]:
                    self.assertEqual(it["kingdom"], z["kingdom"])
                    self.assertNotIn("zone", it)
                    self.assertIn("id", it)
                    self.assertIn("id_kingdom", it)

    def test_zonas_reino_sand_tostarena(self) -> None:
        """zonas_reino: kingdom + todos los goal_lists + moons."""
        data = json.loads((CATALOG_DIR / "zonas_reino.json").read_text(encoding="utf-8"))
        self.assertIn("kingdoms", data)
        self.assertNotIn("zones", data)
        names = [k["kingdom"] for k in data["kingdoms"]]
        self.assertEqual(
            names, [k for k in STORY_ORDER if k in names] + [k for k in names if k not in STORY_ORDER]
        )
        sand = next(k for k in data["kingdoms"] if k["kingdom"] == "sand")
        self.assertGreater(sand["n_items"], 0)
        self.assertEqual(len(sand["list"]), sand["n_moons"] + sand["n_items"])
        self.assertEqual(sand["n_total"], sand["n_moons"] + sand["n_items"])
        self.assertEqual(sand["n_total"], len(sand["list"]))
        self.assertIn("by_zone", sand)
        self.assertEqual(list(sand["by_zone"]), sorted(sand["by_zone"]))
        zoned = sum(1 for it in sand["list"] if it.get("zone") is not None)
        self.assertEqual(sum(sand["by_zone"].values()), zoned)
        self.assertGreaterEqual(sand["by_zone"]["tostarena"], 12)
        cap = next(k for k in data["kingdoms"] if k["kingdom"] == "cap")
        cap_moons = {it["id_kingdom"]: it for it in cap["list"] if it["source"] == "moon"}
        self.assertEqual(cap_moons[6]["zone"], "fog")
        self.assertEqual(cap_moons[8]["zone"], "fog")
        self.assertEqual(cap_moons[5]["zone"], "central_plaza")
        self.assertNotIn("n_with_zone", sand)
        self.assertGreater(sand["n_moons"], 0)
        moons = [it for it in sand["list"] if it["source"] == "moon"]
        self.assertEqual(len(moons), sand["n_moons"])
        self.assertEqual(moons[0]["id_kingdom"], 1)
        self.assertNotIn("moon", moons[0])
        self.assertEqual(moons[0].get("zone"), "ruins")
        self.assertNotIn("kingdom", moons[0])
        self.assertNotIn("tags", moons[0])
        self.assertEqual(
            list(moons[0])[:6],
            ["source", "id", "id_kingdom", "name", "disponibilidad", "zone"],
        )
        # Ítems de lists sí llevan zone (fuente de ubicación).
        first = next(it for it in sand["list"] if it.get("source") != "moon")
        self.assertEqual(next(iter(first)), "source")
        self.assertIn("zone", first)
        self.assertEqual(
            list(first)[:6],
            ["source", "id", "id_kingdom", "name", "disponibilidad", "zone"],
        )
        self.assertNotIn("kingdom", first)
        self.assertNotIn("tags", first)
        # list[]: moons primero, luego lists alfa (id_kingdom en dos bloques)
        moon_rows = [it for it in sand["list"] if it["source"] == "moon"]
        list_rows = [it for it in sand["list"] if it["source"] != "moon"]
        self.assertEqual(sand["list"], moon_rows + list_rows)
        self.assertEqual(
            [it["source"] for it in list_rows],
            sorted(it["source"] for it in list_rows),
        )
        item_kids = [it["id_kingdom"] for it in list_rows]
        self.assertEqual(item_kids, list(range(1, sand["n_items"] + 1)))
        moon_kids = [it["id_kingdom"] for it in moons]
        self.assertEqual(moon_kids, sorted(moon_kids))
        self.assertEqual(
            [it["id"] for it in sand["list"]],
            list(range(1, sand["n_total"] + 1)),
        )
        # moons: id_kingdom = nº luna; nombres = lunas-objetivos
        lunas = json.loads(
            (CATALOG_DIR / "lunas-objetivos.json").read_text(encoding="utf-8")
        )
        sand_lunas = [
            m
            for m in lunas["moons"]
            if isinstance(m.get("tags"), list) and m["tags"] and m["tags"][0] == "sand"
        ]
        sand_lunas.sort(key=lambda m: int(m["moon"]))
        self.assertEqual(
            [(it["id_kingdom"], it["name"]) for it in moons],
            [(int(m["moon"]), m["name"]) for m in sand_lunas],
        )
        # Cabecera alineada con goal_lists
        self.assertEqual(data["n_total"], data["n_moons"] + data["n_items"])
        self.assertNotIn("n_with_zone", data)
        self.assertNotIn("n_without_zone", data)
        gl = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        self.assertEqual(data["n_items"], gl["n_items"])
        self.assertNotIn("n_with_zone", gl)
        self.assertNotIn("n_without_zone", gl)
        for k in data["kingdoms"]:
            with self.subTest(kingdom=k["kingdom"]):
                self.assertEqual(
                    len(k["list"]), k["n_moons"] + k["n_items"]
                )
                self.assertEqual(k["n_total"], k["n_moons"] + k["n_items"])
                self.assertEqual(k["n_total"], len(k["list"]))
                self.assertEqual(
                    k["n_items"],
                    sum(1 for it in k["list"] if it.get("source") != "moon"),
                )
                self.assertNotIn("n_with_zone", k)
                mr = [it for it in k["list"] if it["source"] == "moon"]
                lr = [it for it in k["list"] if it["source"] != "moon"]
                self.assertEqual(k["list"], mr + lr)
                self.assertEqual(
                    [it["source"] for it in lr],
                    sorted(it["source"] for it in lr),
                )
                item_ids = [it["id_kingdom"] for it in lr]
                self.assertEqual(item_ids, list(range(1, k["n_items"] + 1)))
                self.assertEqual(
                    [it["id"] for it in k["list"]],
                    list(range(1, k["n_total"] + 1)),
                )
                for it in k["list"]:
                    if it.get("source") == "moon":
                        self.assertNotIn("tags", it)
                        self.assertNotIn("kingdom", it)
                        self.assertNotIn("moon", it)
                        self.assertIn("zone", it)
                    else:
                        self.assertNotIn("tags", it)
                        self.assertIn("zone", it)
        # Mismo source: nombres siguen aparicion en goal_lists
        lists = gl
        sand_binoc_names = [
            it["name"]
            for it in lists["lists"]["binoculars"]
            if it.get("kingdom") == "sand"
        ]
        out_binocs = [it for it in sand["list"] if it["source"] == "binoculars"]
        out_binoc_names = [it["name"] for it in out_binocs]
        self.assertEqual(out_binoc_names, sand_binoc_names)
        tost = [it for it in sand["list"] if it.get("zone") == "tostarena"]
        tost_sources = {it["source"] for it in tost}
        self.assertIn("regionals", tost_sources)
        self.assertIn("pixel_luigis", tost_sources)
        self.assertIn("jaxi_stands", tost_sources)
        cap = next(k for k in data["kingdoms"] if k["kingdom"] == "cap")
        pixel_sources = {
            it["source"]
            for it in cap["list"]
            if it["source"].startswith("pixel_cat_")
        }
        self.assertEqual(pixel_sources, {"pixel_cat_marios", "pixel_cat_peaches"})
        self.assertEqual(
            sum(1 for it in tost if it["source"] == "regionals"), 9
        )
        self.assertIn("regionals", lists["lists"])
        self.assertEqual(len(lists["lists"]["regionals"]), 287)

    def test_shops_drive_merchandise_zones(self) -> None:
        """Shops/merchandise: zone solo en zonas_reino (heredada por reino)."""
        lists = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        self.assertNotIn("captures", lists["lists"])
        shops = lists["lists"]["shops"]
        self.assertEqual(len(shops), 11)
        for row in shops:
            self.assertNotIn("zone", row)
        for name in (
            "costume_sets",
            "hats",
            "souvenirs",
            "stickers",
            "boxer_shorts",
        ):
            for row in lists["lists"][name]:
                self.assertNotIn("zone", row, f"{name} {row.get('name')}")
        zl = json.loads((CATALOG_DIR / "zonas_reino.json").read_text(encoding="utf-8"))
        by_k = {k["kingdom"]: k for k in zl["kingdoms"]}
        sand_shop = next(
            it
            for it in by_k["sand"]["list"]
            if it["source"] == "shops" and it["name"] == "Crazy Cap"
        )
        self.assertEqual(sand_shop["zone"], "tostarena")
        metro_shop = next(
            it
            for it in by_k["metro"]["list"]
            if it["source"] == "shops" and it["name"] == "Crazy Cap"
        )
        self.assertEqual(metro_shop["zone"], "crazy_cap")
        for name in (
            "costume_sets",
            "hats",
            "souvenirs",
            "stickers",
            "boxer_shorts",
        ):
            for it in by_k["sand"]["list"]:
                if it["source"] == name:
                    self.assertEqual(it["zone"], "tostarena", it["name"])


    def test_unique_captures_no_lista(self) -> None:
        """Capturas viven en capturas_lunas; Unique Captures / Capture X sin lista[]."""
        from goal_list_lib import (
            CAPTURE_SOLO,
            build_goal_lista,
            unique_captures_list,
        )

        self.assertEqual(unique_captures_list(), [])
        for goal in CAPTURE_SOLO:
            self.assertEqual(build_goal_lista(goal, {}, kingdom=None), [])
        self.assertEqual(
            build_goal_lista("{{X}} Unique Captures", {}, kingdom=None), []
        )
        # Binoculars sigue siendo lista curada (ubicaciones).
        bins = build_goal_lista("Capture {{X}} Binoculars", {}, kingdom=None)
        self.assertGreater(len(bins), 0)

    def test_goal_icons_non_smo_counter(self) -> None:
        """Cabecera: non_smo + one/multi (one+multi = with_icon)."""
        icons = json.loads((CATALOG_DIR / "goal_icons.json").read_text(encoding="utf-8"))
        self.assertIn("n_goals_non_smo", icons)
        self.assertIn("n_goals_one_icon", icons)
        self.assertIn("n_goals_multi_icon", icons)
        expected_non_smo: set[str] = set()
        n_one = 0
        n_multi = 0
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        for obj in data["objectives"]:
            if obj.get("disabled"):
                continue
            goal = str(obj.get("goal") or "")
            if not goal:
                continue
            icon_list = [str(i) for i in (obj.get("icons") or []) if i]
            if any(not i.startswith("smo/") for i in icon_list):
                expected_non_smo.add(goal)
            if len(icon_list) == 1:
                n_one += 1
            elif len(icon_list) >= 2:
                n_multi += 1
        self.assertEqual(icons["n_goals_non_smo"], len(expected_non_smo))
        self.assertEqual(icons["n_goals_one_icon"], n_one)
        self.assertEqual(icons["n_goals_multi_icon"], n_multi)
        self.assertEqual(
            icons["n_goals_one_icon"] + icons["n_goals_multi_icon"],
            icons["n_goals_with_icon"],
        )
        self.assertGreater(icons["n_goals_non_smo"], 0)
        self.assertGreater(icons["n_goals_multi_icon"], 0)

    def test_multi_moon_count_semantics(self) -> None:
        """Total Multi-Moons = físicas; Total Moons = Odyssey ×3."""
        from catalog_lib import goal_moon_count_mode, load_combined_objectives_by_goal

        by_goal = load_combined_objectives_by_goal()
        total_multi = by_goal["{{X}} Total Multi-Moons"]
        total_moons = by_goal["{{X}} Total Moons"]
        sand_multi = by_goal["{{X}} Sand Multi-Moon[[s]]"]
        self.assertEqual(
            goal_moon_count_mode("{{X}} Total Multi-Moons", total_multi, moonish=True),
            "physical_moons",
        )
        self.assertEqual(
            goal_moon_count_mode("{{X}} Sand Multi-Moon[[s]]", sand_multi, moonish=True),
            "physical_moons",
        )
        self.assertEqual(
            goal_moon_count_mode("{{X}} Total Moons", total_moons, moonish=True),
            "odyssey_units",
        )
        tip = total_multi.get("tooltip") or ""
        self.assertNotIn("Multi-Moons count as 3", tip)

        ref = json.loads((CATALOG_DIR / "goals_referencia.json").read_text(encoding="utf-8"))
        g = next(x for x in ref["goals"] if x["goal"] == "{{X}} Total Multi-Moons")
        self.assertEqual(g["moon_count_mode"], "physical_moons")
        self.assertEqual(g["range"], [3, 6, 9, 12])
        notas = " ".join(g.get("notas") or [])
        self.assertIn("físicas", notas)
        self.assertNotIn("unidades depositadas", notas)

    def test_no_cloud_kingdom_slug_in_catalog_json(self) -> None:
        """Slug cloud no se escribe; Cloud Kingdom solo en el nombre de la goal."""
        from catalog_lib import _CLOUD_KINGDOM, catalog_kingdom, catalog_kingdom_for_moon

        self.assertEqual(catalog_kingdom(_CLOUD_KINGDOM), "lost")
        self.assertEqual(catalog_kingdom_for_moon("metro", "base"), "lost")
        self.assertEqual(catalog_kingdom_for_moon("metro", "mid_story"), "metro")
        self.assertEqual(
            catalog_kingdom_for_moon("metro", "mid_story", moon=51), "lost"
        )
        self.assertEqual(
            catalog_kingdom_for_moon("metro", "mid_story", moon=13), "lost"
        )
        self.assertEqual(
            catalog_kingdom_for_moon("metro", "mid_story", moon=11), "metro"
        )
        ind = json.loads(
            (CATALOG_DIR / "goals_individuales.json").read_text(encoding="utf-8")
        )
        ids = [gr["id"] for gr in ind["groups"]]
        self.assertNotIn("cloud", ids)
        lost = next(gr for gr in ind["groups"] if gr["id"] == "lost")
        lost_goals = [row["goal"] for row in lost["goals"]]
        self.assertIn("Defeat Bowser in Cloud Kingdom", lost_goals)
        self.assertTrue(
            any("Metro Night" in g for g in lost_goals),
            "Metro Night debe catalogarse en lost",
        )
        luncheon = next(gr for gr in ind["groups"] if gr["id"] == "luncheon")
        luncheon_goals = [row["goal"] for row in luncheon["goals"]]
        self.assertIn(
            "Mushroom Warp-Painting Moon",
            luncheon_goals,
            "Mushroom Warp-Painting debe catalogarse en luncheon",
        )

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

    def test_progression_matches_combined(self) -> None:
        by_combined = {
            o["goal"]: o["progression"] for o in self.combined["objectives"]
        }
        for g in self.ref["goals"]:
            with self.subTest(goal=g["goal"]):
                self.assertEqual(g["progression"], by_combined[g["goal"]])


class BingoGroupsSyncTests(unittest.TestCase):
    def test_group_count(self) -> None:
        data = json.loads((CATALOG_DIR / "bingo_groups.json").read_text(encoding="utf-8"))
        self.assertEqual(data["n_groups"], len(data["groups"]))
        self.assertGreater(data["n_groups"], 0)

    def test_retired_groups_gone(self) -> None:
        data = json.loads((CATALOG_DIR / "bingo_groups.json").read_text(encoding="utf-8"))
        ids = {g["id"] for g in data["groups"]}
        self.assertNotIn("ndc_festival_band", ids)
        self.assertNotIn("special_captures", ids)
        self.assertNotIn("totals", ids)

    def test_lista_vs_moons_pools(self) -> None:
        data = json.loads((CATALOG_DIR / "bingo_groups.json").read_text(encoding="utf-8"))
        by_id = {g["id"]: g for g in data["groups"]}
        for g in data["groups"]:
            for m in g.get("moons") or []:
                self.assertIn("kingdom", m, g.get("id"))
                self.assertIn("moon", m, g.get("id"))
                self.assertIn("name", m, g.get("id"))
                self.assertIn("disponibilidad", m, g.get("id"))
                self.assertLessEqual(
                    set(m),
                    {"kingdom", "moon", "name", "disponibilidad", "odyssey_units"},
                    g.get("id"),
                )
            keys = list(g.keys())
            n = g.get("n") or {}
            if "odyssey_units" in n:
                self.assertIn("moons", keys, g.get("id"))
                self.assertLess(
                    keys.index("n"),
                    keys.index("moons"),
                    g.get("id"),
                )
                self.assertIn("moons", n, g.get("id"))
                has_multi = any(
                    m.get("odyssey_units") for m in (g.get("moons") or [])
                )
                self.assertTrue(has_multi, g.get("id"))
                self.assertNotEqual(n["odyssey_units"], n["moons"], g.get("id"))
            self.assertIn("has", g, g.get("id"))
            self.assertIn("n", g, g.get("id"))
            self.assertEqual(
                set(g["has"]),
                {"goals", "moons", "lista"},
                g.get("id"),
            )
            self.assertTrue(
                {"objectives", "moons", "lista"} <= set(n),
                g.get("id"),
            )
            self.assertNotIn("has_goals", g, g.get("id"))
            self.assertNotIn("n_objectives", g, g.get("id"))
            self.assertNotIn("n_odyssey_units", g, g.get("id"))
        boss = by_id["boss"]
        self.assertEqual(boss["kind"], "goals+lista")
        self.assertEqual(boss["n"]["moons"], 0)
        self.assertGreater(boss["n"]["lista"], 0)
        self.assertEqual(boss.get("lista_source"), "bosses")
        self.assertEqual(boss["n"]["lista"], len(boss["lista"]))
        sample = boss["lista"][0]
        self.assertEqual(
            list(sample.keys()),
            [
                k
                for k in ("kingdom", "source", "id", "id_list", "name", "disponibilidad")
                if k in sample
            ],
        )
        self.assertEqual(sample.get("source"), "bosses")
        self.assertLessEqual(
            set(sample),
            {"kingdom", "source", "id", "id_list", "name", "disponibilidad"},
        )
        self.assertNotIn("zone", sample)
        self.assertIn("id", sample)
        self.assertIn("id_list", sample)
        # Activate Levers: solo lista (sin moons[] duplicando metro#37 / luncheon#2).
        lever = by_id["lever"]
        self.assertEqual(lever["kind"], "goals+lista")
        self.assertEqual(lever["n"]["moons"], 0)
        self.assertEqual(lever.get("moons"), [])
        self.assertEqual(lever["n"]["lista"], 6)
        self.assertEqual(lever.get("lista_source"), "levers")
        self.assertEqual(
            [o["goal"] for o in lever["objectives"]],
            ["Activate {{X}} Levers"],
        )
        checkpoint = by_id["checkpoints"]
        self.assertEqual(checkpoint["kind"], "goals")
        self.assertEqual(checkpoint["n"]["moons"], 0)
        self.assertEqual(checkpoint["n"]["lista"], 0)
        self.assertNotIn("lista_source", checkpoint)
        self.assertIn("{{X}} Total Checkpoints", [o["goal"] for o in checkpoint["objectives"]])
        self.assertIn("{{X}} Cap Checkpoints", [o["goal"] for o in checkpoint["objectives"]])
        regionals = by_id["regionalcoins"]
        self.assertEqual(regionals["kind"], "goals")
        self.assertEqual(regionals["n"]["moons"], 0)
        self.assertEqual(regionals["n"]["lista"], 0)
        self.assertNotIn("lista_source", regionals)
        self.assertIn(
            "{{X}} Total Regional Coins",
            [o["goal"] for o in regionals["objectives"]],
        )
        self.assertIn(
            "{{X}} Cap Regional Coins",
            [o["goal"] for o in regionals["objectives"]],
        )
        for line_id in (
            "artistic",
            "storymoons",
            "subarea",
            "captaintoad",
            "moonrock",
        ):
            self.assertIn(line_id, by_id, line_id)
        self.assertNotIn("miscellaneous", by_id)
        self.assertNotIn("special_seeds", by_id)
        totales = by_id["totales"]
        self.assertEqual(totales["kind"], "goals")
        self.assertEqual(totales["n"]["moons"], 0)
        self.assertEqual(totales["n"]["lista"], 0)
        self.assertEqual(
            {o["goal"] for o in totales["objectives"]},
            {
                "{{X}} Total Moons",
                "{{X}} Total Checkpoints",
                "{{X}} Total Regional Coins",
                "{{X}} Total Multi-Moons",
                "{{X}} Total Story Moons",
            },
        )
        nature = by_id["nature"]
        self.assertEqual(nature["kind"], "goals+moons")
        self.assertGreater(nature["n"]["moons"], 0)
        self.assertEqual(
            nature["n"]["moons"],
            by_id["fauna"]["n"]["moons"] + by_id["flora"]["n"]["moons"],
        )
        self.assertNotIn("checkpoint", by_id)
        self.assertNotIn("regionals", by_id)
        self.assertNotIn("story_moon", by_id)
        self.assertNotIn("kingdommoons", by_id)
        self.assertNotIn("moontype", by_id)
        self.assertNotIn("totals", by_id)
        life_up = by_id["life_up"]
        self.assertEqual(life_up["kind"], "goals+lista")
        self.assertEqual(life_up["n"]["moons"], 0)
        self.assertEqual(life_up["n"]["lista"], 17)
        self.assertEqual(life_up.get("lista_source"), "life_up_hearts")
        for g in data["groups"]:
            for it in g.get("lista") or []:
                if it.get("source") and it.get("name"):
                    self.assertIn("id", it, g.get("id"))
                    self.assertIn("id_list", it, g.get("id"))
        trop = by_id["lost_tropical_wiggler"]
        self.assertEqual(trop["kind"], "goals+moons")
        self.assertGreater(trop["n"]["moons"], 0)
        self.assertEqual(trop["n"]["lista"], 0)
        self.assertNotIn("moon_tag", trop)
        self.assertNotIn("_note", trop)
        shop = by_id["shopping"]
        self.assertEqual(shop["kind"], "todo")
        self.assertIn("lista_source", shop)
        self.assertGreater(shop["n"]["moons"], 0)
        self.assertGreater(shop["n"]["lista"], 0)
        self.assertIn("boxer_shorts", str(shop.get("lista_source") or ""))
        self.assertIn("shops", str(shop.get("lista_source") or ""))
        self.assertTrue(
            any(i.get("source") == "boxer_shorts" for i in shop.get("lista") or [])
        )
        self.assertIn(
            "Snow Boxer Shorts Moon",
            [o["goal"] for o in shop["objectives"]],
        )
        self.assertNotIn("shop", by_id)
        kind_sum = sum(
            int(data.get(k) or 0)
            for k in (
                "n_groups_todo",
                "n_groups_goals_moons",
                "n_groups_goals_lista",
                "n_groups_moons_lista",
                "n_groups_goals",
                "n_groups_moons",
                "n_groups_lista",
                "n_groups_nada",
            )
        )
        self.assertEqual(kind_sum, data["n_groups"])
        self.assertEqual(
            data["n_groups_with_goals"],
            sum(1 for g in data["groups"] if g["has"]["goals"]),
        )
        self.assertEqual(
            data["n_groups_with_moons"],
            sum(1 for g in data["groups"] if g["has"]["moons"]),
        )
        self.assertEqual(
            data["n_groups_with_lista"],
            sum(1 for g in data["groups"] if g["has"]["lista"]),
        )
        self.assertNotIn("n_groups_without_goals", data)
        self.assertNotIn("n_groups_without_moons", data)
        self.assertNotIn("n_groups_without_lista", data)
        self.assertIn("n_objectives_total", data)
        self.assertIn("n_moons_total", data)
        self.assertIn("n_lista_total", data)
        # Totales de cabecera = unicos (no suma con duplicados entre grupos).
        goals_u: set[str] = set()
        moons_u: set[tuple] = set()
        for g in data["groups"]:
            for o in g.get("objectives") or []:
                if o.get("goal"):
                    goals_u.add(o["goal"])
            for m in g.get("moons") or []:
                moons_u.add((m["kingdom"], m["moon"]))
        self.assertEqual(data["n_objectives_total"], len(goals_u))
        self.assertEqual(data["n_moons_total"], len(moons_u))
        self.assertLessEqual(
            data["n_objectives_total"],
            sum(int((g.get("n") or {}).get("objectives") or 0) for g in data["groups"]),
        )
        self.assertLessEqual(
            data["n_moons_total"],
            sum(int((g.get("n") or {}).get("moons") or 0) for g in data["groups"]),
        )
        self.assertLessEqual(
            data["n_lista_total"],
            sum(int((g.get("n") or {}).get("lista") or 0) for g in data["groups"]),
        )
        self.assertNotIn("n_groups_both", data)
        self.assertNotIn("n_groups_empty", data)
        self.assertNotIn("n_groups_objectives", data)
        artistic = by_id["artistic"]
        self.assertEqual(artistic["kind"], "goals+moons")
        self.assertEqual(
            artistic["has"],
            {"goals": True, "moons": True, "lista": False},
        )
        self.assertEqual(artistic["n"]["moons"], 13)
        self.assertEqual(artistic["n"]["objectives"], 15)
        self.assertEqual(
            boss["has"],
            {"goals": True, "moons": False, "lista": True},
        )
        self.assertEqual(
            trop["has"],
            {"goals": True, "moons": True, "lista": False},
        )
        self.assertEqual(
            shop["has"],
            {"goals": True, "moons": True, "lista": True},
        )

    def test_lista_sorted_by_source_then_id_list(self) -> None:
        """lista[] multi-fuente: reino → source alfa → id_list (no intercalado)."""
        data = json.loads((CATALOG_DIR / "bingo_groups.json").read_text(encoding="utf-8"))
        bowser = next(g for g in data["groups"] if g["id"] == "bowser")
        lista = bowser["lista"]
        sources = [it["source"] for it in lista]
        self.assertEqual(sources, sorted(sources))
        by_src: dict[str, list[int]] = {}
        for it in lista:
            by_src.setdefault(it["source"], []).append(int(it["id_list"]))
        for src, ids in by_src.items():
            self.assertEqual(ids, sorted(ids), src)


class CapturasLunasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        data = json.loads((CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8"))
        cls.by_name = {r["capture"]: r for r in data["captures"]}

    def test_shared_capture_lists_subgroup_goals(self) -> None:
        """Varios grupos con el mismo capture aportan objectives + goal:true."""
        pokio = self.by_name["Pokio"]
        goals = {o["goal"] for o in pokio["objectives"]}
        self.assertIn("{{X}} Bowser's Pokio Moons", goals)
        self.assertIn("{{X}} Pokio Hole Moons", goals)
        hole = {
            (m["kingdom"], m["moon"])
            for m in pokio["moons"]
            if m["moon"] in (21, 22, 23)
        }
        self.assertEqual(len(hole), 3)
        for m in pokio["moons"]:
            if m["moon"] in (21, 22, 23):
                self.assertTrue(m["goal"], m)

        goomba = self.by_name["Goomba"]
        g_goals = {o["goal"] for o in goomba["objectives"]}
        self.assertIn("{{X}} Goomba Moon[[s]]", g_goals)
        self.assertIn("{{X}} Snow Goomba Moons", g_goals)
        snow1 = next(m for m in goomba["moons"] if m["kingdom"] == "snow" and m["moon"] == 1)
        self.assertTrue(snow1["goal"])

        uproot = self.by_name["Uproot"]
        u_goals = {o["goal"] for o in uproot["objectives"]}
        self.assertIn("{{X}} Wooded Uproot Moons", u_goals)
        self.assertIn("{{X}} Seaside Uproot Moons", u_goals)

    def test_tag_only_moons_are_goal_false_not_in_group_pool(self) -> None:
        """tag_only (p. ej. Chain Chomp #3/#7) → goal:false; fuera de moons[] del grupo."""
        from catalog_lib import load_bingo_groups, group_moons

        row = self.by_name["Chain Chomp"]
        false_keys = {
            (m["kingdom"], int(m["moon"]))
            for m in row["moons"]
            if m.get("goal") is False
        }
        self.assertIn(("cascade", 3), false_keys)
        self.assertIn(("cascade", 7), false_keys)
        groups = {g["id"]: g for g in load_bingo_groups()}
        pool = {
            (m["kingdom"], int(m["moon"]))
            for m in group_moons(groups["cascade_chain_chomp"])
        }
        self.assertTrue(false_keys.isdisjoint(pool))

    def test_every_moon_has_goal_flag(self) -> None:
        data = json.loads((CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8"))
        for row in data["captures"]:
            for m in row.get("moons") or []:
                self.assertIn("goal", m, (row["capture"], m.get("name")))
                self.assertIsInstance(m["goal"], bool)

    def test_mario_moons_not_on_bullet_bill(self) -> None:
        """sand#7/#11: BB opcional → mario; no en fila Bullet Bill."""
        row = self.by_name["Bullet Bill"]
        keys = {(m["kingdom"], int(m["moon"])) for m in row["moons"]}
        self.assertNotIn(("sand", 7), keys)
        self.assertNotIn(("sand", 11), keys)
        from catalog_lib import MARIO_MOONS

        self.assertIn(("sand", 7), MARIO_MOONS)
        self.assertIn(("sand", 11), MARIO_MOONS)

    def test_moons_is_last_field(self) -> None:
        """Ningún campo tras moons[] (kingdom/moon_tag/lista van antes)."""
        data = json.loads((CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8"))
        for row in data["captures"]:
            keys = list(row.keys())
            self.assertEqual(keys[-1], "moons", row.get("capture"))
            if "kingdom" in keys:
                self.assertLess(keys.index("kingdom"), keys.index("moons"))
            if "moon_tag" in keys:
                self.assertLess(keys.index("moon_tag"), keys.index("moons"))
            if "lista" in keys:
                self.assertLess(keys.index("lista"), keys.index("moons"))


class ProjectAndLunasTests(unittest.TestCase):
    def test_project_in_scope_count(self) -> None:
        project = load_project()
        self.assertEqual(project["n_in_scope_moons"], project["meta"]["in_scope_moon_count"])
        self.assertEqual(project["n_in_scope_moons"], 434)

    def test_lunas_objetivos_count(self) -> None:
        data = json.loads((CATALOG_DIR / "lunas-objetivos.json").read_text(encoding="utf-8"))
        self.assertEqual(data["n_moons"], len(data["moons"]))
        self.assertEqual(data["n_moons"], 434)
        ids = [m["id"] for m in data["moons"]]
        self.assertEqual(ids, list(range(1, 435)))
        first = data["moons"][0]
        self.assertEqual(
            list(first)[:4],
            ["id", "moon", "name", "disponibilidad"],
        )
        self.assertNotIn("kingdom", first)
        self.assertEqual(first["id"], 1)
        self.assertEqual(first["moon"], 1)
        self.assertEqual(first["tags"][0], "cap")
        self.assertEqual(first["tags"][1:], sorted(first["tags"][1:]))

    def test_lunas_catalog_synthetic_mushroom(self) -> None:
        """mushroom#39 → luncheon#50 (sin chocar con Magma Narrow Path #39)."""
        from catalog_lib import (
            LUNAS_CATALOG_SYNTHETIC,
            catalog_kingdom_for_moon,
            lunas_catalog_ref,
        )

        self.assertEqual(lunas_catalog_ref("mushroom", 39), ("luncheon", 50))
        self.assertEqual(
            catalog_kingdom_for_moon("mushroom", "base", moon=39), "luncheon"
        )
        self.assertEqual(LUNAS_CATALOG_SYNTHETIC[("mushroom", 39)], ("luncheon", 50))

        data = json.loads((CATALOG_DIR / "lunas-objetivos.json").read_text(encoding="utf-8"))
        keys = [(m["tags"][0], int(m["moon"])) for m in data["moons"]]
        self.assertEqual(len(keys), len(set(keys)), "tags[0]+moon debe ser único")
        self.assertIn(("luncheon", 39), keys)
        self.assertIn(("luncheon", 50), keys)
        self.assertNotIn(("mushroom", 39), keys)

        luncheon = [
            m for m in data["moons"] if m["tags"] and m["tags"][0] == "luncheon"
        ]
        self.assertEqual(luncheon[-1]["moon"], 50)
        self.assertIn("Peach", luncheon[-1]["name"])
        self.assertIn("painting", luncheon[-1]["tags"])
        ruined_i = next(
            i
            for i, m in enumerate(data["moons"])
            if m["tags"] and m["tags"][0] == "ruined"
        )
        self.assertEqual(data["moons"][ruined_i - 1]["moon"], 50)
        self.assertEqual(data["moons"][ruined_i - 1]["tags"][0], "luncheon")

    def test_no_availability_violations(self) -> None:
        self.assertEqual(collect_availability_violations(), [])


class GoalReferenciaHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ref = json.loads(
            (CATALOG_DIR / "goals_referencia.json").read_text(encoding="utf-8")
        )
        cls.by_goal = {g["goal"]: g for g in cls.ref["goals"]}

    def test_hub_metadata(self) -> None:
        self.assertIn("_hub", self.ref)
        self.assertIn("summaries", self.ref["_hub"])

    def test_ground_pound_has_summaries(self) -> None:
        g = self.by_goal["{{X}} Ground Pound Moons"]
        self.assertIn("ground_pound", g.get("bingo_groups") or [])
        self.assertEqual(g["pool_summary"]["n_moons"], 41)
        self.assertNotIn("n_moons", g)
        rows = g.get("individuales") or []
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["goal"], "7 Ground Pound Moons")
        self.assertEqual(rows[0]["kingdom"], "")

    def test_no_top_level_n_moons(self) -> None:
        with_n = [g["goal"] for g in self.ref["goals"] if "n_moons" in g]
        self.assertEqual(with_n, [])

    def test_no_top_level_regional_total(self) -> None:
        with_rt = [g["goal"] for g in self.ref["goals"] if "regional_total" in g]
        self.assertEqual(with_rt, [])

    def test_no_top_level_n_lista(self) -> None:
        with_nl = [g["goal"] for g in self.ref["goals"] if "n_lista" in g]
        self.assertEqual(with_nl, [])

    def test_regional_total_in_lista_summary(self) -> None:
        g = self.by_goal["{{X}} 8-Bit Regional Coins"]
        self.assertNotIn("regional_total", g)
        self.assertEqual(g["lista_summary"]["regional_total"], 29)
        keys = list(g["lista_summary"].keys())
        self.assertEqual(keys[:3], ["n_items", "regional_total", "by_kingdom"])

    def test_regional_lista_has_disponibilidad(self) -> None:
        g = self.by_goal["{{X}} Cap Regional Coins"]
        self.assertTrue(g["lista"])
        for item in g["lista"]:
            with self.subTest(id=item.get("id")):
                self.assertEqual(item.get("disponibilidad"), "revisit")
        self.assertEqual(
            g["lista_summary"]["by_disponibilidad"], {"revisit": 14}
        )

    def test_sand_ice_regional_disponibilidad_split(self) -> None:
        g = self.by_goal["{{X}} Sand Ice Regional Coins"]
        for item in g["lista"]:
            self.assertNotIn("zone", item)
        by_disp = {i.get("disponibilidad") for i in g["lista"]}
        self.assertEqual(by_disp, {"base", "mid_story"})
        self.assertEqual(
            g["lista_summary"]["by_disponibilidad"],
            {"base": 2, "mid_story": 2},
        )
        # zone vive en zonas_reino
        zl = json.loads((CATALOG_DIR / "zonas_reino.json").read_text(encoding="utf-8"))
        sand = next(k for k in zl["kingdoms"] if k["kingdom"] == "sand")
        ice_names = {i["name"] for i in g["lista"]}
        zones = {
            it["zone"]
            for it in sand["list"]
            if it["source"] == "regionals" and it["name"] in ice_names
        }
        self.assertEqual(zones, {"ice_cave", "underground_temple"})

    def test_total_moons_counts_in_lista_summary(self) -> None:
        g = self.by_goal["{{X}} Total Moons"]
        self.assertNotIn("n_moons", g)
        self.assertEqual(g["lista_summary"]["n_moons"], 434)
        self.assertEqual(g["lista_summary"]["n_odyssey_units"], 462)
        keys = list(g["lista_summary"].keys())
        self.assertEqual(keys.index("n_items") + 1, keys.index("n_moons"))
        self.assertEqual(keys.index("n_moons") + 1, keys.index("n_odyssey_units"))

    def test_lista_goal_has_lista_source(self) -> None:
        g = self.by_goal["{{X}} Unique Life Up Hearts"]
        self.assertEqual(g.get("lista_source"), "life_up_hearts")
        self.assertIn("lista_summary", g)
        self.assertEqual(g["lista_summary"]["n_items"], len(g["lista"]))

    def test_tag_only_on_moon_pool_goals(self) -> None:
        """tag[] = tags de lunas; pool lista usa bingo_groups, sin tag."""
        moon = self.by_goal["{{X}} 8-Bit Moons"]
        self.assertEqual(moon.get("pool"), "moons")
        self.assertEqual(moon.get("tag"), ["8bit"])
        lista = self.by_goal["{{X}} 8-Bit Regional Coins"]
        self.assertEqual(lista.get("pool"), "lista")
        self.assertNotIn("tag", lista)
        self.assertIn("8bit", lista.get("bingo_groups") or [])
        for g in self.by_goal.values():
            if g.get("pool") == "lista":
                self.assertNotIn("tag", g, g.get("goal"))
            elif g.get("pool") == "moons" and "tag" in g:
                self.assertIsInstance(g["tag"], list)
                self.assertTrue(g["tag"])
                self.assertTrue(all(isinstance(t, str) for t in g["tag"]))

    def test_summary_by_kingdom_follows_list_order(self) -> None:
        g = self.by_goal["{{X}} 8-Bit Moons"]
        moons = g["moons"]
        expected = []
        seen: set[str] = set()
        for moon in moons:
            k = moon.get("kingdom")
            if k and k not in seen:
                seen.add(k)
                expected.append(k)
        self.assertEqual(list(g["pool_summary"]["by_kingdom"].keys()), expected)

    def test_n_odyssey_units_after_n_moons_in_summaries(self) -> None:
        """n_odyssey_units solo con multilunas; justo tras n_moons."""
        bowser = self.by_goal["{{X}} Bowser's Moons"]
        ps = bowser["pool_summary"]
        self.assertIn("n_odyssey_units", ps)
        keys = list(ps.keys())
        self.assertEqual(keys.index("n_moons") + 1, keys.index("n_odyssey_units"))
        eight = self.by_goal["{{X}} 8-Bit Moons"]
        self.assertNotIn("n_odyssey_units", eight.get("pool_summary") or {})

    def test_summary_by_disponibilidad_follows_progression(self) -> None:
        g = self.by_goal["{{X}} 8-Bit Moons"]
        self.assertEqual(
            list(g["pool_summary"]["by_disponibilidad"].keys()),
            ["base", "mid_story", "world_peace"],
        )

    def test_lista_summary_by_kingdom_follows_list_order(self) -> None:
        g = self.by_goal["{{X}} 8-Bit Regional Coins"]
        lista = g["lista"]
        expected = []
        seen: set[str] = set()
        for item in lista:
            k = item.get("kingdom")
            if k and k not in seen:
                seen.add(k)
                expected.append(k)
        self.assertEqual(list(g["lista_summary"]["by_kingdom"].keys()), expected)

    def test_pool_summary_multiline_in_file(self) -> None:
        text = (CATALOG_DIR / "goals_referencia.json").read_text(encoding="utf-8")
        self.assertIn('"pool_summary": {\n', text)
        self.assertIn(
            '"by_kingdom": {"cascade": 2, "sand": 2, "lake": 1',
            text,
        )
        self.assertNotIn('"by_kingdom": {\n        "cascade": 2', text)


    def test_ground_pound_field_order(self) -> None:
        g = self.by_goal["{{X}} Ground Pound Moons"]
        keys = list(g.keys())
        self.assertEqual(keys[-1], "moons")
        self.assertEqual(
            keys[keys.index("pool") : keys.index("moons") + 1],
            ["pool", "moon_count_mode", "pool_summary", "moons"],
        )
        self.assertLess(keys.index("individuales"), keys.index("pool"))
        self.assertLess(keys.index("bingo_groups"), keys.index("pool"))

    def test_lista_goal_field_order(self) -> None:
        g = self.by_goal["{{X}} Deep Woods Regional Coins"]
        keys = list(g.keys())
        self.assertEqual(keys[-1], "lista")
        self.assertEqual(
            keys[keys.index("lista_summary") :],
            ["lista_summary", "lista"],
        )
        self.assertLess(keys.index("pool"), keys.index("lista_summary"))
        self.assertLess(keys.index("individuales"), keys.index("pool"))


class GoalListsTests(unittest.TestCase):
    def test_lists_counts(self) -> None:
        data = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        lists = data["lists"]
        self.assertEqual(data["n_lists"], len(lists))
        item_total = sum(len(v) for v in lists.values())
        self.assertEqual(data["n_items"], item_total)
        self.assertNotIn("n_with_zone", data)
        self.assertNotIn("n_without_zone", data)
        global_ids: list[int] = []
        for name in sorted(lists):
            rows = lists[name]
            locals_ = [int(r["id_list"]) for r in rows]
            self.assertTrue(all("id" in r and "id_list" in r for r in rows), name)
            self.assertEqual(list(rows[0])[:3], ["kingdom", "id", "id_list"])
            global_ids.extend(int(r["id"]) for r in rows)
        self.assertEqual(sorted(global_ids), list(range(1, data["n_items"] + 1)))
        self.assertEqual(global_ids, list(range(1, data["n_items"] + 1)))
        # binoculars: id_list 1..n secuencial
        binocs = lists["binoculars"]
        self.assertEqual(
            [r["id_list"] for r in binocs], list(range(1, len(binocs) + 1))
        )

    def test_disponibilidad_list_only_checkpoints_and_life_ups(self) -> None:
        self.assertEqual(collect_disponibilidad_list_violations(), [])

    def test_disponibilidad_matches_goals_referencia(self) -> None:
        self.assertEqual(collect_goal_lists_referencia_mismatches(), [])

    def test_lista_location_no_near(self) -> None:
        self.assertEqual(collect_location_field_violations(), [])

    def test_sphynx_zone_only_in_zonas_reino(self) -> None:
        """Zone no va en lista[] del hub; sí en zonas_reino (p.ej. Sand Sphynx)."""
        ref = json.loads(
            (CATALOG_DIR / "goals_referencia.json").read_text(encoding="utf-8")
        )
        g = next(x for x in ref["goals"] if x["goal"] == "Correct Wooded Sphynx Question")
        item = g["lista"][0]
        self.assertNotIn("zone", item)
        self.assertNotIn("near", item)
        self.assertNotIn("near_checkpoint", item)
        # Wooded/Moon Sphynx: lists.sphynxes; zone curada en zonas_reino
        # (p.ej. Sand Sphynx's Treasure Vault → zone sphynx).
        zl = json.loads((CATALOG_DIR / "zonas_reino.json").read_text(encoding="utf-8"))
        sand = next(k for k in zl["kingdoms"] if k["kingdom"] == "sand")
        vault = next(
            it
            for it in sand["list"]
            if it.get("name") == "Sphynx's Treasure Vault"
        )
        self.assertEqual(vault.get("zone"), "sphynx")
        gl = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        sphynxes = gl["lists"]["sphynxes"]
        self.assertEqual(len(sphynxes), 4)
        self.assertEqual(
            [x["kingdom"] for x in sphynxes],
            ["sand", "wooded", "seaside", "moon"],
        )
        item = g["lista"][0]
        self.assertEqual(item.get("source"), "sphynxes")
        self.assertEqual(item.get("name"), "Wooded Sphynx")


class RegionalCategoriesTests(unittest.TestCase):
    def test_regional_goals_have_no_moontype_category(self) -> None:
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        for obj in data["objectives"]:
            goal = str(obj.get("goal") or "")
            if not goal.endswith(" Regional Coins") and not goal.startswith(
                "All Regional Coins in "
            ):
                continue
            with self.subTest(goal=goal):
                for key in ("board_categories", "line_categories"):
                    cats = obj.get(key) or []
                    self.assertNotIn(
                        "moontype",
                        cats,
                        f"{goal} no debe llevar moontype en {key}",
                    )


if __name__ == "__main__":
    unittest.main()
