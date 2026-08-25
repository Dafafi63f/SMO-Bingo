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
from export_capturas_lunas import CAPTURE_LIST
from fix_bingo_group_ranges import (
    ALL_CHECKPOINTS_EXCLUDED_KINGDOMS,
    KINGDOM_CHECKPOINT_META,
    KINGDOM_CHECKPOINT_NAMES,
    KINGDOM_CHECKPOINT_ODYSSEY_SLOT,
    METRO_NIGHT_CHECKPOINT_NAMES,
    PAINTING_CHECKPOINT_KINGDOMS,
    PAINTING_CHECKPOINT_MOON,
    PAINTING_CHECKPOINT_PROGRESSION,
)

LISTS_PATH = CATALOG_DIR / "goal_lists.json"
ZONAS_REINO_PATH = CATALOG_DIR / "zonas_reino.json"
# Capturas: capturas_lunas.json / CAPTURE_LIST (no lists.captures).
# Pares Level Sub-Area: Files/sub_area_levels_data.py (no lists.*).
REGIONAL_COINS_SMALL = 50
REGIONAL_COINS_LARGE = 100
# Compat: tope de un reino grande (p. ej. docs / All Large Kingdom).
REGIONAL_COINS_PER_KINGDOM = REGIONAL_COINS_LARGE
GOAL_X = "{{X}}"

LARGE_KINGDOMS = ("sand", "wooded", "metro", "seaside", "luncheon", "bowser")
SMALL_KINGDOMS = ("cap", "cascade", "lake", "lost", "snow", "moon")

_zonas_zone_cache: dict[tuple[str, str, str], str] | None = None


def load_zonas_zone_index() -> dict[tuple[str, str, str], str]:
    """(kingdom, source, name) → zone. Fuente: Catalog/zonas_reino.json."""
    global _zonas_zone_cache
    if _zonas_zone_cache is not None:
        return _zonas_zone_cache
    out: dict[tuple[str, str, str], str] = {}
    if ZONAS_REINO_PATH.is_file():
        data = json.loads(ZONAS_REINO_PATH.read_text(encoding="utf-8"))
        for block in data.get("kingdoms") or []:
            if not isinstance(block, dict):
                continue
            kingdom = str(block.get("kingdom") or "")
            for it in block.get("list") or []:
                if not isinstance(it, dict) or not it.get("zone"):
                    continue
                source = str(it.get("source") or "")
                name = str(it.get("name") or "")
                if kingdom and source:
                    out[(kingdom, source, name)] = str(it["zone"])
    _zonas_zone_cache = out
    return out


def lookup_item_zone(
    kingdom: str, source: str, name: str, *, default: str | None = None
) -> str | None:
    """Zone de un ítem/luna desde zonas_reino (no desde goal_lists)."""
    return load_zonas_zone_index().get(
        (str(kingdom), str(source), str(name)), default
    )


def regional_cluster_zone(row: dict) -> str:
    """Zone de un cluster regional (zonas_reino; fallback campo legado)."""
    if row.get("zone"):
        return str(row["zone"])
    return (
        lookup_item_zone(
            str(row.get("kingdom") or ""),
            "regionals",
            str(row.get("name") or ""),
        )
        or ""
    )


def _is_broodal_fight(entry: dict) -> bool:
    return "(Broodal" in str(entry.get("name") or "")


# Fallback si falta lists.bosses en goal_lists.json.
_BOSS_FIGHTS_FALLBACK: list[dict] = [
    {"kingdom": "cap", "name": "Topper (Broodal)", "disponibilidad": "base"},
    {"kingdom": "cascade", "name": "Madame Broode (Broodal)", "disponibilidad": "base"},
    {"kingdom": "sand", "name": "Hariet (Broodal)", "disponibilidad": "base"},
    # 2º boss del reino → mid_story
    {"kingdom": "sand", "name": "Knucklotec (Boss)", "disponibilidad": "mid_story"},
    {"kingdom": "lake", "name": "Rango (Broodal)", "disponibilidad": "base"},
    {"kingdom": "wooded", "name": "Spewart (Broodal)", "disponibilidad": "base"},
    {"kingdom": "wooded", "name": "Torkdrift (Boss)", "disponibilidad": "mid_story"},
    {"kingdom": "lost", "name": "Bowser (Boss)", "disponibilidad": "base"},
    {"kingdom": "lost", "name": "Klepto (Boss)", "disponibilidad": "base"},
    {"kingdom": "metro", "name": "Mecha Wiggler (Boss)", "disponibilidad": "base"},
    {"kingdom": "snow", "name": "Rango (Broodal, rematch)", "disponibilidad": "base"},
    {"kingdom": "seaside", "name": "Mollusque-Lanceur (Boss)", "disponibilidad": "base"},
    {"kingdom": "luncheon", "name": "Spewart (Broodal, rematch)", "disponibilidad": "base"},
    {"kingdom": "luncheon", "name": "Cookatiel (Boss)", "disponibilidad": "mid_story"},
    {"kingdom": "ruined", "name": "Ruined Dragon (Boss)", "disponibilidad": "base"},
    {"kingdom": "bowser", "name": "Hariet (Broodal, rematch)", "moon": 2, "disponibilidad": "base"},
    {"kingdom": "bowser", "name": "Topper (Broodal, rematch)", "moon": 3, "disponibilidad": "base"},
    {"kingdom": "bowser", "name": "RoboBrood (Broodal)", "moon": 4, "disponibilidad": "base"},
    # Una sola pelea Moon (Broodal; no kingdom-boss pool).
    {
        "kingdom": "moon",
        "name": "Madame Broode (Broodal, rematch)",
        "disponibilidad": "base",
    },
]

# Compat: alias al fallback (build_goal_lista usa boss_*_lista()).
BOSS_FIGHTS = _BOSS_FIGHTS_FALLBACK
BROODAL_FIGHTS = [b for b in BOSS_FIGHTS if _is_broodal_fight(b)]
NON_BROODAL_BOSS_FIGHTS = [
    b
    for b in BOSS_FIGHTS
    if not _is_broodal_fight(b) and "Klepto" not in str(b.get("name") or "")
]

# Goal → id en CAPTURE_LIST (capturas_lunas.json; ya no generan lista[]).
CAPTURE_SOLO: dict[str, int] = {
    "Capture Big Chain Chomp": 5,
    "Capture Boulder": 26,
    "Capture Chargin' Chuck": 47,
    "Capture Poison Piranha Plant": 20,
    "Capture Snow Cheep Cheep": 35,
}

