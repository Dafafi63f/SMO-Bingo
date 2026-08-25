"""Export Catalog/zonas_reino.json — inventario por kingdom.

Incluye:
  - todos los ítems de goal_lists (source = nombre de lista)
  - lunas in-scope (source = moon; desde lunas-objetivos.json)

Cabecera: n_items = goal_lists; n_moons = lunas-objetivos (434); n_total = n_moons + n_items.

list[] por kingdom (story): primero source=moon (nº luna); luego lists de
goal_lists en alfa (orden del file dentro).

ids en cada fila:
  - id = 1..n_total (posición en list[])
  - id_kingdom = nº luna o 1..n_items del reino

zone: fuente de verdad de ubicación (POIs + lunas). Se preserva al regenerar
(clave kingdom+source+name). No vive en goal_lists / goals_referencia.

También escribe Catalog/zonas_inventario.json — vista de revisión por zone
(alfa global; no editar; curar zone en zonas_reino).

Uso:
  python Files/export_zonas_reino.py
"""
from __future__ import annotations

from collections import Counter, defaultdict

from catalog_lib import (
    CATALOG_DIR,
    STORY_ORDER,
    load_catalog,
    load_sub_area_levels,
    write_catalog_json,
)
from goal_list_lib import load_goal_lists, load_zonas_zone_index, write_goal_lists

ZONAS_REINO_PATH = CATALOG_DIR / "zonas_reino.json"
ZONAS_INVENTARIO_PATH = CATALOG_DIR / "zonas_inventario.json"
LUNAS_PATH = CATALOG_DIR / "lunas-objetivos.json"

MOON_SOURCE = "moon"

_KEY_ORDER = (
    "source",
    "id",
    "id_kingdom",
    "name",
    "disponibilidad",
    "zone",
)


def _row_name(raw: dict) -> str:
    if raw.get("name") is not None:
        return str(raw.get("name") or "")
    if raw.get("capture") is not None:
        return str(raw.get("capture") or "")
    if raw.get("level") is not None:
        return str(raw.get("level") or "")
    return ""


def _zone_key(kingdom: str, source: str, name: str) -> tuple[str, str, str]:
    return (str(kingdom), str(source), str(name))


def _copy_list_item(raw: dict, list_name: str) -> dict:
    """Copia + source; sin kingdom / ids / zone de goal_lists."""
    src = dict(raw)
    src.pop("kingdom", None)
    src.pop("id_list", None)
    src.pop("id", None)
    src.pop("zone", None)
    item: dict = {"source": str(list_name)}
    if "name" in src:
        item["name"] = src.pop("name")
    elif "capture" in src:
        item["name"] = src.pop("capture")
    elif "level" in src:
        item["name"] = src.pop("level")
    if "disponibilidad" in src:
        item["disponibilidad"] = src.pop("disponibilidad")
    for key, value in src.items():
        item[key] = value
    return item


def _moon_item(raw: dict) -> dict:
    """Fila source=moon; id_kingdom = nº luna (id de list[] se asigna al export)."""
    return {
        "source": MOON_SOURCE,
        "id_kingdom": int(raw["moon"]),
        "name": str(raw.get("name") or ""),
        "disponibilidad": raw.get("disponibilidad") or "base",
    }


def _kingdom_from_lunas_row(raw: dict) -> str | None:
    """Reino desde tags[0] (lunas-objetivos sin campo kingdom)."""
    tags = raw.get("tags")
    if isinstance(tags, list) and tags:
        return str(tags[0])
    kingdom = raw.get("kingdom")
    return str(kingdom) if kingdom else None


def _finalize_item(
    item: dict, *, row_id: int, kingdom_id: int | None = None
) -> dict:
    """Fija id de list[] (+ id_kingdom de ítem) y ordena claves."""
    out = dict(item)
    out["id"] = row_id
    if kingdom_id is not None:
        out["id_kingdom"] = kingdom_id
    ordered: dict = {}
    for key in _KEY_ORDER:
        if key in out:
            ordered[key] = out.pop(key)
    for key, value in out.items():
        ordered[key] = value
    return ordered


