"""Export de referencia de goals Combined.

Salida: catalog/goals_referencia.json (estructura tipo bingo_groups)

Uso: python export_goals_referencia.py
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from catalog_lib import (
    CATALOG_DIR,
    JSON_PATH,
    KINGDOM_COLUMNS,
    KINGDOM_GOAL_PREFIXES,
    ROOT,
    STORY_ORDER,
    build_matrix_moon_registry,
    compute_in_scope_moon_totals,
    enrich_moon_ref_odyssey,
    goal_moon_count_mode,
    group_moons,
    group_objective_refs,
    kingdom_story_index,
    load_bingo_groups,
    load_combined_objectives_by_goal,
    objective_ref_from_combined,
    refresh_in_scope_odyssey_meta,
    sort_category_list,
    write_catalog_json,
)
from goal_list_lib import (
    build_goal_lista,
    checkpoint_goal_fields,
    enrich_lista_locations,
    multi_moon_totals_lista,
    regionales_zonas_entry,
    regional_goal_fields,
    sort_lista_items,
)

OUT_JSON = CATALOG_DIR / "goals_referencia.json"

NON_MOON_GOAL_MARKERS = (
    "Regional Coin",
    "Checkpoint",
    "Call Jaxi",
    "Seed Planted",
    "Seeds Planted",
    "Pixel",
)


def is_moon_count_objective(goal: str, obj: dict) -> bool:
    """True si el objetivo se completa contando Power Moons (Moon Get)."""
    tip = (obj.get("tooltip") or "").lower()
    gl = goal.lower()
    if "moon get" in tip:
        return True
    if any(m.lower() in gl for m in NON_MOON_GOAL_MARKERS):
        return False
    if goal.startswith("Defeat ") or goal.startswith("Win "):
        return False
    if goal.startswith("Purchase ") or goal.startswith("Buy ") or goal.startswith("Wear "):
        return False
    if goal.startswith("Activate ") or goal.startswith("Look at ") or goal.startswith("Talk to "):
        return False
    if "freerunning" in gl:
        return False
    if "moon" in gl:
        return True
    return False

_HYBRID_NO_MOON_GOALS = frozenset(
    {
        "{{X}} Talkatoos",
        "{{X}} Moon Rocks",
        "{{X}} Total Moons",
        "{{X}} Seed Moon (No Time Travel)",
    }
)

# No son Moon Get, pero el pool contable son lunas → moons[] (no lista[]).
_MOONS_POOL_NON_GET = frozenset(
    {
        "{{X}} Seeds Planted",
        "Look at {{X}} Hint-Arts",
    }
)

# No unir estas fuentes cuando exista un grupo mas concreto.
_UMBRELLA = frozenset(
    {
        "captures",
        "cappy",
        "seeds",
        "fauna",
        "flora",
        "nature",
        "sub_area",
        "transport",
        "mario",
        "totals",
    }
)

# Pools compartidos: si el goal nombra un reino, filtrar a ese reino.
_SHARED_POOLS = frozenset(
    {
        "story_moon",
        "multi_moon",
        "outfit_door",
        "ground_pound",
        "shop",
        "hint_art",
        "captain_toad",
        "painting",
        "minigame",
        "fauna",
        "flora",
        "nature",
    }
)

_POOL_ONLY_BY_ID: dict[str, bool] | None = None


def _group_is_pool_only(gid: str) -> bool:
    """True si el grupo es pool dedicado (apply_moon_tag=False y 1 goal).

    Evita umbrellas flora/nature (varios goals) frente a cactus_tree, etc.
    """
    global _POOL_ONLY_BY_ID
    if _POOL_ONLY_BY_ID is None:
        _POOL_ONLY_BY_ID = {}
        for g in load_bingo_groups():
            gid_g = str(g.get("id") or "")
            n_goals = sum(
                1
                for o in g.get("objectives") or []
                if isinstance(o, dict) and o.get("goal")
            )
            _POOL_ONLY_BY_ID[gid_g] = (
                g.get("apply_moon_tag") is False and n_goals == 1
            )
    return bool(_POOL_ONLY_BY_ID.get(gid))


def goal_kingdom(goal: str, board: list[str]) -> str | None:
    for display, slug in KINGDOM_GOAL_PREFIXES:
        if goal.startswith(display + " ") or goal.startswith(display + "'"):
            return slug
        if goal.startswith("{{X}} " + display + " ") or goal.startswith(
            "{{X}} " + display + "'s "
        ):
            return slug
    cats = [c for c in board if c in KINGDOM_COLUMNS]
    if len(cats) == 1:
        return cats[0]
    return None


def collect_membership() -> dict[str, list[tuple[str, list[dict]]]]:
    membership: dict[str, list[tuple[str, list[dict]]]] = defaultdict(list)
    combined = load_combined_objectives_by_goal(include_disabled=True)
    for group in load_bingo_groups():
        gid = group["id"]
        moons = group_moons(group)
        for ref in group_objective_refs(group, combined):
            goal = ref.get("goal")
            if goal:
                membership[str(goal)].append((gid, moons))
    return membership


def pick_moons_for_goal(
    goal: str,
    entries: list[tuple[str, list[dict]]],
    board: list[str],
    registry: dict,
) -> tuple[list[str], list[dict], str]:
    """Devuelve (group_ids_usados, moons, nota)."""
    if not entries:
        return [], [], "sin grupo bingo"

    kingdom_ids = set(KINGDOM_COLUMNS)
    kd = goal_kingdom(goal, board)
    gl = goal.lower()

    # Sub-Area: pool del grupo sub_area (no el reino entero; sub_area es umbrella).
    # Goals temáticas (Hybrid 2D, etc.) tienen grupo propio → preferir ese pool.
    _SUB_AREA_SPECIFIC = frozenset({"hybrid_2d"})
    if "sub-area" in gl:
        specific = [
            (gid, ms)
            for gid, ms in entries
            if gid != "sub_area" and ms and gid in _SUB_AREA_SPECIFIC
        ]
        if specific:
            specific.sort(key=lambda gm: (len(gm[1]), gm[0]))
            gid, moons = specific[0]
            return [gid], moons, f"{gid} pool"
        for gid, ms in entries:
            if gid == "sub_area" and ms:
                moons = list(ms)
                if kd:
                    filtered = [m for m in moons if m.get("kingdom") == kd]
                    if filtered:
                        moons = filtered
                return ["sub_area"], moons, "sub_area pool"

    thematic = [(g, m) for g, m in entries if g not in kingdom_ids]
    pool = thematic if thematic else entries
    concrete = [(g, m) for g, m in pool if g not in _UMBRELLA]
    if concrete:
        pool = concrete

    # Preferir grupo pool (apply_moon_tag=False) frente a tags concretas
    # que heredan el mismo CAPTURE_OBJECTIVE.
    with_moons = [(g, m) for g, m in pool if m]
    pool_only = [(g, m) for g, m in with_moons if _group_is_pool_only(g)]
    if pool_only:
        pool_only.sort(key=lambda gm: (-len(gm[1]), gm[0]))
        chosen_gid, moons = pool_only[0]
        used = [chosen_gid]
    elif with_moons:
        with_moons.sort(key=lambda gm: (len(gm[1]), gm[0]))
        # Si hay varios con el minimo, preferir shared-pool o stem en el id
        min_n = len(with_moons[0][1])
        candidates = [gm for gm in with_moons if len(gm[1]) == min_n]
        stem = re.sub(r"[^a-z0-9]+", "_", goal.lower())
        preferred = next(
            (
                gm
                for gm in candidates
                if gm[0] in stem or stem.startswith(gm[0]) or gm[0] in goal.lower()
            ),
            candidates[0],
        )
        # Si el mas pequeno es un reino con muchas lunas y hay shared pool
        # del mismo tamano relativo, ya elegimos preferred.
        chosen_gid, moons = preferred
        # Si hay varios grupos pequenos utiles (beanstalk + nada), OK.
        # Si preferred es reino enorme y existe shared con filtro, usar shared.
        shared = [
            gm
            for gm in with_moons
            if gm[0] in _SHARED_POOLS or gm[0] not in kingdom_ids
        ]
        if chosen_gid in kingdom_ids and shared:
            shared.sort(key=lambda gm: (len(gm[1]), gm[0]))
            chosen_gid, moons = shared[0]
        used = [chosen_gid]
    else:
        used = [g for g, _ in pool]
        moons = []

    # Filtro por reino en pools compartidos o goals de reino
    skip_kd_filter = "special seed" in gl
    if kd and not skip_kd_filter and (
        any(g in _SHARED_POOLS for g in used)
        or any(g == kd for g, _ in entries)
        or re.search(r"\b(Shop|Talkatoo|Moon Rock|Captain Toad|Hint Art|Outfit Door|"
                     r"Warp-Painting|Story|Multi-Moon|Ground Pound|Seed)\b", goal)
    ):
        filtered = [m for m in moons if m["kingdom"] == kd]
        if filtered:
            moons = filtered
        elif any(g == kd for g, m in entries for _ in [1]):
            # fallback: buscar en grupo tematico del mismo tipo por nombre
            pass

    # Goals singulares de shop / toad / etc.: una luna del reino
    if goal == "Snow Boxer Shorts Moon":
        # snow#20 I'm Not Cold! (traje boxers al NPC)
        moons = [
            m
            for m in moons
            if m.get("kingdom") == "snow" and int(m.get("moon") or 0) == 20
        ]
    elif "{{x}}" not in gl and moons and kd:
        if "shop moon" in gl:
            moons = [
                m
                for m in moons
                if m["kingdom"] == kd
                and "shopping" in str(m.get("name") or "").lower()
            ] or [m for m in moons if m["kingdom"] == kd][:1]
        elif "captain toad" in gl:
            moons = [
                m
                for m in moons
                if m["kingdom"] == kd
                and "captain toad" in str(m.get("name") or "").lower()
            ] or [m for m in moons if m["kingdom"] == kd][:1]
        elif "hint art" in gl:
            moons = [
                m
                for m in moons
                if m["kingdom"] == kd
                and "art" in str(m.get("name") or "").lower()
            ] or [m for m in moons if m["kingdom"] == kd][:1]
        elif "warp-painting" in gl or "warp painting" in gl:
            moons = [
                m
                for m in moons
                if m["kingdom"] == kd
                and "secret path" in str(m.get("name") or "").lower()
            ] or [m for m in moons if m["kingdom"] == kd][:1]
        elif "outfit door" in gl and "{{x}}" not in gl:
            moons = [m for m in moons if m["kingdom"] == kd]
        elif "multi-moon" in gl and "{{x}}" not in gl:
            moons = [m for m in moons if m["kingdom"] == kd]
        elif "bowser statue" in gl:
            moons = [
                m
                for m in moons
                if "bowser statue" in str(m.get("name") or "").lower()
            ] or [
                {
                    "kingdom": "moon",
                    "moon": 9,
                    "name": "Under the Bowser Statue",
                }
            ]
        elif "sheep" in gl:
            moons = [
                {"kingdom": k, "moon": m, "name": e.get("name") or "?"}
                for (k, m), e in registry.items()
                if k == "sand" and "sheep" in str(e.get("name") or "").lower()
            ] or [
                {"kingdom": "sand", "moon": 33, "name": "Herding Sheep in the Dunes"}
            ]
            used = ["fauna"]
        elif "festival" in gl:
            # 8-bit Celebrating in the Streets — no #7 A Traditional Festival!
            moons = [
                m
                for m in moons
                if "celebrating" in str(m.get("name") or "").lower()
                or (
                    "festival" in str(m.get("name") or "").lower()
                    and "traditional" not in str(m.get("name") or "").lower()
                )
            ] or [
                {
                    "kingdom": "metro",
                    "moon": 36,
                    "name": "Celebrating in the Streets!",
                }
            ]
        elif "puzzle" in gl:
            moons = [
                m
                for m in moons
                if "puzzle" in str(m.get("name") or "").lower()
                or "repair" in str(m.get("name") or "").lower()
                or "blowing and sliding" in str(m.get("name") or "").lower()
            ]
        elif "fire piranha" in gl:
            moons = [
                m
                for m in moons
                if "far-off lanterns" in str(m.get("name") or "").lower()
                or "magma swamp" in str(m.get("name") or "").lower()
                or "fire piranha" in str(m.get("name") or "").lower()
            ] or [
                {
                    "kingdom": "luncheon",
                    "moon": 32,
                    "name": "Light the Far-Off Lanterns",
                }
            ]
        elif "banzai" in gl:
            moons = [
                m
                for m in moons
                if "around the barrier" in str(m.get("name") or "").lower()
                or "treasure chest and back" in str(m.get("name") or "").lower()
                or "banzai" in str(m.get("name") or "").lower()
            ] or [
                {
                    "kingdom": "moon",
                    "moon": 11,
                    "name": "Around the Barrier Wall",
                },
                {
                    "kingdom": "moon",
                    "moon": 13,
                    "name": "Fly to the Treasure Chest and Back",
                },
            ]
        elif "parabones" in gl:
            moons = [
                m
                for m in moons
                if "hole in the magma" in str(m.get("name") or "").lower()
                or "parabones" in str(m.get("name") or "").lower()
            ] or [
                {
                    "kingdom": "moon",
                    "moon": 10,
                    "name": "In a Hole in the Magma",
                }
            ]
        elif "special seed" in gl:
            _SPECIAL_SEED_KEYS = {("lake", 9), ("wooded", 33), ("seaside", 26)}
            moons = [
                m
                for m in moons
                if (m.get("kingdom"), int(m.get("moon") or 0)) in _SPECIAL_SEED_KEYS
                or "spiky passage seed" in str(m.get("name") or "").lower()
                or "treasure made from coins" in str(m.get("name") or "").lower()
                or "ocean trench seed" in str(m.get("name") or "").lower()
            ] or [
                {
                    "kingdom": "lake",
                    "moon": 9,
                    "name": "Lake Gardening: Spiky Passage Seed",
                },
                {
                    "kingdom": "wooded",
                    "moon": 33,
                    "name": "A Treasure Made from Coins",
                },
                {
                    "kingdom": "seaside",
                    "moon": 26,
                    "name": "Sea Gardening: Ocean Trench Seed",
                },
            ]

    # NTT y Seeds Planted: 9 macetas (3 sand + 3 metro + 3 seaside #23–#25).
    _STANDARD_SEED_POTS = {
        ("sand", 25),
        ("sand", 26),
        ("sand", 27),
        ("metro", 21),
        ("metro", 22),
        ("metro", 23),
        ("seaside", 23),
        ("seaside", 24),
        ("seaside", 25),
    }
    if "seed moon (no time travel)" in gl:
        moons = [
            m
            for m in moons
            if (m.get("kingdom"), int(m.get("moon") or 0)) in _STANDARD_SEED_POTS
        ]
    elif "seeds planted" in gl and "lake seed" not in gl:
        moons = [
            m
            for m in moons
            if (m.get("kingdom"), int(m.get("moon") or 0)) in _STANDARD_SEED_POTS
        ]
    elif "golden turnip" in gl:
        moons = [
            m
            for m in moons
            if "golden turnip" in str(m.get("name") or "").lower()
            or "turnip recipe" in str(m.get("name") or "").lower()
        ]

    if "volleyball" in gl:
        moons = [
            m
            for g, ms in entries
            for m in ms
            if "volleyball" in str(m.get("name") or "").lower()
        ]
        used = ["minigame/volleyball"]

    if "slots moon" in gl:
        moons = [
            m
            for g, ms in entries
            for m in ms
            if "slots" in str(m.get("name") or "").lower()
        ]
        if not moons:
            # grupo slots o minigame
            for g, ms in entries:
                moons.extend(
                    m for m in ms if "slots" in str(m.get("name") or "").lower()
                )
        used = ["slots"]

    # Dedup + sort
    by_key: dict[tuple[str, int], dict] = {}
    for raw in moons:
        if "kingdom" not in raw or "moon" not in raw:
            continue
        key = (raw["kingdom"], int(raw["moon"]))
        by_key[key] = raw
    moons = [
        by_key[k]
        for k in sorted(
            by_key,
            key=lambda km: (
                KINGDOM_COLUMNS.index(km[0]) if km[0] in KINGDOM_COLUMNS else 99,
                km[1],
            ),
        )
    ]
    return used, moons, ""


def needs_lista(goal: str, moonish: bool, n_moons: int) -> bool:
    if n_moons and goal not in _HYBRID_NO_MOON_GOALS:
        return False
    if not moonish:
        return True
    if goal in _HYBRID_NO_MOON_GOALS and goal != "{{X}} Total Moons":
        return True
    return n_moons == 0


def normalize_moon_ref(raw: dict, registry: dict) -> dict:
    k, m = raw["kingdom"], int(raw["moon"])
    entry = registry.get((k, m))
    name = (entry or {}).get("name") or raw.get("name") or "?"
    out: dict = {"kingdom": k, "moon": m, "name": name}
    if entry is None:
        out["out_of_scope"] = True
    else:
        out["disponibilidad"] = str(entry.get("availability") or "base")
    return enrich_moon_ref_odyssey(out, registry)


def goal_notas(goal: str, obj: dict) -> list[str]:
    tip = obj.get("tooltip") or ""
    notas: list[str] = []
    if "Multi-Moons count as 3" in tip:
        notas.append(
            "Multi-Moons cuentan como 3 hacia el total. "
            "{{X}} = unidades depositadas en la Odyssey, no entradas de la lista."
        )
    if "Multi-Moons do not count" in tip and "without Multi-Moons" not in tip:
        notas.append("Multi-Moons no cuentan.")
    if goal.startswith("All Checkpoints"):
        notas.append(
            "Sin snow/seaside/bowser (Secret Path fuera). "
            "Incluye mushroom (Yoshi's House, como mushroom#39). "
            "progression solo si la pintura retrasa respecto a la zona del reino."
        )
    if goal.startswith("All Multi-Moons"):
        notas.append(
            "Reinos con ≥1 Multi-Moon; total = nº de Multi-Moons del reino."
        )
    return notas


def combined_fields_flat(goal: str, obj: dict) -> dict:
    """range/progression/limits + board/line/icons (referencia completa)."""
    ref = objective_ref_from_combined(goal, obj)
    ref.pop("goal", None)
    board = list(obj.get("board_categories") or [])
    line = list(obj.get("line_categories") or [])
    icons = list(obj.get("icons") or [])
    if board:
        ref["board_categories"] = board
    if line:
        ref["line_categories"] = line
    if icons:
        ref["icons"] = icons
    return ref


# Keys allowed on kingdom-aggregate rows (lista → by_kingdom).
_KINGDOM_AGG_KEYS = frozenset(
    {"kingdom", "total", "painting", "progression", "zone", "n_groups"}
)

# Totales / umbrellas multi-reino: siempre resumen by_kingdom (sin moons[]).
_ALWAYS_BY_KINGDOM_MOON_GOALS = frozenset(
    {
        "{{X}} Sub-Area Moons",
        "{{X}} Total Moons",
    }
)

# Resumen by_kingdom solo si el dump de lunas es largo (si no → moons[]).
_SUMMARIZE_MOONS_MIN = 50


def lista_is_kingdom_aggregate(lista: list[dict]) -> bool:
    """True si cada fila es un total por reino (no ítems nombrados)."""
    if not lista:
        return False
    for row in lista:
        if not isinstance(row, dict):
            return False
        if "kingdom" not in row or "total" not in row:
            return False
        if set(row.keys()) - _KINGDOM_AGG_KEYS:
            return False
    return True


def by_kingdom_from_moons(moon_refs: list[dict]) -> list[dict]:
    """Resumen {kingdom, n_moons[, n_odyssey_units]} en orden de historia."""
    buckets: dict[str, dict] = {}
    for m in moon_refs:
        k = str(m.get("kingdom") or "")
        if not k:
            continue
        b = buckets.setdefault(k, {"kingdom": k, "n_moons": 0, "n_odyssey_units": 0})
        b["n_moons"] += 1
        b["n_odyssey_units"] += int(m.get("odyssey_units") or 1)
    order = list(STORY_ORDER)
    if "mushroom" not in order:
        order.append("mushroom")
    out: list[dict] = []
    seen: set[str] = set()
    for k in order:
        if k not in buckets:
            continue
        seen.add(k)
        row = buckets[k]
        entry: dict = {"kingdom": k, "n_moons": row["n_moons"]}
        if row["n_odyssey_units"] != row["n_moons"]:
            entry["n_odyssey_units"] = row["n_odyssey_units"]
        out.append(entry)
    for k, row in sorted(buckets.items(), key=lambda kv: kingdom_story_index(kv[0])):
        if k in seen:
            continue
        entry = {"kingdom": k, "n_moons": row["n_moons"]}
        if row["n_odyssey_units"] != row["n_moons"]:
            entry["n_odyssey_units"] = row["n_odyssey_units"]
        out.append(entry)
    return out


def should_summarize_moons_by_kingdom(
    goal: str, moon_refs: list[dict], kd: str | None
) -> bool:
    """by_kingdom solo para umbrellas fijas o pools multi-reino muy grandes.

    Umbral: >= _SUMMARIZE_MOONS_MIN lunas y >=2 reinos. Debajo → moons[].
    No confiar solo en kd: "{{X}} Moon Shard Moons" matchea prefijo Moon.
    """
    if not moon_refs:
        return False
    kingdoms = {str(m.get("kingdom")) for m in moon_refs if m.get("kingdom")}
    if len(kingdoms) < 2:
        return False
    if goal in _ALWAYS_BY_KINGDOM_MOON_GOALS:
        return True
    # Pool realmente de un solo reino (Cap Sub-Area, etc.).
    if kd and kingdoms == {kd}:
        return False
    return len(moon_refs) >= _SUMMARIZE_MOONS_MIN


def odyssey_units_by_kingdom_rows(registry: dict) -> list[dict]:
    """by_kingdom para {{X}} Total Moons (unidades Odyssey + lunas físicas)."""
    totals = compute_in_scope_moon_totals(registry)
    moon_by = totals["moon_count_by_kingdom"]
    units_by = totals["odyssey_units_by_kingdom"]
    assert isinstance(moon_by, dict) and isinstance(units_by, dict)
    out: list[dict] = []
    for k in STORY_ORDER:
        if k not in units_by and k not in moon_by:
            continue
        n_m = int(moon_by.get(k) or 0)
        n_u = int(units_by.get(k) or 0)
        entry: dict = {"kingdom": k, "n_moons": n_m, "n_odyssey_units": n_u}
        out.append(entry)
    return out


def goal_pool(
    *,
    n_moons_detail: int,
    n_lista: int,
    n_by_kingdom: int,
) -> str | None:
    """De dónde sale el pool contable: moons[], lista[], by_kingdom o mixto."""
    if n_by_kingdom and not n_moons_detail and not n_lista:
        return "by_kingdom"
    if n_moons_detail and n_lista:
        return "mixto"
    if n_moons_detail:
        return "moons"
    if n_lista:
        return "lista"
    return None


def lista_n(lista: list[dict]) -> int:
    """Número de filas en lista[] (no la suma de totales agregados)."""
    return len(lista)


def build_goal_record(
    orden: int,
    goal: str,
    obj: dict,
    entries: list[tuple[str, list[dict]]],
    registry: dict,
) -> tuple[dict, bool]:
    board = list(obj.get("board_categories") or [])
    moonish = is_moon_count_objective(goal, obj)
    moons: list[dict] = []
    # All Multi-Moons: cuenta reinos (by_kingdom), no lunas sueltas.
    all_multi = goal.startswith("All Multi-Moons")
    if not all_multi and (moonish or goal in _MOONS_POOL_NON_GET) and entries:
        _, moons, _note = pick_moons_for_goal(goal, entries, board, registry)

    moon_refs = [normalize_moon_ref(m, registry) for m in moons]
    kd = goal_kingdom(goal, board)
    regional = regional_goal_fields(goal, kd)
    checkpoint_meta = checkpoint_goal_fields(goal)
    rz = regionales_zonas_entry(goal)

    lista: list[dict] = []
    summarize_moons = False

    # Multi-reino / umbrellas / regionales → lista[].
    if rz and rz.get("groups"):
        # Clusters de monedas regionales (regionales_zonas.groups).
        lista = [dict(g) for g in rz["groups"]]
    elif rz and rz.get("by_kingdom"):
        lista = [dict(x) for x in rz["by_kingdom"]]
    elif goal == "{{X}} Total Moons":
        lista = odyssey_units_by_kingdom_rows(registry)
        summarize_moons = True
    elif should_summarize_moons_by_kingdom(goal, moon_refs, kd):
        lista = by_kingdom_from_moons(moon_refs)
        summarize_moons = True
    elif all_multi:
        lista = multi_moon_totals_lista()
    else:
        want_lista = needs_lista(goal, moonish, len(moon_refs))
        gl = goal.lower()
        # Total Regional / All Large|Small / checkpoints: lista por reino
        if want_lista and (
            regional is None
            or "total regional" in gl
            or "large kingdom" in gl
            or "small kingdom" in gl
            or checkpoint_meta is not None
        ):
            lista = build_goal_lista(goal, obj, kingdom=kd)
        elif regional and regional.get("regional_total") is not None:
            # Fallback si no hay groups[] en regionales_zonas.
            row: dict = {"total": int(regional["regional_total"])}
            if kd:
                row["kingdom"] = kd
            elif rz and rz.get("kingdom"):
                row["kingdom"] = str(rz["kingdom"])
            lista = [row]
        elif rz and rz.get("total") is not None and rz.get("kingdom"):
            lista = [
                {
                    "kingdom": str(rz["kingdom"]),
                    "total": int(rz["total"]),
                }
            ]

    # moons[] solo si no resumimos por reino
    moon_detail = [] if summarize_moons else moon_refs

    pool = goal_pool(
        n_moons_detail=len(moon_detail),
        n_lista=len(lista),
        n_by_kingdom=0,
    )
    record: dict = {
        "orden": orden,
        "goal": goal,
        **combined_fields_flat(goal, obj),
    }
    if regional:
        record.update(regional)
    if checkpoint_meta:
        record.update(checkpoint_meta)
    if pool:
        record["pool"] = pool

    if moon_refs and (moon_detail or summarize_moons):
        record["n_moons"] = len(moon_refs)
        odyssey_units = sum(int(m.get("odyssey_units") or 1) for m in moon_refs)
        if odyssey_units != len(moon_refs):
            record["n_odyssey_units"] = odyssey_units
    elif goal == "{{X}} Total Moons" and lista:
        totals = compute_in_scope_moon_totals(registry)
        record["n_moons"] = int(totals["moon_count"])
        record["n_odyssey_units"] = int(totals["odyssey_units"])

    if moon_detail:
        record["moons"] = moon_detail

    count_mode = goal_moon_count_mode(goal, obj, moonish=moonish)
    if count_mode:
        record["moon_count_mode"] = count_mode
    if lista:
        record["n_lista"] = lista_n(lista)
        enriched = enrich_lista_locations(lista)
        if goal == "{{X}} Unique Captures":
            record["lista"] = sorted(enriched, key=lambda x: int(x.get("id") or 0))
        elif rz and rz.get("groups"):
            # Grupos regionales: reino (historia) → id.
            record["lista"] = sorted(
                enriched,
                key=lambda x: (
                    kingdom_story_index(str(x.get("kingdom") or "")),
                    int(x.get("id") or 0),
                ),
            )
        else:
            record["lista"] = sort_lista_items(enriched)
    notas = goal_notas(goal, obj)
    if notas:
        record["notas"] = notas
    return record, moonish


def main() -> None:
    registry = build_matrix_moon_registry()
    for (k, m), e in list(registry.items()):
        e.setdefault("kingdom", k)
        e.setdefault("moon", m)

    # Orden = el de Combined (tras apply_progression_accessibility.sort_combined_json:
    # {{X}}+alfa + campo orden).
    combined_list = [
        o
        for o in json.loads(JSON_PATH.read_text(encoding="utf-8"))["objectives"]
        if not o.get("disabled")
    ]
    membership = collect_membership()

    n_moon = 0  # goals con moons[]
    n_lista = 0  # goals con lista[] (sin moons[])
    n_fixed = 0  # sin range o range de un solo valor
    n_normal = 0  # range con 2+ umbrales (progressive)
    goal_records: list[dict] = []
    for i, obj in enumerate(combined_list, 1):
        goal = str(obj["goal"])
        orden = int(obj["orden"]) if obj.get("orden") is not None else i
        entries = membership.get(goal, [])
        record, _moonish = build_goal_record(orden, goal, obj, entries, registry)
        goal_records.append(record)
        if record.get("moons"):
            n_moon += 1
        else:
            n_lista += 1
        rng = obj.get("range")
        if isinstance(rng, list) and len(rng) > 1:
            n_normal += 1
        else:
            n_fixed += 1

    goal_records.sort(key=lambda r: int(r.get("orden") or 0))

    totals = compute_in_scope_moon_totals(registry)
    refresh_in_scope_odyssey_meta()

    write_catalog_json(
        OUT_JSON,
        {
            "_definition": (
                "Referencia de cada goal Combined: goal + range/progression "
                "(+ individual_limit / progressive_ranges) + board_categories / "
                "line_categories + icons[]. "
                "Grupos → bingo_groups; tooltip en Combined. "
                "Pool contable: moons[] o lista[] "
                "(totales multi-reino / regionales / checkpoints / Multi-Moons "
                "en lista[]; ver catalog/regionales_zonas.json). "
                "Pares Sub-Area Level: goal_lists.lists.sub_area_levels. "
                "Algunas goals no son Moon Get pero el pool son lunas "
                "(Seeds Planted, Look at Hint-Arts, …) → moons[]. "
                "n_moons = lunas físicas; n_odyssey_units si multi×3. "
                "moon_count_mode: odyssey_units | physical_moons. "
                "moons[]: {kingdom,moon,name,tags}; lista[] con near CP/Odyssey "
                "o filas {kingdom,total|n_moons,…}. "
                "n_moon_goals = con moons[]; n_lista_goals = con lista[] "
                "(o sin moons). "
                "n_fixed_goals = sin range o range de 1 valor; "
                "n_normal_goals = range con 2+ umbrales. "
                "orden = Combined 1..N."
            ),
            "_note": "Regenerar con export_goals_referencia.py o regenerate_all.py.",
            "in_scope_moon_count": totals["moon_count"],
            "in_scope_odyssey_units": totals["odyssey_units"],
            "n_goals": len(goal_records),
            "n_moon_goals": n_moon,
            "n_lista_goals": n_lista,
            "n_fixed_goals": n_fixed,
            "n_normal_goals": n_normal,
            "goals": goal_records,
        },
    )

    print(
        f"Escrito: {OUT_JSON.relative_to(ROOT).as_posix()} "
        f"({len(goal_records)} goals, {OUT_JSON.stat().st_size // 1024} KiB)"
    )
    print(f"  moons[]: {n_moon}, lista[]: {n_lista}")
    print(f"  fijas: {n_fixed}, normales: {n_normal}")


if __name__ == "__main__":
    main()