_lists_cache: dict | None = None
_moon_avail_cache: dict[tuple[str, int], str] | None = None
_sub_area_disp_cache: dict[tuple[str, str], str] | None = None


# zone slug → level name en lists.sub_area_levels (misma disponibilidad).
# Solo zones físicas 1:1 (las interiors se colapsaron a overworld).
_REGIONAL_ZONE_TO_SUB_AREA_LEVEL: dict[str, str] = {
    "jaxi_ruins": "Jaxi Driving",
    "iron_road": "Flooding Pipeway",
    "deep_woods": "Foggy Room",
    "station_8": "Elevator Shaft",
    "observation_deck": "Cloud Walking",
    "snowy_mountain": "Cloud Spinning",
}

# Zonas overworld con disponibilidad distinta de base.
_REGIONAL_ZONE_DISPONIBILIDAD: dict[tuple[str, str], str] = {
    ("sand", "underground_temple"): "mid_story",
    ("sand", "ice_cave"): "base",
    ("lost", "moon_rock"): "world_peace",
    ("bowser", "inner_wall"): "world_peace",  # Spinning Tower door / regionals
}

# Nombres → level sub_area (cuando varias subáreas comparten zone física).
_REGIONAL_NAME_TO_SUB_AREA_LEVEL: tuple[tuple[str, str], ...] = (
    ("frog pond", "Frog Pond"),
    ("push-block peril", "Push-Block Peril"),
    ("poison tide", "Poison Tide"),
    ("chasm lifts", "Chasm Lifts"),
    ("invisible maze", "Invisible Maze"),
    ("strange neighborhood", "Strange Neighborhood"),
    ("flower road", "Flower Road Run"),
    ("elevator escalation", "Elevator Shaft"),
    ("walking on clouds", "Cloud Walking"),
    ("flooding pipeway", "Flooding Pipeway"),
    ("jump, grab, cling", "Climbing Course"),
    ("high-rise", "High-Rise Building"),
    ("bullet billding", "Bullet Billding"),
    ("motor scooter", "T-Rex Chase"),
    ("fork flickin", "Fork Flickin'"),
    ("cheese rocks", "Cheese Rocks Room"),
    ("magma narrow", "Magma Crossing"),
    ("spinning athletics", "Spinning Athletics"),
    ("spinning tower", "Spinning Tower"),
)


def _sub_area_disponibilidad_lookup() -> dict[tuple[str, str], str]:
    """(kingdom, level_name) → disponibilidad desde sub_area_levels_data."""
    global _sub_area_disp_cache
    if _sub_area_disp_cache is None:
        from catalog_lib import load_sub_area_levels

        out: dict[tuple[str, str], str] = {}
        for row in load_sub_area_levels():
            k = str(row.get("kingdom") or "")
            level = str(row.get("level") or "")
            disp = row.get("disponibilidad")
            if k and level and disp:
                out[(k, level)] = str(disp)
        _sub_area_disp_cache = out
    return _sub_area_disp_cache


def infer_regional_cluster_disponibilidad(
    item: dict, *, kingdom: str | None = None
) -> str:
    """Disponibilidad de un cluster de monedas regionales.

    Reglas:
      - Cap: revisit (wiki: no se cogen hasta potenciar Odyssey en Cascade).
      - Match Sub-Area Level (sub_area_levels_data) por zone / nombre.
      - Overrides de zona (p. ej. Underground Temple → mid_story).
      - Resto: base.
    """
    explicit = item.get("disponibilidad")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    k = str(kingdom or item.get("kingdom") or "")
    if k == "cap":
        return "revisit"
    zone = regional_cluster_zone(item)
    name_l = str(item.get("name") or "").lower()
    sub_lookup = _sub_area_disponibilidad_lookup()
    level = _REGIONAL_ZONE_TO_SUB_AREA_LEVEL.get(zone)
    if level and (k, level) in sub_lookup:
        return sub_lookup[(k, level)]
    for needle, level_name in _REGIONAL_NAME_TO_SUB_AREA_LEVEL:
        if needle in name_l and (k, level_name) in sub_lookup:
            return sub_lookup[(k, level_name)]
    if (k, zone) in _REGIONAL_ZONE_DISPONIBILIDAD:
        return _REGIONAL_ZONE_DISPONIBILIDAD[(k, zone)]
    if zone == "summit_path":
        if "cloud" in name_l:
            return "world_peace"
        if "flower" in name_l or "elevator" in name_l:
            return "mid_story"
    return "base"


def enrich_regional_cluster(item: dict, *, kingdom: str | None = None) -> dict:
    """Añade kingdom (si falta) y disponibilidad al cluster regional."""
    out = dict(item)
    k = str(kingdom or out.get("kingdom") or "")
    if k and not out.get("kingdom"):
        out["kingdom"] = k
    out["disponibilidad"] = infer_regional_cluster_disponibilidad(
        out, kingdom=k or None
    )
    return out


def all_regional_clusters() -> list[dict]:
    """lists.regionals (fuente de clusters)."""
    raw = list((load_goal_lists().get("lists") or {}).get("regionals") or [])
    return [enrich_regional_cluster(x) for x in raw]


def _regional_counts_by_kingdom() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in all_regional_clusters():
        k = str(row.get("kingdom") or "")
        if not k:
            continue
        bucket = out.setdefault(k, {"total": 0, "n_groups": 0})
        bucket["total"] += int(row.get("total") or 0)
        bucket["n_groups"] += 1
    return out


def regional_by_kingdom_lista(*, kingdoms: tuple[str, ...] | None = None) -> list[dict]:
    """Agregado por reino desde lists.regionals (total + n_groups)."""
    counts = _regional_counts_by_kingdom()
    keys = kingdoms if kingdoms is not None else tuple(regional_coin_kingdoms())
    return [
        {
            "kingdom": k,
            "total": int(counts.get(k, {}).get("total") or regional_coins_for_kingdom(k)),
            "n_groups": int(counts.get(k, {}).get("n_groups") or 0),
        }
        for k in keys
        if k in counts or kingdoms is not None
    ]


