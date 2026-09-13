"""Export Catalog/items_goals.json — cada ítem del juego → goals Combined.

Universo e orden = build_zonas_reino() (story kingdoms; moons → lists alfa +
binoculars), plano sin agrupar. goals[] = nombres de templates (compacto,
como goal_icons). Lookup estricto vía moons[] / lista[] de goals_referencia
(moons con remap mushroom#39→luncheon#50). Sin expandir lista_source a toda
la lista ni respaldo bingo_groups (evita inflación cruzada entre reinos).

Uso:
  python Files/export_items_goals.py
"""
from __future__ import annotations

from collections import defaultdict

from catalog_lib import (
    CATALOG_DIR,
    load_bingo_groups,
    load_catalog,
    lunas_catalog_ref,
    write_catalog_json,
)
from export_zonas_reino import BINOCULARS_SOURCE, MOON_SOURCE, build_zonas_reino
from goal_list_lib import (
    list_item_match_key,
    load_zonas_zone_index,
    regional_lista_for_goal,
    resolve_lista_item_source,
)

OUT_PATH = CATALOG_DIR / "items_goals.json"
REF_PATH = CATALOG_DIR / "goals_referencia.json"
GOAL_TOTAL_STORY_MOONS = "{{X}} Total Story Moons"

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


def _build_umbrella_children() -> dict[str, frozenset[str]]:
    """umbrella → hijos que la hacen redundante en el mismo ítem."""
    groups = [g for g in load_bingo_groups() if isinstance(g, dict)]
    by_id = {str(g.get("id") or ""): g for g in groups}
    drop: dict[str, set[str]] = defaultdict(set)

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

    for gid, umbrella in (
        ("ground_pound", "{{X}} Ground Pound Moons"),
        ("outfit_door", "{{X}} Outfit Door Moons"),
    ):
        g = by_id.get(gid) or {}
        drop[umbrella] |= {x for x in _group_goal_names(g) if x != umbrella}

    labels = list(_KINGDOM_LABELS.values()) + ["Bowser's"]
    all_goals: set[str] = set()
    for g in groups:
        all_goals |= _group_goal_names(g)

    by_norm = {_norm_goal_key(g): g for g in all_goals}

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

    for child, umbrellas in _ZONE_GOAL_UMBRELLAS.items():
        if child in all_goals or _norm_goal_key(child) in by_norm:
            real = by_norm.get(_norm_goal_key(child), child)
            for umbrella in umbrellas:
                drop[umbrella].add(real)

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
    """Mismo esquema que zonas_revision: reino/source/nº."""
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