def _by_zone_counts(items: list[dict]) -> dict[str, int]:
    counts = Counter(
        str(it["zone"]) for it in items if it.get("zone") is not None
    )
    return {zone: counts[zone] for zone in sorted(counts)}


def _resolve_zone(
    *,
    kingdom: str,
    source: str,
    name: str,
    zone_map: dict[tuple[str, str, str], str],
    seed: str | None = None,
) -> str | None:
    """Prioridad: mapa zonas_reino → seed legado (p. ej. goal_lists)."""
    key = _zone_key(kingdom, source, name)
    if key in zone_map:
        return zone_map[key]
    if seed:
        return str(seed)
    return None


# Tag de luna que coincide con un slug de zone (o alias → slug).
_TAG_ZONE_ALIAS: dict[str, str] = {
    "pyramid": "inverted_pyramid",
    "ruins": "ruins",
    "tostarena": "tostarena",
    "oasis": "oasis",
    "sphynx": "sphynx",
    "deep_woods": "deep_woods",
    "shiveria": "shiveria",
    "overworld": "overworld",
    "jaxi_ruins": "jaxi_ruins",
    "moe_eye": "moe_eye",
}

_TOAD_ZONE: dict[str, str] = {
    "cap": "top_hat_tower",
    "cascade": "heights",
    "sand": "oasis",
    "lake": "lake",
    "wooded": "observation_deck",
    "lost": "swamp",
    "metro": "outdoor_cafe",
    "snow": "snowy_mountain",
    "seaside": "rolling_canyon",
    "luncheon": "meat_plateau",
    "bowser": "keep",
    "moon": "moon_cave",
}

