"""Export Catalog/items_goals.json — cada ítem del juego → goals Combined.

Universo e orden = build_zonas_inventario() (story kingdoms; moons → lists alfa +
binoculars), plano sin agrupar. goals[] = nombres de templates (compacto,
como goal_icons). Lookup estricto vía moons[] / lista[] de goals_referencia
(moons con remap mushroom#39→luncheon#50). Sin expandir lista_source a toda
la lista ni respaldo bingo_groups (evita inflación cruzada entre reinos).

Uso:
  python Files/export_items_goals.py
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from catalog_lib import (
    CATALOG_DIR,
    load_bingo_groups,
    load_catalog,
    lunas_catalog_ref,
    write_catalog_json,
)
from export_zonas_inventario import BINOCULARS_SOURCE, MOON_SOURCE, build_zonas_inventario
from goal_list_lib import (
    SHOP_ITEM_LISTS,
    list_item_match_key,
    load_zonas_zone_index,
    regional_lista_for_goal,
    resolve_lista_item_source,
)

OUT_PATH = CATALOG_DIR / "items_goals.json"
REF_PATH = CATALOG_DIR / "goals_referencia.json"
GOAL_TOTAL_STORY_MOONS = "{{X}} Total Story Moons"
GOAL_SHOP_MOONS_AGG = "{{X}} Shop Moons"
GOAL_SNOW_BOXER_SHORTS = "Snow Boxer Shorts Moon"

# En Crazy Cap: no heredar agregados genéricos / exclusivos de un ítem suelto.
_SHOP_INHERIT_SKIP_GOALS = frozenset(
    {
        GOAL_SHOP_MOONS_AGG,
        GOAL_SNOW_BOXER_SHORTS,
    }
)

# Agregados multi-reino / capturas sueltas: no van en items_goals (evitan inflación).
SKIP_GOALS = frozenset(
    {
        # Totales / All que cruzan varios reinos
        "{{X}} Sub-Area Moons",
        "{{X}} Total Moons",
        "{{X}} Total Multi-Moons",
        GOAL_TOTAL_STORY_MOONS,
        "{{X}} Total Checkpoints",
        "{{X}} Total Regional Coins",
        "All Multi-Moons in {{X}} Kingdoms",
        "All Checkpoints in {{X}} Kingdoms",
        "All Regional Coins in {{X}} Large Kingdom",
        "All Regional Coins in {{X}} Small Kingdom[[s]]",
        # Capturas sin POI en el universo zonas
        "{{X}} Unique Captures",
        "Capture Big Chain Chomp",
        "Capture Boulder",
        "Capture Chargin' Chuck",
        "Capture Poison Piranha Plant",
        "Capture Snow Cheep Cheep",
    }
)

_KINGDOM_LABELS = {
    "cap": "Cap",
    "cascade": "Cascade",
    "sand": "Sand",
    "lake": "Lake",
    "wooded": "Wooded",
    "lost": "Lost",
    "metro": "Metro",
    "snow": "Snow",
    "seaside": "Seaside",
    "luncheon": "Luncheon",
    "ruined": "Ruined",
    "bowser": "Bowser",
    "moon": "Moon",
}

# Zonas geográficas: si hay goal de zona, se quita el paraguas del reino.
_KINGDOM_ZONE_FRAGMENTS = (
    "Deep Woods",
    "Flower Road",
    "Tostarena",
    "Overworld",
    "Shiveria",
    "Pyramid",
    "Oasis",
    "Ruins",
    "Jaxi",
    "Ice",
)

# Goals de zona sin prefijo de reino en el nombre → paraguas del reino.
_ZONE_GOAL_UMBRELLAS: dict[str, tuple[str, ...]] = {
    "{{X}} Deep Woods Moons": ("{{X}} Wooded Moons",),
    "{{X}} Deep Woods Regional Coins": ("{{X}} Wooded Regional Coins",),
}

_UMBRELLA_CHILDREN: dict[str, frozenset[str]] | None = None


def _norm_goal_key(goal: str) -> str:
    """Normaliza Moon[[s]] → Moons para cruzar umbrellas."""
    g = str(goal or "")
    g = g.replace("Moon[[s]]", "Moons").replace("Moon[[S]]", "Moons")
    return g.replace("[[s]]", "").replace("[[S]]", "")


def _group_goal_names(group: dict) -> set[str]:
    return {
        str(o.get("goal") or "")
        for o in group.get("objectives") or []
        if isinstance(o, dict) and o.get("goal")
    }


def _add_fauna_flora_nature_drops(
    groups: list[dict], drop: dict[str, set[str]]
) -> None:
    fauna_u = "{{X}} Fauna Moons"
    flora_u = "{{X}} Flora Moons"
    nature_u = "{{X}} Nature Moons"
    for g in groups:
        tag = str(g.get("moon_tag") or "")
        goals = _group_goal_names(g)
        if tag == "fauna" or g.get("id") == "fauna":
            drop[fauna_u] |= {x for x in goals if x != fauna_u}
        if tag == "flora" or g.get("id") == "flora":
            drop[flora_u] |= {x for x in goals if x != flora_u}
    drop[nature_u] |= drop[fauna_u] | drop[flora_u] | {fauna_u, flora_u}


def _add_group_id_umbrella_drops(
    by_id: dict[str, dict], drop: dict[str, set[str]]
) -> None:
    for gid, umbrella in (
        ("ground_pound", "{{X}} Ground Pound Moons"),
        ("outfit_door", "{{X}} Outfit Door Moons"),
    ):
        g = by_id.get(gid) or {}
        drop[umbrella] |= {x for x in _group_goal_names(g) if x != umbrella}


def _collect_all_group_goals(groups: list[dict]) -> set[str]:
    all_goals: set[str] = set()
    for g in groups:
        all_goals |= _group_goal_names(g)
    return all_goals


def _add_zone_fragment_umbrella_drops(
    *,
    labels: list[str],
    by_norm: dict[str, str],
    drop: dict[str, set[str]],
) -> None:
    for frag in _KINGDOM_ZONE_FRAGMENTS:
        for label in labels:
            for suffix, umbrella_suffix in (
                (" Moons", " Moons"),
                (" Regional Coins", " Regional Coins"),
            ):
                child_norm = f"{{{{X}}}} {label} {frag}{suffix}"
                child = by_norm.get(child_norm)
                if child:
                    drop[f"{{{{X}}}} {label}{umbrella_suffix}"].add(child)


def _add_zone_goal_umbrella_drops(
    *,
    all_goals: set[str],
    by_norm: dict[str, str],
    drop: dict[str, set[str]],
) -> None:
    for child, umbrellas in _ZONE_GOAL_UMBRELLAS.items():
        if child in all_goals or _norm_goal_key(child) in by_norm:
            real = by_norm.get(_norm_goal_key(child), child)
            for umbrella in umbrellas:
                drop[umbrella].add(real)


def _build_umbrella_children() -> dict[str, frozenset[str]]:
    """umbrella → hijos que la hacen redundante en el mismo ítem."""
    groups = [g for g in load_bingo_groups() if isinstance(g, dict)]
    by_id = {str(g.get("id") or ""): g for g in groups}
    drop: dict[str, set[str]] = defaultdict(set)

    _add_fauna_flora_nature_drops(groups, drop)
    _add_group_id_umbrella_drops(by_id, drop)

    labels = list(_KINGDOM_LABELS.values()) + ["Bowser's"]
    all_goals = _collect_all_group_goals(groups)
    by_norm = {_norm_goal_key(g): g for g in all_goals}

    _add_zone_fragment_umbrella_drops(labels=labels, by_norm=by_norm, drop=drop)
    _add_zone_goal_umbrella_drops(all_goals=all_goals, by_norm=by_norm, drop=drop)

    return {k: frozenset(v) for k, v in drop.items() if v}


def umbrella_children() -> dict[str, frozenset[str]]:
    global _UMBRELLA_CHILDREN
    if _UMBRELLA_CHILDREN is None:
        _UMBRELLA_CHILDREN = _build_umbrella_children()
    return _UMBRELLA_CHILDREN


def prune_umbrella_goals(goals: list[str]) -> list[str]:
    """Quita paraguas si el ítem ya tiene una goal más concreta."""
    if len(goals) < 2:
        return goals
    present = set(goals)
    drop_map = umbrella_children()
    remove = {
        umbrella
        for umbrella, children in drop_map.items()
        if umbrella in present and present & children
    }
    if not remove:
        return goals
    return [g for g in goals if g not in remove]


def _is_kingdom_story_goal(goal: str) -> bool:
    """{{X}} Sand Story Moons / Bowser's Story Moons (no Total Story)."""
    g = _norm_goal_key(goal)
    return g.startswith("{{X}} ") and g.endswith(" Story Moons")