# Filtros de goals regionales subset → lists.regionals.
# zone se resuelve vía zonas_reino (regional_cluster_zone).
_REGIONAL_CLUSTER_FILTERS: dict[str, object] = {
    "{{X}} Sand Tostarena Regional Coins": lambda r: r.get("kingdom") == "sand"
    and regional_cluster_zone(r) == "tostarena",
    "{{X}} Sand Jaxi Regional Coins": lambda r: r.get("kingdom") == "sand"
    and regional_cluster_zone(r) == "jaxi_ruins",
    "{{X}} Sand Ruins Regional Coins": lambda r: r.get("kingdom") == "sand"
    and regional_cluster_zone(r) in {"ruins", "moe_eye_path"},
    "{{X}} Sand Ice Regional Coins": lambda r: r.get("kingdom") == "sand"
    and regional_cluster_zone(r) in {"ice_cave", "underground_temple"},
    "{{X}} Deep Woods Regional Coins": lambda r: r.get("kingdom") == "wooded"
    and regional_cluster_zone(r) == "deep_woods",
    "{{X}} Snow Overworld Regional Coins": lambda r: r.get("kingdom") == "snow"
    and regional_cluster_zone(r) == "overworld",
    "{{X}} Snow Shiveria Regional Coins": lambda r: r.get("kingdom") == "snow"
    and regional_cluster_zone(r) != "overworld",
    "{{X}} Sub-Area Regional Coins": lambda r: bool(r.get("sub_area")),
    "{{X}} 8-Bit Regional Coins": lambda r: bool(r.get("eight_bit")),
}

_KINGDOM_REGIONAL_GOALS: dict[str, str] = {
    "{{X}} Cap Regional Coins": "cap",
    "{{X}} Cascade Regional Coins": "cascade",
    "{{X}} Sand Regional Coins": "sand",
    "{{X}} Lake Regional Coins": "lake",
    "{{X}} Wooded Regional Coins": "wooded",
    "{{X}} Lost Regional Coins": "lost",
    "{{X}} Metro Regional Coins": "metro",
    "{{X}} Snow Regional Coins": "snow",
    "{{X}} Seaside Regional Coins": "seaside",
    "{{X}} Luncheon Regional Coins": "luncheon",
    "{{X}} Bowser's Regional Coins": "bowser",
    "{{X}} Moon Regional Coins": "moon",
}


def regional_clusters_for_goal(goal: str) -> list[dict] | None:
    """Clusters de lists.regionals para una goal Combined, o None."""
    filt = _REGIONAL_CLUSTER_FILTERS.get(goal)
    if filt is not None:
        return [dict(r) for r in all_regional_clusters() if filt(r)]  # type: ignore[operator]
    kingdom = _KINGDOM_REGIONAL_GOALS.get(goal)
    if kingdom is not None:
        return [
            dict(r) for r in all_regional_clusters() if r.get("kingdom") == kingdom
        ]
    return None


def regional_lista_for_goal(goal: str) -> list[dict] | None:
    """lista[] regional: clusters o by_kingdom. None si la goal no es regional."""
    gl = goal.lower().replace("[[s]]", "")
    if "regional coin" not in gl:
        return None
    if "total regional" in gl:
        return regional_by_kingdom_lista()
    if "large kingdom" in gl:
        return regional_by_kingdom_lista(kingdoms=LARGE_KINGDOMS)
    if "small kingdom" in gl:
        return regional_by_kingdom_lista(kingdoms=SMALL_KINGDOMS)
    clusters = regional_clusters_for_goal(goal)
    if clusters is not None:
        return clusters
    return None


def apply_regional_disponibilidad_to_lists() -> int:
    """Escribe disponibilidad en lists.regionals. Devuelve n cambios."""
    data = load_goal_lists()
    rows = list((data.get("lists") or {}).get("regionals") or [])
    n = 0
    new_rows: list[dict] = []
    for raw in rows:
        item = enrich_regional_cluster(raw)
        if item.get("disponibilidad") != raw.get("disponibilidad"):
            n += 1
        new_rows.append(item)
    data.setdefault("lists", {})["regionals"] = new_rows
    write_goal_lists(data)
    return n


def load_goal_lists() -> dict:
    global _lists_cache
    if _lists_cache is None:
        _lists_cache = json.loads(LISTS_PATH.read_text(encoding="utf-8"))
    return _lists_cache


def goal_lists_item_count(data: dict | None = None) -> int:
    """Número de filas en lists.* (dicts)."""
    if data is None:
        data = load_goal_lists()
    n_items = 0
    for _list_name, rows in (data.get("lists") or {}).items():
        if not isinstance(rows, list):
            continue
        for raw in rows:
            if isinstance(raw, dict):
                n_items += 1
    return n_items


_LIST_ITEM_KEY_ORDER = (
    "kingdom",
    "id",
    "id_list",
    "name",
    "capture",
    "level",
    "disponibilidad",
)


def _reorder_list_item(row: dict) -> dict:
    ordered: dict = {}
    for key in _LIST_ITEM_KEY_ORDER:
        if key in row:
            ordered[key] = row.pop(key)
    ordered.update(row)
    return ordered


def assign_goal_lists_ids(data: dict) -> dict:
    """Asegura id (global 1..n_items) e id_list (por sublista).

    id_list: conserva el valor previo (id_list o id); si falta, 1..n en la lista.
    id: 1..n_items al recorrer lists.* en orden alfa, filas en orden del file.
    """
    lists = data.get("lists") or {}
    if not isinstance(lists, dict):
        return data
    # 1) id_list por sublista
    for list_name in sorted(lists):
        rows = lists.get(list_name) or []
        next_local = 0
        out_rows: list[dict] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            local = item.get("id_list")
            if local is None:
                local = item.get("id")
            if local is None:
                next_local += 1
                local = next_local
            else:
                next_local = max(next_local, int(local))
            item["id_list"] = int(local)
            out_rows.append(item)
        lists[list_name] = out_rows
    # 2) id global del file
    next_global = 0
    for list_name in sorted(lists):
        out_rows = []
        for item in lists.get(list_name) or []:
            next_global += 1
            item = dict(item)
            item["id"] = next_global
            out_rows.append(_reorder_list_item(item))
        lists[list_name] = out_rows
    data["lists"] = lists
    return data