# Fallback (kingdom, nº luna) cuando listas/tags no bastan.
_MOON_ZONE_FALLBACK: dict[tuple[str, int], str] = {
    ("cap", 1): "fog",
    ("cap", 2): "odyssey",
    ("cap", 3): "fog",
    ("cap", 4): "top_hat_tower",
    ("cascade", 1): "odyssey",
    ("cascade", 2): "heights",
    ("cascade", 3): "basin",
    ("cascade", 4): "basin",
    ("cascade", 5): "odyssey",
    ("cascade", 6): "basin",
    ("cascade", 7): "heights",
    ("cascade", 8): "floating_isles",
    ("cascade", 9): "basin",
    ("cascade", 10): "heights",
    ("cascade", 11): "heights",
    ("cascade", 19): "odyssey",
    ("cascade", 20): "basin",
    ("sand", 2): "ruins",
    ("sand", 4): "underground_temple",
    ("sand", 10): "inverted_pyramid",
    ("sand", 13): "southwest",
    ("sand", 14): "inverted_pyramid",
    ("sand", 17): "southwest",
    ("sand", 18): "oasis",
    ("sand", 22): "southwest",
    ("sand", 23): "inverted_pyramid",
    ("sand", 28): "ruins",
    ("sand", 29): "ruins",
    ("sand", 30): "inverted_pyramid",
    ("sand", 33): "southwest",
    ("sand", 36): "southwest",
    ("sand", 39): "inverted_pyramid",
    ("sand", 44): "tostarena",
    ("sand", 45): "northwest",
    ("sand", 47): "underground_temple",
    ("sand", 48): "underground_temple",
    ("sand", 49): "underground_temple",
    ("sand", 52): "northwest",
    ("sand", 53): "jaxi_ruins",
    ("lake", 1): "water_plaza",
    ("lake", 2): "lake",
    ("lake", 3): "lake",
    ("lake", 4): "courtyard",
    ("lake", 5): "courtyard",
    ("lake", 6): "odyssey",
    ("lake", 7): "start",
    ("lake", 8): "spiky_tunnel",
    ("lake", 9): "spiky_tunnel",
    ("lake", 10): "water_plaza",
    ("lake", 11): "terrace",
    ("lake", 12): "lake",
    ("lake", 13): "lake",
    ("lake", 14): "water_plaza",
    ("lake", 15): "lake",
    ("lake", 16): "lake",
    ("lake", 17): "courtyard",
    ("lake", 18): "lake",
    ("lake", 20): "courtyard",
    ("lake", 21): "water_plaza",
    ("wooded", 1): "summit_path",
    ("wooded", 2): "sky_garden",
    ("wooded", 3): "summit_path",
    ("wooded", 4): "flower_field",
    ("wooded", 5): "iron_road",
    ("wooded", 6): "summit_path",
    ("wooded", 7): "iron_road",
    ("wooded", 8): "iron_road",
    ("wooded", 9): "iron_road",
    ("wooded", 10): "observation_deck",
    ("wooded", 11): "iron_road",
    ("wooded", 12): "iron_road",
    ("wooded", 13): "iron_road",
    ("wooded", 14): "summit_path",
    ("wooded", 15): "sky_garden",
    ("wooded", 16): "sky_garden",
    ("wooded", 17): "sky_garden",
    ("wooded", 18): "sky_garden",
    ("wooded", 19): "iron_road",
    ("wooded", 20): "observation_deck",
    ("wooded", 21): "iron_road",
    ("wooded", 22): "iron_road",
    ("wooded", 24): "sky_garden",
    ("wooded", 25): "odyssey_start",
    ("wooded", 26): "summit_path",
    ("wooded", 27): "flower_field",
    ("wooded", 37): "flower_field",
    ("wooded", 38): "sky_garden",
    ("lost", 1): "propeller",
    ("lost", 2): "start",
    ("lost", 3): "start",
    ("lost", 5): "swamp",
    ("lost", 6): "swamp",
    ("lost", 7): "propeller",
    ("lost", 8): "summit",
    ("lost", 9): "path",
    ("lost", 10): "propeller",
    ("lost", 11): "mountainside",
    ("lost", 12): "mountainside",
    ("lost", 13): "swamp",
    ("lost", 14): "cave",
    ("lost", 15): "swamp",
    ("lost", 16): "path",
    ("lost", 17): "swamp",
    ("lost", 18): "summit",
    ("lost", 19): "swamp",
    ("lost", 20): "swamp",
    ("metro", 1): "city_hall",
    ("metro", 2): "musicians",
    ("metro", 3): "musicians",
    ("metro", 4): "musicians",
    ("metro", 5): "musicians",
    ("metro", 6): "main_street",
    ("metro", 7): "city_hall",
    ("metro", 8): "girders",
    ("metro", 9): "girders",
    ("metro", 10): "girders",
    ("metro", 11): "park",
    ("metro", 12): "rooftops",
    ("metro", 13): "girders",
    ("metro", 14): "garbage",
    ("metro", 15): "garbage",
    ("metro", 16): "outdoor_cafe",
    ("metro", 17): "rooftops",
    ("metro", 18): "garbage",
    ("metro", 19): "rooftops",
    ("metro", 20): "heliport",
    ("metro", 21): "rooftops",
    ("metro", 22): "park",
    ("metro", 23): "rooftop_garden",
    ("metro", 24): "outdoor_cafe",
    ("metro", 25): "rooftops",
    ("metro", 26): "park",
    ("metro", 28): "slots",
    ("metro", 29): "main_street",
    ("metro", 30): "main_street",
    ("metro", 31): "park",
    ("metro", 32): "park",
    ("metro", 33): "city_hall_interior",
    ("metro", 34): "city_hall_interior",
    ("metro", 35): "sewers",
    ("metro", 36): "main_street",
    ("metro", 52): "odyssey",
    ("snow", 1): "icicle_cavern",
    ("snow", 2): "hollow_crevasse",
    ("snow", 3): "wind_chill",
    ("snow", 4): "snowy_mountain",
    ("snow", 5): "shiveria",
    ("snow", 6): "shiveria",
    ("snow", 7): "snowy_mountain",
    ("snow", 8): "shiveria",
    ("snow", 9): "wind_chill",
    ("snow", 10): "overworld",
    ("snow", 11): "shiveria",
    ("snow", 12): "hollow_crevasse",
    ("snow", 13): "overworld",
    ("snow", 14): "snowy_mountain",
    ("snow", 15): "overworld",
    ("snow", 16): "overworld",
    ("snow", 17): "freezing_sea",
    ("snow", 18): "overworld",
    ("snow", 19): "snowy_mountain",
    ("snow", 20): "shiveria",
    ("snow", 22): "shiveria",
    ("snow", 23): "shiveria",
    ("snow", 28): "wind_chill",
    ("seaside", 1): "beach_house",
    ("seaside", 2): "lighthouse",
    ("seaside", 3): "hot_spring",
    ("seaside", 4): "rolling_canyon",
    ("seaside", 5): "glass_palace",
    ("seaside", 6): "beach_house",
    ("seaside", 7): "lighthouse",
    ("seaside", 8): "ocean_maze",
    ("seaside", 9): "ocean_maze",
    ("seaside", 10): "ocean_trench",
    ("seaside", 11): "lighthouse_tunnel",
    ("seaside", 12): "ocean_trench",
    ("seaside", 13): "ocean_trench",
    ("seaside", 14): "ocean_trench",
    ("seaside", 15): "ocean_trench",
    ("seaside", 16): "southwest",
    ("seaside", 17): "waves",
    ("seaside", 18): "rolling_canyon",
    ("seaside", 19): "north_island",
    ("seaside", 20): "southeast",
    ("seaside", 22): "southwest",
    ("seaside", 23): "southwest",
    ("seaside", 24): "rolling_canyon",
    ("seaside", 25): "hot_spring",
    ("seaside", 27): "ocean_maze",
    ("seaside", 28): "glass_palace",
    ("seaside", 29): "beach_house",
    ("seaside", 30): "ocean_trench",
    ("seaside", 31): "waves",
    ("seaside", 32): "beach_house",
    ("seaside", 33): "lighthouse",
    ("seaside", 34): "rolling_canyon",
    ("seaside", 35): "glass_palace",
    ("seaside", 37): "beach_house",
    ("seaside", 38): "beach_house",
    ("seaside", 39): "lighthouse_tunnel",
    ("seaside", 40): "glass_palace",
    ("seaside", 41): "southeast",
    ("seaside", 42): "hot_spring",
    ("luncheon", 1): "plaza",
    ("luncheon", 2): "volcano_cave",
    ("luncheon", 3): "peak",
    ("luncheon", 4): "peak",
    ("luncheon", 5): "peak",
    ("luncheon", 6): "salt_pile",
    ("luncheon", 7): "plaza",
    ("luncheon", 8): "plaza",
    ("luncheon", 9): "plaza",
    ("luncheon", 10): "plaza",
    ("luncheon", 11): "meat_plateau",
    ("luncheon", 12): "salt_pile",
    ("luncheon", 13): "veggies",
    ("luncheon", 14): "remote_island",
    ("luncheon", 15): "veggies",
    ("luncheon", 16): "veggies",
    ("luncheon", 17): "veggies",
    ("luncheon", 18): "plaza",
    ("luncheon", 19): "meat_plateau",
    ("luncheon", 20): "peak",
    ("luncheon", 21): "veggies",
    ("luncheon", 22): "plaza",
    ("luncheon", 23): "lava",
    ("luncheon", 24): "lava",
    ("luncheon", 26): "plaza",
    ("luncheon", 29): "peak",
    ("luncheon", 30): "volcano_cave",
    ("luncheon", 31): "meat_plateau",
    ("luncheon", 32): "peak",
    ("luncheon", 33): "meat_plateau",
    ("luncheon", 34): "veggies",
    ("luncheon", 35): "peak",
    ("luncheon", 36): "peak",
    ("luncheon", 48): "odyssey",
    ("luncheon", 50): "peak",  # mushroom#39 sintético (pintura → Yoshi's House)
    ("ruined", 1): "odyssey",
    ("ruined", 2): "odyssey",
    ("bowser", 1): "entrance",
    ("bowser", 2): "third_courtyard",
    ("bowser", 3): "second_courtyard",
    ("bowser", 4): "showdown",
    ("bowser", 5): "outer_wall",
    ("bowser", 6): "third_courtyard",
    ("bowser", 7): "main_courtyard",
    ("bowser", 8): "main_courtyard",
    ("bowser", 9): "inner_wall",
    ("bowser", 10): "inner_wall",
    ("bowser", 11): "second_courtyard",
    ("bowser", 12): "third_courtyard",
    ("bowser", 13): "keep",
    ("bowser", 14): "keep",
    ("bowser", 15): "showdown",
    ("bowser", 16): "second_courtyard",
    ("bowser", 17): "second_courtyard",
    ("bowser", 18): "second_courtyard",
    ("bowser", 19): "outer_wall",
    ("bowser", 20): "keep",
    ("bowser", 21): "second_courtyard",
    ("bowser", 22): "third_courtyard",
    ("bowser", 23): "main_courtyard",
    ("bowser", 24): "main_courtyard",
    ("bowser", 25): "main_courtyard",
    ("bowser", 26): "keep",
    ("bowser", 27): "keep",
    ("bowser", 28): "keep",
    ("bowser", 30): "treasure_vault",
    ("moon", 1): "surface",
    ("moon", 2): "surface",
    ("moon", 3): "ringing_bells",
    ("moon", 4): "surface",
    ("moon", 5): "surface",
    ("moon", 6): "quiet_wall",
    ("moon", 7): "surface",
    ("moon", 8): "surface",
    ("moon", 9): "moon_cave",
    ("moon", 10): "moon_cave",
    ("moon", 11): "surface",
    ("moon", 12): "surface",
    ("moon", 13): "surface",
    ("moon", 14): "wedding_hall",
    ("moon", 25): "odyssey",
}