def _story_moon_keys() -> frozenset[tuple[str, int]]:
    """Lunas reales de historia = grupo bingo story_moon."""
    return _bingo_group_moon_keys("story_moon")


def _outfit_door_moon_keys() -> frozenset[tuple[str, int]]:
    """Lunas de puerta con outfit = grupo bingo outfit_door."""
    return _bingo_group_moon_keys("outfit_door")


def _bingo_group_moon_keys(group_id: str) -> frozenset[tuple[str, int]]:
    for group in load_bingo_groups():
        if not isinstance(group, dict) or group.get("id") != group_id:
            continue
        out: set[tuple[str, int]] = set()
        for row in group.get("moons") or []:
            if not isinstance(row, dict) or row.get("moon") is None:
                continue
            out.add((str(row.get("kingdom") or ""), int(row["moon"])))
        return frozenset(out)
    return frozenset()


def _is_sub_area_related_goal(goal: str) -> bool:
    """Kingdom Sub-Area (no Outfit Door)."""
    return "Sub-Area" in _norm_goal_key(goal)


def prune_outfit_door_sub_area_goals(
    goals: list[str], *, is_outfit_door: bool
) -> list[str]:
    """Outfit door: solo outfits (+ resto); sin goals de sub-area."""
    if not is_outfit_door:
        return goals
    return [g for g in goals if not _is_sub_area_related_goal(g)]


