"""Reconstruye el grupo bingo 'sub_area' (moons) en bingo_groups.json.

Regla estricta — un Level (smo.wiki) es subarea SOLO si tiene exactamente 2
lunas en alcance (base/world_peace/revisit):

  - 1 luna  → NO (p. ej. New Donk City Hall Interior)
  - 2 lunas → SI (p. ej. Sky Garden Tower, Icicle Cavern)
  - 3+     → NO (p. ej. Deep Woods, Shiveria Town)

Excluye Overworld y Crazy Cap.

Deep Woods, Secret Flower Field, Snowline Circuit y zonas hielo de Sand
NO son sub_area: deep_woods / bloom_flower / sand_ice / shiverian_racer
(o no aplica).

Los pares Level (para capturas) se escriben en catalog/goal_lists.json
(sub_area_levels dentro de lists), no en el grupo bingo.

Usage:
  python rebuild_sub_area_bingo.py
"""
from __future__ import annotations

import re
import time
import urllib.request
from collections import defaultdict
from html import unescape

from catalog_lib import (
    BINGO_GROUPS_PATH,
    CATALOG_DIR,
    KINGDOM_COLUMNS,
    KINGDOM_DISPLAY,
    assign_bingo_group_orden,
    build_matrix_moon_registry,
    entity_sort_key,
    load_catalog,
    normalize_bingo_group,
    objective_ref_from_combined,
    write_catalog_json,
)
from export_lunas_tags import export_lunas

OUT_GROUPS = BINGO_GROUPS_PATH
GOAL_LISTS_PATH = CATALOG_DIR / "goal_lists.json"

SMO_PAGES: dict[str, str] = {
    "cap": "Cap_Kingdom",
    "cascade": "Cascade_Kingdom",
    "sand": "Sand_Kingdom",
    "lake": "Lake_Kingdom",
    "wooded": "Wooded_Kingdom",
    "lost": "Lost_Kingdom",
    "metro": "Metro_Kingdom",
    "snow": "Snow_Kingdom",
    "seaside": "Seaside_Kingdom",
    "luncheon": "Luncheon_Kingdom",
    "bowser": "Bowser%27s_Kingdom",
    "moon": "Moon_Kingdom",
}

EXCLUDE_LEVELS = frozenset(
    {
        "overworld",
        "crazy cap",
        "crazy cap slots",
        # Multiluna + bloom: no cuenta como sub_area bingo (exactamente 2 normales).
        "secret flower field",
        # Circuito de carreras (Bound Bowl / Class S): no es subárea de exploración.
        "snowline circuit",
        # Guía bingo: fuera del pool Sub-Area Moons (otros goals / no guía).
        "sky garden tower",  # nuts / uproot
        "underground power plant",  # spark_pylon / manhole
        "icicle cavern",  # story / goomba
        "hollow crevasse",
        "wind-chill cavern",  # Ty-Foo story pair
        "snowy mountain",
        "volcano cave",  # story Luncheon
    }
)

# Ice Cave y demás ice Levels: solo sand_ice, no Sub-Area Moons.
SAND_ICE_LEVELS_NOT_SUB_AREA = frozenset(
    {
        "underground temple",
        "deepest underground",
        "ice cave",
        "freezing waterway",
    }
)

SAND_ICE_LEVELS = frozenset(
    {
        "underground temple",
        "deepest underground",
        "ice cave",
        "freezing waterway",
    }
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 BingoCatalog"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_moon_levels(html: str) -> dict[int, str]:
    levels: dict[int, str] = {}
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I)
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        if len(cells) < 4:
            continue
        texts = [unescape(re.sub(r"<[^>]+>", "", c)) for c in cells]
        texts = [re.sub(r"\s+", " ", t).strip() for t in texts]
        if not texts[0].isdigit():
            continue
        num = int(texts[0])
        level = re.sub(r"\[\d+\]", "", texts[3]).strip()
        levels[num] = level
    return levels


def level_excluded(level: str) -> bool:
    low = level.lower().strip()
    return low in EXCLUDE_LEVELS or low.endswith(" overworld")


def group_moon_ref(entry: dict) -> dict:
    return {
        "kingdom": entry["kingdom"],
        "moon": entry["moon"],
        "name": entry["name"],
    }


