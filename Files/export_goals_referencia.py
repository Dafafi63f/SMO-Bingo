"""Export de referencia de goals Combined.

Salida: Catalog/goals_referencia.json (estructura tipo bingo_groups)

Uso: python export_goals_referencia.py
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from catalog_lib import (
    CATALOG_DIR,
    GROUP_MOON_TAG,
    JSON_PATH,
    KINGDOM_COLUMNS,
    KINGDOM_GOAL_PREFIXES,
    ROOT,
    STORY_ORDER,
    UMBRELLA_MOON_TAGS,
    build_matrix_moon_registry,
    compute_in_scope_moon_totals,
    enrich_moon_ref_odyssey,
    goal_moon_count_mode,
    group_moon_tag,
    group_moons,
    group_objective_refs,
    kingdom_story_index,
    load_bingo_groups,
    load_combined_objectives_by_goal,
    normalize_moon_tags,
    objective_ref_from_combined,
    refresh_in_scope_odyssey_meta,
    write_catalog_json,
)
from goal_list_lib import (
    CAPTURE_SOLO,
    build_goal_lista,
    checkpoint_goal_fields,
    enrich_lista_locations,
    goal_list_source,
    multi_moon_totals_lista,
    regional_goal_fields,
    regional_lista_for_goal,
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
    if goal.startswith(("Defeat ", "Win ")):
        return False
    if goal.startswith(("Purchase ", "Buy ", "Wear ")):
        return False
    if goal.startswith(("Activate ", "Look at ", "Talk to ")):
        return False
    if "freerunning" in gl:
        return False
    if "moon" in gl:
        return True
    return False

GOAL_TOTAL_MOONS = "{{X}} Total Moons"
GOAL_X_LOWER = "{{x}}"

_HYBRID_NO_MOON_GOALS = frozenset(
    {
        "{{X}} Talkatoos",
        "{{X}} Moon Rocks",
        GOAL_TOTAL_MOONS,
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


_SUB_AREA_SPECIFIC = frozenset({"hybrid_2d"})

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

_SPECIAL_SEED_KEYS = {("lake", 9), ("wooded", 33), ("seaside", 26)}

_KD_FILTER_GOAL_RE = re.compile(
    r"\b(Shop|Talkatoo|Moon Rock|Captain Toad|Hint Art|Outfit Door|"
    r"Warp-Painting|Story|Multi-Moon|Ground Pound|Seed)\b"
)

_FALLBACK_BOWSER_STATUE = [
    {"kingdom": "moon", "moon": 9, "name": "Under the Bowser Statue"}
]
_FALLBACK_SHEEP = [
    {"kingdom": "sand", "moon": 33, "name": "Herding Sheep in the Dunes"}
]
_FALLBACK_FESTIVAL = [
    {"kingdom": "metro", "moon": 36, "name": "Celebrating in the Streets!"}
]
_FALLBACK_FIRE_PIRANHA = [
    {"kingdom": "luncheon", "moon": 32, "name": "Light the Far-Off Lanterns"}
]
_FALLBACK_BANZAI = [
    {"kingdom": "moon", "moon": 11, "name": "Around the Barrier Wall"},
    {"kingdom": "moon", "moon": 13, "name": "Fly to the Treasure Chest and Back"},
]
_FALLBACK_PARABONES = [
    {"kingdom": "moon", "moon": 10, "name": "In a Hole in the Magma"}
]
_FALLBACK_SPECIAL_SEED = [
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


def _moon_name(m: dict) -> str:
    return str(m.get("name") or "").lower()


def _try_sub_area_pool(
    entries: list[tuple[str, list[dict]]],
    kd: str | None,
    gl: str,
) -> tuple[list[str], list[dict], str] | None:
    """Sub-Area: pool dedicado o grupo temático (hybrid_2d)."""
    if "sub-area" not in gl:
        return None
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
        if gid != "sub_area" or not ms:
            continue
        moons = list(ms)
        if kd:
            filtered = [m for m in moons if m.get("kingdom") == kd]
            if filtered:
                moons = filtered
        return ["sub_area"], moons, "sub_area pool"
    return None


def _prefer_shared_over_kingdom(
    chosen_gid: str,
    moons: list[dict],
    with_moons: list[tuple[str, list[dict]]],
    kingdom_ids: set[str],
) -> tuple[str, list[dict]]:
    if chosen_gid not in kingdom_ids:
        return chosen_gid, moons
    shared = [
        gm
        for gm in with_moons
        if gm[0] in _SHARED_POOLS or gm[0] not in kingdom_ids
    ]
    if not shared:
        return chosen_gid, moons
    shared.sort(key=lambda gm: (len(gm[1]), gm[0]))
    return shared[0]


def _pick_smallest_pool(
    goal: str, with_moons: list[tuple[str, list[dict]]], kingdom_ids: set[str]
) -> tuple[str, list[dict]]:
    with_moons = sorted(with_moons, key=lambda gm: (len(gm[1]), gm[0]))
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
    return _prefer_shared_over_kingdom(
        preferred[0], preferred[1], with_moons, kingdom_ids
    )


def _choose_pool_moons(
    goal: str,
    entries: list[tuple[str, list[dict]]],
    kingdom_ids: set[str],
) -> tuple[list[str], list[dict]]:
    """Elige group_ids + moons del membership (pool_only / concreto / shared)."""
    thematic = [(g, m) for g, m in entries if g not in kingdom_ids]
    pool = thematic if thematic else entries
    concrete = [(g, m) for g, m in pool if g not in _UMBRELLA]
    if concrete:
        pool = concrete

    with_moons = [(g, m) for g, m in pool if m]
    pool_only = [(g, m) for g, m in with_moons if _group_is_pool_only(g)]
    if pool_only:
        pool_only.sort(key=lambda gm: (-len(gm[1]), gm[0]))
        chosen_gid, moons = pool_only[0]
        return [chosen_gid], moons
    if not with_moons:
        return [g for g, _ in pool], []
    chosen_gid, moons = _pick_smallest_pool(goal, with_moons, kingdom_ids)
    return [chosen_gid], moons


def _maybe_filter_by_kingdom(
    goal: str,
    gl: str,
    kd: str | None,
    used: list[str],
    entries: list[tuple[str, list[dict]]],
    moons: list[dict],
) -> list[dict]:
    if not kd or "special seed" in gl:
        return moons
    needs = (
        any(g in _SHARED_POOLS for g in used)
        or any(g == kd for g, _ in entries)
        or bool(_KD_FILTER_GOAL_RE.search(goal))
    )
    if not needs:
        return moons
    filtered = [m for m in moons if m["kingdom"] == kd]
    return filtered if filtered else moons


def _kd_name_or_first(
    moons: list[dict], kd: str, *needles: str
) -> list[dict]:
    hit = [
        m
        for m in moons
        if m["kingdom"] == kd and any(n in _moon_name(m) for n in needles)
    ]
    return hit or [m for m in moons if m["kingdom"] == kd][:1]


def _name_any(moons: list[dict], *needles: str) -> list[dict]:
    return [m for m in moons if any(n in _moon_name(m) for n in needles)]


def _filter_festival(moons: list[dict]) -> list[dict]:
    hit = [
        m
        for m in moons
        if "celebrating" in _moon_name(m)
        or ("festival" in _moon_name(m) and "traditional" not in _moon_name(m))
    ]
    return hit or list(_FALLBACK_FESTIVAL)


def _filter_special_seed(moons: list[dict]) -> list[dict]:
    hit = [
        m
        for m in moons
        if (m.get("kingdom"), int(m.get("moon") or 0)) in _SPECIAL_SEED_KEYS
        or "spiky passage seed" in _moon_name(m)
        or "treasure made from coins" in _moon_name(m)
        or "ocean trench seed" in _moon_name(m)
    ]
    return hit or list(_FALLBACK_SPECIAL_SEED)


def _sheep_moons(registry: dict) -> list[dict]:
    hit = [
        {"kingdom": k, "moon": m, "name": e.get("name") or "?"}
        for (k, m), e in registry.items()
        if k == "sand" and "sheep" in str(e.get("name") or "").lower()
    ]
    return hit or list(_FALLBACK_SHEEP)


def _snow_boxer_moons(moons: list[dict]) -> list[dict]:
    return [
        m
        for m in moons
        if m.get("kingdom") == "snow" and int(m.get("moon") or 0) == 20
    ]


# (needle in gl, handler) — orden = prioridad de la cadena elif original.
# handler(moons, kd, registry) → (moons, used_override|None)
_SINGULAR_GL_HANDLERS: list[tuple[str, object]] = []


def _init_singular_handlers() -> None:
    """Tabla de filtros singulares (evita cadena elif larga)."""
    if _SINGULAR_GL_HANDLERS:
        return

    def shop(moons: list[dict], kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return _kd_name_or_first(moons, kd, "shopping"), None

    def toad(moons: list[dict], kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return _kd_name_or_first(moons, kd, "captain toad"), None

    def hint(moons: list[dict], kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return _kd_name_or_first(moons, kd, "art"), None

    def warp(moons: list[dict], kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return _kd_name_or_first(moons, kd, "secret path"), None

    def outfit(moons: list[dict], kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return [m for m in moons if m["kingdom"] == kd], None

    def multi(moons: list[dict], kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return [m for m in moons if m["kingdom"] == kd], None

    def statue(moons: list[dict], _kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return _name_any(moons, "bowser statue") or list(_FALLBACK_BOWSER_STATUE), None

    def sheep(_moons: list[dict], _kd: str, reg: dict) -> tuple[list[dict], list[str] | None]:
        return _sheep_moons(reg), ["fauna"]

    def festival(moons: list[dict], _kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return _filter_festival(moons), None

    def puzzle(moons: list[dict], _kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return _name_any(moons, "puzzle", "repair", "blowing and sliding"), None

    def fire_p(moons: list[dict], _kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return (
            _name_any(moons, "far-off lanterns", "magma swamp", "fire piranha")
            or list(_FALLBACK_FIRE_PIRANHA)
        ), None

    def banzai(moons: list[dict], _kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return (
            _name_any(
                moons, "around the barrier", "treasure chest and back", "banzai"
            )
            or list(_FALLBACK_BANZAI)
        ), None

    def parabones(moons: list[dict], _kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return (
            _name_any(moons, "hole in the magma", "parabones")
            or list(_FALLBACK_PARABONES)
        ), None

    def special(moons: list[dict], _kd: str, _reg: dict) -> tuple[list[dict], list[str] | None]:
        return _filter_special_seed(moons), None

    def city_hall(
        moons: list[dict], kd: str, _reg: dict
    ) -> tuple[list[dict], list[str] | None]:
        return _kd_name_or_first(moons, kd, "city hall"), None

    _SINGULAR_GL_HANDLERS.extend(
        [
            ("shop moon", shop),
            ("city hall", city_hall),
            ("captain toad", toad),
            ("hint art", hint),
            ("warp-painting", warp),
            ("warp painting", warp),
            ("outfit door", outfit),
            ("multi-moon", multi),
            ("bowser statue", statue),
            ("sheep", sheep),
            ("festival", festival),
            ("puzzle", puzzle),
            ("fire piranha", fire_p),
            ("banzai", banzai),
            ("parabones", parabones),
            ("special seed", special),
        ]
    )


def _apply_singular_goal_moons(
    goal: str,
    gl: str,
    kd: str | None,
    moons: list[dict],
    used: list[str],
    registry: dict,
) -> tuple[list[dict], list[str]]:
    """Filtros de goals singulares (shop / toad / statue / …)."""
    if goal == "Snow Boxer Shorts Moon":
        return _snow_boxer_moons(moons), used
    if GOAL_X_LOWER in gl or not moons or not kd:
        return moons, used

    _init_singular_handlers()
    for needle, handler in _SINGULAR_GL_HANDLERS:
        if needle not in gl:
            continue
        new_moons, used_override = handler(moons, kd, registry)
        return new_moons, used_override if used_override is not None else used
    return moons, used


def _filter_standard_seed_pots(moons: list[dict]) -> list[dict]:
    return [
        m
        for m in moons
        if (m.get("kingdom"), int(m.get("moon") or 0)) in _STANDARD_SEED_POTS
    ]


def _volleyball_moons(entries: list[tuple[str, list[dict]]]) -> list[dict]:
    return [
        m
        for _g, ms in entries
        for m in ms
        if "volleyball" in _moon_name(m)
    ]


def _slots_moons(entries: list[tuple[str, list[dict]]]) -> list[dict]:
    return [
        m
        for _g, ms in entries
        for m in ms
        if "slots" in _moon_name(m)
    ]


def _apply_seed_and_minigame_filters(
    gl: str,
    moons: list[dict],
    used: list[str],
    entries: list[tuple[str, list[dict]]],
) -> tuple[list[dict], list[str]]:
    is_ntt_seed = "seed moon (no time travel)" in gl
    is_seeds_planted = "seeds planted" in gl and "lake seed" not in gl
    if is_ntt_seed or is_seeds_planted:
        moons = _filter_standard_seed_pots(moons)
    elif "golden turnip" in gl:
        moons = _name_any(moons, "golden turnip", "turnip recipe")

    if "volleyball" in gl:
        return _volleyball_moons(entries), ["minigame/volleyball"]
    if "slots moon" in gl:
        return _slots_moons(entries), ["slots"]
    return moons, used


def _dedup_sort_moons(moons: list[dict]) -> list[dict]:
    """Deduplica conservando el orden del pool (SPEC / bingo_groups)."""
    out: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for raw in moons:
        if "kingdom" not in raw or "moon" not in raw:
            continue
        key = (str(raw["kingdom"]), int(raw["moon"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
    return out


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

    early = _try_sub_area_pool(entries, kd, gl)
    if early is not None:
        return early

    used, moons = _choose_pool_moons(goal, entries, kingdom_ids)
    moons = _maybe_filter_by_kingdom(goal, gl, kd, used, entries, moons)
    moons, used = _apply_singular_goal_moons(goal, gl, kd, moons, used, registry)
    moons, used = _apply_seed_and_minigame_filters(gl, moons, used, entries)
    return used, _dedup_sort_moons(moons), ""


def needs_lista(goal: str, moonish: bool, n_moons: int) -> bool:
    if n_moons and goal not in _HYBRID_NO_MOON_GOALS:
        return False
    if not moonish:
        return True
    if goal in _HYBRID_NO_MOON_GOALS and goal != GOAL_TOTAL_MOONS:
        return True
    return n_moons == 0


def normalize_moon_ref(raw: dict, registry: dict) -> dict:
    from catalog_lib import catalog_kingdom

    k, m = catalog_kingdom(raw["kingdom"]), int(raw["moon"])
    entry = registry.get((k, m))
    name = (entry or {}).get("name") or raw.get("name") or "?"
    out: dict = {"kingdom": k, "moon": m, "name": name}
    if entry is None:
        out["out_of_scope"] = True
    else:
        out["disponibilidad"] = str(entry.get("availability") or "base")
    out = enrich_moon_ref_odyssey(out, registry)
    return out


def goal_notas(goal: str, obj: dict) -> list[str]:
    tip = obj.get("tooltip") or ""
    notas: list[str] = []
    # Total Multi-Moons: físico; no heredar nota Odyssey del tooltip de Total Moons.
    if "Total Multi-Moon" in goal:
        notas.append(
            "{{X}} = nº de Multi-Moons físicas (Moon Get), no unidades Odyssey ×3."
        )
    elif "Multi-Moons count as 3" in tip:
        notas.append(
            "Multi-Moons cuentan como 3 hacia el total. "
            "{{X}} = unidades depositadas en la Odyssey, no entradas de la lista."
        )
    if "Multi-Moons do not count" in tip and "without Multi-Moons" not in tip:
        notas.append("Multi-Moons no cuentan.")
    if "Metro Night" in goal:
        notas.append(
            "Metro noche: base (#8/#9/#10/#27/#34) + #51 Secret Path. "
            "Individuales Night → lost/m; Metro Warp-Painting (misma #51) → lost/m."
        )
    if "Mushroom Warp-Painting" in goal:
        notas.append(
            "mushroom#39 (Secret Path); en lunas-objetivos como luncheon#50. "
            "Individuales → luncheon/l."
        )
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
    if goal == "{{X}} Unique Captures" or goal in CAPTURE_SOLO:
        notas.append(
            "Sin lista[] aquí: catálogo de capturas en capturas_lunas.json "
            "(CAPTURE_LIST)."
        )
    return notas


def combined_fields_flat(goal: str, obj: dict) -> dict:
    """range/progression/limits/weighting + board/line/icons/tooltip."""
    ref = objective_ref_from_combined(goal, obj)
    ref.pop("goal", None)
    board = list(obj.get("board_categories") or [])
    line = list(obj.get("line_categories") or [])
    icons = list(obj.get("icons") or [])
    tip = obj.get("tooltip")
    if board:
        ref["board_categories"] = board
    if line:
        ref["line_categories"] = line
    if icons:
        ref["icons"] = icons
    if tip:
        ref["tooltip"] = str(tip)
    return ref


_KINGDOM_LIKE_TAGS = frozenset(STORY_ORDER) | {"mushroom", "cloud", GROUP_MOON_TAG}
_groups_by_id_cache: dict[str, dict] | None = None


def _groups_by_id() -> dict[str, dict]:
    global _groups_by_id_cache
    if _groups_by_id_cache is None:
        _groups_by_id_cache = {
            str(g["id"]): g for g in load_bingo_groups() if g.get("id")
        }
    return _groups_by_id_cache


def _moon_pool_tags(
    moon_refs: list[dict], registry: dict
) -> list[set[str]]:
    out: list[set[str]] = []
    for m in moon_refs:
        kingdom = str(m.get("kingdom") or "")
        try:
            moon = int(m["moon"])
        except (KeyError, TypeError, ValueError):
            continue
        entry = registry.get((kingdom, moon))
        if not entry:
            continue
        tags = normalize_moon_tags(
            entry.get("tags") or [], kingdom=kingdom, moon=moon
        )
        if tags:
            out.append(set(tags))
    return out


def _thematic_tags(tags: set[str]) -> set[str]:
    return {t for t in tags if t not in _KINGDOM_LIKE_TAGS}


def _group_tag_hints(entries: list[tuple[str, list[dict]]]) -> list[str]:
    """moon_tag / tag de los bingo_groups de la goal (orden de membership)."""
    hints: list[str] = []
    groups = _groups_by_id()
    for gid, _ in entries:
        g = groups.get(gid)
        if not g:
            continue
        particular = g.get("moon_tag") or g.get("tag")
        if particular:
            hints.append(str(particular))
            continue
        if g.get("apply_moon_tag") is False:
            # Pool dedicado / paraguas: la tag de goal es el id del grupo.
            hints.append(str(gid))
            continue
        hints.append(group_moon_tag(g))
    return hints


def resolve_goal_tags(
    moon_refs: list[dict],
    entries: list[tuple[str, list[dict]]],
    registry: dict,
) -> list[str]:
    """Tags comunes del pool de lunas (solo goals pool=moons).

    Intersección temática de tags de lunas; hints de grupo primero si encajan.
    Vacío si no hay tags comunes. No aplica a pool lista.
    """
    hints = [t for t in _group_tag_hints(entries) if t]
    thematic_hints = [t for t in hints if t not in _KINGDOM_LIKE_TAGS]

    thematic: set[str] = set()
    tag_sets = _moon_pool_tags(moon_refs, registry)
    if tag_sets:
        thematic = _thematic_tags(set.intersection(*tag_sets))

    ordered: list[str] = []
    seen: set[str] = set()
    for t in thematic_hints:
        if t in thematic and t not in seen:
            ordered.append(t)
            seen.add(t)
    for t in sorted(thematic, key=lambda x: (x in UMBRELLA_MOON_TAGS, len(x), x)):
        if t not in seen:
            ordered.append(t)
            seen.add(t)
    if ordered:
        return ordered
    uniq = list(dict.fromkeys(thematic_hints))
    if uniq:
        return uniq
    return list(dict.fromkeys(t for t in hints if t in STORY_ORDER))


# Keys allowed on kingdom-aggregate rows (lista → by_kingdom).
_KINGDOM_AGG_KEYS = frozenset(
    {"kingdom", "total", "painting", "progression", "zone", "n_groups"}
)

# Totales / umbrellas multi-reino: siempre resumen by_kingdom (sin moons[]).
_ALWAYS_BY_KINGDOM_MOON_GOALS = frozenset(
    {
        "{{X}} Sub-Area Moons",
        GOAL_TOTAL_MOONS,
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


def _bucket_to_kingdom_row(k: str, row: dict) -> dict:
    entry: dict = {"kingdom": k, "n_moons": row["n_moons"]}
    if row["n_odyssey_units"] != row["n_moons"]:
        entry["n_odyssey_units"] = row["n_odyssey_units"]
    return entry


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
        out.append(_bucket_to_kingdom_row(k, buckets[k]))
    for k, row in sorted(buckets.items(), key=lambda kv: kingdom_story_index(kv[0])):
        if k in seen:
            continue
        out.append(_bucket_to_kingdom_row(k, row))
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
        entry: dict = {"kingdom": k, "n_moons": n_m}
        if n_u != n_m:
            entry["n_odyssey_units"] = n_u
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


def _want_kingdom_lista(
    want_lista: bool,
    regional: dict | None,
    checkpoint_meta: dict | None,
    gl: str,
) -> bool:
    if not want_lista:
        return False
    if regional is None or checkpoint_meta is not None:
        return True
    return any(
        needle in gl
        for needle in ("total regional", "large kingdom", "small kingdom")
    )


def _regional_total_lista(
    regional: dict, kd: str | None, _lista: list[dict] | None
) -> list[dict]:
    row: dict = {"total": int(regional["regional_total"])}
    if kd:
        row["kingdom"] = kd
    return [row]


def _lista_from_regional_or_totals(
    *,
    goal: str,
    moon_refs: list[dict],
    kd: str | None,
    all_multi: bool,
    registry: dict,
) -> tuple[list[dict], bool] | None:
    """Early lista paths (regionales / totals / multi). None = seguir."""
    regional_lista = regional_lista_for_goal(goal)
    if regional_lista is not None:
        return regional_lista, False
    if goal == GOAL_TOTAL_MOONS:
        return odyssey_units_by_kingdom_rows(registry), True
    if should_summarize_moons_by_kingdom(goal, moon_refs, kd):
        return by_kingdom_from_moons(moon_refs), True
    if all_multi:
        return multi_moon_totals_lista(), False
    return None


def _build_goal_lista(
    *,
    goal: str,
    obj: dict,
    moonish: bool,
    moon_refs: list[dict],
    kd: str | None,
    regional: dict | None,
    checkpoint_meta: dict | None,
    all_multi: bool,
    registry: dict,
) -> tuple[list[dict], bool]:
    """Construye lista[] y si moons[] se resume por reino."""
    early = _lista_from_regional_or_totals(
        goal=goal,
        moon_refs=moon_refs,
        kd=kd,
        all_multi=all_multi,
        registry=registry,
    )
    if early is not None:
        return early

    want_lista = needs_lista(goal, moonish, len(moon_refs))
    gl = goal.lower()
    if _want_kingdom_lista(want_lista, regional, checkpoint_meta, gl):
        return build_goal_lista(goal, obj, kingdom=kd), False
    if regional and regional.get("regional_total") is not None:
        return _regional_total_lista(regional, kd, None), False
    return [], False


def _moon_count_meta(
    *,
    goal: str,
    moon_refs: list[dict],
    moon_detail: list[dict],
    summarize_moons: bool,
    lista: list[dict],
    registry: dict,
) -> dict:
    """Conteos físicos/Odyssey para pool_summary o lista_summary (no top-level)."""
    meta: dict = {}
    if moon_refs and (moon_detail or summarize_moons):
        meta["n_moons"] = len(moon_refs)
        odyssey_units = sum(int(m.get("odyssey_units") or 1) for m in moon_refs)
        if odyssey_units != len(moon_refs):
            meta["n_odyssey_units"] = odyssey_units
    elif goal == GOAL_TOTAL_MOONS and lista:
        totals = compute_in_scope_moon_totals(registry)
        meta["n_moons"] = int(totals["moon_count"])
        meta["n_odyssey_units"] = int(totals["odyssey_units"])
    return meta


def _insert_after_key(
    summary: dict, after_key: str, new_key: str, new_value: object
) -> dict:
    """Inserta new_key justo tras after_key (omite duplicados de new_key)."""
    out: dict = {}
    placed = False
    for key, value in summary.items():
        if key == new_key:
            continue
        out[key] = value
        if key == after_key:
            out[new_key] = new_value
            placed = True
    if not placed:
        out[new_key] = new_value
    return out


def _insert_after_n_moons(summary: dict, n_odyssey_units: int) -> dict:
    """n_odyssey_units justo tras n_moons (solo si hay multilunas en el pool)."""
    return _insert_after_key(summary, "n_moons", "n_odyssey_units", n_odyssey_units)


def attach_referencia_summaries(
    record: dict,
    *,
    goal: str,
    entries: list[tuple[str, list[dict]]],
    moon_detail: list[dict],
    lista: list[dict],
    moon_meta: dict | None = None,
    regional: dict | None = None,
) -> None:
    """Resúmenes cross-file; detalle completo sigue en moons[]/lista[]/otros JSON."""
    moon_meta = moon_meta or {}
    if entries:
        record["bingo_groups"] = sorted({gid for gid, _ in entries})
    src = goal_list_source(goal)
    if src:
        record["lista_source"] = src
    n_ody = moon_meta.get("n_odyssey_units")
    if moon_detail:
        summary = summarize_moon_pool(moon_detail)
        if n_ody:
            summary = _insert_after_n_moons(summary, int(n_ody))
        record["pool_summary"] = summary
    elif moon_meta.get("n_moons"):
        summary = {"n_moons": moon_meta["n_moons"]}
        if n_ody:
            summary["n_odyssey_units"] = int(n_ody)
        record["pool_summary"] = summary
    if lista:
        regional_total = (
            int(regional["regional_total"])
            if regional and regional.get("regional_total") is not None
            else None
        )
        summary = summarize_lista_pool(lista, regional_total=regional_total)
        if moon_meta and not moon_detail:
            # Conteos juntos al inicio: n_items → n_moons → n_odyssey → by_*
            if "n_moons" in moon_meta:
                summary = _insert_after_key(
                    summary, "n_items", "n_moons", moon_meta["n_moons"]
                )
            if n_ody:
                summary = _insert_after_n_moons(summary, int(n_ody))
        record["lista_summary"] = summary


def _sorted_lista_for_goal(goal: str, lista: list[dict]) -> list[dict]:
    enriched = enrich_lista_locations(lista)
    if goal == "{{X}} Unique Captures":
        return sorted(enriched, key=lambda x: int(x.get("id") or 0))
    if regional_lista_for_goal(goal) is not None and lista and "id" in lista[0]:
        return sorted(
            enriched,
            key=lambda x: (
                kingdom_story_index(str(x.get("kingdom") or "")),
                int(x.get("id") or 0),
            ),
        )
    return sort_lista_items(enriched)


def _count_preserve_list_order(items: list[dict], key_fn) -> dict[str, int]:
    """Cuenta por clave conservando el orden de primera aparición en la lista."""
    counts: dict[str, int] = {}
    for item in items:
        key = key_fn(item)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


# Mismo orden que catalog_lib._AVAILABILITY_PRIORITY (progresión de juego).
_DISPONIBILIDAD_ORDER = {"base": 0, "mid_story": 1, "world_peace": 2, "revisit": 3}


def _disp_label(item: dict) -> str:
    disp = item.get("disponibilidad")
    if isinstance(disp, list):
        return "+".join(str(x) for x in disp)
    return str(disp or "")


def _sort_by_disponibilidad(counts: dict[str, int]) -> dict[str, int]:
    def sort_key(label: str) -> tuple:
        if "+" in label:
            parts = label.split("+")
            return (min(_DISPONIBILIDAD_ORDER.get(p, 99) for p in parts), label)
        return (_DISPONIBILIDAD_ORDER.get(label, 99), label)

    return {k: counts[k] for k in sorted(counts, key=sort_key)}


def summarize_moon_pool(moons: list[dict]) -> dict:
    by_kingdom = _count_preserve_list_order(
        moons, lambda m: str(m.get("kingdom") or "")
    )
    by_disp = _sort_by_disponibilidad(
        _count_preserve_list_order(moons, _disp_label)
    )
    out: dict = {"n_moons": len(moons)}
    if by_kingdom:
        out["by_kingdom"] = by_kingdom
    if by_disp:
        out["by_disponibilidad"] = by_disp
    return out


def summarize_lista_pool(
    lista: list[dict], *, regional_total: int | None = None
) -> dict:
    by_kingdom = _count_preserve_list_order(
        lista, lambda item: str(item.get("kingdom") or "")
    )
    by_disp = _sort_by_disponibilidad(
        _count_preserve_list_order(lista, _disp_label)
    )
    out: dict = {"n_items": len(lista)}
    if regional_total is not None:
        out["regional_total"] = regional_total
    if by_kingdom:
        out["by_kingdom"] = by_kingdom
    if by_disp:
        out["by_disponibilidad"] = by_disp
    return out


# Orden fijo por goal: campos relacionados juntos; moons[]/lista[] al final.
_GOAL_RECORD_KEY_ORDER = (
    # Identidad
    "orden",
    "goal",
    # Combined / Rush
    "range",
    "progression",
    "individual_limit",
    "progressive_ranges",
    # Tablero / presentación
    "board_categories",
    "line_categories",
    "icons",
    "weighting",
    "tooltip",
    "tag",
    "bingo_groups",
    # Metadatos de goal (checkpoints, …)
    "checkpoint_total",
    # Notas, umbrales expandidos, tipo de pool
    "notas",
    "individuales",
    "pool",
    # Moon pool: resumen → detalle (n_moons solo en pool_summary)
    "moon_count_mode",
    "pool_summary",
    "moons",
    # Lista pool: fuente → resumen → detalle
    "lista_source",
    "lista_summary",
    "lista",
)
_GOAL_RECORD_KEY_SET = frozenset(_GOAL_RECORD_KEY_ORDER)


def finalize_goal_record_order(record: dict) -> dict:
    """Campos agrupados por bloque; moons[] y lista[] siempre al final."""
    rec = dict(record)
    rec.pop("n_moons", None)
    rec.pop("n_odyssey_units", None)
    rec.pop("regional_total", None)
    rec.pop("n_lista", None)
    ordered: dict = {}
    for key in _GOAL_RECORD_KEY_ORDER:
        if key == "notas":
            for extra in sorted(k for k in rec if k not in _GOAL_RECORD_KEY_SET):
                ordered[extra] = rec.pop(extra)
        if key in rec:
            ordered[key] = rec.pop(key)
    if rec:
        ordered.update(rec)
    return ordered


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
    all_multi = goal.startswith("All Multi-Moons")
    if not all_multi and (moonish or goal in _MOONS_POOL_NON_GET) and entries:
        _, moons, _note = pick_moons_for_goal(goal, entries, board, registry)

    moon_refs = [normalize_moon_ref(m, registry) for m in moons]
    kd = goal_kingdom(goal, board)
    regional = regional_goal_fields(goal, kd)
    checkpoint_meta = checkpoint_goal_fields(goal)

    lista, summarize_moons = _build_goal_lista(
        goal=goal,
        obj=obj,
        moonish=moonish,
        moon_refs=moon_refs,
        kd=kd,
        regional=regional,
        checkpoint_meta=checkpoint_meta,
        all_multi=all_multi,
        registry=registry,
    )
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
    # tag[] = tags de lunas (intersección / moon_tag); solo pool moons, no lista.
    if pool == "moons":
        tags = resolve_goal_tags(moon_refs, entries, registry)
        if tags:
            record["tag"] = tags
    if checkpoint_meta:
        record.update(checkpoint_meta)

    moon_meta = _moon_count_meta(
        goal=goal,
        moon_refs=moon_refs,
        moon_detail=moon_detail,
        summarize_moons=summarize_moons,
        lista=lista,
        registry=registry,
    )
    count_mode = goal_moon_count_mode(goal, obj, moonish=moonish)
    if count_mode:
        record["moon_count_mode"] = count_mode
    notas = goal_notas(goal, obj)
    if notas:
        record["notas"] = notas
    attach_referencia_summaries(
        record,
        goal=goal,
        entries=entries,
        moon_detail=moon_detail,
        lista=lista,
        moon_meta=moon_meta,
        regional=regional,
    )
    if pool:
        record["pool"] = pool
    if moon_detail:
        record["moons"] = moon_detail
    if lista:
        record["lista"] = _sorted_lista_for_goal(goal, lista)
    return finalize_goal_record_order(record), moonish


def main() -> None:
    global _groups_by_id_cache
    _groups_by_id_cache = None
    registry = build_matrix_moon_registry()
    for (k, m), e in registry.items():
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
                "Hub por goal Combined. Completo aquí: range/progression/weighting, "
                "board/line_categories, icons, tooltip; tag[] solo si pool=moons "
                "(tags comunes del pool de lunas; suele incluir moon_tag del grupo). "
                "Pool: moons[] o lista[] (no ambos). "
                "Resúmenes (detalle en otro JSON): bingo_groups→bingo_groups.json; "
                "pool_summary/lista_summary (n_moons, n_odyssey_units si hay "
                "multi, by_kingdom, …); "
                "lista_source→goal_lists.json; "
                "individuales[]→goals_individuales.json (umbrales expandidos). "
                "Pares Sub-Area: Files/sub_area_levels_data.py. "
                "Regionales: lists.regionals en goal_lists.json "
                "(+ filtros zone vía zonas_reino / sub_area/eight_bit). "
                "Conteos físicos/Odyssey/regional_total/n_items solo en pool_summary "
                "o lista_summary (sin n_moons/n_lista/regional_total top-level). "
                "moon_count_mode: odyssey_units | physical_moons. "
                "orden = Combined 1..N. weighting siempre explícito "
                "(100 si Combined lo omite)."
            ),
            "_hub": {
                "full": [
                    "goal",
                    "range",
                    "progression",
                    "weighting",
                    "board_categories",
                    "line_categories",
                    "icons",
                    "tooltip",
                    "tag[] (solo pool=moons)",
                    "moons[]",
                    "lista[]",
                    "notas",
                ],
                "summaries": {
                    "bingo_groups": "Catalog/bingo_groups.json",
                    "pool_summary": "conteos desde moons[]",
                    "lista_summary": "conteos desde lista[]",
                    "lista_source": "Catalog/goal_lists.json → lists.*",
                    "individuales": "Catalog/goals_individuales.json (post enrich)",
                },
            },
            "_note": (
                "Regenerar: export_goals_referencia.py + enrich_goals_referencia.py "
                "o regenerate_all.py."
            ),
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