def _moon_key(kingdom: str, moon: int) -> tuple:
    return ("moon", str(kingdom), int(moon))


def _lista_keys(
    *,
    kingdom: str,
    source: str,
    name: str,
    item: dict,
) -> list[tuple]:
    """Claves de lookup para emparejar filas de goals_referencia.lista[]."""
    keys: list[tuple] = [("ksn", kingdom, source, name)]
    num = item.get("id_list")
    if num is None:
        num = item.get("id")
    if num is not None:
        keys.append(("ksi", kingdom, source, int(num)))
    keys.append(("mk", source, list_item_match_key(item, source)))
    return keys


def _item_id(kingdom: str, source: str, id_kingdom: object) -> str:
    """Id reino/source/nº (mismo esquema que la cola local zonas_revision)."""
    return f"{kingdom}/{source}/{id_kingdom}"


def _split_lista_sources(src: object) -> list[str]:
    if not src:
        return []
    return [p for p in str(src).split("+") if p]


def _resolve_lista_source(goal_row: dict, raw: dict) -> str | None:
    src = raw.get("source")
    if src:
        return str(src)
    hint = goal_row.get("lista_source")
    resolved = resolve_lista_item_source(raw, str(hint) if hint else None)
    if resolved:
        return resolved
    name = str(raw.get("name") or "").casefold()
    if "binocular" in name:
        return BINOCULARS_SOURCE
    parts = _split_lista_sources(hint)
    if len(parts) == 1:
        return parts[0]
    return None


def _goal_stem(text: str) -> str:
    """Quita {{X}} / [[s]] para detectar reino en el nombre."""
    stem = str(text or "").replace("[[s]]", "").replace("[[S]]", "")
    stem = stem.replace("{{X}}", " ").replace("  ", " ").strip()
    return stem


