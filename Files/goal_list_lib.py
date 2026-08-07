"""Listas contables para goals sin Moon Get (referencia goals_referencia)."""
from __future__ import annotations

import json

from catalog_lib import (
    CATALOG_DIR,
    KINGDOM_COLUMNS,
    ZONE_ORDER,
    entity_sort_key,
    kingdom_story_index,
    load_bingo_groups,
    load_meta,
    register_cache_clear,
)
from export_capturas_lunas import (
    CAPTURE_BY_ID,
    CAPTURE_LIST,
    CAPTURE_MERGE_DISPLAY,
    CAPTURE_MERGE_INTO,
)
from fix_bingo_group_ranges import (
    ALL_CHECKPOINTS_EXCLUDED_KINGDOMS,
    KINGDOM_CHECKPOINT_META,
    KINGDOM_CHECKPOINT_NAMES,
    KINGDOM_CHECKPOINT_ODYSSEY_SLOT,
    PAINTING_CHECKPOINT_KINGDOMS,
    PAINTING_CHECKPOINT_PROGRESSION,
)

LISTS_PATH = CATALOG_DIR / "goal_lists.json"
REGIONALES_ZONAS_PATH = CATALOG_DIR / "regionales_zonas.json"
# sub_area_levels vive en lists.sub_area_levels (al final).
REGIONAL_COINS_SMALL = 50
REGIONAL_COINS_LARGE = 100
# Compat: tope de un reino grande (p. ej. docs / All Large Kingdom).
REGIONAL_COINS_PER_KINGDOM = REGIONAL_COINS_LARGE
GOAL_X = "{{X}}"

LARGE_KINGDOMS = ("sand", "wooded", "metro", "seaside", "luncheon", "bowser")
SMALL_KINGDOMS = ("cap", "cascade", "lake", "lost", "snow", "moon")

BOSS_FIGHTS = [
    {"kingdom": "cap", "name": "Topper (Broodal)"},
    {"kingdom": "cascade", "name": "Madame Broode (Broodal)"},
    {"kingdom": "sand", "name": "Hariet (Broodal)"},
    {"kingdom": "sand", "name": "Knucklotec (Boss)"},
    {"kingdom": "lake", "name": "Rango (Broodal)"},
    {"kingdom": "wooded", "name": "Spewart (Broodal)"},
    {"kingdom": "wooded", "name": "Torkdrift (Boss)"},
    {"kingdom": "cloud", "name": "Bowser (Boss)"},
    {"kingdom": "lost", "name": "Klepto (Boss)"},
    {"kingdom": "metro", "name": "Mecha Wiggler (Boss)"},
    {"kingdom": "snow", "name": "Rango (Broodal, rematch)"},
    {"kingdom": "seaside", "name": "Mollusque-Lanceur (Boss)"},
    {"kingdom": "luncheon", "name": "Spewart (Broodal, rematch)"},
    {"kingdom": "luncheon", "name": "Cookatiel (Boss)"},
    {"kingdom": "ruined", "name": "Ruined Dragon (Boss)"},
    {"kingdom": "bowser", "name": "Hariet (Broodal, rematch)", "moon": 2},
    {"kingdom": "bowser", "name": "Topper (Broodal, rematch)", "moon": 3},
    {"kingdom": "bowser", "name": "RoboBrood (Broodal)", "moon": 4},
    {"kingdom": "moon", "name": "Madame Broode (Broodal, rematch)"},
]

def _is_broodal_fight(entry: dict) -> bool:
    return "(Broodal" in str(entry.get("name") or "")


NON_BROODAL_BOSS_FIGHTS = [
    b for b in BOSS_FIGHTS if not _is_broodal_fight(b)
] + [{"kingdom": "moon", "name": "Madame Broode (Boss)"}]

BROODAL_FIGHTS = [b for b in BOSS_FIGHTS if _is_broodal_fight(b)]

# Goal → id en CAPTURE_LIST (lista[] = id + name oficial).
CAPTURE_SOLO: dict[str, int] = {
    "Capture Big Chain Chomp": 5,
    "Capture Boulder": 26,
    "Capture Chargin' Chuck": 47,
    "Capture Poison Piranha Plant": 20,
    "Capture Snow Cheep Cheep": 35,
}

_lists_cache: dict | None = None
_regionales_zonas_cache: dict | None = None


def load_regionales_zonas() -> dict:
    global _regionales_zonas_cache
    if _regionales_zonas_cache is None:
        if REGIONALES_ZONAS_PATH.exists():
            _regionales_zonas_cache = json.loads(
                REGIONALES_ZONAS_PATH.read_text(encoding="utf-8")
            )
        else:
            _regionales_zonas_cache = {}
    return _regionales_zonas_cache