SUB_AREA_GOALS = (
    "{{X}} Sub-Area Moons",
    "{{X}} Cap Sub-Area Moons",
    "{{X}} Cascade Sub-Area Moons",
    "{{X}} Sand Sub-Area Moons",
    "{{X}} Lake Sub-Area Moons",
    "{{X}} Wooded Sub-Area Moons",
    "{{X}} Metro Sub-Area Moons",
    "{{X}} Snow Sub-Area Moons",
    "{{X}} Seaside Sub-Area Moons",
    "{{X}} Luncheon Sub-Area Moons",
    "{{X}} Bowser's Sub-Area Moons",
    "{{X}} Beanstalk Moons",
    "{{X}} Bowser's Jizo Moons",
    "{{X}} Bowser's Pokio Moons",
    "{{X}} Bullet Bill Moons",
    "{{X}} Cap Frog Moons",
    "{{X}} Cascade Chain Chomp Moons",
    "{{X}} Cascade Chasm Lifts Moons",
    "{{X}} Hidden Timer Moon[[s]]",
    "{{X}} Lake Zipper Moons",
    "{{X}} Ledge Grab Moons",
    "{{X}} Luncheon Lava Bubble Moons",
    "{{X}} Luncheon Volbonan Moons",
    "{{X}} Metro Manhole Moons",
    "{{X}} Metro Taxi Moons",
    "{{X}} Mini Rocket Moons",
    "{{X}} Paragoomba Moons",
    "{{X}} Rocket Flower Moons",
    "{{X}} Sand Ice Moon[[s]]",
    "{{X}} Sand Jaxi Moons",
    "{{X}} Sand Moe-Eye Moons",
    "{{X}} Seaside Gushen Moons",
    "{{X}} Seaside Uproot Moons",
    "{{X}} Sherm Moons",
    "{{X}} Spark Pylon Moons",
    "{{X}} T-Rex Moons",
    "{{X}} Wooded Flower Road Moons",
    "{{X}} Wooded Pipe Moons",
    "{{X}} Wooded Uproot Moons",
)


def sync_bingo_group(
    catalog: dict,
    group_id: str,
    moons: list[dict],
    *,
    goal: str,
    kingdom: str,
    **extra,
) -> None:
    groups = catalog.setdefault("groups", [])
    moons_sorted = sorted(
        moons,
        key=entity_sort_key,
    )
    goal_names = SUB_AREA_GOALS if group_id == "sub_area" else (goal,)
    objectives = [objective_ref_from_combined(g) for g in goal_names]
    for group in groups:
        if group.get("id") == group_id:
            group.pop("goal", None)
            group["objectives"] = objectives
            group["kingdom"] = kingdom
            group["moons"] = moons_sorted
            for k, v in extra.items():
                group[k] = v
            return
    payload = {
        "id": group_id,
        "objectives": objectives,
        "kingdom": kingdom,
        "moons": moons_sorted,
        **extra,
    }
    groups.append(payload)