def refresh_goal_lists_header(data: dict) -> dict:
    """n_lists / n_items + nota; orden de claves estable."""
    assign_goal_lists_ids(data)
    lists = data.get("lists") or {}
    if isinstance(lists, dict):
        data["lists"] = {k: lists[k] for k in sorted(lists)}
    data["n_lists"] = len(data.get("lists") or {})
    data["n_items"] = goal_lists_item_count(data)
    data.pop("n_with_zone", None)
    data.pop("n_without_zone", None)
    data["_note"] = (
        "Listas curadas a mano. lists.regionals = clusters de monedas; "
        "lists.shops = Crazy Cap por reino; merchandise en costume_sets/hats/"
        "souvenirs/stickers/boxer_shorts. "
        "Capturas: capturas_lunas.json / CAPTURE_LIST (no lists.captures). "
        "Pares Level Sub-Area: Files/sub_area_levels_data.py (no lists.*). "
        "Ubicación (zone): solo Catalog/zonas_reino.json (no aquí). "
        "id = global del file (1..n_items, lists alfa + orden del file); "
        "id_list = id dentro de la sublista. "
        "n_items → Catalog/zonas_reino.json n_items."
    )
    ordered: dict = {}
    for key in (
        "_note",
        "_definition",
        "n_lists",
        "n_items",
        "lists",
    ):
        if key in data:
            ordered[key] = data[key]
    for key, value in data.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def strip_goal_lists_zones(data: dict) -> dict:
    """Quita zone de lists.* (vive solo en zonas_reino.json)."""
    lists = data.get("lists") or {}
    if not isinstance(lists, dict):
        return data
    for name, rows in lists.items():
        if not isinstance(rows, list):
            continue
        cleaned: list = []
        for raw in rows:
            if not isinstance(raw, dict):
                cleaned.append(raw)
                continue
            item = dict(raw)
            item.pop("zone", None)
            cleaned.append(item)
        lists[name] = cleaned
    data["lists"] = lists
    return data


def write_goal_lists(data: dict) -> None:
    """Escribe goal_lists.json con cabecera de conteos actualizada.

    Sin zone (ubicación solo en zonas_reino.json).
    """
    from catalog_lib import write_catalog_json

    strip_goal_lists_zones(data)
    write_catalog_json(LISTS_PATH, refresh_goal_lists_header(data))
    clear_goal_lists_cache()


def clear_goal_lists_cache() -> None:
    global _lists_cache, _moon_avail_cache, _sub_area_disp_cache, _zonas_zone_cache
    _lists_cache = None
    _moon_avail_cache = None
    _sub_area_disp_cache = None
    _zonas_zone_cache = None


register_cache_clear(clear_goal_lists_cache)


def _moon_disponibilidad_lookup() -> dict[tuple[str, int], str]:
    """Cache (kingdom, moon) → disponibilidad de la matriz."""
    global _moon_avail_cache
    if _moon_avail_cache is None:
        from catalog_lib import build_matrix_moon_registry

        _moon_avail_cache = {
            key: str(entry.get("availability") or "base")
            for key, entry in build_matrix_moon_registry().items()
        }
    return _moon_avail_cache


def disponibilidad_from_moon_ref(item: dict) -> str | None:
    """Disponibilidad de moon_link o campo moon (+kingdom); None si no hay link."""
    link = item.get("moon_link")
    if isinstance(link, dict) and link.get("moon") is not None:
        k = str(link.get("kingdom") or item.get("kingdom") or "")
        try:
            n = int(link["moon"])
        except (TypeError, ValueError):
            return None
        if k:
            return _moon_disponibilidad_lookup().get((k, n))
    if item.get("moon") is not None:
        k = str(item.get("kingdom") or "")
        try:
            n = int(item["moon"])
        except (TypeError, ValueError):
            return None
        if k:
            return _moon_disponibilidad_lookup().get((k, n))
    return None


def curated_sub_area_levels() -> list[dict]:
    """Pares Level Sub-Area (misma fuente que catalog_lib.load_sub_area_levels)."""
    from catalog_lib import load_sub_area_levels

    return list(load_sub_area_levels())


def checkpoint_name(kingdom: str, checkpoint: int) -> str | None:
    names = KINGDOM_CHECKPOINT_NAMES.get(kingdom) or []
    if 1 <= checkpoint <= len(names):
        return names[checkpoint - 1]
    return None


_NEAR_LOCATION_KEYS = frozenset(
    {
        "near",
        "near_checkpoint",
        "near_checkpoints",
        "near_odyssey",
        "near_checkpoint_name",
        "near_reference",
    }
)


def enrich_lista_locations(items: list[dict]) -> list[dict]:
    """Limpia curación para export (referencia / grupos).

    Sin zone (solo en zonas_reino). Sin near* / purchase_site / eight_bit.
    Si hay moon_link o moon y falta disponibilidad → hereda de la luna.
    """
    out: list[dict] = []
    for raw in items:
        item = dict(raw)
        for key in _NEAR_LOCATION_KEYS:
            item.pop(key, None)
        item.pop("zone", None)
        item.pop("_note", None)
        item.pop("purchase_site", None)
        item.pop("eight_bit", None)  # solo curación (filtro 8-Bit Regional)
        # moon_link ya marca Secret Path / pintura inbound
        if item.get("moon_link") is not None:
            item.pop("painting", None)
        # moon_link null → omitir en export
        if item.get("moon_link") is None:
            item.pop("moon_link", None)
        if not item.get("disponibilidad"):
            inherited = disponibilidad_from_moon_ref(item)
            if inherited:
                item["disponibilidad"] = inherited
        out.append(item)
    return out


def sort_lista_items(items: list[dict]) -> list[dict]:
    """Reino (historia) → source alfa → id_list/id → nombre/precio.

    Agrupa por `source` (como zonas_reino tras moons) para no intercalear
    p. ej. checkpoints y regionals por el mismo id_list.
    """
    return sorted(
        items,
        key=lambda item: (
            kingdom_story_index(str(item.get("kingdom") or "")),
            str(item.get("source") or ""),
            entity_sort_key(item),
        ),
    )


def curated_list(name: str) -> list[dict]:
    """Lista curada ordenada por historia (sort → enrich ubicaciones)."""
    data = load_goal_lists()
    raw = list((data.get("lists") or {}).get(name) or [])
    return enrich_lista_locations(sort_lista_items(raw))


def _strip_boss_flags(item: dict) -> dict:
    """Quita flags internos de curación (no van a goals_referencia)."""
    item.pop("kingdom_boss", None)
    item.pop("kingdom_boss_only", None)  # legacy
    return item


