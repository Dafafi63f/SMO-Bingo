"""Pasada completa: availability + tags segun la logica del proyecto.

Orden:
  1) Grupos de reino (lunas in-scope + objetivos Combined del reino)
  2) Grupos tematicos objetivo↔lunas (sync_objective_moon_groups)
  3) story_moon XOR multi_moon → grupos en bingo_groups
  4) captures / cappy / mario → grupos en bingo_groups
  5) Availability (in_scope_moons en project.json)
  6) Untyped (diagnostico; sin archivo)
  7) Export parcial: tags_inventario, lunas-objetivos, bingo_lineas,
     goal_icons, goals_referencia

Preferible tras cambios de catálogo: python Files/regenerate_all.py
(incluye capturas, individuales, zonas_reino, enrich, etc.).

JSON en Catalog/: project, bingo_groups, bingo_lineas, goal_icons,
  moon_names_wiki, goals_referencia, goals_individuales, zonas_reino,
  capturas_lunas, tags_inventario, lunas-objetivos, goal_lists,
  goal_tooltips (+ Combined en Bingos/).

Listas obtain/context/reino/tematicos/story/action viven en bingo_groups.json.

Usage:
  python sync_lunas.py
"""
from __future__ import annotations

from catalog_lib import (
    compute_in_scope_limits,
    refresh_in_scope_odyssey_meta,
    FORCE_IN_SCOPE_MOONS,
    load_kingdom_availability,
    load_meta,
    load_wiki_moon_meta,
    rebuild_untyped_moons,
    sync_kingdom_groups,
    upsert_moon_tag_group,
    wiki_moon_in_scope,
    KINGDOM_COLUMNS,
)
from export_combined_meta import export_icons as export_goal_icons
from export_combined_meta import export_lineas as export_bingo_lineas
from export_goals_referencia import main as export_goals_referencia
from export_lunas_tags import export_lunas, export_tags
from fill_captures_cappy import main as fill_captures
from sync_objective_moon_groups import sync_objective_moon_groups


def sync_story(wiki, rules) -> None:
    print("3) story_moon XOR multi_moon → bingo_groups...")
    story: list[dict] = []
    multi: list[dict] = []
    kingdoms = list(KINGDOM_COLUMNS)
    for kingdom, _moon in FORCE_IN_SCOPE_MOONS:
        if kingdom not in kingdoms:
            kingdoms.append(kingdom)
    for kingdom in kingdoms:
        for moon, entry in sorted(wiki.get(kingdom, {}).items()):
            if not wiki_moon_in_scope(kingdom, moon, entry, rules):
                continue
            type_l = (entry.get("type") or "").lower()
            ref = {
                "kingdom": kingdom,
                "moon": moon,
                "name": entry["name"],
            }
            if "multi moon" in type_l:
                multi.append(ref)
            elif "story moon" in type_l:
                story.append(ref)
    n_story = upsert_moon_tag_group(
        "storymoons",
        story,
        moon_tag="story_moon",
        note=(
            "XOR multi_moon. Desde tipo wiki. Multiluna de historia → solo "
            "multi_moon. Goals Combined: cat bingo_lineas storymoons."
        ),
        objectives=None,  # conserva goals del SPECS (sync_objective_moon_groups)
    )
    n_multi = upsert_moon_tag_group(
        "multi_moon",
        multi,
        moon_tag="multi_moon",
        note=(
            "14 multilunas in-scope (XOR story_moon; tipo wiki). "
            "Goals: Total + All Kingdoms + por reino con goal Combined "
            "(Sand/Wooded/Metro/Luncheon/Seaside/Snow). "
            "Sin Cascade/Lake/Bowser/Ruined (1 multi; Ruined = Defeat Dragon)."
        ),
    )
    print(f"  storymoons: {n_story}  multi_moon: {n_multi}")


def refresh_availability(wiki, rules) -> None:
    print("5) Availability (in_scope_moons)...")
    limits = compute_in_scope_limits(wiki, rules)
    meta = load_meta()
    meta["in_scope_moons"] = limits
    meta = refresh_in_scope_odyssey_meta(meta)
    for kingdom, n in sorted(limits.items(), key=lambda kv: KINGDOM_COLUMNS.index(kv[0]) if kv[0] in KINGDOM_COLUMNS else 99):
        print(f"  {kingdom}: {n}")
    print(
        f"  in-scope: {meta['in_scope_moon_count']} lunas físicas, "
        f"{meta['in_scope_odyssey_units']} unidades Odyssey"
    )


def rebuild_untyped(_wiki=None, _rules=None) -> None:
    print("6) untyped (diagnostico)...")
    n = rebuild_untyped_moons()
    print(f"  sin tags extra: {n}")


def main() -> None:
    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()

    print("1) Grupos de reino en bingo_groups...")
    kingdom_counts = sync_kingdom_groups()
    for kingdom, n in kingdom_counts.items():
        print(f"  {kingdom}: {n}")

    print("2) Grupos tematicos objetivo↔lunas...")
    thematic = sync_objective_moon_groups()
    for gid, n in sorted(thematic.items()):
        print(f"  {gid}: {n}")

    sync_story(wiki, rules)

    print("4) captures / cappy / mario...")
    fill_captures(export=False)

    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()
    refresh_availability(wiki, rules)
    rebuild_untyped()

    print("7) Exportando...")
    export_tags()
    export_lunas()
    export_bingo_lineas()
    export_goal_icons()
    export_goals_referencia()


if __name__ == "__main__":
    main()