def _item_display_name(raw: dict) -> str:
    return str(raw.get("name") or raw.get("level") or raw.get("capture") or "")


def _list_item_zone(
    kingdom: str, source: str, name: str, zone_map: dict[tuple[str, str, str], str]
) -> str | None:
    return zone_map.get(_zone_key(kingdom, source, name))


def _kingdom_zones_from_map(
    zone_map: dict[tuple[str, str, str], str],
) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for kingdom, _source, _name in zone_map:
        z = zone_map[(kingdom, _source, _name)]
        if z:
            out[kingdom].add(z)
    return out


def _build_moon_ref_zones(
    lists: dict, zone_map: dict[tuple[str, str, str], str]
) -> dict[tuple[str, int], list[tuple[str, str]]]:
    """(kingdom, moon) → [(source, zone), ...] desde moons/moon/moon_link."""
    out: dict[tuple[str, int], list[tuple[str, str]]] = defaultdict(list)
    for source, rows in (lists or {}).items():
        src = str(source)
        for raw in rows or []:
            if not isinstance(raw, dict):
                continue
            kingdom = str(raw.get("kingdom") or "")
            name = _item_display_name(raw)
            zone = _list_item_zone(kingdom, src, name, zone_map)
            if not zone:
                continue
            nums: list[int] = []
            for m in raw.get("moons") or []:
                try:
                    nums.append(int(m))
                except (TypeError, ValueError):
                    pass
            if raw.get("moon") is not None:
                try:
                    nums.append(int(raw["moon"]))
                except (TypeError, ValueError):
                    pass
            link = raw.get("moon_link")
            if isinstance(link, dict) and link.get("moon") is not None:
                try:
                    mk = str(link.get("kingdom") or kingdom)
                    out[(mk, int(link["moon"]))].append((src, zone))
                except (TypeError, ValueError):
                    pass
            for n in nums:
                out[(kingdom, n)].append((src, zone))
    return out