def boss_fights_lista() -> list[dict]:
    """Todas las pelea de lists.bosses (orden curado del JSON = historia)."""
    data = load_goal_lists()
    raw = list((data.get("lists") or {}).get("bosses") or [])
    if not raw:
        raw = list(_BOSS_FIGHTS_FALLBACK)
    return [
        _strip_boss_flags(dict(x)) for x in enrich_lista_locations(raw)
    ]


def broodal_fights_lista() -> list[dict]:
    return [x for x in boss_fights_lista() if _is_broodal_fight(x)]


def kingdom_boss_fights_lista() -> list[dict]:
    """Kingdom bosses: pelea no-Broodal (×7). Sin Klepto (goal propia).

    Knucklotec, Torkdrift, Bowser (Cloud), Mecha Wiggler, Mollusque,
    Cookatiel, Ruined Dragon. Broodals (incl. RoboBrood / Moon Broode) no.
    Orden = lists.bosses (curado).
    """
    return [
        x
        for x in boss_fights_lista()
        if not _is_broodal_fight(x)
        and "Klepto" not in str(x.get("name") or "")
    ]


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
    """Un entry por reino con su tope de regionales (+ n_groups)."""
    return regional_by_kingdom_lista()


def regional_size_lista(*, large: bool) -> list[dict]:
    """Reinos grandes (100) o pequeños (50), orden de historia."""
    kingdoms = LARGE_KINGDOMS if large else SMALL_KINGDOMS
    return regional_by_kingdom_lista(kingdoms=kingdoms)


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
    """Banderas del reino: lists.checkpoints si existe; si no, meta generada."""
    curated = [
        dict(x)
        for x in curated_list("checkpoints")
        if str(x.get("kingdom") or "") == kingdom
    ]
    if curated:
        return curated
    return _checkpoints_for_kingdom_generated(kingdom)


def _checkpoints_for_kingdom_generated(kingdom: str) -> list[dict]:
    meta = KINGDOM_CHECKPOINT_META.get(kingdom)
    if not meta:
        return []
    names = KINGDOM_CHECKPOINT_NAMES.get(kingdom) or []
    odyssey_slot = KINGDOM_CHECKPOINT_ODYSSEY_SLOT.get(kingdom)
    total = int(meta["total"])
    out: list[dict] = []
    for i in range(1, total + 1):
        entry: dict = {"kingdom": kingdom, "id": i}
        name = names[i - 1] if i <= len(names) else ""
        if name:
            entry["name"] = name
        entry["disponibilidad"] = checkpoint_disponibilidad(kingdom, i, name)
        if odyssey_slot == i:
            entry["odyssey"] = True
        if kingdom in PAINTING_CHECKPOINT_KINGDOMS and i == total:
            mk = PAINTING_CHECKPOINT_MOON.get(kingdom)
            if mk:
                entry["moon_link"] = {"kingdom": mk[0], "moon": mk[1]}
                # moon_link implica pintura; no hace falta flag painting
                entry.pop("disponibilidad", None)
        out.append(entry)
    return out


def checkpoint_disponibilidad(kingdom: str, index: int, name: str) -> str:
    """Casi todas base. Metro día → mid_story; pintura → avail Secret Path."""
    del index
    if kingdom == "metro":
        if name in METRO_NIGHT_CHECKPOINT_NAMES:
            return "base"
        # Isolated Rooftop (pintura): hereda Secret Path, no “día genérico”.
        if name == "Isolated Rooftop":
            mk = PAINTING_CHECKPOINT_MOON.get("metro")
            if mk:
                return _moon_disponibilidad_lookup().get(mk, "mid_story")
        return "mid_story"
    link = PAINTING_CHECKPOINT_MOON.get(kingdom)
    if link:
        names = KINGDOM_CHECKPOINT_NAMES.get(kingdom) or []
        # Último CP del reino (o el único en mushroom) = isla inbound.
        if names and name == names[-1]:
            return _moon_disponibilidad_lookup().get(link, "mid_story")
    return "base"


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
    clusters = regional_clusters_for_goal(goal)
    if clusters is not None:
        return {"regional_total": sum(int(x.get("total") or 0) for x in clusters)}
    zone = _regional_zone_total(gl)
    if zone is not None:
        return {"regional_total": zone}
    if "sub-area" in gl and "regional" in gl:
        clusters = regional_clusters_for_goal("{{X}} Sub-Area Regional Coins") or []
        return {"regional_total": sum(int(x.get("total") or 0) for x in clusters) or 84}
    if kingdom:
        return {"regional_total": regional_coins_for_kingdom(kingdom)}
    return None


def _regional_lista(goal: str) -> list[dict]:
    lista = regional_lista_for_goal(goal)
    return list(lista or [])


def _capture_lista_entry(meta: dict) -> dict | None:
    """Una fila lista: kingdom (primer reino), id y capture."""
    if meta.get("kingdom"):
        first = str(meta["kingdom"])
    else:
        reinos = list(meta.get("reinos") or [])
        first = next(
            (
                k
                for k in reinos
                if k in KINGDOM_COLUMNS or k in ("mushroom", "ruined")
            ),
            None,
        )
    if first is None:
        return None
    name = str(meta.get("capture") or meta.get("name") or "")
    return {
        "kingdom": first,
        "id": int(meta["id"]),
        "capture": name,
    }


def captures_identity_from_capture_list() -> list[dict]:
    """Identidad → lists.captures (sin moons/objectives)."""
    out: list[dict] = []
    for meta in CAPTURE_LIST:
        reinos = list(meta.get("reinos") or [])
        first = next(
            (
                k
                for k in reinos
                if k in KINGDOM_COLUMNS or k in ("mushroom", "ruined")
            ),
            None,
        )
        if first is None:
            continue
        item: dict = {
            "kingdom": first,
            "id": int(meta["id"]),
            "capture": str(meta["name"]),
        }
        for flag in ("special", "transport"):
            if meta.get(flag):
                item[flag] = True
        out.append(item)
    out.sort(key=lambda x: int(x["id"]))
    return out


def sync_captures_into_goal_lists() -> int:
    """No-op: capturas viven en capturas_lunas / CAPTURE_LIST (quita lists.captures)."""
    data = load_goal_lists()
    lists = dict(data.get("lists") or {})
    if "captures" not in lists:
        return 0
    lists.pop("captures", None)
    data["lists"] = lists
    write_goal_lists(data)
    return 0