def _goal_kingdom_hint(goal_row: dict) -> str | None:
    """Reino único de la goal (nombre / individuales), o None si es multi."""
    text = str(goal_row.get("goal") or "")
    stem = _goal_stem(text)
    for suffix in (" Moon Rock", " Talkatoo", " Sphynx Question"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            if stem.startswith("Correct "):
                stem = stem[len("Correct ") :]
            stem = stem.strip()
            break
    named = []
    for k, label in _KINGDOM_LABELS.items():
        # "Moon Rocks" / "Moon Rock" no son el reino Moon.
        if k == "moon" and (
            stem == "Moon Rocks"
            or stem.startswith("Moon Rock")
            or stem.startswith("Moon Rocks ")
        ):
            continue
        if (
            stem == label
            or stem == f"{label}'s"
            or stem.startswith(f"{label} ")
            or stem.startswith(f"{label}'s ")
        ):
            named.append(k)
    if len(named) == 1:
        return named[0]
    kingdoms: set[str] = set()
    saw_blank_kingdom = False
    for ind in goal_row.get("individuales") or []:
        if not isinstance(ind, dict):
            continue
        k = str(ind.get("kingdom") or "").strip()
        if not k:
            # Umbral sin reino fijo → goal multi-reino (p. ej. Activate P-Switches).
            saw_blank_kingdom = True
            continue
        kingdoms.add(k)
    if saw_blank_kingdom:
        return None
    if len(kingdoms) == 1:
        return next(iter(kingdoms))
    return None


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


def build_items_goals() -> dict:
    zone_map = load_zonas_zone_index()
    payload = build_zonas_reino(zone_map=zone_map)
    ref = load_catalog(REF_PATH) if REF_PATH.is_file() else {}

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
            row: dict = {
                "id": _item_id(kingdom, source, id_kingdom),
                "name": name,
                "order": idx + 1,
                "n_goals": 0,
                "goals": [],
            }
            if source == MOON_SOURCE:
                moon_num = int(id_kingdom or raw.get("moon") or 0)
                moon_index[_moon_key(kingdom, moon_num)] = idx
            else:
                for key in _lista_keys(
                    kingdom=kingdom, source=source, name=name, item=raw
                ):
                    lista_index.setdefault(key, idx)
                by_kingdom_source[(kingdom, source)].append(idx)
            items.append(row)

    goals_by_idx: dict[int, list[tuple[int, str]]] = defaultdict(list)
    seen_goal: dict[int, set[int]] = defaultdict(set)
    story_keys = _story_moon_keys()
    outfit_door_keys = _outfit_door_moon_keys()
    # idx → (kingdom, moon) para moons del universo
    idx_moon_ref: dict[int, tuple[str, int]] = {}
    for key, idx in moon_index.items():
        idx_moon_ref[idx] = (str(key[1]), int(key[2]))

    def _add(idx: int, goal_row: dict) -> None:
        goal = str(goal_row.get("goal") or "")
        if not goal or goal in SKIP_GOALS:
            return
        orden = int(goal_row.get("orden") or 0)
        if orden in seen_goal[idx]:
            return
        seen_goal[idx].add(orden)
        goals_by_idx[idx].append((orden, goal))

    def _add_moon(idx: int, goal_row: dict, *, cat_k: str, cat_m: int) -> None:
        goal = str(goal_row.get("goal") or "")
        # Solo lunas del grupo story_moon llevan * Story Moons.
        if _is_kingdom_story_goal(goal) and (cat_k, cat_m) not in story_keys:
            return
        _add(idx, goal_row)

    def _add_lista_row(goal_row: dict, raw: dict) -> None:
        kingdom = str(raw.get("kingdom") or "")
        name = str(raw.get("name") or "")
        source = _resolve_lista_source(goal_row, raw)
        idx = _lookup_lista_idx(
            lista_index, kingdom=kingdom, source=source, name=name, item=raw
        )
        if idx is None:
            return
        hint_k = _goal_kingdom_hint(goal_row)
        if hint_k and kingdom and kingdom != hint_k:
            return
        _add(idx, goal_row)

    def _add_kingdom_source(
        goal_row: dict, *, kingdom: str, source: str
    ) -> None:
        hint_k = _goal_kingdom_hint(goal_row)
        if hint_k and kingdom and kingdom != hint_k:
            return
        for idx in by_kingdom_source.get((kingdom, source), []):
            _add(idx, goal_row)

    def _attach_lista_pool(goal_row: dict) -> None:
        lista_rows = [
            r for r in (goal_row.get("lista") or []) if isinstance(r, dict)
        ]
        concrete = [r for r in lista_rows if _is_concrete_lista_row(r)]
        aggregates = [r for r in lista_rows if not _is_concrete_lista_row(r)]
        sources = _split_lista_sources(goal_row.get("lista_source"))

        if concrete:
            for raw in concrete:
                _add_lista_row(goal_row, raw)
            return

        if aggregates:
            fallback_source = sources[0] if len(sources) == 1 else None
            for raw in aggregates:
                kingdom = str(raw.get("kingdom") or "")
                source = str(raw.get("source") or "") or fallback_source
                if not kingdom or not source:
                    continue
                _add_kingdom_source(goal_row, kingdom=kingdom, source=source)
            return

        # lista vacía: regionals tipados vía goal_list_lib (clusters / by_kingdom).
        goal = str(goal_row.get("goal") or "")
        regional = regional_lista_for_goal(goal)
        if regional is not None:
            reg_concrete = [r for r in regional if _is_concrete_lista_row(r)]
            if reg_concrete:
                for raw in reg_concrete:
                    seeded = dict(raw)
                    seeded.setdefault("source", "regionals")
                    _add_lista_row(goal_row, seeded)
                return
            for raw in regional:
                if not isinstance(raw, dict):
                    continue
                kingdom = str(raw.get("kingdom") or "")
                if kingdom:
                    _add_kingdom_source(
                        goal_row, kingdom=kingdom, source="regionals"
                    )
            if regional or not sources:
                return

        # POI singleton (sphynxes / moon_rocks / …): lista_source + hint de reino.
        hint_k = _goal_kingdom_hint(goal_row)
        if hint_k and len(sources) == 1 and sources[0] != "regionals":
            _add_kingdom_source(goal_row, kingdom=hint_k, source=sources[0])
            return

        # Sand Ice: clusters conocidos si el filtro zone aún no está curado.
        if goal == "{{X}} Sand Ice Regional Coins":
            for name in (
                "Inside the Ice Caves",
                "Inside the Underground Temple",
            ):
                _add_lista_row(
                    goal_row,
                    {
                        "kingdom": "sand",
                        "source": "regionals",
                        "name": name,
                    },
                )
            return

        # 8-Bit Regional: eight_bit se strippea de goal_lists; usar nombre.
        if goal == "{{X}} 8-Bit Regional Coins":
            for i, row in enumerate(items):
                if "/regionals/" not in str(row.get("id") or ""):
                    continue
                if _looks_eight_bit_regional(str(row.get("name") or "")):
                    _add(i, goal_row)

    for goal_row in ref.get("goals") or []:
        if not isinstance(goal_row, dict):
            continue
        goal = str(goal_row.get("goal") or "")
        if not goal or goal in SKIP_GOALS:
            continue

        for moon in goal_row.get("moons") or []:
            if not isinstance(moon, dict) or moon.get("moon") is None:
                continue
            cat_k, cat_m = lunas_catalog_ref(
                str(moon.get("kingdom") or ""), int(moon["moon"])
            )
            moon_idx = moon_index.get(_moon_key(cat_k, cat_m))
            if moon_idx is None:
                continue
            _add_moon(moon_idx, goal_row, cat_k=cat_k, cat_m=cat_m)

        _attach_lista_pool(goal_row)

    # POIs sin fila en lista[] de referencia pero con goal Combined clara.
    ref_by_goal = {
        str(g.get("goal") or ""): g
        for g in ref.get("goals") or []
        if isinstance(g, dict) and g.get("goal")
    }

    def _add_ks_forced(goal_row: dict, *, kingdom: str, source: str) -> None:
        """Como _add_kingdom_source pero sin filtrar por hint de reino."""
        for idx in by_kingdom_source.get((kingdom, source), []):
            _add(idx, goal_row)

    boxer = ref_by_goal.get("Snow Boxer Shorts Moon")
    if boxer:
        # Merch en Sand; la luna Combined es Snow (hint ≠ reino del POI).
        _add_ks_forced(boxer, kingdom="sand", source="boxer_shorts")
    sphynx = ref_by_goal.get("{{X}} Sphynx Moons")
    if sphynx:
        for kingdom in ("sand", "seaside"):
            _add_ks_forced(sphynx, kingdom=kingdom, source="sphynxes")

    # story_moon sin template de reino (Cascade #1): Total Story Moons.
    total_story = ref_by_goal.get(GOAL_TOTAL_STORY_MOONS)
    if total_story:
        orden_ts = int(total_story.get("orden") or 0)
        for cat_k, cat_m in story_keys:
            moon_idx = moon_index.get(_moon_key(cat_k, cat_m))
            if moon_idx is None:
                continue
            if any(
                _is_kingdom_story_goal(g) for _, g in goals_by_idx.get(moon_idx) or []
            ):
                continue
            if orden_ts in seen_goal[moon_idx]:
                continue
            seen_goal[moon_idx].add(orden_ts)
            goals_by_idx[moon_idx].append((orden_ts, GOAL_TOTAL_STORY_MOONS))

    n_with = 0
    by_n: dict[int, int] = defaultdict(int)
    for i, row in enumerate(items):
        pairs = sorted(goals_by_idx.get(i) or [], key=lambda p: p[0])
        goals = prune_umbrella_goals([name for _, name in pairs if name])
        moon_ref = idx_moon_ref.get(i)
        goals = prune_outfit_door_sub_area_goals(
            goals,
            is_outfit_door=bool(moon_ref and moon_ref in outfit_door_keys),
        )
        row["n_goals"] = len(goals)
        row["goals"] = goals
        by_n[len(goals)] += 1
        if goals:
            n_with += 1

    n_moons = sum(1 for r in items if "/moon/" in str(r.get("id") or ""))
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
            "Detalle → goals_referencia. No editar."
        ),
        "_note": (
            "Regenerar: python Files/export_items_goals.py (o regenerate_all.py). "
            "n_items_by_n_goals como goal_icons.n_icons_by_n_goals."
        ),
        "n_items": len(items),
        "n_moons": n_moons,
        "n_lista_items": len(items) - n_moons,
        "n_with_goals": n_with,
        "n_without_goals": len(items) - n_with,
        "n_items_by_n_goals": n_items_by_n_goals,
        "items": items,
    }


def _looks_eight_bit_regional(name: str) -> bool:
    """Heurística mientras lists.regionals no conserve eight_bit."""
    n = name.casefold()
    if n.startswith(("8-bit", "last 8-bit")):
        return True
    # Seaside: flag histórico sin prefijo 8-bit en el nombre.
    return n.startswith("ocean-bottom maze")


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