def infer_moon_zone(
    *,
    kingdom: str,
    moon: int,
    name: str,
    tags: list[str],
    lists: dict,
    zone_map: dict[tuple[str, str, str], str],
    moon_refs: dict[tuple[str, int], list[tuple[str, str]]] | None = None,
    kingdom_zones: dict[str, set[str]] | None = None,
) -> str | None:
    """Zone de una luna: listas cercanas, tags, fallback curado."""
    k_zones = (kingdom_zones or _kingdom_zones_from_map(zone_map)).get(kingdom) or set()
    refs = (moon_refs or {}).get((kingdom, moon)) or []
    if refs:
        sub = [z for src, z in refs if src == "sub_area_levels"]
        if len(set(sub)) == 1:
            return sub[0]
        uniq = list(dict.fromkeys(z for _s, z in refs))
        if len(uniq) == 1:
            return uniq[0]
        if sub:
            return sub[0]

    tag_set = {str(t) for t in tags[1:]} if tags else set()
    tag_hits: list[str] = []
    for tag in tag_set:
        slug = _TAG_ZONE_ALIAS.get(tag, tag)
        if slug in k_zones:
            tag_hits.append(slug)
    uniq_tags = list(dict.fromkeys(tag_hits))
    if len(uniq_tags) == 1:
        return uniq_tags[0]

    if "shop" in tag_set:
        z = _list_item_zone(kingdom, "shops", "Crazy Cap", zone_map)
        if z:
            return z
    if "captain_toad" in tag_set and kingdom in _TOAD_ZONE:
        return _TOAD_ZONE[kingdom]
    nl = name.lower()
    if "talkatoo" in nl or name.startswith("A Relaxing Dance"):
        z = _list_item_zone(kingdom, "talkatoos", "Talkatoo", zone_map)
        if z:
            return z
    if "found with" in nl and "art" in nl:
        for src in ("pixel_luigis", "pixel_cat_marios"):
            for (kk, source, nm), z in zone_map.items():
                if kk == kingdom and source == src:
                    return z
    if "moon rock" in nl:
        z = _list_item_zone(kingdom, "moon_rocks", "Moon Rock", zone_map)
        if z:
            return z

    for (kk, source, nm), z in zone_map.items():
        if kk != kingdom or source == MOON_SOURCE or not z:
            continue
        if source in {
            "costume_sets",
            "hats",
            "souvenirs",
            "stickers",
            "boxer_shorts",
        }:
            continue
        nml = nm.lower()
        if len(nml) >= 6 and nml in nl:
            return z
        slug = z.replace("_", " ")
        if len(slug) >= 5 and slug in nl:
            return z

    fb = _MOON_ZONE_FALLBACK.get((kingdom, moon))
    if fb:
        return fb
    if kingdom == "ruined" and "odyssey" in k_zones:
        return "odyssey"
    return None