def _strip_goal_stem_suffix(stem: str) -> str:
    for suffix in (" Moon Rock", " Talkatoo", " Sphynx Question"):
        if not stem.endswith(suffix):
            continue
        stem = stem[: -len(suffix)]
        if stem.startswith("Correct "):
            stem = stem[len("Correct ") :]
        return stem.strip()
    return stem


def _is_moon_rocks_stem(stem: str) -> bool:
    return (
        stem == "Moon Rocks"
        or stem.startswith("Moon Rock")
        or stem.startswith("Moon Rocks ")
    )


def _kingdom_from_stem(stem: str) -> str | None:
    named: list[str] = []
    for k, label in _KINGDOM_LABELS.items():
        if k == "moon" and _is_moon_rocks_stem(stem):
            continue
        if (
            stem == label
            or stem == f"{label}'s"
            or stem.startswith(f"{label} ")
            or stem.startswith(f"{label}'s ")
        ):
            named.append(k)
    return named[0] if len(named) == 1 else None


def _kingdom_from_individuales(goal_row: dict) -> str | None:
    kingdoms: set[str] = set()
    saw_blank_kingdom = False
    for ind in goal_row.get("individuales") or []:
        if not isinstance(ind, dict):
            continue
        k = str(ind.get("kingdom") or "").strip()
        if not k:
            saw_blank_kingdom = True
            continue
        kingdoms.add(k)
    if saw_blank_kingdom:
        return None
    if len(kingdoms) == 1:
        return next(iter(kingdoms))
    return None


def _goal_kingdom_hint(goal_row: dict) -> str | None:
    """Reino único de la goal (nombre / individuales), o None si es multi."""
    stem = _strip_goal_stem_suffix(_goal_stem(str(goal_row.get("goal") or "")))
    named = _kingdom_from_stem(stem)
    if named:
        return named
    return _kingdom_from_individuales(goal_row)


def _is_concrete_lista_row(row: dict) -> bool:
    return bool(
        row.get("name")
        or row.get("id") is not None
        or row.get("id_list") is not None
        or row.get("moon") is not None
    )


def _lookup_lista_idx(
    lista_index: dict[tuple, int],
    *,
    kingdom: str,
    source: str | None,
    name: str,
    item: dict,
) -> int | None:
    if not source:
        return None
    for key in _lista_keys(
        kingdom=kingdom, source=source, name=name, item=item
    ):
        if key in lista_index:
            return lista_index[key]
    return None


def _looks_eight_bit_regional(name: str) -> bool:
    """Heurística mientras lists.regionals no conserve eight_bit."""
    n = name.casefold()
    if n.startswith(("8-bit", "last 8-bit")):
        return True
    # Seaside: flag histórico sin prefijo 8-bit en el nombre.
    return n.startswith("ocean-bottom maze")