def unique_captures_list() -> list[dict]:
    """Unique Captures: sin lista[] (catálogo en capturas_lunas.json)."""
    return []


SHOP_ITEM_LISTS = (
    "costume_sets",
    "hats",
    "souvenirs",
    "stickers",
    "boxer_shorts",
)


def apply_shop_zones(data: dict | None = None) -> dict:
    """No-op: zone ya no vive en goal_lists (solo zonas_reino)."""
    if data is None:
        data = load_goal_lists()
    return data


def capture_solo_lista(goal: str) -> list[dict]:
    """Capture X: sin lista[] (identidad en capturas_lunas / CAPTURE_LIST)."""
    return []


def moon_rock_entry(kingdom: str) -> dict:
    for item in curated_list("moon_rocks"):
        if item.get("kingdom") == kingdom:
            return dict(item)
    return {"kingdom": kingdom, "name": "Moon Rock", "disponibilidad": "base"}


def talkatoo_entry(kingdom: str) -> dict:
    for item in curated_list("talkatoos"):
        if item.get("kingdom") == kingdom:
            return dict(item)
    return {"kingdom": kingdom, "name": "Talkatoo", "disponibilidad": "base"}


def _checkpoint_lista(goal: str, kingdom: str | None) -> list[dict]:
    gl = goal.lower()
    if goal.startswith("All Checkpoints"):
        return checkpoint_totals_lista(for_all=True)
    if "total" in gl:
        return checkpoint_totals_lista()
    if kingdom and kingdom in KINGDOM_CHECKPOINT_META:
        return checkpoints_for_kingdom(kingdom)
    return checkpoint_totals_lista()


_FIXED_GOAL_LISTAS: dict[str, list[dict]] = {
    # Resuelto en build_goal_lista vía boss_*_lista() (lists.bosses).
    "Defeat Bowser in Cloud Kingdom": [
        {
            "kingdom": "lost",
            "name": "Bowser (Boss)",
            "disponibilidad": "base",
        }
    ],
    "Defeat Madame Broode in Moon Kingdom": [
        {
            "kingdom": "moon",
            "name": "Madame Broode (Broodal, rematch)",
            "disponibilidad": "base",
        }
    ],
    "Defeat Ruined Dragon": [
        {
            "kingdom": "ruined",
            "name": "Ruined Dragon (Boss)",
            "disponibilidad": "base",
        }
    ],
    "Save Cappy From Klepto": [
        {
            "kingdom": "lost",
            "name": "Klepto (Boss)",
            "disponibilidad": "base",
        }
    ],
}

_CURATED_GOAL_LISTAS: dict[str, str | tuple[str, ...]] = {
    "{{X}} Talkatoos": "talkatoos",
    "{{X}} Moon Rocks": "moon_rocks",
    "Call Jaxi from {{X}} Stand[[s]]": "jaxi_stands",
    "{{X}} Unique Life Up Hearts": "life_up_hearts",
    "Capture {{X}} Binoculars": "binoculars",
    "Activate {{X}} Levers": "levers",
    "Activate {{X}} P-Switches": "p_switches",
    "Activate {{X}} Ground-Pound Switches": "ground_pound_switches",
    "{{X}} Pixel Cat Marios/Peaches": ("pixel_cat_marios", "pixel_cat_peaches"),
    "{{X}} Pixel Luigis": "pixel_luigis",
    "{{X}} Souvenirs": "souvenirs",
    "{{X}} Stickers": "stickers",
    "Purchase {{X}} Costume Sets": "costume_sets",
    "Purchase {{X}} Hats": "hats",
}


def _curated_list_names(goal: str) -> list[str]:
    raw = _CURATED_GOAL_LISTAS.get(goal)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    return list(raw)


def sphynx_for_kingdom(kingdom: str) -> list[dict]:
    """Esfinge de un reino desde lists.sphynxes (×4 in-scope)."""
    return [
        dict(row)
        for row in curated_list("sphynxes")
        if str(row.get("kingdom") or "") == kingdom
    ]


def goal_list_source(goal: str) -> str | None:
    """Nombre de lista en goal_lists.json si la goal usa curación manual."""
    names = _curated_list_names(goal)
    if names:
        return "+".join(names)
    if goal in _FIXED_GOAL_LISTAS:
        return None
    if goal.startswith("Correct ") and goal.endswith(" Sphynx Question"):
        return "sphynxes"
    gl = goal.lower()
    if goal == "{{X}} Boss Fights":
        return "bosses"
    if "checkpoint" in gl:
        return "checkpoints"
    if "regional coin" in goal.lower():
        return "regionals"
    if goal.startswith("All Multi-Moons"):
        return None
    return None


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
    elif goal == "{{X}} Boss Fights":
        items = boss_fights_lista()
    elif goal == "{{X}} Kingdom Boss Fight[[s]]":
        items = kingdom_boss_fights_lista()
    elif goal == "{{X}} Broodal Fights":
        items = broodal_fights_lista()
    elif goal in _FIXED_GOAL_LISTAS:
        items = enrich_lista_locations(list(_FIXED_GOAL_LISTAS[goal]))
    elif goal == "Correct Wooded Sphynx Question":
        items = enrich_lista_locations(sphynx_for_kingdom("wooded"))
    elif goal == "Correct Moon Sphynx Question":
        items = enrich_lista_locations(sphynx_for_kingdom("moon"))
    elif goal.endswith(" Talkatoo") and GOAL_X not in goal and kingdom:
        items = [talkatoo_entry(kingdom)]
    elif goal.endswith(" Moon Rock") and kingdom:
        items = [moon_rock_entry(kingdom)]
    elif goal in _CURATED_GOAL_LISTAS:
        items = []
        for list_name in _curated_list_names(goal):
            items.extend(curated_list(list_name))
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

    # Bosses: orden curado en lists.bosses (p. ej. Luncheon Spewart → Cookatiel).
    if goal in (
        "{{X}} Boss Fights",
        "{{X}} Broodal Fights",
        "{{X}} Kingdom Boss Fight[[s]]",
    ):
        return items
    return sort_lista_items(items)


# Solo checkpoints y life_up_hearts pueden llevar disponibilidad como lista.
LIST_DISPONIBILIDAD_MULTI_ALLOWED = frozenset({"checkpoints", "life_up_hearts"})