def regionales_zonas_entry(goal: str) -> dict | None:
    """Entrada de catalog/regionales_zonas.json para una goal Combined."""
    for entry in load_regionales_zonas().get("goals") or []:
        if entry.get("goal") == goal:
            return entry
    return None


def load_goal_lists() -> dict:
    global _lists_cache
    if _lists_cache is None:
        _lists_cache = json.loads(LISTS_PATH.read_text(encoding="utf-8"))
    return _lists_cache


def clear_goal_lists_cache() -> None:
    global _lists_cache, _regionales_zonas_cache
    _lists_cache = None
    _regionales_zonas_cache = None


register_cache_clear(clear_goal_lists_cache)


def curated_sub_area_levels() -> list[dict]:
    """Pares Level Sub-Area (misma fuente que catalog_lib.load_sub_area_levels)."""
    return list((load_goal_lists().get("lists") or {}).get("sub_area_levels") or [])


def checkpoint_name(kingdom: str, checkpoint: int) -> str | None:
    names = KINGDOM_CHECKPOINT_NAMES.get(kingdom) or []
    if 1 <= checkpoint <= len(names):
        return names[checkpoint - 1]
    return None


def _format_checkpoint_near(kingdom: str, checkpoint: int) -> str:
    name = checkpoint_name(kingdom, int(checkpoint))
    return f"#{int(checkpoint)} {name}" if name else f"#{int(checkpoint)}"


def _resolve_near_field(item: dict) -> None:
    """Mutates item: near_odyssey / near_checkpoint(s) → near; drops curation keys."""
    if item.pop("near_odyssey", None):
        item["near"] = "Odyssey"
        return
    cps = item.pop("near_checkpoints", None)
    cp = item.pop("near_checkpoint", None)
    k = str(item.get("kingdom") or "")
    if cps is not None:
        item["near"] = " / ".join(_format_checkpoint_near(k, int(c)) for c in cps)
    elif cp is not None:
        item["near"] = _format_checkpoint_near(k, int(cp))


def enrich_lista_locations(items: list[dict]) -> list[dict]:
    """Resuelve near_checkpoint(s) / near_odyssey → near.

    near_checkpoint: int → \"#N Nombre\"
    near_checkpoints: [int, ...] → \"#N Nombre / #M Nombre\" (varios CP
    para el mismo ítem).
    near_odyssey: true → \"Odyssey\"
    purchase_site (solo curación): se omite en export.
    """
    out: list[dict] = []
    for raw in items:
        item = dict(raw)
        _resolve_near_field(item)
        item.pop("near_checkpoint_name", None)
        item.pop("near_reference", None)
        item.pop("_note", None)
        item.pop("purchase_site", None)
        # moon_link null → omitir en export
        if item.get("moon_link") is None:
            item.pop("moon_link", None)
        out.append(item)
    return out


def sort_lista_items(items: list[dict]) -> list[dict]:
    """Reino (historia) → moon/checkpoint/id → nombre alfabetico/natural."""
    return sorted(items, key=entity_sort_key)


def curated_list(name: str) -> list[dict]:
    """Lista curada ordenada por historia (sort antes de enrich: near_checkpoint)."""
    data = load_goal_lists()
    raw = list((data.get("lists") or {}).get(name) or [])
    return enrich_lista_locations(sort_lista_items(raw))


def _group_moons(group_id: str) -> list[dict]:
    for group in load_bingo_groups():
        if group.get("id") == group_id:
            return list(group.get("moons") or [])
    return []


def _kingdoms_from_fixed_objectives(group: dict) -> list[str]:
    kingdoms: list[str] = []
    for ref in group.get("objectives") or []:
        goal = str(ref.get("goal") or "")
        if goal.startswith(GOAL_X):
            continue
        for cat in ref.get("board_categories") or []:
            if cat in KINGDOM_COLUMNS:
                kingdoms.append(cat)
                break
    return kingdoms


def kingdoms_from_group(group_id: str) -> list[str]:
    """Reinos con goal fija en un grupo bingo (p. ej. talkatoo, moon_rock)."""
    kingdoms: list[str] = []
    for group in load_bingo_groups():
        if group.get("id") != group_id:
            continue
        kingdoms.extend(_kingdoms_from_fixed_objectives(group))
    return sorted(set(kingdoms), key=lambda k: KINGDOM_COLUMNS.index(k))