@dataclass
class _ItemsGoalsState:
    items: list[dict]
    moon_index: dict[tuple, int]
    lista_index: dict[tuple, int]
    by_kingdom_source: dict[tuple[str, str], list[int]]
    goals_by_idx: dict[int, list[tuple[int, str]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    seen_goal: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    story_keys: frozenset[tuple[str, int]] = field(default_factory=_story_moon_keys)
    outfit_door_keys: frozenset[tuple[str, int]] = field(
        default_factory=_outfit_door_moon_keys
    )


def _new_zonas_item_row(
    *, kingdom: str, source: str, name: str, id_kingdom: object, idx: int
) -> dict:
    return {
        "id": _item_id(kingdom, source, id_kingdom),
        "name": name,
        "order": idx + 1,
        "n_goals": 0,
        "goals": [],
    }


def _register_moon_item(
    *,
    moon_index: dict[tuple, int],
    kingdom: str,
    idx: int,
    id_kingdom: object,
    raw: dict,
) -> None:
    moon_num = int(str(id_kingdom or raw.get("moon") or 0))
    moon_index[_moon_key(kingdom, moon_num)] = idx


def _register_lista_item(
    *,
    lista_index: dict[tuple, int],
    by_kingdom_source: dict[tuple[str, str], list[int]],
    kingdom: str,
    source: str,
    name: str,
    idx: int,
    raw: dict,
) -> None:
    for key in _lista_keys(kingdom=kingdom, source=source, name=name, item=raw):
        lista_index.setdefault(key, idx)
    by_kingdom_source[(kingdom, source)].append(idx)


def _index_zonas_items(payload: dict) -> _ItemsGoalsState:
    items: list[dict] = []
    moon_index: dict[tuple, int] = {}
    lista_index: dict[tuple, int] = {}
    by_kingdom_source: dict[tuple[str, str], list[int]] = defaultdict(list)

    for block in payload.get("kingdoms") or []:
        kingdom = str(block.get("kingdom") or "")
        for raw in block.get("list") or []:
            if not isinstance(raw, dict):
                continue
            source = str(raw.get("source") or "")
            name = str(raw.get("name") or "")
            id_kingdom = raw.get("id_kingdom")
            idx = len(items)
            if source == MOON_SOURCE:
                _register_moon_item(
                    moon_index=moon_index,
                    kingdom=kingdom,
                    idx=idx,
                    id_kingdom=id_kingdom,
                    raw=raw,
                )
            else:
                _register_lista_item(
                    lista_index=lista_index,
                    by_kingdom_source=by_kingdom_source,
                    kingdom=kingdom,
                    source=source,
                    name=name,
                    idx=idx,
                    raw=raw,
                )
            items.append(
                _new_zonas_item_row(
                    kingdom=kingdom,
                    source=source,
                    name=name,
                    id_kingdom=id_kingdom,
                    idx=idx,
                )
            )

    return _ItemsGoalsState(
        items=items,
        moon_index=moon_index,
        lista_index=lista_index,
        by_kingdom_source=dict(by_kingdom_source),
    )


def _goal_add(state: _ItemsGoalsState, idx: int, goal_row: dict) -> None:
    goal = str(goal_row.get("goal") or "")
    if not goal or goal in SKIP_GOALS:
        return
    orden = int(goal_row.get("orden") or 0)
    if orden in state.seen_goal[idx]:
        return
    state.seen_goal[idx].add(orden)
    state.goals_by_idx[idx].append((orden, goal))


def _goal_add_moon(
    state: _ItemsGoalsState,
    idx: int,
    goal_row: dict,
    *,
    cat_k: str,
    cat_m: int,
) -> None:
    goal = str(goal_row.get("goal") or "")
    if _is_kingdom_story_goal(goal) and (cat_k, cat_m) not in state.story_keys:
        return
    _goal_add(state, idx, goal_row)


def _goal_add_lista_row(
    state: _ItemsGoalsState, goal_row: dict, raw: dict
) -> None:
    kingdom = str(raw.get("kingdom") or "")
    name = str(raw.get("name") or "")
    source = _resolve_lista_source(goal_row, raw)
    idx = _lookup_lista_idx(
        state.lista_index, kingdom=kingdom, source=source, name=name, item=raw
    )
    if idx is None:
        return
    hint_k = _goal_kingdom_hint(goal_row)
    if hint_k and kingdom and kingdom != hint_k:
        return
    _goal_add(state, idx, goal_row)


def _goal_add_kingdom_source(
    state: _ItemsGoalsState, goal_row: dict, *, kingdom: str, source: str
) -> None:
    hint_k = _goal_kingdom_hint(goal_row)
    if hint_k and kingdom and kingdom != hint_k:
        return
    for idx in state.by_kingdom_source.get((kingdom, source), []):
        _goal_add(state, idx, goal_row)


def _goal_add_ks_forced(
    state: _ItemsGoalsState, goal_row: dict, *, kingdom: str, source: str
) -> None:
    """Como _goal_add_kingdom_source pero sin filtrar por hint de reino."""
    for idx in state.by_kingdom_source.get((kingdom, source), []):
        _goal_add(state, idx, goal_row)


def _attach_concrete_lista(
    state: _ItemsGoalsState, goal_row: dict, concrete: list[dict]
) -> None:
    for raw in concrete:
        _goal_add_lista_row(state, goal_row, raw)


def _attach_aggregate_lista(
    state: _ItemsGoalsState,
    goal_row: dict,
    aggregates: list[dict],
    sources: list[str],
) -> None:
    fallback_source = sources[0] if len(sources) == 1 else None
    for raw in aggregates:
        kingdom = str(raw.get("kingdom") or "")
        source = str(raw.get("source") or "") or fallback_source
        if not kingdom or not source:
            continue
        _goal_add_kingdom_source(state, goal_row, kingdom=kingdom, source=source)


def _attach_regional_lista(
    state: _ItemsGoalsState,
    goal_row: dict,
    goal: str,
    sources: list[str],
) -> bool:
    """Regional fallback; True si consumió el goal."""
    regional = regional_lista_for_goal(goal)
    if regional is None:
        return False

    reg_concrete = [r for r in regional if _is_concrete_lista_row(r)]
    if reg_concrete:
        for raw in reg_concrete:
            seeded = dict(raw)
            seeded.setdefault("source", "regionals")
            _goal_add_lista_row(state, goal_row, seeded)
        return True

    for raw in regional:
        if not isinstance(raw, dict):
            continue
        kingdom = str(raw.get("kingdom") or "")
        if kingdom:
            _goal_add_kingdom_source(
                state, goal_row, kingdom=kingdom, source="regionals"
            )
    return bool(regional or not sources)


def _attach_poi_singleton_lista(
    state: _ItemsGoalsState, goal_row: dict, sources: list[str]
) -> bool:
    hint_k = _goal_kingdom_hint(goal_row)
    if not hint_k or len(sources) != 1 or sources[0] == "regionals":
        return False
    _goal_add_kingdom_source(state, goal_row, kingdom=hint_k, source=sources[0])
    return True


def _attach_sand_ice_regional(state: _ItemsGoalsState, goal_row: dict) -> None:
    for name in (
        "Inside the Ice Caves",
        "Inside the Underground Temple",
    ):
        _goal_add_lista_row(
            state,
            goal_row,
            {
                "kingdom": "sand",
                "source": "regionals",
                "name": name,
            },
        )


def _attach_eight_bit_regional(state: _ItemsGoalsState, goal_row: dict) -> None:
    for i, row in enumerate(state.items):
        if "/regionals/" not in str(row.get("id") or ""):
            continue
        if _looks_eight_bit_regional(str(row.get("name") or "")):
            _goal_add(state, i, goal_row)


def _attach_special_lista_goals(
    state: _ItemsGoalsState, goal_row: dict, goal: str, sources: list[str]
) -> bool:
    if _attach_poi_singleton_lista(state, goal_row, sources):
        return True
    if goal == "{{X}} Sand Ice Regional Coins":
        _attach_sand_ice_regional(state, goal_row)
        return True
    if goal == "{{X}} 8-Bit Regional Coins":
        _attach_eight_bit_regional(state, goal_row)
        return True
    return False


def _attach_lista_pool(state: _ItemsGoalsState, goal_row: dict) -> None:
    lista_rows = [
        r for r in (goal_row.get("lista") or []) if isinstance(r, dict)
    ]
    concrete = [r for r in lista_rows if _is_concrete_lista_row(r)]
    aggregates = [r for r in lista_rows if not _is_concrete_lista_row(r)]
    sources = _split_lista_sources(goal_row.get("lista_source"))

    if concrete:
        _attach_concrete_lista(state, goal_row, concrete)
        return

    if aggregates:
        _attach_aggregate_lista(state, goal_row, aggregates, sources)
        return

    goal = str(goal_row.get("goal") or "")
    if _attach_regional_lista(state, goal_row, goal, sources):
        return

    if _attach_special_lista_goals(state, goal_row, goal, sources):
        return


def _process_goal_moons(state: _ItemsGoalsState, goal_row: dict) -> None:
    for moon in goal_row.get("moons") or []:
        if not isinstance(moon, dict) or moon.get("moon") is None:
            continue
        cat_k, cat_m = lunas_catalog_ref(
            str(moon.get("kingdom") or ""), int(moon["moon"])
        )
        moon_idx = state.moon_index.get(_moon_key(cat_k, cat_m))
        if moon_idx is None:
            continue
        _goal_add_moon(state, moon_idx, goal_row, cat_k=cat_k, cat_m=cat_m)


def _ref_by_goal(ref: dict) -> dict[str, dict]:
    return {
        str(g.get("goal") or ""): g
        for g in ref.get("goals") or []
        if isinstance(g, dict) and g.get("goal")
    }


def _shop_moon_goal_by_kingdom(
    ref_by_goal: dict[str, dict],
) -> dict[str, dict]:
    """Shop Moon por reino (1 luna shopping) → forzar enlace a Crazy Cap."""
    by_kingdom: dict[str, dict] = {}
    for goal, row in ref_by_goal.items():
        if goal == "{{X}} Shop Moons" or "Shop Moon" not in goal:
            continue
        moons = [
            m
            for m in (row.get("moons") or [])
            if isinstance(m, dict) and m.get("kingdom")
        ]
        if len(moons) != 1:
            continue
        kingdom = str(moons[0]["kingdom"])
        by_kingdom.setdefault(kingdom, row)
    return by_kingdom


def _goal_add_pair(
    state: _ItemsGoalsState, idx: int, orden: int, goal: str
) -> None:
    if not goal or goal in SKIP_GOALS:
        return
    if orden in state.seen_goal[idx]:
        return
    state.seen_goal[idx].add(orden)
    state.goals_by_idx[idx].append((orden, goal))


def _apply_shop_inherits_sold_item_goals(state: _ItemsGoalsState) -> None:
    """Crazy Cap = unión de goals de mercancía del reino (+ Shop Moon del reino)."""
    for (kingdom, source), shop_idxs in state.by_kingdom_source.items():
        if source != "shops" or not shop_idxs:
            continue
        by_orden: dict[int, str] = {}
        for merch_src in SHOP_ITEM_LISTS:
            if merch_src == "boxer_shorts":
                continue
            for idx in state.by_kingdom_source.get((kingdom, merch_src), []):
                for orden, goal in state.goals_by_idx.get(idx) or []:
                    if goal in _SHOP_INHERIT_SKIP_GOALS:
                        continue
                    by_orden[int(orden)] = goal
        if not by_orden:
            continue
        for shop_idx in shop_idxs:
            for orden, goal in by_orden.items():
                _goal_add_pair(state, shop_idx, orden, goal)


def _apply_forced_poi_goals(
    state: _ItemsGoalsState, ref_by_goal: dict[str, dict]
) -> None:
    boxer = ref_by_goal.get(GOAL_SNOW_BOXER_SHORTS)
    if boxer:
        _goal_add_ks_forced(state, boxer, kingdom="sand", source="boxer_shorts")
    sphynx = ref_by_goal.get("{{X}} Sphynx Moons")
    if sphynx:
        for kingdom in ("sand", "seaside"):
            _goal_add_ks_forced(state, sphynx, kingdom=kingdom, source="sphynxes")
    # Solo Shop Moon del reino (no {{X}} Shop Moons).
    for kingdom, shop_row in _shop_moon_goal_by_kingdom(ref_by_goal).items():
        _goal_add_ks_forced(state, shop_row, kingdom=kingdom, source="shops")
    _apply_shop_inherits_sold_item_goals(state)


def _attach_total_story_moons(
    state: _ItemsGoalsState, total_story: dict | None
) -> None:
    if not total_story:
        return
    orden_ts = int(total_story.get("orden") or 0)
    for cat_k, cat_m in state.story_keys:
        moon_idx = state.moon_index.get(_moon_key(cat_k, cat_m))
        if moon_idx is None:
            continue
        if any(
            _is_kingdom_story_goal(g)
            for _, g in state.goals_by_idx.get(moon_idx) or []
        ):
            continue
        if orden_ts in state.seen_goal[moon_idx]:
            continue
        state.seen_goal[moon_idx].add(orden_ts)
        state.goals_by_idx[moon_idx].append((orden_ts, GOAL_TOTAL_STORY_MOONS))


def _finalize_items(state: _ItemsGoalsState) -> tuple[int, dict[int, int]]:
    idx_moon_ref: dict[int, tuple[str, int]] = {}
    for key, idx in state.moon_index.items():
        idx_moon_ref[idx] = (str(key[1]), int(key[2]))

    n_with = 0
    by_n: dict[int, int] = defaultdict(int)
    for i, row in enumerate(state.items):
        pairs = sorted(state.goals_by_idx.get(i) or [], key=lambda p: p[0])
        goals = prune_umbrella_goals([name for _, name in pairs if name])
        moon_ref = idx_moon_ref.get(i)
        goals = prune_outfit_door_sub_area_goals(
            goals,
            is_outfit_door=bool(moon_ref and moon_ref in state.outfit_door_keys),
        )
        row["n_goals"] = len(goals)
        row["goals"] = goals
        by_n[len(goals)] += 1
        if goals:
            n_with += 1
    return n_with, dict(by_n)


def _attach_goals_from_ref(state: _ItemsGoalsState, ref: dict) -> None:
    for goal_row in ref.get("goals") or []:
        if not isinstance(goal_row, dict):
            continue
        goal = str(goal_row.get("goal") or "")
        if not goal or goal in SKIP_GOALS:
            continue
        _process_goal_moons(state, goal_row)
        _attach_lista_pool(state, goal_row)


def build_items_goals() -> dict:
    zone_map = load_zonas_zone_index()
    payload = build_zonas_inventario(zone_map=zone_map)
    ref = load_catalog(REF_PATH) if REF_PATH.is_file() else {}

    state = _index_zonas_items(payload)
    _attach_goals_from_ref(state, ref)

    ref_by_goal = _ref_by_goal(ref)
    _apply_forced_poi_goals(state, ref_by_goal)
    _attach_total_story_moons(state, ref_by_goal.get(GOAL_TOTAL_STORY_MOONS))

    n_with, by_n = _finalize_items(state)
    n_moons = sum(1 for r in state.items if "/moon/" in str(r.get("id") or ""))
    n_items_by_n_goals = {str(k): by_n[k] for k in sorted(by_n)}
    return {
        "_definition": (
            "Ítem → templates Combined (como goal_icons: goals[] = nombres). "
            "id = reino/source/nº; order = 1..N plano (= zonas); n_goals antes "
            "de goals[]. Matching estricto moons[]/lista[]. Sin totales/All "
            "multi-reino ni Capture X. Si hay goal concreta, se quita el "
            "paraguas (Nature←Fauna/Flora; Ground Pound/Outfit Door globales; "
            "Sand Moons←Oasis/Ruins/…). * Story Moons solo en lunas del "
            "grupo story_moon (Cascade #1 → Total Story Moons). Lunas "
            "outfit_door: sin goals Sub-Area (solo outfit + resto). "
            "n_items_by_n_goals[k] = ítems con exactamente k goals "
            "(Σ = n_items). Moon remap mushroom#39 → luncheon#50. "
            "Crazy Cap (shops): Shop Moon del reino + unión de goals de "
            "merchandise (costume_sets/hats/souvenirs/stickers); sin "
            "{{X}} Shop Moons ni Snow Boxer Shorts Moon. "
            "Detalle → goals_referencia. No editar."
        ),
        "_note": (
            "Regenerar: python Files/export_items_goals.py (o regenerate_all.py). "
            "n_items_by_n_goals como goal_icons.n_icons_by_n_goals."
        ),
        "n_items": len(state.items),
        "n_moons": n_moons,
        "n_lista_items": len(state.items) - n_moons,
        "n_with_goals": n_with,
        "n_without_goals": len(state.items) - n_with,
        "n_items_by_n_goals": n_items_by_n_goals,
        "items": state.items,
    }


def main() -> int:
    payload = build_items_goals()
    write_catalog_json(OUT_PATH, payload)
    print(
        f"items={payload['n_items']} with_goals={payload['n_with_goals']} "
        f"without={payload['n_without_goals']} -> {OUT_PATH.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