def build_zonas_reino(
    *, zone_map: dict[tuple[str, str, str], str] | None = None
) -> dict:
    """kingdoms[]: kingdom, by_zone, n_moons, n_items, n_total, list."""
    data = load_goal_lists()
    zones = zone_map if zone_map is not None else load_zonas_zone_index()

    # kingdom → [(item_dict, source, sort_key)]
    buckets: dict[str, list[tuple[dict, str, tuple]]] = defaultdict(list)
    lists = data.get("lists") or {}
    # Pares Level viven fuera de goal_lists; solo para inferir zone de lunas.
    lists_for_moon_refs = {
        **lists,
        "sub_area_levels": load_sub_area_levels(),
    }
    moon_refs = _build_moon_ref_zones(lists_for_moon_refs, zones)
    k_zones = _kingdom_zones_from_map(zones)
    for list_name in sorted(lists):
        source = str(list_name)
        for idx, raw in enumerate(lists.get(list_name) or []):
            if not isinstance(raw, dict) or not raw.get("kingdom"):
                continue
            kingdom = str(raw["kingdom"])
            item = _copy_list_item(raw, source)
            name = str(item.get("name") or "")
            zone = _resolve_zone(
                kingdom=kingdom,
                source=source,
                name=name,
                zone_map=zones,
                seed=str(raw["zone"]) if raw.get("zone") else None,
            )
            if zone:
                item["zone"] = zone
            buckets[kingdom].append((item, source, (1, source, idx)))

    lunas = load_catalog(LUNAS_PATH) if LUNAS_PATH.is_file() else {}
    for raw in lunas.get("moons") or []:
        if not isinstance(raw, dict):
            continue
        kingdom = _kingdom_from_lunas_row(raw)
        if not kingdom or raw.get("moon") is None:
            continue
        moon_num = int(raw["moon"])
        item = _moon_item(raw)
        tags = list(raw.get("tags") or [])
        zone = _resolve_zone(
            kingdom=kingdom,
            source=MOON_SOURCE,
            name=str(item.get("name") or ""),
            zone_map=zones,
        )
        if not zone:
            zone = infer_moon_zone(
                kingdom=kingdom,
                moon=moon_num,
                name=str(item.get("name") or ""),
                tags=tags,
                lists=lists_for_moon_refs,
                zone_map=zones,
                moon_refs=moon_refs,
                kingdom_zones=k_zones,
            )
        if zone:
            item["zone"] = zone
        buckets[kingdom].append((item, MOON_SOURCE, (0, moon_num)))

    ordered = [k for k in STORY_ORDER if k in buckets] + sorted(
        k for k in buckets if k not in STORY_ORDER
    )
    kingdoms: list[dict] = []
    for kingdom in ordered:
        rows = sorted(buckets[kingdom], key=lambda t: t[2])
        items: list[dict] = []
        item_id = 0
        for row_id, (item, source, _key) in enumerate(rows, start=1):
            if source == MOON_SOURCE:
                items.append(_finalize_item(item, row_id=row_id))
            else:
                item_id += 1
                items.append(
                    _finalize_item(item, row_id=row_id, kingdom_id=item_id)
                )
        n_moons_k = sum(1 for it in items if it.get("source") == MOON_SOURCE)
        n_items_k = len(items) - n_moons_k
        kingdoms.append(
            {
                "kingdom": kingdom,
                "by_zone": _by_zone_counts(items),
                "n_moons": n_moons_k,
                "n_items": n_items_k,
                "n_total": n_moons_k + n_items_k,
                "list": items,
            }
        )

    n_moons = sum(k["n_moons"] for k in kingdoms)
    n_items = sum(k["n_items"] for k in kingdoms)
    return {
        "_note": (
            "Inventario por kingdom (story order). "
            "Fuente de ubicación (zone) del proyecto: editar zone aquí; "
            "goal_lists / goals_referencia / bingo_groups no llevan zone. "
            "n_items = Catalog/goal_lists.json; "
            "n_moons = lunas-objetivos (434; mushroom#39 como luncheon#50); "
            "n_total = n_moons + n_items (cabecera y por kingdom). "
            "list[]: primero moon (nº luna), luego sources goal_lists en alfa "
            "(orden del file dentro). "
            "id = 1..n_total (posición en list[]); "
            "id_kingdom = nº luna o 1..n_items del reino. "
            "Al regenerar, zone se preserva por (kingdom, source, name). "
            "Lunas: zone inferida de lists (sub_area/moon_link/tags/POI) "
            "o fallback curado; sin tags. "
            "Regenerar: python Files/export_zonas_reino.py"
        ),
        "n_kingdoms": len(kingdoms),
        "n_moons": n_moons,
        "n_items": n_items,
        "n_total": n_moons + n_items,
        "kingdoms": kingdoms,
    }