def kingdom_entries(kingdoms: list[str]) -> list[dict]:
    return [{"kingdom": k} for k in kingdoms]


def regional_coin_kingdoms() -> list[str]:
    """Reinos con monedas regionales in-scope (orden de historia).

    Sin Cloud/Ruined (0 purple coins) ni Mushroom (fuera de alcance).
    """
    return [k for k in KINGDOM_COLUMNS if k in SMALL_KINGDOMS or k in LARGE_KINGDOMS]


def regional_coins_for_kingdom(kingdom: str) -> int:
    """Tope SMO: 50 en reinos pequeños, 100 en grandes. 0 si no aplica."""
    if kingdom in SMALL_KINGDOMS:
        return REGIONAL_COINS_SMALL
    if kingdom in LARGE_KINGDOMS:
        return REGIONAL_COINS_LARGE
    return 0


def multi_moon_totals_lista() -> list[dict]:
    """Un entry por reino con Multi-Moons (total = nº de Multi-Moons)."""
    counts: dict[str, int] = {}
    for m in _group_moons("multi_moon"):
        k = str(m.get("kingdom") or "")
        if not k:
            continue
        counts[k] = counts.get(k, 0) + 1
    return [
        {"kingdom": k, "total": counts[k]}
        for k in sorted(counts.keys(), key=kingdom_story_index)
    ]


def regional_totals_lista() -> list[dict]:
    """Un entry por reino con su tope de regionales."""
    return [
        {"kingdom": k, "total": regional_coins_for_kingdom(k)}
        for k in regional_coin_kingdoms()
    ]


def regional_size_lista(*, large: bool) -> list[dict]:
    """Reinos grandes (100) o pequeños (50), orden de historia."""
    kingdoms = LARGE_KINGDOMS if large else SMALL_KINGDOMS
    total = REGIONAL_COINS_LARGE if large else REGIONAL_COINS_SMALL
    return [
        {"kingdom": k, "total": total}
        for k in sorted(kingdoms, key=kingdom_story_index)
    ]


def _zone_max(a: str, b: str) -> str:
    ia = ZONE_ORDER.index(a) if a in ZONE_ORDER else -1
    ib = ZONE_ORDER.index(b) if b in ZONE_ORDER else -1
    return a if ia >= ib else b


def _kingdom_visit_zone(kingdom: str) -> str:
    meta = load_meta()
    story_order = meta["story_order"]
    ceilings = meta["run_tier_ceiling"]
    if kingdom not in story_order:
        return "n"
    ki = story_order.index(kingdom)
    for zone in ZONE_ORDER:
        if ki <= story_order.index(ceilings[zone]):
            return zone
    return "n"


def checkpoint_totals_lista(*, for_all: bool = False) -> list[dict]:
    """Un entry por reino: total, painting; progression solo si ≠ zona del reino.

    for_all=True (All Checkpoints): omite snow/seaside/bowser; si la pintura
    retrasa el tope respecto a la visita, progression = zona de entrada.
    Incluye mushroom (1 CP Yoshi's House), como mushroom#39 en pinturas.
    """
    kingdoms = [k for k in KINGDOM_COLUMNS if k in KINGDOM_CHECKPOINT_META]
    if "mushroom" in KINGDOM_CHECKPOINT_META:
        kingdoms.append("mushroom")
    out: list[dict] = []
    for k in kingdoms:
        if for_all and k in ALL_CHECKPOINTS_EXCLUDED_KINGDOMS:
            continue
        total = int(KINGDOM_CHECKPOINT_META[k]["total"])
        visit = _kingdom_visit_zone(k)
        has_painting = k in PAINTING_CHECKPOINT_KINGDOMS
        entry: dict = {
            "kingdom": k,
            "total": total,
            "painting": has_painting,
        }
        if for_all and has_painting:
            paint_zone = PAINTING_CHECKPOINT_PROGRESSION.get(k, visit)
            effective = _zone_max(visit, paint_zone)
            if effective != visit:
                entry["progression"] = effective
        out.append(entry)
    return out


def checkpoints_for_kingdom(kingdom: str) -> list[dict]:
    meta = KINGDOM_CHECKPOINT_META.get(kingdom)
    if not meta:
        return []
    names = KINGDOM_CHECKPOINT_NAMES.get(kingdom) or []
    odyssey_slot = KINGDOM_CHECKPOINT_ODYSSEY_SLOT.get(kingdom)
    total = int(meta["total"])
    out: list[dict] = []
    for i in range(1, total + 1):
        entry: dict = {"kingdom": kingdom, "checkpoint": i}
        if i <= len(names):
            entry["name"] = names[i - 1]
        if odyssey_slot == i:
            entry["odyssey"] = True
        if kingdom in PAINTING_CHECKPOINT_KINGDOMS and i == total:
            entry["painting"] = True
        out.append(entry)
    return out


