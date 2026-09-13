"""Integridad de Catalog/ respecto al Combined y project.json."""
from __future__ import annotations

import json
import unittest
from collections import Counter, defaultdict
from typing import Any, ClassVar

from catalog_lib import (
    ALL_KINGDOMS_REFERENCE_PATH,
    CATALOG_DIR,
    DEFAULT_GOALS_REFERENCE_PATH,
    JSON_PATH,
    KINGDOM_COLUMNS,
    LONG_GOALS_REFERENCE_PATH,
    SHORT_GOALS_REFERENCE_PATH,
    _resolve_bingo_group_moons_raw,
    canonicalize_palabra,
    catalog_tag_ids,
    collect_availability_violations,
    load_project,
)
from goal_list_lib import (
    collect_disponibilidad_list_violations,
    collect_goal_lists_referencia_mismatches,
    collect_location_field_violations,
)
from export_palabras_inventario import (
    _build_capture_lista_counts,
    _build_goal_list_counts,
    _build_grupo_item_counts,
    _build_grupo_lista_computed_counts,
    _resolve_lista_n,
    _slug as palabra_slug,
    parse_usos,
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
            "zonas_inventario.json",
            "palabras_inventario.json",
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
        """Vista de revisión: zones[] en alfa por slug; ≥3 por zona."""
        data = json.loads((CATALOG_DIR / "zonas_inventario.json").read_text(encoding="utf-8"))
        self.assertEqual(data["n_zones"], len(data["zones"]))
        self.assertEqual(data["n_zoned"], sum(z["n_total"] for z in data["zones"]))
        self.assertEqual(data["n_total"], data["n_moons"] + data["n_items"])
        self.assertEqual(data["n_total"], data["n_zoned"] + data["n_without_zone"])
        self.assertEqual(data["n_items"], 582)
        self.assertNotIn("n_total_all", data)
        zones = [z["zone"] for z in data["zones"]]
        self.assertEqual(zones, sorted(zones, key=str.lower))
        self.assertEqual(len(zones), len(set(zones)))
        self.assertEqual([z["orden"] for z in data["zones"]], list(range(1, data["n_zones"] + 1)))
        for z in data["zones"]:
            with self.subTest(zone=z["zone"]):
                self.assertGreaterEqual(z["n_total"], 1)
                self.assertEqual(z["n_total"], len(z["list"]))
                self.assertEqual(sum(z["by_source"].values()), z["n_total"])
                src_keys = list(z["by_source"])
                if "moon" in z["by_source"]:
                    self.assertEqual(src_keys[0], "moon")
                    self.assertEqual(src_keys[1:], sorted(src_keys[1:]))
                else:
                    self.assertEqual(src_keys, sorted(src_keys))
                kingdom = z.get("kingdom")
                for it in z["list"]:
                    if kingdom is not None:
                        self.assertEqual(it["kingdom"], kingdom)
                    self.assertIn("zone", it)
                    self.assertIn("id", it)
                    self.assertIn("id_kingdom", it)
        self.assertIn("cap_odyssey", zones)
        self.assertNotIn("odyssey", zones)

    def test_palabras_inventario_alpha_and_usos(self) -> None:
        """Slugs en alfa; usos ⊆ uso_order; ejemplos multi-uso."""
        data = json.loads(
            (CATALOG_DIR / "palabras_inventario.json").read_text(encoding="utf-8")
        )
        words = data["palabras"]
        self.assertEqual(data["n_palabras"], len(words))
        self.assertEqual(
            [w["palabra"] for w in words],
            sorted(w["palabra"] for w in words),
        )
        self.assertEqual([w["id"] for w in words], list(range(1, len(words) + 1)))
        order = list(data["uso_order"])
        for row in words:
            with self.subTest(palabra=row["palabra"]):
                parsed = parse_usos(row["usos"])
                self.assertEqual(row["n_usos"], sum(parsed.values()))
                self.assertTrue(row["usos"])
                self.assertEqual(
                    list(parsed),
                    [u for u in order if u in parsed],
                )
                self.assertTrue(all(u in order for u in parsed))
                for uso, n in parsed.items():
                    if uso in ("bingo", "goal", "luna"):
                        self.assertGreater(n, 0)
                    elif uso == "captura":
                        self.assertGreaterEqual(n, 0)
                    elif uso == "grupo":
                        self.assertEqual(n, 1)
                    elif uso == "zona":
                        self.assertEqual(n, 1)
                    elif uso == "lista":
                        self.assertGreaterEqual(n, 0)
                    elif uso == "tag":
                        self.assertGreater(n, 0)
                        if "luna" in parsed:
                            self.assertEqual(n, parsed["luna"])
                    else:
                        self.assertEqual(n, 0)
                    if "grupo" in parsed and uso in ("goal", "luna", "lista"):
                        # Conteos de grupo se validan más abajo con bingo_groups.
                        pass
        by_word = {w["palabra"]: w for w in words}
        sand_usos = parse_usos(by_word["sand"]["usos"])
        self.assertIn("bingo", sand_usos)
        self.assertIn("grupo", sand_usos)
        self.assertNotIn("reino", sand_usos)
        self.assertNotIn("mushroom", by_word)
        self.assertNotIn("reino", data["uso_order"])
        self.assertNotIn("reino", data["n_by_uso"])
        bit_usos = parse_usos(by_word["8bit"]["usos"])
        self.assertIn("tag", bit_usos)
        self.assertIn("grupo", bit_usos)
        self.assertIn("zona", parse_usos(by_word["tostarena"]["usos"]))
        # Captain Toad: id grupo = tag captain_toad (bingo_lineas sigue captaintoad).
        toad = parse_usos(by_word["captain_toad"]["usos"])
        self.assertIn("bingo", toad)
        self.assertIn("grupo", toad)
        self.assertIn("tag", toad)
        self.assertEqual(toad["goal"], 12)
        self.assertEqual(toad["luna"], 11)
        self.assertNotIn("lista", toad)
        cappy = parse_usos(by_word["cappy"]["usos"])
        self.assertIn("grupo", cappy)
        self.assertIn("luna", cappy)
        self.assertEqual(parse_usos(by_word["cappy"]["usos"]).get("lista"), 1)
        self.assertNotIn("captaintoad", by_word)
        self.assertNotIn("subarea", by_word)
        self.assertNotIn("storymoons", by_word)
        self.assertNotIn("shopping", by_word)
        self.assertNotIn("checkpoints", by_word)
        self.assertNotIn("npc_moons", by_word)
        self.assertNotIn("girders", by_word)
        self.assertNotIn("bosses", by_word)
        self.assertNotIn("shops", by_word)
        self.assertNotIn("talkatoos", by_word)
        self.assertNotIn("levers", by_word)
        self.assertIn("grupo", parse_usos(by_word["sub_area"]["usos"]))
        self.assertIn("grupo", parse_usos(by_word["story_moon"]["usos"]))
        self.assertIn("grupo", parse_usos(by_word["shop"]["usos"]))
        self.assertIn("grupo", parse_usos(by_word["checkpoint"]["usos"]))
        self.assertIn("grupo", parse_usos(by_word["npc"]["usos"]))
        self.assertEqual(
            by_word["artistic"]["usos"],
            {"bingo": 15, "goal": 15, "grupo": 1, "luna": 13},
        )
        artistic = parse_usos(by_word["artistic"]["usos"])
        self.assertNotIn("tag", artistic)
        self.assertEqual(by_word["artistic"]["n_usos"], 44)
        # Capturas: 46 filas; uso captura omitido si pool=0 (taxi/tree); Σ = hub 163 + sin luna.
        self.assertIn("captura", parse_usos(by_word["chain_chomp"]["usos"]))
        self.assertIn("grupo", parse_usos(by_word["chain_chomp"]["usos"]))
        self.assertEqual(
            parse_usos(by_word["chain_chomp"]["usos"]),
            {"captura": 5, "goal": 1, "grupo": 1, "luna": 5, "tag": 5},
        )
        self.assertEqual(
            parse_usos(by_word["captures"]["usos"]),
            {"goal": 48, "grupo": 1, "lista": 22, "luna": 163, "tag": 163},
        )
        self.assertIn("captura", parse_usos(by_word["big_chain_chomp"]["usos"]))
        self.assertIn("goal", parse_usos(by_word["big_chain_chomp"]["usos"]))
        self.assertIn("captura", parse_usos(by_word["broodes_chain_chomp"]["usos"]))
        self.assertIn("goal", parse_usos(by_word["broodes_chain_chomp"]["usos"]))
        self.assertEqual(
            data["n_by_uso"]["captura"],
            sum(parse_usos(w["usos"]).get("captura", 0) for w in words),
        )
        self.assertEqual(data["n_by_uso"]["captura"], 182)
        captura_words = [w for w in words if "captura" in parse_usos(w["usos"])]
        self.assertEqual(len(captura_words), 44)
        self.assertEqual(data["n_palabras_by_uso"]["captura"], 44)
        self.assertNotIn("captura", parse_usos(by_word["taxi"]["usos"]))
        self.assertNotIn("captura", parse_usos(by_word["tree"]["usos"]))
        lists_data = json.loads(
            (CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8")
        )["lists"]
        groups_data = json.loads(
            (CATALOG_DIR / "bingo_groups.json").read_text(encoding="utf-8")
        )["groups"]
        for list_name in lists_data:
            with self.subTest(lista=list_name):
                word = canonicalize_palabra(list_name, uso="lista") or list_name
                self.assertIn(
                    "lista",
                    parse_usos(by_word[word]["usos"]),
                    f"falta lista para clave {list_name!r} (canónico {word!r})",
                )
        for g in groups_data:
            gid = g["id"]
            with self.subTest(grupo=gid):
                word = canonicalize_palabra(gid, uso="grupo") or gid
                self.assertIn(
                    "grupo",
                    parse_usos(by_word[word]["usos"]),
                    f"falta grupo para id {gid!r} (canónico {word!r})",
                )
        self.assertEqual(data["n_by_uso"]["grupo"], 130)
        self.assertEqual(
            data["n_by_uso"]["lista"],
            sum(parse_usos(w["usos"]).get("lista", 0) for w in words),
        )
        self.assertEqual(data["n_by_uso"]["zona"], 95)
        lineas_data = json.loads(
            (CATALOG_DIR / "bingo_lineas.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            data["n_by_uso"]["bingo"],
            sum(g.get("n_goals", 0) for g in lineas_data.get("groups") or []),
        )
        self.assertEqual(
            data["n_by_uso"]["tag"],
            sum(parse_usos(w["usos"]).get("tag", 0) for w in words),
        )
        self.assertEqual(
            data.get("uso_fijo"),
            ["grupo", "zona"],
        )
        self.assertEqual(
            data.get("uso_palabra_fija"),
            ["bingo", "captura", "grupo", "lista", "tag", "zona"],
        )
        self.assertEqual(
            len(data["uso_fijo"]) + len(data["uso_palabra_fija"]),
            len(data["uso_order"]),
        )
        self.assertNotIn("uso_variable", data)
        self.assertNotIn("n_palabras_fija_by_uso", data)
        self.assertEqual(
            [u for u in order if u not in data["uso_fijo"]],
            ["bingo", "captura", "goal", "lista", "luna", "tag"],
        )
        self.assertEqual(
            [u for u in order if u not in data["uso_palabra_fija"]],
            ["goal", "luna"],
        )
        n_palabras_by_uso = data.get("n_palabras_by_uso") or {}
        for row in words:
            parsed = parse_usos(row["usos"])
            for u in parsed:
                self.assertIn(u, n_palabras_by_uso)
        for uso in order:
            self.assertEqual(
                n_palabras_by_uso.get(uso, 0),
                sum(1 for w in words if uso in parse_usos(w["usos"])),
            )
        for uso, want in {
            "bingo": 24,
            "captura": 44,
            "grupo": 130,
            "lista": 50,
            "tag": 99,
            "zona": 95,
        }.items():
            self.assertEqual(n_palabras_by_uso[uso], want)
        self.assertEqual(n_palabras_by_uso["grupo"], data["n_by_uso"]["grupo"])
        self.assertEqual(n_palabras_by_uso["zona"], data["n_by_uso"]["zona"])
        caps_data = json.loads(
            (CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8")
        )
        from export_palabras_inventario import _capture_row_palabra

        capture_slugs = {
            w
            for row in caps_data.get("captures") or []
            if isinstance(row, dict)
            for w in [_capture_row_palabra(row)]
            if w
        }
        anchors = {"grupo", "zona", "bingo", "captura", "lista", "tag"}
        for row in words:
            parsed = parse_usos(row["usos"])
            with self.subTest(palabra=row["palabra"]):
                for var in ("goal", "luna"):
                    if var in parsed:
                        self.assertTrue(
                            anchors & set(parsed)
                            or row["palabra"] in capture_slugs,
                            f"{row['palabra']!r}: {var} sin ancla de catálogo",
                        )
        zones_data = json.loads(
            (CATALOG_DIR / "zonas_inventario.json").read_text(encoding="utf-8")
        )["zones"]
        tags_data = json.loads(
            (CATALOG_DIR / "tags_inventario.json").read_text(encoding="utf-8")
        )
        for uso, expected in {
            "grupo": len(groups_data),
            "zona": len(zones_data),
        }.items():
            with self.subTest(uso=uso):
                self.assertEqual(data["n_by_uso"][uso], expected)
        self.assertEqual(len(lists_data), 20)
        goal_list_counts = _build_goal_list_counts()
        grupo_counts = _build_grupo_item_counts()
        capture_lista_counts = _build_capture_lista_counts()
        grupo_lista_computed = _build_grupo_lista_computed_counts()
        groups_by_id = {g["id"]: g for g in groups_data}
        want_lista = sum(
            _resolve_lista_n(
                row["palabra"],
                set(parse_usos(row["usos"])),
                grupo_counts=grupo_counts,
                goal_list_counts=goal_list_counts,
                capture_lista_counts=capture_lista_counts,
                grupo_lista_computed=grupo_lista_computed,
            )
            for row in words
            if "lista" in parse_usos(row["usos"])
        )
        self.assertEqual(data["n_by_uso"]["lista"], want_lista)
        self.assertEqual(
            parse_usos(by_word["boxer_shorts"]["usos"]),
            {"lista": 1},
        )
        self.assertEqual(
            goal_list_counts["boxer_shorts"],
            len(lists_data["boxer_shorts"]),
        )
        for kingdom in KINGDOM_COLUMNS:
            if kingdom not in by_word:
                continue
            parsed_k = parse_usos(by_word[kingdom]["usos"])
            if "lista" not in parsed_k:
                continue
            with self.subTest(reino=kingdom):
                n = (groups_by_id[kingdom].get("n") or {}).get("lista", 0)
                self.assertEqual(parsed_k["lista"], n)
        self.assertEqual(
            parse_usos(by_word["bowser"]["usos"])["lista"],
            groups_by_id["bowser"]["n"]["lista"],
        )
        self.assertEqual(len(caps_data.get("captures") or []), 46)
        self.assertEqual(len(tags_data.get("tags") or []), 99)
        # goal/luna: sin conteo fijo de catálogo; varían con otros usos.
        self.assertNotIn("n_goals", data)
        self.assertNotIn("n_lunas", data)
        self.assertNotIn("n_capturas", data)
        self.assertNotIn("n_bingo", data)
        for row in zones_data:
            word = canonicalize_palabra(palabra_slug(row["zone"]), uso="zona") or palabra_slug(
                row["zone"]
            )
            if not word:
                continue
            with self.subTest(zone=row["zone"]):
                self.assertIn(
                    "zona",
                    parse_usos(by_word[word]["usos"]),
                    f"falta zona para {row['zone']!r}",
                )
        self.assertIn("zona", parse_usos(by_word["cap_odyssey"]["usos"]))
        self.assertIn("zona", parse_usos(by_word["sand_southwest"]["usos"]))
        self.assertNotIn("odyssey", by_word)
        # Capturas: goal/luna/lista + captura (pool captures repartido por slug).
        self.assertIn("captura", parse_usos(by_word["binoculars"]["usos"]))
        self.assertIn("lista", parse_usos(by_word["binoculars"]["usos"]))
        self.assertIn("goal", parse_usos(by_word["binoculars"]["usos"]))
        self.assertNotIn("luna", parse_usos(by_word["binoculars"]["usos"]))
        self.assertIn("luna", parse_usos(by_word["meat"]["usos"]))
        self.assertEqual(
            by_word["meat"]["usos"],
            {"captura": 1, "goal": 1, "luna": 1},
        )
        self.assertEqual(by_word["meat"]["n_usos"], 3)
        self.assertIn("luna", parse_usos(by_word["bowser_statue"]["usos"]))
        self.assertIn("goal", parse_usos(by_word["bowser_statue"]["usos"]))
        self.assertEqual(len(lineas_data.get("groups") or []), 24)
        self.assertEqual(
            parse_usos(by_word["bowser"]["usos"])["bingo"],
            next(g["n_goals"] for g in lineas_data["groups"] if g["id"] == "bowser"),
        )
        self.assertEqual(
            parse_usos(by_word["binoculars"]["usos"]),
            {"captura": 14, "goal": 1, "lista": 14},
        )
        self.assertEqual(
            parse_usos(by_word["big_chain_chomp"]["usos"]),
            {"captura": 1, "goal": 1},
        )
        self.assertEqual(
            parse_usos(by_word["boulder"]["usos"]),
            {"captura": 1, "goal": 1},
        )
        self.assertEqual(
            parse_usos(by_word["broodes_chain_chomp"]["usos"]),
            {"captura": 1, "goal": 1, "lista": 2, "luna": 1},
        )
        self.assertEqual(
            parse_usos(by_word["cactus"]["usos"]),
            {"captura": 3, "goal": 1, "luna": 3},
        )
        self.assertEqual(
            parse_usos(by_word["tree"]["usos"]),
            {"goal": 1, "luna": 3},
        )
        self.assertEqual(
            parse_usos(by_word["checkpoint"]["usos"]),
            {"bingo": 14, "goal": 14, "grupo": 1, "lista": 78},
        )
        self.assertEqual(
            parse_usos(by_word["ground_pound"]["usos"]),
            {"goal": 5, "grupo": 1, "lista": 4, "luna": 41, "tag": 41},
        )
        self.assertEqual(
            parse_usos(by_word["regionalcoins"]["usos"]),
            {"bingo": 24, "goal": 24, "grupo": 1, "lista": 274},
        )
        self.assertEqual(
            parse_usos(by_word["cactus_tree"]["usos"]),
            {"goal": 1, "grupo": 1, "luna": 3, "tag": 3},
        )
        self.assertEqual(
            parse_usos(by_word["8bit"]["usos"]),
            {"goal": 4, "grupo": 1, "lista": 39, "luna": 18, "tag": 18},
        )
        self.assertEqual(by_word["8bit"]["n_usos"], 80)
        self.assertEqual(
            parse_usos(by_word["uproot"]["usos"]),
            {"captura": 11, "goal": 1, "grupo": 1, "lista": 1, "luna": 2, "tag": 2},
        )
        # Grupo: goal/luna/lista = n del bingo_groups (lista efectiva si omitida).
        groups_by_id = {g["id"]: g for g in groups_data}
        for g in groups_data:
            gid = g["id"]
            parsed = parse_usos(by_word[gid]["usos"])
            n_raw = g.get("n")
            n_counts = n_raw if isinstance(n_raw, dict) else {}
            with self.subTest(grupo_items=gid):
                if int(n_counts.get("objectives") or 0) > 0:
                    self.assertEqual(parsed.get("goal"), n_counts["objectives"])
                if int(n_counts.get("moons") or 0) > 0:
                    self.assertEqual(parsed.get("luna"), n_counts["moons"])
                if "lista" in parsed:
                    want_lista_n = _resolve_lista_n(
                        gid,
                        set(parsed),
                        grupo_counts=grupo_counts,
                        goal_list_counts=goal_list_counts,
                        capture_lista_counts=capture_lista_counts,
                        grupo_lista_computed=grupo_lista_computed,
                    )
                    self.assertEqual(parsed["lista"], want_lista_n)
        self.assertEqual(
            parse_usos(by_word["boss"]["usos"]),
            {"goal": 6, "grupo": 1, "lista": 19, "luna": 14, "tag": 14},
        )
        self.assertEqual(
            data["n_by_uso"]["bingo"],
            sum(parse_usos(w["usos"]).get("bingo", 0) for w in words),
        )
        fixed = set(data.get("uso_fijo") or [])
        fixed_word_usos = fixed
        self.assertEqual(
            sum(data["n_by_uso"][u] for u in fixed_word_usos),
            sum(
                1
                for w in words
                for u in parse_usos(w["usos"])
                if u in fixed_word_usos
            ),
        )
        self.assertEqual(
            data["n_by_uso"]["goal"],
            sum(parse_usos(w["usos"]).get("goal", 0) for w in words),
        )
        self.assertEqual(
            data["n_by_uso"]["luna"],
            sum(parse_usos(w["usos"]).get("luna", 0) for w in words),
        )
        self.assertEqual(
            data["n_by_uso"]["tag"],
            sum(
                parse_usos(w["usos"]).get("luna", 0)
                for w in words
                if "tag" in parse_usos(w["usos"])
            ),
        )

    def test_zonas_inventario_sand_tostarena(self) -> None:
        """zonas_inventario: zones[] con ítems kingdom/source/name/zone."""
        data = json.loads(
            (CATALOG_DIR / "zonas_inventario.json").read_text(encoding="utf-8")
        )
        self.assertIn("zones", data)
        self.assertNotIn("kingdoms", data)
        by_zone = {z["zone"]: z for z in data["zones"]}
        tost = by_zone["tostarena"]
        self.assertEqual(tost["kingdom"], "sand")
        self.assertGreaterEqual(tost["n_total"], 12)
        self.assertEqual(tost["n_total"], len(tost["list"]))
        self.assertEqual(sum(tost["by_source"].values()), tost["n_total"])
        src_keys = list(tost["by_source"])
        self.assertEqual(src_keys[0], "moon")
        self.assertEqual(src_keys[1:], sorted(src_keys[1:]))
        tost_sources = {it["source"] for it in tost["list"]}
        self.assertIn("regionals", tost_sources)
        self.assertIn("pixel_luigis", tost_sources)
        self.assertIn("jaxi_stands", tost_sources)
        self.assertEqual(
            sum(1 for it in tost["list"] if it["source"] == "regionals"), 7
        )
        for it in tost["list"]:
            self.assertEqual(it["kingdom"], "sand")
            self.assertEqual(it["zone"], "tostarena")
            self.assertIn("source", it)
            self.assertIn("name", it)
            self.assertNotIn("tags", it)

        cap_moons = {
            it["id_kingdom"]: it
            for z in data["zones"]
            for it in z["list"]
            if it.get("kingdom") == "cap" and it.get("source") == "moon"
        }
        self.assertEqual(cap_moons[1]["zone"], "odyssey")
        self.assertEqual(cap_moons[2]["zone"], "central_plaza")
        self.assertEqual(cap_moons[6]["zone"], "top_hat_tower")
        self.assertEqual(cap_moons[8]["zone"], "top_hat_tower")
        self.assertEqual(cap_moons[5]["zone"], "central_plaza")
        self.assertNotIn("fog", by_zone)

        sand_moons = [
            it
            for z in data["zones"]
            for it in z["list"]
            if it.get("kingdom") == "sand" and it.get("source") == "moon"
        ]
        sand_moons.sort(key=lambda it: int(it["id_kingdom"]))
        self.assertEqual(sand_moons[0]["id_kingdom"], 1)
        self.assertEqual(sand_moons[0].get("zone"), "ruins")
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
            [(it["id_kingdom"], it["name"]) for it in sand_moons],
            [(int(m["moon"]), m["name"]) for m in sand_lunas],
        )

        self.assertEqual(data["n_total"], data["n_moons"] + data["n_items"])
        self.assertIn("n_without_zone", data)
        gl = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        caps = json.loads(
            (CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8")
        )
        n_binoculars = len(
            next(
                r["lista"]
                for r in caps["captures"]
                if r.get("capture") == "Binoculars"
            )
        )
        self.assertEqual(data["n_items"], gl["n_items"] + n_binoculars)
        self.assertEqual(data["n_items"], 582)
        self.assertNotIn("n_with_zone", gl)
        self.assertNotIn("n_without_zone", gl)
        self.assertNotIn("binoculars", gl["lists"])
        # Binoculars cuentan en n_items pero no van a zones[] (sin zone).
        bin_in_zones = [
            it
            for z in data["zones"]
            for it in z["list"]
            if it.get("source") == "binoculars"
        ]
        self.assertEqual(bin_in_zones, [])
        self.assertGreaterEqual(data["n_without_zone"], n_binoculars)
        pixel_sources = {
            it["source"]
            for z in data["zones"]
            for it in z["list"]
            if it.get("kingdom") == "cap" and it["source"].startswith("pixel_cat_")
        }
        self.assertEqual(pixel_sources, {"pixel_cat_marios", "pixel_cat_peaches"})
        self.assertIn("regionals", gl["lists"])
        self.assertEqual(len(gl["lists"]["regionals"]), 274)

    def test_shops_drive_merchandise_zones(self) -> None:
        """Shops/merchandise: zone solo en zonas_inventario (heredada por reino)."""
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
        zl = json.loads(
            (CATALOG_DIR / "zonas_inventario.json").read_text(encoding="utf-8")
        )
        items = [it for z in zl["zones"] for it in z["list"]]
        sand_shop = next(
            it
            for it in items
            if it["source"] == "shops"
            and it["name"] == "Crazy Cap"
            and it["kingdom"] == "sand"
        )
        self.assertEqual(sand_shop["zone"], "tostarena")
        metro_shop = next(
            it
            for it in items
            if it["source"] == "shops"
            and it["name"] == "Crazy Cap"
            and it["kingdom"] == "metro"
        )
        self.assertEqual(metro_shop["zone"], "crazy_cap")
        for name in (
            "costume_sets",
            "hats",
            "souvenirs",
            "stickers",
            "boxer_shorts",
        ):
            for it in items:
                if it["source"] == name and it["kingdom"] == "sand":
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
        # Binoculars: ubicaciones en capturas_lunas (no lists.binoculars).
        bins = build_goal_lista("Capture {{X}} Binoculars", {}, kingdom=None)
        self.assertGreater(len(bins), 0)
        self.assertNotIn(
            "binoculars",
            json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))[
                "lists"
            ],
        )

    def test_goal_icons_non_smo_counter(self) -> None:
        """Cabecera: conteos de goals e icons coherentes con Combined."""
        icons = json.loads((CATALOG_DIR / "goal_icons.json").read_text(encoding="utf-8"))
        self.assertIn("n_goals_non_smo", icons)
        self.assertIn("n_goals_one_icon", icons)
        self.assertIn("n_goals_multi_icon", icons)
        self.assertIn("n_goals_smo_only", icons)
        self.assertIn("n_icons_shared", icons)
        self.assertIn("n_icons_by_n_goals", icons)
        expected_non_smo: set[str] = set()
        expected_smo_only: set[str] = set()
        n_one = 0
        n_multi = 0
        n_active = 0
        n_no_icon = 0
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        for obj in data["objectives"]:
            if obj.get("disabled"):
                continue
            goal = str(obj.get("goal") or "")
            if not goal:
                continue
            n_active += 1
            icon_list = [str(i) for i in (obj.get("icons") or []) if i]
            if not icon_list:
                n_no_icon += 1
                continue
            if any(not i.startswith("smo/") for i in icon_list):
                expected_non_smo.add(goal)
            else:
                expected_smo_only.add(goal)
            if len(icon_list) == 1:
                n_one += 1
            elif len(icon_list) >= 2:
                n_multi += 1
        self.assertEqual(icons["n_goals"], n_active)
        self.assertEqual(icons["n_goals_no_icon"], n_no_icon)
        self.assertEqual(icons["n_goals_non_smo"], len(expected_non_smo))
        self.assertEqual(icons["n_goals_smo_only"], len(expected_smo_only))
        self.assertEqual(icons["n_goals_one_icon"], n_one)
        self.assertEqual(icons["n_goals_multi_icon"], n_multi)
        self.assertEqual(
            icons["n_goals_one_icon"] + icons["n_goals_multi_icon"],
            icons["n_goals_with_icon"],
        )
        self.assertEqual(
            icons["n_goals_smo_only"] + icons["n_goals_non_smo"],
            icons["n_goals_with_icon"],
        )
        self.assertEqual(
            icons["n_goals_with_icon"] + icons["n_goals_no_icon"],
            icons["n_goals"],
        )
        self.assertEqual(
            icons["n_icons_shared"],
            sum(1 for e in icons["icons"] if int(e.get("n_goals") or 0) > 1),
        )
        by_n = icons["n_icons_by_n_goals"]
        self.assertEqual(sum(int(v) for v in by_n.values()), icons["n_icons"])
        self.assertEqual(
            icons["n_icons_shared"],
            sum(int(n) for k, n in by_n.items() if int(k) >= 2),
        )
        for entry in icons["icons"]:
            n = int(entry.get("n_goals") or 0)
            self.assertEqual(entry.get("shared"), n >= 2)
        # Cada bucket del histograma coincide con los iconos.
        hist: dict[int, int] = defaultdict(int)
        for entry in icons["icons"]:
            hist[int(entry.get("n_goals") or 0)] += 1
        self.assertEqual(
            {str(k): v for k, v in sorted(hist.items())},
            {str(k): int(v) for k, v in by_n.items()},
        )
        self.assertEqual(icons["n_used"] + icons["n_unused"], icons["n_icons"])
        if "n_official" in icons:
            self.assertEqual(
                icons["n_icons_extra"],
                icons["n_icons"] - icons["n_official"],
            )
        self.assertGreater(icons["n_goals_non_smo"], 0)
        self.assertGreater(icons["n_goals_multi_icon"], 0)
        self.assertGreater(icons["n_icons_shared"], 0)

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
                    {
                        "kingdom",
                        "moon",
                        "name",
                        "disponibilidad",
                        "goal",
                        "tag",
                        "odyssey_units",
                    },
                    g.get("id"),
                )
                self.assertIn("goal", m, g.get("id"))
                self.assertIn("tag", m, g.get("id"))
                self.assertIsInstance(m["goal"], bool, g.get("id"))
                self.assertIsInstance(m["tag"], bool, g.get("id"))
            keys = list(g.keys())
            n = g.get("n") or {}
            pool_moons = list(g.get("moons") or [])
            if pool_moons:
                self.assertEqual(
                    n.get("goal"),
                    sum(1 for m in pool_moons if m.get("goal")),
                    g.get("id"),
                )
                self.assertEqual(
                    n.get("tag"),
                    sum(1 for m in pool_moons if m.get("tag")),
                    g.get("id"),
                )
            if "odyssey_units" in n and pool_moons:
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
                {"objectives", "moons", "lista"},
                g.get("id"),
            )
            self.assertNotIn("goals", g["has"], g.get("id"))
            self.assertTrue(
                {"objectives", "moons", "goal", "tag", "lista"} <= set(n),
                g.get("id"),
            )
            self.assertNotIn("has_goals", g, g.get("id"))
            self.assertNotIn("n_objectives", g, g.get("id"))
            self.assertNotIn("n_odyssey_units", g, g.get("id"))
        boss = by_id["boss"]
        self.assertEqual(boss["kind"], "todo")
        self.assertEqual(boss["n"]["moons"], 14)
        self.assertTrue(boss["tag_inventario"])
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
        checkpoint = by_id["checkpoint"]
        self.assertEqual(checkpoint["kind"], "goals+lista")
        self.assertEqual(checkpoint["n"]["moons"], 0)
        self.assertEqual(checkpoint["n"]["lista"], 78)
        if checkpoint.get("lista"):
            self.assertEqual(checkpoint.get("lista_source"), "checkpoints")
        else:
            self.assertNotIn("lista_source", checkpoint)
            self.assertEqual(checkpoint["lista_summary"]["n_items"], 78)
            self.assertIn("by_kingdom", checkpoint["lista_summary"])
        self.assertIn("{{X}} Total Checkpoints", [o["goal"] for o in checkpoint["objectives"]])
        self.assertIn("{{X}} Cap Checkpoints", [o["goal"] for o in checkpoint["objectives"]])
        regionals = by_id["regionalcoins"]
        self.assertEqual(regionals["kind"], "goals+lista")
        self.assertEqual(regionals["n"]["moons"], 0)
        self.assertEqual(regionals["n"]["lista"], 274)
        self.assertNotIn("lista", regionals)
        self.assertNotIn("lista_source", regionals)
        self.assertEqual(regionals["lista_summary"]["n_items"], 274)
        self.assertIn("regional_total", regionals["lista_summary"])
        self.assertIn("by_kingdom", regionals["lista_summary"])
        self.assertIn(
            "{{X}} Total Regional Coins",
            [o["goal"] for o in regionals["objectives"]],
        )
        self.assertIn(
            "{{X}} Cap Regional Coins",
            [o["goal"] for o in regionals["objectives"]],
        )
        captures = by_id["captures"]
        self.assertEqual(captures["kind"], "todo")
        self.assertEqual(captures["n"]["moons"], 163)
        self.assertNotIn("moons", captures)
        self.assertEqual(captures["moons_summary"]["n_moons"], 163)
        self.assertNotIn("moon_keys", captures["moons_summary"])
        self.assertIn("by_kingdom", captures["moons_summary"])
        self.assertEqual(
            len(_resolve_bingo_group_moons_raw(captures)),
            captures["moons_summary"]["n_moons"],
        )
        sub_area = by_id["sub_area"]
        self.assertEqual(sub_area["n"]["moons"], 76)
        self.assertNotIn("moons", sub_area)
        self.assertEqual(sub_area["moons_summary"]["n_moons"], 76)
        self.assertNotIn("moon_keys", sub_area["moons_summary"])
        self.assertIn("by_kingdom", sub_area["moons_summary"])
        self.assertEqual(
            len(_resolve_bingo_group_moons_raw(sub_area)),
            sub_area["moons_summary"]["n_moons"],
        )
        for line_id in (
            "artistic",
            "story_moon",
            "sub_area",
            "captain_toad",
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
        self.assertEqual(nature["n"]["moons"], 24)
        self.assertEqual(by_id["fauna"]["n"]["moons"], 12)
        self.assertEqual(by_id["flora"]["n"]["moons"], 13)
        # nature ≠ fauna+flora (pools solapan / filtran distinto).
        self.assertNotEqual(
            nature["n"]["moons"],
            by_id["fauna"]["n"]["moons"] + by_id["flora"]["n"]["moons"],
        )
        self.assertNotIn("regionals", by_id)
        self.assertNotIn("storymoons", by_id)  # → story_moon
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
        trop = by_id["tropical_wiggler"]
        self.assertEqual(trop["kind"], "goals+moons")
        self.assertGreater(trop["n"]["moons"], 0)
        self.assertEqual(trop["n"]["lista"], 0)
        self.assertNotIn("moon_tag", trop)
        self.assertNotIn("_note", trop)
        shop = by_id["shop"]
        self.assertEqual(shop["kind"], "todo")
        self.assertIn("lista_source", shop)
        self.assertEqual(shop.get("lista_source"), "shops")
        self.assertEqual(shop["n"]["moons"], 11)
        self.assertEqual(shop["n"]["lista"], 11)
        self.assertEqual(shop["n"]["objectives"], 12)
        self.assertNotIn("boxer_shorts", str(shop.get("lista_source") or ""))
        self.assertFalse(
            any(i.get("source") == "boxer_shorts" for i in shop.get("lista") or [])
        )
        self.assertNotIn(
            "Snow Boxer Shorts Moon",
            [o["goal"] for o in shop["objectives"]],
        )
        merch = by_id["merchandise"]
        self.assertEqual(merch["kind"], "goals+lista")
        self.assertEqual(merch["n"]["moons"], 0)
        self.assertEqual(merch["n"]["lista"], 78)
        self.assertEqual(merch["n"]["objectives"], 5)
        self.assertIn("boxer_shorts", str(merch.get("lista_source") or ""))
        self.assertIn("costume_sets", str(merch.get("lista_source") or ""))
        self.assertTrue(
            any(i.get("source") == "boxer_shorts" for i in merch.get("lista") or [])
        )
        self.assertIn(
            "Snow Boxer Shorts Moon",
            [o["goal"] for o in merch["objectives"]],
        )
        self.assertNotIn("shopping", by_id)  # → shop
        self.assertNotIn("shop_moons", by_id)
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
            data["n_groups_with_objectives"],
            sum(1 for g in data["groups"] if g["has"]["objectives"]),
        )
        self.assertNotIn("n_groups_with_goals", data)
        self.assertEqual(
            data["n_groups_with_moons"],
            sum(1 for g in data["groups"] if g["has"]["moons"]),
        )
        self.assertEqual(
            data["n_groups_with_lista"],
            sum(1 for g in data["groups"] if g["has"]["lista"]),
        )
        self.assertNotIn("n_groups_with_tag", data)
        tag_ids = catalog_tag_ids()
        n_sin_tag_inv = 0
        for g in data["groups"]:
            self.assertIn("tag_inventario", g, g["id"])
            self.assertNotIn("tag", g, g["id"])
            self.assertIsInstance(g["tag_inventario"], bool, g["id"])
            expected_tag = g["id"] in tag_ids
            self.assertEqual(g["tag_inventario"], expected_tag, g["id"])
            if not g["tag_inventario"]:
                n_sin_tag_inv += 1
        if n_sin_tag_inv:
            self.assertEqual(data.get("n_groups_sin_tag_inventario"), n_sin_tag_inv)
        else:
            self.assertNotIn("n_groups_sin_tag_inventario", data)
        self.assertNotIn("n_groups_tag_false", data)
        # kind_goal_tag: solo eq|gt|na; counters solo si >0; suman n_groups.
        for g in data["groups"]:
            self.assertIn(g["kind_goal_tag"], {"eq", "gt", "na"}, g["id"])
            self.assertEqual(
                g["kind_goal_tag"],
                (
                    "na"
                    if int((g.get("n") or {}).get("moons") or 0) <= 0
                    else (
                        "gt"
                        if int((g.get("n") or {}).get("goal") or 0)
                        > int((g.get("n") or {}).get("tag") or 0)
                        else "eq"
                    )
                ),
                g["id"],
            )
        self.assertEqual(
            sum(
                int(data.get(k) or 0)
                for k in (
                    "n_groups_goal_eq_tag",
                    "n_groups_goal_gt_tag",
                    "n_groups_goal_tag_na",
                )
            ),
            data["n_groups"],
        )
        self.assertNotIn("n_groups_goal_lt_tag", data)
        # Combos has/goal_tag con 0 grupos: clave ausente.
        for k in (
            "n_groups_moons_lista",
            "n_groups_moons",
            "n_groups_lista",
            "n_groups_nada",
            "n_groups_goal_lt_tag",
        ):
            self.assertNotIn(k, data)
        self.assertEqual(
            data.get("n_groups_goal_tag_na"),
            sum(1 for g in data["groups"] if g["kind_goal_tag"] == "na"),
        )
        self.assertEqual(
            data.get("n_groups_goal_eq_tag"),
            sum(1 for g in data["groups"] if g["kind_goal_tag"] == "eq"),
        )
        self.assertEqual(
            data.get("n_groups_goal_gt_tag"),
            sum(1 for g in data["groups"] if g["kind_goal_tag"] == "gt"),
        )
        # Tag concreta / paraguas real en la luna (no solo id∈tags_inventario).
        self.assertEqual(by_id["dog"]["n"]["tag"], 2)  # moon_tag fauna
        self.assertEqual(by_id["artistic"]["n"]["tag"], 0)
        self.assertGreater(by_id["birds"]["n"]["tag"], 0)
        self.assertGreater(by_id["jaxi"]["n"]["tag"], 0)
        moe = by_id["moe_eye"]
        self.assertTrue(moe["tag_inventario"])
        self.assertEqual(moe["kind_goal_tag"], "eq")
        self.assertEqual(moe["n"]["moons"], 4)
        self.assertEqual(moe["n"]["goal"], 3)
        self.assertEqual(moe["n"]["tag"], 4)
        by_key = {(m["kingdom"], int(m["moon"])): m for m in moe["moons"]}
        self.assertTrue(by_key[("sand", 2)]["tag"])
        self.assertFalse(by_key[("sand", 2)]["goal"])
        for key in (("sand", 29), ("sand", 54), ("sand", 55)):
            self.assertTrue(by_key[key]["goal"], key)
            self.assertTrue(by_key[key]["tag"], key)
        # Paraguas: solo lunas minoritarias llevan fauna/flora (no las ≥umbral).
        self.assertEqual(by_id["fauna"]["n"]["tag"], 3)
        self.assertEqual(by_id["flora"]["n"]["tag"], 4)
        self.assertEqual(by_id["nature"]["n"]["tag"], 6)
        self.assertLess(by_id["fauna"]["n"]["tag"], by_id["fauna"]["n"]["moons"])
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
            for m in _resolve_bingo_group_moons_raw(g):
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
        gl = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        caps = json.loads((CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8"))
        n_binoculars = 0
        for row in caps.get("captures") or []:
            if row.get("capture") == "Binoculars" or row.get("id") == 8:
                n_binoculars = len(row.get("lista") or [])
                break
        self.assertEqual(
            data["n_lista_total"],
            int(gl["n_items"]) + n_binoculars,
            "n_lista_total = goal_lists.n_items + ubicaciones Binoculars",
        )
        self.assertNotIn("n_groups_both", data)
        self.assertNotIn("n_groups_empty", data)
        self.assertNotIn("n_groups_objectives", data)
        artistic = by_id["artistic"]
        self.assertEqual(artistic["kind"], "goals+moons")
        self.assertEqual(
            artistic["has"],
            {"objectives": True, "moons": True, "lista": False},
        )
        self.assertEqual(artistic["n"]["moons"], 13)
        self.assertEqual(artistic["n"]["objectives"], 15)
        self.assertEqual(
            boss["has"],
            {"objectives": True, "moons": True, "lista": True},
        )
        self.assertEqual(
            trop["has"],
            {"objectives": True, "moons": True, "lista": False},
        )
        self.assertEqual(
            shop["has"],
            {"objectives": True, "moons": True, "lista": True},
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
    data: ClassVar[dict[str, Any]]
    by_name: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        data = json.loads((CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8"))
        cls.data = data
        cls.by_name = {r["capture"]: r for r in data["captures"]}

    def test_n_matches_captures_bingo_group(self) -> None:
        """Cabecera n.* alineada con bingo_groups captures."""
        from catalog_lib import load_bingo_groups

        captures = next(g for g in load_bingo_groups() if g["id"] == "captures")
        data = self.data
        self.assertEqual(data["n"], captures["n"])
        self.assertEqual(data["n"]["objectives"], 48)
        self.assertEqual(data["n"]["moons"], 163)
        self.assertEqual(data["n"]["lista"], 22)
        self.assertEqual(data["n_moons_pool"], 129)
        for key in (
            "n_objectives_total",
            "n_lista_total",
            "n_moons_group",
            "n_moons_unique",
        ):
            self.assertNotIn(key, data, key)

    def test_curated_capture_pool_moons_in_capturas_rows(self) -> None:
        """Curated pool: Broode tag; Meat/Knuck multiluna; Bowser/Parabones goal fija."""
        from export_capturas_lunas import curated_capture_pool_moon_keys

        keys = curated_capture_pool_moon_keys()
        self.assertEqual(
            keys,
            {("cascade", 2), ("luncheon", 3), ("moon", 9)},
        )
        broode = self.by_name["Broode's Chain Chomp"]
        meat = self.by_name["Meat"]
        statue = self.by_name["Bowser statue"]
        parabones = self.by_name["Parabones"]
        knuck = self.by_name["Knucklotec's Fist"]
        for row, key, expect_goal in (
            (broode, ("cascade", 2), False),
            (meat, ("luncheon", 3), True),
            (statue, ("moon", 9), True),
            (parabones, ("moon", 10), True),
            (knuck, ("sand", 4), True),
        ):
            moons = row.get("moons") or []
            self.assertEqual(len(moons), 1)
            self.assertEqual((moons[0]["kingdom"], moons[0]["moon"]), key)
            self.assertEqual(moons[0].get("goal"), expect_goal)
            if expect_goal:
                self.assertNotIn("tag", moons[0])
            else:
                self.assertTrue(moons[0].get("tag"))
        self.assertEqual(meat["objectives"][0]["goal"], "{{X}} Luncheon Multi-Moon[[s]]")
        self.assertEqual(knuck["objectives"][0]["goal"], "{{X}} Sand Multi-Moon[[s]]")

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
        self.assertEqual(u_goals, {"{{X}} Seaside Uproot Moons"})
        uproot_goal_true = {
            (m["kingdom"], int(m["moon"]))
            for m in uproot["moons"]
            if m.get("goal") is True
        }
        self.assertEqual(uproot_goal_true, {("seaside", 47), ("seaside", 48)})

    def test_tag_only_moons_are_goal_false_in_group_pool(self) -> None:
        """tag_only (p. ej. Chain Chomp #3/#7) → goal:false; en moons[] del grupo."""
        from catalog_lib import load_bingo_groups, group_moons
        from export_capturas_lunas import CURATED_PRIMARY

        row = self.by_name["Chain Chomp"]
        cap_id = int(row["id"])
        false_keys = {
            (m["kingdom"], int(m["moon"]))
            for m in row["moons"]
            if m.get("goal") is False
        }
        self.assertIn(("cascade", 1), false_keys)
        self.assertIn(("cascade", 3), false_keys)
        self.assertIn(("cascade", 7), false_keys)
        groups = {g["id"]: g for g in load_bingo_groups()}
        pool = {
            (m["kingdom"], int(m["moon"]))
            for m in group_moons(groups["chain_chomp"])
        }
        curated_extra = {
            key for key, cid in CURATED_PRIMARY.items() if int(cid) == cap_id
        }
        self.assertTrue((false_keys - curated_extra).issubset(pool))
        chomp = groups["chain_chomp"]
        by_key = {(m["kingdom"], int(m["moon"])): m for m in chomp["moons"]}
        self.assertFalse(by_key[("cascade", 3)]["goal"])
        self.assertTrue(by_key[("cascade", 3)]["tag"])
        self.assertEqual(chomp["n"]["moons"], 5)
        self.assertEqual(chomp["n"]["goal"], 2)
        self.assertEqual(chomp["n"]["tag"], 5)

        sherm = self.by_name["Sherm"]
        sherm_false = {
            (m["kingdom"], int(m["moon"]))
            for m in sherm["moons"]
            if m.get("goal") is False
        }
        self.assertIn(("wooded", 3), sherm_false)
        self.assertIn(("metro", 1), sherm_false)
        for key in (("wooded", 3), ("metro", 1)):
            m = next(
                x
                for x in sherm["moons"]
                if (x["kingdom"], int(x["moon"])) == key
            )
            self.assertTrue(m.get("tag"))

        gushen = self.by_name["Gushen"]
        gushen_false = {
            (m["kingdom"], int(m["moon"]))
            for m in gushen["moons"]
            if m.get("goal") is False
        }
        for key in (("seaside", 1), ("seaside", 3), ("seaside", 5)):
            self.assertIn(key, gushen_false)
            m = next(
                x
                for x in gushen["moons"]
                if (x["kingdom"], int(x["moon"])) == key
            )
            self.assertTrue(m.get("tag"))

        lava = self.by_name["Lava Bubble"]
        lava_true = {
            (m["kingdom"], int(m["moon"]))
            for m in lava["moons"]
            if m.get("goal") is True
        }
        self.assertEqual(
            lava_true,
            {("luncheon", 8), ("luncheon", 39), ("luncheon", 40)},
        )
        self.assertEqual(lava["n_goal_moons"], 3)
        lava_false = {
            (m["kingdom"], int(m["moon"]))
            for m in lava["moons"]
            if m.get("goal") is False
        }
        for key in (
            ("luncheon", 4),
            ("luncheon", 5),
            ("luncheon", 14),
            ("luncheon", 23),
            ("luncheon", 27),
            ("luncheon", 28),
            ("luncheon", 36),
        ):
            self.assertIn(key, lava_false)

        uproot = self.by_name["Uproot"]
        uproot_true = {
            (m["kingdom"], int(m["moon"]))
            for m in uproot["moons"]
            if m.get("goal") is True
        }
        self.assertEqual(uproot_true, {("seaside", 47), ("seaside", 48)})
        self.assertNotIn(("wooded", 4), uproot_true)
        self.assertNotIn(("wooded", 25), uproot_true)
        uproot_4 = next(
            m for m in uproot["moons"] if (m["kingdom"], int(m["moon"])) == ("wooded", 4)
        )
        self.assertFalse(uproot_4.get("goal"))
        self.assertTrue(uproot_4.get("tag"))
        self.assertEqual(uproot["n_goal_moons"], 2)

        pokio = self.by_name["Pokio"]
        pokio_true = {
            (m["kingdom"], int(m["moon"]))
            for m in pokio["moons"]
            if m.get("goal") is True
        }
        self.assertEqual(pokio_true, {
            ("bowser", 5), ("bowser", 6), ("bowser", 9),
            ("bowser", 21), ("bowser", 22), ("bowser", 23),
            ("bowser", 33), ("bowser", 34),
        })
        self.assertEqual(pokio["n_goal_moons"], 8)

        cheep = self.by_name["Cheep Cheep"]
        lake3 = next(
            m for m in cheep["moons"] if (m["kingdom"], int(m["moon"])) == ("lake", 3)
        )
        self.assertFalse(lake3.get("goal"))
        self.assertTrue(lake3.get("tag"))
        self.assertEqual(cheep["n_goal_moons"], 7)

        hammer = self.by_name["Hammer Bro"]
        hammer_true = {
            (m["kingdom"], int(m["moon"]))
            for m in hammer["moons"]
            if m.get("goal") is True
        }
        self.assertEqual(
            hammer_true,
            {
                ("luncheon", 17), ("luncheon", 30),
                ("luncheon", 43), ("luncheon", 44),
            },
        )
        self.assertEqual(hammer["n_goal_moons"], 4)

        coffer = self.by_name["Coin Coffer"]
        self.assertEqual(coffer["n_goal_moons"], 1)
        w33 = coffer["moons"][0]
        self.assertEqual((w33["kingdom"], int(w33["moon"])), ("wooded", 33))
        self.assertTrue(w33.get("goal"))

        cactus = self.by_name["Cactus"]
        tree = self.by_name["Tree"]
        cactus_by_key = {
            (m["kingdom"], int(m["moon"])): m for m in cactus["moons"]
        }
        tree_by_key = {
            (m["kingdom"], int(m["moon"])): m for m in tree["moons"]
        }
        self.assertTrue(cactus_by_key[("sand", 36)]["goal"])
        self.assertTrue(cactus_by_key[("sand", 40)]["goal"])
        self.assertFalse(cactus_by_key[("wooded", 34)]["goal"])
        self.assertTrue(cactus_by_key[("wooded", 34)]["tag"])
        self.assertEqual(cactus["n_goal_moons"], 2)
        self.assertTrue(tree_by_key[("wooded", 34)]["goal"])
        self.assertFalse(tree_by_key[("sand", 36)]["goal"])
        self.assertFalse(tree_by_key[("sand", 40)]["goal"])
        self.assertTrue(tree_by_key[("sand", 36)]["tag"])
        self.assertTrue(tree_by_key[("sand", 40)]["tag"])
        self.assertEqual(tree["n_goal_moons"], 1)

        puzzle = self.by_name["Puzzle Part (Lake Kingdom)"]
        tyfoo = self.by_name["Ty-foo"]
        puzzle_moons = puzzle["moons"]
        self.assertEqual(len(puzzle_moons), 1)
        self.assertEqual(
            (puzzle_moons[0]["kingdom"], int(puzzle_moons[0]["moon"])),
            ("lake", 20),
        )
        self.assertTrue(puzzle_moons[0]["goal"])
        self.assertEqual(puzzle["n_goal_moons"], 1)
        tyfoo_by_key = {
            (m["kingdom"], int(m["moon"])): m for m in tyfoo["moons"]
        }
        self.assertTrue(tyfoo_by_key[("snow", 28)]["goal"])
        self.assertEqual(tyfoo["n_goal_moons"], 3)

        manhole = self.by_name["Manhole"]
        manhole_false = {
            (m["kingdom"], int(m["moon"]))
            for m in manhole["moons"]
            if m.get("goal") is False
        }
        self.assertIn(("metro", 6), manhole_false)
        m6 = next(
            x for x in manhole["moons"] if (x["kingdom"], int(x["moon"])) == ("metro", 6)
        )
        self.assertTrue(m6.get("tag"))
        self.assertEqual(manhole["n_goal_moons"], 3)

    def test_capturas_lunas_global_counters(self) -> None:
        """Cabecera: n, pool, listados y goal/false en moons[]."""
        data = self.data
        n = data["n"]
        self.assertEqual(
            n["objectives"],
            sum(int(r.get("n_objectives") or 0) for r in data["captures"]),
        )
        self.assertEqual(
            n["lista"],
            sum(len(r.get("lista") or []) for r in data["captures"]),
        )
        self.assertEqual(n["lista"], 22)  # 14 binoculars + 8 bosses
        listed = [
            m
            for r in data["captures"]
            for m in r.get("moons") or []
        ]
        keys = {(m["kingdom"], m["moon"]) for m in listed}
        goal_moons = [m for m in listed if m.get("goal") is True]
        goal_keys = {(m["kingdom"], m["moon"]) for m in goal_moons}
        goal_false = [m for m in listed if m.get("goal") is False]
        self.assertEqual(data["n_moons_listed"], len(listed))
        self.assertEqual(n["moons"], len(keys))
        self.assertEqual(data["n_goal_moons"], len(goal_moons))
        self.assertEqual(data["n_goal_moons_unique"], len(goal_keys))
        self.assertEqual(data["n_goal_false"], len(goal_false))
        self.assertEqual(data["n_goal_moons"] + data["n_goal_false"], len(listed))
        self.assertGreater(data["n_goal_moons"], data["n_goal_moons_unique"])
        self.assertEqual(n["moons"], 163)
        self.assertEqual(data["n_moons_pool"], 129)
        self.assertGreater(data["n_moons_listed"], n["moons"])
        self.assertNotIn("n_moons", data)
        rocket = self.by_name["Mini Rocket"]
        self.assertGreater(rocket["n_moons"], 0)
        self.assertGreater(rocket["n_goal_moons"], 0)

    def test_binoculars_lista_only_in_capturas(self) -> None:
        """Ubicaciones Binoculars viven en capturas_lunas (no lists.binoculars)."""
        row = self.by_name["Binoculars"]
        lista = row.get("lista") or []
        self.assertEqual(row.get("pool"), "lista")
        self.assertEqual(len(lista), 14)
        self.assertEqual(
            [int(x["id_list"]) for x in lista], list(range(1, len(lista) + 1))
        )
        self.assertTrue(all(x.get("source") == "binoculars" for x in lista))
        lists = json.loads((CATALOG_DIR / "goal_lists.json").read_text(encoding="utf-8"))
        self.assertNotIn("binoculars", lists["lists"])

    def test_capture_bosses_lista(self) -> None:
        """8 peleas jefe+captura en lista[] con source bosses."""
        boss_items = []
        for row in self.data["captures"]:
            for item in row.get("lista") or []:
                if item.get("source") == "bosses":
                    boss_items.append(item)
        self.assertEqual(len(boss_items), 8)
        broode = self.by_name["Broode's Chain Chomp"]
        self.assertEqual(broode["n_lista"], 2)
        lista = broode["lista"]
        self.assertEqual(
            [b["name"] for b in lista],
            [
                "Madame Broode (Broodal)",
                "Madame Broode (Broodal, rematch)",
            ],
        )
        self.assertEqual(lista[0]["source"], "bosses")
        self.assertEqual(lista[0]["moon"], 2)
        self.assertNotIn("moon", lista[1])
        knuck = self.by_name["Knucklotec's Fist"]
        self.assertEqual(knuck["n_lista"], 1)
        self.assertEqual(knuck["lista"][0]["moon"], 4)
        self.assertEqual(knuck["lista"][0]["source"], "bosses")
        pokio = self.by_name["Pokio"]
        self.assertEqual(pokio["lista"][0]["name"], "RoboBrood (Broodal)")
        self.assertEqual(pokio["lista"][0]["source"], "bosses")

    def test_every_moon_has_goal_flag(self) -> None:
        data = json.loads((CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8"))
        for row in data["captures"]:
            for m in row.get("moons") or []:
                self.assertIn("goal", m, (row["capture"], m.get("name")))
                self.assertIsInstance(m["goal"], bool)
                if m["goal"] is False:
                    self.assertTrue(m.get("tag"), (row["capture"], m.get("name")))
                else:
                    self.assertNotIn("tag", m, (row["capture"], m.get("name")))

    def test_mario_moons_not_on_bullet_bill(self) -> None:
        """sand#7/#11: BB opcional → mario; no en fila Bullet Bill."""
        row = self.by_name["Bullet Bill"]
        keys = {(m["kingdom"], int(m["moon"])) for m in row["moons"]}
        self.assertNotIn(("sand", 7), keys)
        self.assertNotIn(("sand", 11), keys)
        from catalog_lib import MARIO_MOONS

        self.assertIn(("sand", 7), MARIO_MOONS)
        self.assertIn(("sand", 11), MARIO_MOONS)

    def test_no_empty_array_fields(self) -> None:
        """Sin claves con valor []."""
        for row in self.data["captures"]:
            for key, value in row.items():
                self.assertFalse(
                    isinstance(value, list) and len(value) == 0,
                    (row.get("capture"), key),
                )

    def test_capture_array_field_order(self) -> None:
        """Orden: objectives → moons → lista (solo claves presentes)."""
        data = json.loads((CATALOG_DIR / "capturas_lunas.json").read_text(encoding="utf-8"))
        for row in data["captures"]:
            keys = list(row.keys())
            order = [k for k in ("objectives", "moons", "lista") if k in keys]
            self.assertEqual(
                order,
                sorted(order, key=("objectives", "moons", "lista").index),
                row.get("capture"),
            )
            if "lista" in keys:
                self.assertIn("n_lista", keys, row.get("capture"))
                self.assertLess(keys.index("n_lista"), keys.index("lista"), row.get("capture"))
            if "objectives" in keys and "moons" in keys:
                self.assertLess(keys.index("objectives"), keys.index("moons"), row.get("capture"))
            if "moons" in keys and "lista" in keys:
                self.assertLess(keys.index("moons"), keys.index("lista"), row.get("capture"))
            if "objectives" in keys and "lista" in keys and "moons" not in keys:
                self.assertLess(keys.index("objectives"), keys.index("lista"), row.get("capture"))


class ProjectAndLunasTests(unittest.TestCase):
    def test_project_in_scope_count(self) -> None:
        project = load_project()
        self.assertEqual(project["n_in_scope_moons"], project["meta"]["in_scope_moon_count"])
        self.assertEqual(project["n_in_scope_moons"], 434)

    def test_lunas_objetivos_count(self) -> None:
        data = json.loads((CATALOG_DIR / "lunas-objetivos.json").read_text(encoding="utf-8"))
        self.assertEqual(data["n_moons"], len(data["moons"]))
        self.assertEqual(data["n_moons"], 434)
        by_n = data.get("n_moons_by_n_tags") or {}
        self.assertTrue(by_n)
        self.assertEqual(sum(int(v) for v in by_n.values()), data["n_moons"])
        ones = [
            (m["tags"][0], int(m["moon"]), m["name"])
            for m in data["moons"]
            if len(m.get("tags") or []) == 1
        ]
        self.assertEqual(ones, [], "ninguna luna solo con tag de reino")
        counted: dict[str, int] = {}
        for m in data["moons"]:
            k = str(len(m.get("tags") or []))
            counted[k] = counted.get(k, 0) + 1
        self.assertEqual(by_n, counted)
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

    def test_force_moon_tags_not_omitted(self) -> None:
        """FORCE_MOON_TAGS: tags que la política omitiría siguen en el catálogo."""
        from catalog_lib import FORCE_MOON_TAGS

        data = json.loads((CATALOG_DIR / "lunas-objetivos.json").read_text(encoding="utf-8"))
        by = {(m["tags"][0], int(m["moon"])): m for m in data["moons"]}
        self.assertTrue(FORCE_MOON_TAGS)
        for (kingdom, moon), want in FORCE_MOON_TAGS.items():
            row = by[(kingdom, moon)]
            self.assertTrue(
                set(want) <= set(row["tags"]),
                f"{kingdom}#{moon}: falta {sorted(want - set(row['tags']))} en {row['tags']}",
            )

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


class ItemsGoalsTests(unittest.TestCase):
    def test_without_goals_only_crazy_cap(self) -> None:
        """Solo las 11 Crazy Cap quedan sin goal (P-Switches multi-reino sí cuentan)."""
        data = json.loads((CATALOG_DIR / "items_goals.json").read_text(encoding="utf-8"))
        without = [it for it in data["items"] if not (it.get("goals") or [])]
        self.assertEqual(data.get("n_without_goals"), 11)
        self.assertEqual(len(without), 11)
        self.assertTrue(all(it.get("name") == "Crazy Cap" for it in without))
        by_id = {it["id"]: it for it in data["items"]}
        for pid in (
            "sand/p_switches/36",
            "lake/p_switches/13",
            "lake/p_switches/14",
            "metro/p_switches/25",
        ):
            self.assertIn(
                "Activate {{X}} P-Switches",
                by_id[pid].get("goals") or [],
                pid,
            )

    def test_p_switches_goal_not_metro_only_hint(self) -> None:
        from export_items_goals import _goal_kingdom_hint

        ref = json.loads((CATALOG_DIR / "goals_referencia.json").read_text(encoding="utf-8"))
        g = next(x for x in ref["goals"] if x["goal"] == "Activate {{X}} P-Switches")
        self.assertIsNone(_goal_kingdom_hint(g))


class GoalReferenciaHubTests(unittest.TestCase):
    ref: ClassVar[dict[str, Any]]
    by_goal: ClassVar[dict[str, Any]]

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
        g = self.by_goal["{{X}} Cap Regional Coins"]
        self.assertNotIn("regional_total", g)
        self.assertEqual(g["lista_summary"]["regional_total"], 50)
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
        self.assertEqual(g["lista_summary"]["n_items"], 2)
        self.assertEqual(g["lista_summary"]["regional_total"], 11)
        self.assertEqual(
            g["lista_summary"]["by_disponibilidad"],
            {"base": 1, "mid_story": 1},
        )
        names = {i["name"] for i in g["lista"]}
        self.assertEqual(
            names,
            {"Inside the Ice Caves", "Inside the Underground Temple"},
        )

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
        """tags[] = intersección/moon_tag; moons[].tag bool; lista sin tags."""
        moon = self.by_goal["{{X}} 8-Bit Moons"]
        self.assertEqual(moon.get("pool"), "moons")
        self.assertEqual(moon.get("tags"), ["8bit"])
        self.assertNotIn("tag", moon)  # tag bool vive en moons[], no en la goal
        for row in moon["moons"]:
            self.assertIn("tag", row)
            self.assertIs(row["tag"], True)
            self.assertEqual(list(row)[-1], "tag")
        # 8-Bit Regional Coins: solo lista_source (sin pool/lista expandida).
        eight_reg = self.by_goal["{{X}} 8-Bit Regional Coins"]
        self.assertEqual(eight_reg.get("lista_source"), "regionals")
        self.assertNotIn("pool", eight_reg)
        self.assertNotIn("lista", eight_reg)
        self.assertNotIn("lista_summary", eight_reg)
        self.assertNotIn("tags", eight_reg)
        lista = self.by_goal["{{X}} Cap Regional Coins"]
        self.assertEqual(lista.get("pool"), "lista")
        self.assertNotIn("tags", lista)
        self.assertNotIn("tag", lista)
        self.assertIn("regionalcoins", lista.get("bingo_groups") or [])
        for g in self.by_goal.values():
            if g.get("pool") == "lista":
                self.assertNotIn("tags", g, g.get("goal"))
                self.assertNotIn("tag", g, g.get("goal"))
            elif g.get("pool") == "moons" and "tags" in g:
                self.assertIsInstance(g["tags"], list)
                self.assertTrue(g["tags"])
                self.assertTrue(all(isinstance(t, str) for t in g["tags"]))
                for row in g.get("moons") or []:
                    self.assertIn("tag", row, g.get("goal"))
                    self.assertIsInstance(row["tag"], bool)
                    self.assertEqual(list(row)[-1], "tag")

    def test_moon_tag_false_when_pool_without_concrete_tag(self) -> None:
        """Pool con tag de grupo no aplicada a lunas → moons[].tag=false."""
        g = self.by_goal["{{X}} Nature Moons"]
        self.assertEqual(g.get("tags"), ["nature"])
        self.assertTrue(g.get("moons"))
        self.assertTrue(all(row.get("tag") is False for row in g["moons"]))
        # Sub-Area de reino: mini_rocket / beanstalk caen sub_area (sin tag).
        # Outfit door (Folding #31+#32) ya no está en el pool Sub-Area.
        sub = self.by_goal["{{X}} Bowser's Sub-Area Moons"]
        self.assertEqual(sub.get("tags"), ["sub_area"])
        by_flag = {True: 0, False: 0}
        for row in sub["moons"]:
            by_flag[bool(row["tag"])] += 1
        self.assertGreater(by_flag[True], 0)
        self.assertGreater(by_flag[False], 0)
        beanstalk = next(
            r
            for r in sub["moons"]
            if r["kingdom"] == "bowser" and r["moon"] == 38
        )
        self.assertIs(beanstalk["tag"], False)
        self.assertFalse(
            any(r["moon"] in (31, 32) for r in sub["moons"] if r["kingdom"] == "bowser")
        )

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
        g = self.by_goal["{{X}} Unique Life Up Hearts"]
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
        self.assertNotIn("binoculars", lists)
        self.assertNotIn("captures", lists)

    def test_disponibilidad_list_only_checkpoints_and_life_ups(self) -> None:
        self.assertEqual(collect_disponibilidad_list_violations(), [])

    def test_disponibilidad_matches_goals_referencia(self) -> None:
        self.assertEqual(collect_goal_lists_referencia_mismatches(), [])

    def test_lista_location_no_near(self) -> None:
        self.assertEqual(collect_location_field_violations(), [])

    def test_sphynx_zone_only_in_zonas_inventario(self) -> None:
        """Zone no va en lista[] del hub; sí en zonas_inventario (p.ej. Sand Sphynx)."""
        ref = json.loads(
            (CATALOG_DIR / "goals_referencia.json").read_text(encoding="utf-8")
        )
        g = next(x for x in ref["goals"] if x["goal"] == "Correct Wooded Sphynx Question")
        item = g["lista"][0]
        self.assertNotIn("zone", item)
        self.assertNotIn("near", item)
        self.assertNotIn("near_checkpoint", item)
        # Wooded/Moon Sphynx: lists.sphynxes; zone curada en zonas_inventario
        # (p.ej. Sand Sphynx's Treasure Vault → zone sphynx).
        zl = json.loads(
            (CATALOG_DIR / "zonas_inventario.json").read_text(encoding="utf-8")
        )
        vault = next(
            it
            for z in zl["zones"]
            for it in z["list"]
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