def main() -> None:
    registry = build_matrix_moon_registry()
    levels: list[dict] = []
    moon_refs: list[dict] = []
    deep_refs: list[dict] = []
    sand_ice_refs: list[dict] = []
    seen: set[tuple[str, int]] = set()

    for kingdom in KINGDOM_COLUMNS:
        page = SMO_PAGES.get(kingdom)
        if not page:
            continue
        url = f"https://smo.wiki/{page}"
        print(f"  {KINGDOM_DISPLAY.get(kingdom, kingdom)}...")
        try:
            html = fetch(url)
        except Exception as exc:  # noqa: BLE001
            print(f"    AVISO: {exc}")
            continue
        moon_levels = parse_moon_levels(html)
        by_level: dict[str, list[int]] = defaultdict(list)
        for moon, level in moon_levels.items():
            entry = registry.get((kingdom, moon))
            if not entry:
                continue
            if level_excluded(level):
                continue
            by_level[level].append(moon)

        for level, moons in sorted(by_level.items(), key=lambda kv: min(kv[1])):
            moons = sorted(set(moons))
            level_l = level.lower()

            # Deep Woods + subzonas (Treasure Trap / Treasure Vault).
            if level_l == "deep woods" or level_l.startswith("deep woods "):
                for moon in moons:
                    deep_refs.append(group_moon_ref(registry[(kingdom, moon)]))
                continue

            if kingdom == "sand" and level_l in SAND_ICE_LEVELS:
                for moon in moons:
                    entry = registry[(kingdom, moon)]
                    # Sin story/multi (sand#4 The Hole in the Desert).
                    type_l = str(entry.get("type") or "").lower()
                    if "story moon" in type_l or "multi moon" in type_l:
                        continue
                    sand_ice_refs.append(group_moon_ref(entry))
                # Ice Levels: solo sand_ice (no Sub-Area), salvo si no están en NOT_SUB_AREA.
                if level_l in SAND_ICE_LEVELS_NOT_SUB_AREA or len(moons) != 2:
                    continue

            if len(moons) != 2:
                continue
            levels.append(
                {
                    "kingdom": kingdom,
                    "level": level,
                    "moons": moons,
                    "names": [registry[(kingdom, m)]["name"] for m in moons],
                }
            )
            for moon in moons:
                key = (kingdom, moon)
                if key in seen:
                    continue
                seen.add(key)
                moon_refs.append(group_moon_ref(registry[key]))
        time.sleep(0.25)

    moon_refs.sort(key=entity_sort_key)

    bingo = load_catalog(OUT_GROUPS) if OUT_GROUPS.exists() else {"groups": []}
    sync_bingo_group(
        bingo,
        "sub_area",
        moon_refs,
        goal="{{X}} Sub-Area Moons",
        kingdom="",
        moon_tag="sub_area",
        large=True,
        _note=(
            f"{len(levels)} zonas / {len(moon_refs)} lunas (guía bingo, pares). "
            "Ruined Roulette Tower incluido. Sin Sky Garden / Power Plant / "
            "barreras Snow / Volcano Cave. Ice Cave solo sand_ice (no Sub-Area). "
            "Sin #28 Blowing (Ty-Foo). Pares Level en catalog/goal_lists.json "
            "(lists.sub_area_levels)."
        ),
        _definition=(
            "Bingo Sub-Area Moons: niveles de la guía (pares Level). "
            "Sin #28. Deep Woods y resto hielo Sand → deep_woods / sand_ice."
        ),
    )
    # Quitar levels del grupo si quedaron de builds viejos.
    for g in bingo.get("groups") or []:
        if g.get("id") == "sub_area":
            g.pop("levels", None)
            break
    lists_data = load_catalog(GOAL_LISTS_PATH) if GOAL_LISTS_PATH.exists() else {}
    lists = dict(lists_data.get("lists") or {})
    lists.pop("sub_area_levels", None)
    lists["sub_area_levels"] = levels  # al final
    lists_data["lists"] = lists
    lists_data["n_lists"] = len(lists)
    lists_data["n_items"] = sum(len(v) for v in lists.values() if isinstance(v, list))
    lists_data.pop("n_sub_area_levels", None)
    lists_data.pop("sub_area_levels", None)  # no top-level
    # Orden: nota → contadores → lists
    ordered_lists = {
        k: lists_data[k]
        for k in ("_note", "_definition", "n_lists", "n_items", "lists")
        if k in lists_data
    }
    for k, v in lists_data.items():
        if k not in ordered_lists:
            ordered_lists[k] = v
    write_catalog_json(GOAL_LISTS_PATH, ordered_lists)
    sync_bingo_group(
        bingo,
        "deep_woods",
        deep_refs,
        goal="{{X}} Deep Woods Moons",
        kingdom="wooded",
    )
    sync_bingo_group(
        bingo,
        "sand_ice",
        sand_ice_refs,
        goal="{{X}} Sand Ice Moon[[s]]",
        kingdom="sand",
    )
    bingo["groups"] = [
        normalize_bingo_group(g)
        for g in assign_bingo_group_orden(
            [normalize_bingo_group(g) for g in bingo["groups"]]
        )
    ]
    from catalog_lib import finalize_bingo_groups_doc

    write_catalog_json(OUT_GROUPS, finalize_bingo_groups_doc(bingo))

    print(f"\nActualizado: {OUT_GROUPS.name}")
    print(f"  sub_area: {len(levels)} levels, {len(moon_refs)} lunas")
    print(f"  deep_woods={len(deep_refs)}, sand_ice={len(sand_ice_refs)}")
    for g in levels:
        print(f"  {g['kingdom']}: {g['level']} -> {g['moons']}")

    export_lunas()


if __name__ == "__main__":
    main()