def all_checkpoints() -> list[dict]:
    out: list[dict] = []
    for k in KINGDOM_COLUMNS:
        if k in KINGDOM_CHECKPOINT_META:
            out.extend(checkpoints_for_kingdom(k))
    if "mushroom" in KINGDOM_CHECKPOINT_META:
        out.extend(checkpoints_for_kingdom("mushroom"))
    return out


def checkpoint_goal_fields(goal: str) -> dict | None:
    """Metadatos de pool: checkpoint_total solo en Total (suma de CPs).

    All Checkpoints cuenta reinos (n_kingdoms / by_kingdom), no checkpoints sueltos.
    """
    gl = goal.lower().replace("[[s]]", "")
    if "checkpoint" not in gl:
        return None
    if goal.startswith("All Checkpoints"):
        return None
    if "total" in gl and goal.startswith(GOAL_X):
        lista = checkpoint_totals_lista()
        return {"checkpoint_total": sum(int(x["total"]) for x in lista)}
    return None


_REGIONAL_ZONE_TOTALS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("8-bit", "regional"), 29),
    (("deep woods",), 9),
    (("shiveria", "regional"), 37),
    (("snow overworld", "regional"), 13),
    (("tostarena", "regional"), 29),
    (("sand ruins", "regional"), 16),
    (("sand ice", "regional"), 11),
    (("jaxi", "regional"), 12),
)


def _regional_zone_total(gl: str) -> int | None:
    for frags, total in _REGIONAL_ZONE_TOTALS:
        if all(f in gl for f in frags):
            return total
    return None


def regional_goal_fields(goal: str, kingdom: str | None) -> dict | None:
    """Metadatos de pool regional; Total usa suma de la lista por reino."""
    gl = goal.lower().replace("[[s]]", "")
    if "regional coin" not in gl:
        return None
    if "total regional" in gl:
        lista = regional_totals_lista()
        return {"regional_total": sum(int(x["total"]) for x in lista)}
    if "large kingdom" in gl or "small kingdom" in gl:
        return None  # lista en regional_size_lista; sin regional_total agregado
    # Pirámide invertida: sin goal regional propia.
    zone = _regional_zone_total(gl)
    if zone is not None:
        return {"regional_total": zone}
    # Clusters dentro de Levels sub_area (catalog/regionales_zonas.json).
    if "sub-area" in gl and "regional" in gl:
        rz = regionales_zonas_entry(goal)
        total = int((rz or {}).get("total") or 84)
        return {"regional_total": total}
    if kingdom:
        return {"regional_total": regional_coins_for_kingdom(kingdom)}
    return None


def _capture_lista_entry(meta: dict) -> dict | None:
    """Una fila lista: kingdom (primer reino in-scope), id y name de CAPTURE_LIST."""
    reinos = list(meta.get("reinos") or [])
    first = next(
        (k for k in reinos if k in KINGDOM_COLUMNS or k in ("mushroom", "cloud", "ruined")),
        None,
    )
    if first is None:
        return None
    return {
        "kingdom": first,
        "id": int(meta["id"]),
        "capture": str(meta["name"]),
    }


def unique_captures_list() -> list[dict]:
    """Lista Unique Captures: {id, kingdom, capture} (una fila por captura).

    Capturas con merge_into (p. ej. Fire Bro → Fire/Hammer Bro) no se listan
    aparte; el id primario usa CAPTURE_MERGE_DISPLAY si existe.
    """
    skip = set(CAPTURE_MERGE_INTO)
    out: list[dict] = []
    for meta in CAPTURE_LIST:
        if meta.get("postgame"):
            continue
        cap_id = int(meta["id"])
        if cap_id in skip:
            continue
        entry = _capture_lista_entry(meta)
        if not entry:
            continue
        display = CAPTURE_MERGE_DISPLAY.get(cap_id)
        out.append(
            {
                "id": int(entry["id"]),
                "kingdom": str(entry["kingdom"]),
                "capture": str(display or entry["capture"]),
            }
        )
    out.sort(key=lambda x: int(x["id"]))
    return out


def capture_solo_lista(goal: str) -> list[dict]:
    """lista[] de Capture X: id + name desde CAPTURE_LIST."""
    cap_id = CAPTURE_SOLO.get(goal)
    if cap_id is None:
        return []
    meta = CAPTURE_BY_ID.get(cap_id)
    if not meta:
        return []
    entry = _capture_lista_entry(meta)
    return [entry] if entry else []