def list_item_match_key(item: dict, list_name: str | None = None) -> tuple:
    """Clave estable para emparejar filas goal_lists ↔ goals_referencia.

    list_name=checkpoints → clave cp (aunque el CP tenga zone física).
    Usa id_list (sublista) si existe; si no, id.
    moon solo si no hay name/capture/id (refs lunares puras); bosses con
    moon metadata (Hariet rematch, …) usan id+name como el resto.
    """
    kingdom = str(item.get("kingdom") or "")
    # moons usan moon; CPs usan cp; resto id+name.
    has_lista_identity = bool(
        item.get("name")
        or item.get("capture")
        or item.get("id") is not None
        or item.get("id_list") is not None
    )
    if item.get("moon") is not None and not has_lista_identity:
        return ("moon", kingdom, int(item["moon"]))
    num = item.get("id_list")
    if num is None:
        num = item.get("id")
    if num is None:
        num = item.get("checkpoint")  # legacy
    if num is not None:
        if item.get("capture") is not None:
            return ("capture", kingdom, int(num), str(item.get("capture") or ""))
        name = str(item.get("name") or "")
        if list_name == "checkpoints":
            return ("cp", kingdom, int(num), name)
        # Sin list_name: CPs legacy sin zone (goals_referencia aún puede omitir zone).
        checkpoint_like = (
            item.get("zone") is None
            and item.get("total") is None
            and item.get("regional") is None
            and item.get("coins") is None
            and item.get("level") is None
            and item.get("id_list") is None
        )
        if checkpoint_like:
            return ("cp", kingdom, int(num), name)
        return ("id", kingdom, int(num), name)
    if item.get("moon") is not None:
        return ("moon", kingdom, int(item["moon"]))
    return ("name", kingdom, str(item.get("name") or ""))


def kingdom_context_for_group_goal(group: dict, goal: str) -> str | None:
    """Reino de contexto para expandir lista[] de un goal dentro de un grupo."""
    from catalog_lib import parse_kingdom_prefixed_goal

    gid = str(group.get("id") or "")
    if gid in KINGDOM_COLUMNS:
        return gid
    if group.get("kingdom"):
        return str(group["kingdom"])
    kingdom, _rest = parse_kingdom_prefixed_goal(goal)
    return kingdom


def _split_lista_sources(src: str | None) -> list[str]:
    if not src:
        return []
    return [part for part in str(src).split("+") if part]


def resolve_lista_item_source(item: dict, hint: str | None = None) -> str | None:
    """Nombre de lists.* en goal_lists.json para un elemento."""
    hints = _split_lista_sources(hint)
    if len(hints) == 1:
        return hints[0]

    data = load_goal_lists()
    lists = data.get("lists") or {}
    kingdom = str(item.get("kingdom") or "")
    name = str(item.get("name") or item.get("capture") or "")

    def _match_in(list_name: str) -> bool:
        key = list_item_match_key(item, list_name=list_name)
        for raw in lists.get(list_name) or []:
            if not isinstance(raw, dict):
                continue
            enriched = enrich_lista_locations([dict(raw)])[0]
            if list_item_match_key(enriched, list_name=list_name) == key:
                return True
            if list_item_match_key(dict(raw), list_name=list_name) == key:
                return True
            # Fijos sin id (p. ej. Klepto): emparejar kingdom+name.
            if (
                name
                and str(enriched.get("kingdom") or "") == kingdom
                and str(enriched.get("name") or enriched.get("capture") or "") == name
            ):
                return True
        return False

    for list_name in hints:
        if list_name in lists and _match_in(list_name):
            return list_name
    for list_name in sorted(lists):
        if _match_in(list_name):
            return list_name
    return hints[0] if hints else None


def format_bingo_group_lista_item(item: dict, source: str | None) -> dict:
    """Elemento lista[] de bingo_groups: kingdom, source, id, id_list, name, ….

    id = global de goal_lists (1..n_items); id_list = nº en la sublista.
    Capturas (CAPTURE_LIST): id = id_list = id wiki. Sin zone (→ zonas_reino).
    """
    raw = dict(item)
    out: dict = {}
    kingdom = raw.get("kingdom")
    if kingdom:
        out["kingdom"] = kingdom
    if source:
        out["source"] = source

    global_id = raw.get("id")
    local_id = raw.get("id_list")
    if local_id is None and raw.get("moon") is not None and not raw.get("name"):
        local_id = raw.get("moon")

    row_match: dict | None = None
    if source and source != "captures" and raw.get("name"):
        for row in (load_goal_lists().get("lists") or {}).get(source) or []:
            if not isinstance(row, dict):
                continue
            if (
                str(row.get("kingdom") or "") == str(kingdom or "")
                and str(row.get("name") or "") == str(raw.get("name") or "")
            ):
                row_match = row
                break
    if row_match is not None:
        if global_id is None and row_match.get("id") is not None:
            global_id = row_match["id"]
        if local_id is None:
            local_id = row_match.get("id_list")
            if local_id is None:
                local_id = row_match.get("id")

    # CAPTURE_LIST / filas con un solo id numérico.
    if global_id is None and local_id is not None:
        global_id = local_id
    if local_id is None and global_id is not None:
        local_id = global_id

    if global_id is not None:
        out["id"] = int(global_id)
    if local_id is not None:
        out["id_list"] = int(local_id)

    name = raw.get("name") or raw.get("capture")
    if name:
        out["name"] = name
    disp = raw.get("disponibilidad")
    if disp not in (None, ""):
        out["disponibilidad"] = disp
    return out