def _detalle_item(kingdom: str, raw: dict) -> dict:
    """Fila compacta de revisión (ids de zonas_reino para cruzar)."""
    out: dict = {
        "kingdom": kingdom,
        "source": str(raw.get("source") or ""),
    }
    if raw.get("id") is not None:
        out["id"] = raw["id"]
    if raw.get("id_kingdom") is not None:
        out["id_kingdom"] = raw["id_kingdom"]
    out["name"] = str(raw.get("name") or "")
    if raw.get("disponibilidad") is not None:
        out["disponibilidad"] = raw["disponibilidad"]
    if raw.get("total") is not None:
        out["total"] = raw["total"]
    if raw.get("sub_area") is True:
        out["sub_area"] = True
    if raw.get("eight_bit") is True:
        out["eight_bit"] = True
    return out


def build_zonas_inventario(payload: dict | None = None) -> dict:
    """Vista de revisión: una entrada por (zone, kingdom), zone en alfa global."""
    if payload is None:
        if not ZONAS_REINO_PATH.exists():
            payload = build_zonas_reino()
        else:
            payload = load_catalog(ZONAS_REINO_PATH)

    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for kblock in payload.get("kingdoms") or []:
        kingdom = str(kblock.get("kingdom") or "")
        if not kingdom:
            continue
        for raw in kblock.get("list") or []:
            if not isinstance(raw, dict):
                continue
            zone = raw.get("zone")
            if zone is None or zone == "":
                continue
            buckets[(str(zone), kingdom)].append(_detalle_item(kingdom, raw))

    zones_out: list[dict] = []
    for orden, (zone, kingdom) in enumerate(
        sorted(buckets.keys(), key=lambda zk: (zk[0].lower(), zk[1])),
        start=1,
    ):
        items = buckets[(zone, kingdom)]
        by_source = {
            src: n
            for src, n in sorted(
                Counter(str(it["source"]) for it in items).items(),
                key=lambda p: p[0],
            )
        }
        zones_out.append(
            {
                "zone": zone,
                "kingdom": kingdom,
                "orden": orden,
                "n_total": len(items),
                "by_source": by_source,
                "list": items,
            }
        )

    n_total = sum(z["n_total"] for z in zones_out)
    return {
        "_definition": (
            "Vista de revisión: contenido por zone (alfa global, sin "
            "orden de historia). No editar a mano: curar zone en "
            "zonas_reino.json y regenerar. Una entrada = (zone, kingdom); "
            "el mismo slug en reinos distintos son filas distintas. "
            "Campos: zone, kingdom, orden, n_total, by_source, list[] "
            "(list: kingdom, source, id, id_kingdom, name, …; ids = zonas_reino)."
        ),
        "_note": (
            "Regenerar: python Files/export_zonas_reino.py "
            "(escribe también este file)."
        ),
        "n_zones": len(zones_out),
        "n_total": n_total,
        "zones": zones_out,
    }


def main() -> int:
    # 1) Escribir zonas (preserva zone; seed desde goal_lists si aún hay zone).
    payload = build_zonas_reino()
    write_catalog_json(ZONAS_REINO_PATH, payload)
    # 2) Limpiar zone de goal_lists (ya migrada / cubierta por zonas_reino).
    write_goal_lists(load_goal_lists())
    # 3) Vista de revisión por zone (alfa).
    detalle = build_zonas_inventario(payload)
    write_catalog_json(ZONAS_INVENTARIO_PATH, detalle)
    print(
        f"kingdoms={payload['n_kingdoms']} moons={payload['n_moons']} "
        f"items={payload['n_items']} "
        f"total={payload['n_total']} -> {ZONAS_REINO_PATH.name}"
    )
    print(
        f"zonas_inventario: n_zones={detalle['n_zones']} "
        f"n_total={detalle['n_total']} -> {ZONAS_INVENTARIO_PATH.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