def moon_rock_entry(kingdom: str) -> dict:
    for item in curated_list("moon_rocks"):
        if item.get("kingdom") == kingdom:
            return dict(item)
    return {"kingdom": kingdom, "name": "Moon Rock"}


def talkatoo_entry(kingdom: str) -> dict:
    for item in curated_list("talkatoos"):
        if item.get("kingdom") == kingdom:
            return dict(item)
    return {"kingdom": kingdom, "name": "Talkatoo"}


def _checkpoint_lista(goal: str, kingdom: str | None) -> list[dict]:
    gl = goal.lower()
    if goal.startswith("All Checkpoints"):
        return checkpoint_totals_lista(for_all=True)
    if "total" in gl:
        return checkpoint_totals_lista()
    if kingdom and kingdom in KINGDOM_CHECKPOINT_META:
        return checkpoints_for_kingdom(kingdom)
    return checkpoint_totals_lista()


def _regional_lista(goal: str) -> list[dict]:
    gl = goal.lower()
    if "total regional" in gl:
        return regional_totals_lista()
    if "large kingdom" in gl:
        return regional_size_lista(large=True)
    if "small kingdom" in gl:
        return regional_size_lista(large=False)
    return []


_FIXED_GOAL_LISTAS: dict[str, list[dict]] = {
    "{{X}} Boss Fights": BOSS_FIGHTS,
    "{{X}} Kingdom Boss Fight[[s]]": NON_BROODAL_BOSS_FIGHTS,
    "{{X}} Broodal Fights": BROODAL_FIGHTS,
    "Defeat Bowser in Cloud Kingdom": [
        {"kingdom": "cloud", "name": "Bowser (Boss)"}
    ],
    "Defeat Madame Broode in Moon Kingdom": [
        {"kingdom": "moon", "name": "Madame Broode (Broodal, rematch)"}
    ],
    "Defeat Ruined Dragon": [
        {"kingdom": "ruined", "name": "Ruined Dragon (Boss)"}
    ],
    "Save Cappy From Klepto": [
        {"kingdom": "lost", "name": "Klepto (Boss)"}
    ],
    "Correct Wooded Sphynx Question": [
        {"kingdom": "wooded", "name": "Wooded Sphynx"}
    ],
}

_CURATED_GOAL_LISTAS: dict[str, str] = {
    "{{X}} Talkatoos": "talkatoos",
    "{{X}} Moon Rocks": "moon_rocks",
    "Call Jaxi from {{X}} Stands": "jaxi_stands",
    "{{X}} Unique Life Up Hearts": "life_up_hearts",
    "Capture {{X}} Binoculars": "binoculars",
    "Activate {{X}} Levers": "levers",
    "Activate {{X}} P-Switch[[es]]": "p_switches",
    "Activate {{X}} Ground-Pound Switch[[es]]": "ground_pound_switches",
    "{{X}} Pixel Cat Marios/Peaches": "pixel_cat_mario_peach",
    "{{X}} Pixel Luigis": "pixel_luigis",
    "{{X}} Souvenirs": "souvenirs",
    "{{X}} Stickers": "stickers",
    "Purchase {{X}} Costume Sets": "costume_sets",
    "Purchase {{X}} Hats": "hats",
}


def build_goal_lista(
    goal: str,
    _obj: dict,
    *,
    kingdom: str | None,
) -> list[dict]:
    """Devuelve la lista de elementos que cuentan para completar la goal."""
    gl = goal.lower()

    if goal in CAPTURE_SOLO:
        items = capture_solo_lista(goal)
    elif goal in _FIXED_GOAL_LISTAS:
        items = list(_FIXED_GOAL_LISTAS[goal])
    elif goal.endswith(" Talkatoo") and GOAL_X not in goal and kingdom:
        items = [talkatoo_entry(kingdom)]
    elif goal.endswith(" Moon Rock") and kingdom:
        items = [moon_rock_entry(kingdom)]
    elif goal in _CURATED_GOAL_LISTAS:
        items = curated_list(_CURATED_GOAL_LISTAS[goal])
    elif goal.startswith("All Multi-Moons"):
        items = multi_moon_totals_lista()
    elif "checkpoint" in gl:
        items = _checkpoint_lista(goal, kingdom)
    elif "regional coin" in gl:
        items = _regional_lista(goal)
    elif goal == "{{X}} Unique Captures":
        items = unique_captures_list()
    else:
        items = []

    return sort_lista_items(items)