def build_bingo_group_lista(
    group: dict,
    objectives: list[dict] | None = None,
    *,
    combined_by_goal: dict | None = None,
) -> tuple[list[dict], str | None]:
    """Union de elementos de goal_lists para objectives con pool lista.

    Cada item: kingdom, source, id, id_list, name, disponibilidad (omitidos si vacíos).
    Devuelve (lista, lista_source). lista_source une fuentes curadas con '+'.
    """
    if objectives is None:
        raw = group.get("objectives") or []
        objectives = [o for o in raw if isinstance(o, dict) and o.get("goal")]
    seen: set[tuple] = set()
    items: list[dict] = []
    sources: set[str] = set()
    combined_by_goal = combined_by_goal or {}
    for obj in objectives:
        goal = str(obj.get("goal") or "")
        if not goal:
            continue
        combined = combined_by_goal.get(goal) or obj
        kingdom = kingdom_context_for_group_goal(group, goal)
        src = goal_list_source(goal)
        raw_items = build_goal_lista(goal, combined, kingdom=kingdom)
        if not raw_items:
            continue
        if src:
            sources.add(src)
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            # Agregados por reino (Total Checkpoints / All Multi-Moons, …):
            # valen en goals_referencia de esa goal, no en lista[] del grupo
            # temático (ahí solo ítems con name / capture / moon).
            if not (
                item.get("name")
                or item.get("capture")
                or item.get("moon") is not None
            ):
                continue
            key = list_item_match_key(item)
            if key in seen:
                continue
            seen.add(key)
            item_source = resolve_lista_item_source(item, src)
            items.append(format_bingo_group_lista_item(item, item_source))

    # shopping: unión completa de Crazy Cap + mercancía (incl. boxer_shorts).
    if str(group.get("id") or "") == "shopping":
        for list_name in ("shops", *SHOP_ITEM_LISTS):
            sources.add(list_name)
            for item in curated_list(list_name):
                if not isinstance(item, dict):
                    continue
                if not (
                    item.get("name")
                    or item.get("capture")
                    or item.get("moon") is not None
                ):
                    continue
                key = list_item_match_key(item, list_name=list_name)
                if key in seen:
                    continue
                seen.add(key)
                items.append(format_bingo_group_lista_item(item, list_name))

    lista = sort_lista_items(items)
    lista_source = "+".join(sorted(sources)) if sources else None
    return lista, lista_source



def normalize_disponibilidad(value: str | list[str] | None) -> str | list[str]:
    if isinstance(value, list):
        return list(value)
    return str(value or "base")


def collect_disponibilidad_list_violations() -> list[tuple[str, str, str]]:
    """[(list_name, item_key, issue), ...] si lista multi fuera de CP/life-up."""
    data = load_goal_lists()
    violations: list[tuple[str, str, str]] = []
    for list_name, items in (data.get("lists") or {}).items():
        if list_name not in LIST_DISPONIBILIDAD_MULTI_ALLOWED:
            for raw in items:
                disp = raw.get("disponibilidad")
                if isinstance(disp, list):
                    key = str(list_item_match_key(raw))
                    violations.append(
                        (
                            list_name,
                            key,
                            "disponibilidad lista solo permitida en "
                            "checkpoints y life_up_hearts",
                        )
                    )
    return violations


def collect_location_field_violations() -> list[tuple[str, str, str]]:
    """Ubicación: zone solo en zonas_reino; near* prohibido en lists/referencia.

    No audita moons[] / lunas-objetivos.
    """
    violations: list[tuple[str, str, str]] = []

    # goal_lists: sin zone ni near*.
    for list_name, items in (load_goal_lists().get("lists") or {}).items():
        for raw in items:
            if not isinstance(raw, dict):
                continue
            key = str(list_item_match_key(raw))
            if "zone" in raw:
                violations.append(
                    (
                        f"goal_lists:{list_name}",
                        key,
                        "zone solo en Catalog/zonas_reino.json",
                    )
                )
            near_hit = sorted(k for k in _NEAR_LOCATION_KEYS if k in raw)
            if near_hit:
                violations.append(
                    (
                        f"goal_lists:{list_name}",
                        key,
                        f"near* prohibido ({near_hit})",
                    )
                )

    # goals_referencia.lista[]: sin zone ni near*.
    ref_path = CATALOG_DIR / "goals_referencia.json"
    if ref_path.exists():
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
        for goal in ref.get("goals") or []:
            gname = str(goal.get("goal") or "")
            for item in goal.get("lista") or []:
                if not isinstance(item, dict):
                    continue
                key = str(list_item_match_key(item))
                if "zone" in item:
                    violations.append(
                        (
                            f"goals_referencia:{gname}",
                            key,
                            "lista[] sin zone (usar zonas_reino)",
                        )
                    )
                near_hit = sorted(k for k in _NEAR_LOCATION_KEYS if k in item)
                if near_hit:
                    violations.append(
                        (
                            f"goals_referencia:{gname}",
                            key,
                            f"lista[] con near* ({near_hit})",
                        )
                    )

    return violations


def build_referencia_lista_disponibilidad_index() -> dict[tuple, str | list[str]]:
    """Índice (match_key) → disponibilidad desde goals_referencia.lista[]."""
    path = CATALOG_DIR / "goals_referencia.json"
    ref = json.loads(path.read_text(encoding="utf-8"))
    index: dict[tuple, str | list[str]] = {}
    for goal in ref.get("goals") or []:
        src = str(goal.get("lista_source") or "")
        list_name = src if src and "+" not in src else None
        for item in goal.get("lista") or []:
            if "disponibilidad" not in item:
                continue
            key = list_item_match_key(item, list_name=list_name)
            disp = normalize_disponibilidad(item.get("disponibilidad"))
            if key in index and index[key] != disp:
                raise ValueError(
                    f"disponibilidad contradictoria en referencia para {key!r}: "
                    f"{index[key]!r} vs {disp!r}"
                )
            index[key] = disp
    return index


def collect_goal_lists_referencia_mismatches() -> list[tuple[str, str, str]]:
    """[(list_name, item_key, issue), ...] si goal_lists ≠ goals_referencia."""
    data = load_goal_lists()
    sync_lists = frozenset(
        n
        for v in _CURATED_GOAL_LISTAS.values()
        for n in ((v,) if isinstance(v, str) else v)
    ) | {
        "checkpoints",
        "life_up_hearts",
    }
    index = build_referencia_lista_disponibilidad_index()
    mismatches: list[tuple[str, str, str]] = []
    for list_name, items in (data.get("lists") or {}).items():
        if list_name not in sync_lists:
            continue
        for raw in items:
            enriched = enrich_lista_locations([dict(raw)])[0]
            key = list_item_match_key(enriched, list_name=list_name)
            expected = normalize_disponibilidad(enriched.get("disponibilidad"))
            actual = index.get(key)
            if actual is None:
                continue
            if actual != expected:
                mismatches.append(
                    (
                        list_name,
                        str(key),
                        f"disponibilidad {expected!r} ≠ referencia {actual!r}",
                    )
                )
    return mismatches
