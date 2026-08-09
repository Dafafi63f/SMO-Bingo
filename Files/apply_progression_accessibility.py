"""Ajusta progression/range del Combined para Rush/Ascend/Summit.

Lockout schema: progression = zonas unicas e/m/l/n (sin repetidos).
No se alinea a len(range); progressive_ranges escala los umbrales
dentro de esas zonas solo si hay 2+ progression (si solo hay una zona,
los valores de range son equiprobables).

Con lunas (grupo bingo mas especifico):
  Cada luna aporta la zona de su reino. Un solo reino → progression de frontera
    (Sand/Lake e+m; Lost/Metro m+l; Seaside/Luncheon l+n; interiores 1 zona).
  Multireino → zonas naturales cubiertas (sin forzar mas).

len(range) NO determina cuantas progression hay: cuenta las zonas e/m/l/n
con ≥1 reino en el pool de la goal. Ej.: Broodal Fights range [x,y,z] pero
las 4 zonas → progression e,m,l,n. Activate Levers solo e+m → [e,m]
aunque range tenga 4 umbrales (progressive_ranges reparte umbrales en esas zonas).

Regla de producto (totales / moontype multi-reino):
  Totales y agregados (Total Moons, All … Kingdoms, Large/Small Regional, …)
  → siempre e,m,l,n.
  Moontype (u otros pools) con reinos en las 4 zonas naturales → e,m,l,n,
  independiente de len(range), salvo si el min(range) no cabe en Early
  (Blocks / Outfit Door / Hint-Arts / Warp-Painting → m,l,n). Si solo cubren
  2–3 zonas, progression = esas.
  Prefijo de reino / puente frontera → 1–2 zonas (no forzar emln).
  Overrides puntuales (Tourist, Minigame, Seeds, Warp-Painting, Lake Hint Art, …) ganan.

Goals fijas (range de 1 valor) + puente 2+ zonas son validas e intencionales;
no colapsar progression. Restricciones lockout + patron puente:
  Bingos/README.md («Restricciones al crear una goal» / «Range vs progression»).

Goals con lunas, 2 zonas naturales y 2+ reinos: range = acumulado por reino
(orden historia), un umbral por reino.
  Dorrie (lake×1 + seaside×2): [1, 2, 3]
  Tres reinos (1+1+1) en 2 zonas: [1, 2, 3]

Sin lunas: reinos por lista curada / nombre / board / captura → misma logica.

Usage:
  python apply_progression_accessibility.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from catalog_lib import (
    GLOBAL_AGGREGATE_GOALS,
    JSON_PATH,
    KINGDOM_COLUMNS,
    KINGDOM_GOAL_PREFIXES,
    ZONE_ORDER,
    clear_runtime_caches,
    group_moons,
    load_bingo_groups,
    load_combined_objectives_by_goal,
    load_meta,
    normalize_bingo_groups_file,
    parse_kingdom_prefixed_goal,
    stamp_combined_filename_today,
)
from export_capturas_lunas import CAPTURE_LIST

FULL_ZONE_PROGRESSION = list(ZONE_ORDER)  # e, m, l, n

GOAL_CAPPY_MOONS = "{{X}} Cappy Moons"
GOAL_MARIO_MOONS = "{{X}} Mario Moons"
GOAL_TOURIST_MOONS = "{{X}} Tourist Moon[[s]]"

GLOBAL_FROM_MID: frozenset[str] = frozenset(
    {
        "{{X}} Total Moons",
        "{{X}} Boss Fights",
        "{{X}} Kingdom Boss Fight[[s]]",
    }
)

GLOBAL_FROM_CAP: frozenset[str] = frozenset(
    {
        "{{X}} Sub-Area Moons",
        "{{X}} Ground Pound Moons",
        "{{X}} Treasure Chest Moons",
        "{{X}} Timer Challenge Moons",
        "{{X}} Music Note Moons",
        "{{X}} Moon Shard Moons",
        GOAL_CAPPY_MOONS,
        GOAL_MARIO_MOONS,
        "{{X}} Capture Moons",
        "{{X}} Captain Toad Moons",
        "{{X}} Shop Moons",
        "{{X}} Talkatoos",
        "{{X}} Moon Rocks",
        "{{X}} Total Regional Coins",
        "{{X}} Total Checkpoints",
        "{{X}} Total Story Moons",
        "{{X}} Total Multi-Moons",
        "{{X}} Unique Life Up Hearts",
        "{{X}} Souvenirs",
        "{{X}} Stickers",
        "{{X}} NPC Moons",
        GOAL_TOURIST_MOONS,
        "{{X}} Minigame Moons",
        "{{X}} Warp-Painting Moons",
        "{{X}} Outfit Door Moons",
        "{{X}} Seed Moon (No Time Travel)",
        "{{X}} Seeds Planted",
        "{{X}} Broodal Fights",
        "{{X}} Unique Captures",
        "Capture {{X}} Binoculars",
        "Look at {{X}} Hint-Arts",
        "Purchase {{X}} Costume Sets",
        "Purchase {{X}} Hats",
        "All Checkpoints in {{X}} Kingdoms",
        "All Multi-Moons in {{X}} Kingdoms",
        "All Regional Coins in {{X}} Large Kingdom",
        "All Regional Coins in {{X}} Small Kingdom[[s]]",
    }
)

# Ranges curados: no recalcular con acumulado por reino (pools grandes).
RANGE_PRESERVE: dict[str, list[int]] = {
    GOAL_TOURIST_MOONS: [1, 2, 3, 4],
    "{{X}} Bullet Bill Moons": [2, 4],
    "{{X}} Cheep Cheep Moons": [2, 4, 6],
    "{{X}} Critter Moon[[s]]": [1, 2, 3],
    "{{X}} Dorrie Moon[[s]]": [1, 2, 3],
    "{{X}} Rabbit Chase Moon[[s]]": [1, 3, 5],
    "{{X}} Rocket Flower Moons": [2, 4, 6],
    "{{X}} Sand Bird Moons": [2, 3],
    "{{X}} Sand Jaxi Moons": [2, 4, 6],
    "{{X}} Sand Oasis Moons": [3, 6],
    "{{X}} Seaside Gushen Moons": [2, 4, 6],
    "{{X}} Seaside Komboo Moons": [2, 4],
    "{{X}} Fire Bro Moon[[s]]": [1, 2],
    "{{X}} Hammer Bro Moons": [2, 3],
    "{{X}} Luncheon Fire Piranha Plant Moons": [2, 3],
    "{{X}} Luncheon Lantern Moon[[s]]": [1, 2, 3],
    "{{X}} Luncheon Lava Bubble Moons": [2, 3],
    GOAL_MARIO_MOONS: [3, 6, 9, 12],
    GOAL_CAPPY_MOONS: [3, 6, 9, 12],
    "{{X}} Bowser's Pokio Moons": [2, 4],
    "{{X}} Shiny Rock Moon[[s]]": [1, 2, 3, 4],
    "{{X}} Spark Pylon Moons": [2, 4],
    "{{X}} Moon Banzai Bill Moon[[s]]": [1, 2],
    "{{X}} Bowser's Stairface Ogre Moon[[s]]": [1, 2, 3],
    "{{X}} Lurker/Rumble Moon[[s]]": [1, 2, 3, 4],
    "{{X}} Sand Ground Pound Moons": [2, 4, 6],
    "{{X}} Sherm Moons": [2, 4, 6],
    "{{X}} Wooded Uproot Moons": [4, 6, 8],
    "{{X}} Snow Shiveria Moons": [4, 8, 12],
    "{{X}} Snow Overworld Moons": [4, 8, 12],
}

PROGRESSION_OVERRIDES: dict[str, list[str]] = {
    # Estaciones: cap1 cascade1 sand3 lake1 wooded2 lost1 metro1 snow0
    # seaside≥3 luncheon1 bowser1 moon1 → techos 5/9/13/16 → rango [3,5,7,9]
    "Capture {{X}} Binoculars": ["e", "m", "l", "n"],
    # Warp paintings: progression = reino de ENTRADA (outbound), no destino.
    # Cadena fija: Sand→Metro, Lake/Wooded→Sand|Luncheon, Snow/Seaside→Cascade,
    # Metro|Snow/Seaside→Lake|Wooded, Luncheon→Mushroom.
    # Metro WP: entra desde Sand, pero requiere Night Sand → Mid (no Early).
    "Metro Warp-Painting Moon": ["m"],
    "Sand Warp-Painting Moon": ["m"],  # entra desde Lake/Wooded (1º fork)
    "Luncheon Warp-Painting Moon": ["m"],  # entra desde Lake/Wooded (2º)
    "Cascade Warp-Painting Moon": ["l"],  # entra desde Snow/Seaside
    "Lake Warp-Painting Moon": ["l"],  # entra desde Metro o Snow/Seaside
    "Wooded Warp-Painting Moon": ["l"],  # entra desde Metro o Snow/Seaside
    "Mushroom Warp-Painting Moon": ["n"],  # entra desde Luncheon
    # Techos por entrada: e=1 m=3 l=6 n=7 → rango [2,3,4] desde Mid (sin Early:
    # primer warp usable en cadena Lake/Wooded → Sand|Luncheon).
    "{{X}} Warp-Painting Moons": ["m", "l", "n"],
    # Multireino a pie: todas las zonas aunque falten lunas en alguna (puente Rush).
    GOAL_MARIO_MOONS: ["e", "m", "l", "n"],
    GOAL_CAPPY_MOONS: ["e", "m", "l", "n"],
    # Cadena turista: 1ª luna tras Metro WP (late); Moon cierra en full.
    GOAL_TOURIST_MOONS: ["l", "n"],
    # key: sand(e) + lost(l) + metro(l) + luncheon×2(n)
    "{{X}} Key Moon[[s]]": ["e", "m", "l", "n"],
    # Mirar Hint-Arts: primeras en Lake/Wooded → sin Early (min 2).
    "Look at {{X}} Hint-Arts": ["m", "l", "n"],
    # Hint Art de Lake: zona natural Mid (no puente e,m del reino).
    "Lake Hint Art Moon": ["m"],
    # Seeds: NTT = plaza Sand (fijo 1); solo Early.
    # Seeds Planted: sin Endgame (no backtracking de semillas).
    "{{X}} Seed Moon (No Time Travel)": ["e"],
    "{{X}} Seeds Planted": ["e", "m", "l"],
    # Pixels 8-bit (no Power Moons). Cat Mario/Peach: 2/reino excl. Cloud/Ruined
    # → techos e/m/l/n = 6/12/18/24 → rango [3,6,9,12].
    # Pixel Luigis: coin Hint Art; sin Cloud/Snow/Ruined Toad/Mushroom → 15 total.
    "{{X}} Pixel Cat Marios/Peaches": ["e", "m", "l", "n"],
    "{{X}} Pixel Luigis": ["e", "m", "l", "n"],
    # Story events (no Moon Get de story_moon group).
    "Correct Wooded Sphynx Question": ["m"],
    "Defeat Bowser in Cloud Kingdom": ["m"],
    "Defeat Madame Broode in Moon Kingdom": ["n"],
    "Defeat Ruined Dragon": ["n"],
    # Totales / pools multi-reino que tocan las 4 zonas → siempre emln
    # (da igual len(range)); weighting ~55. No restringir a e,m.
    "All Regional Coins in {{X}} Small Kingdom[[s]]": ["e", "m", "l", "n"],
    # Lake + Seaside; disponible Mid→Endgame (Seaside empuja a n).
    "{{X}} Cheep Cheep Moons": ["m", "l", "n"],
    # Wooded + Lost + Seaside → Mid→Endgame.
    "{{X}} Glydon Moon[[s]]": ["m", "l", "n"],
    "{{X}} Mini Rocket Moons": ["e", "m", "l", "n"],
    # Cascade + Wooded + Moon.
    "{{X}} Shiny Rock Moon[[s]]": ["e", "m", "n"],
    "Activate {{X}} Ground-Pound Switches": ["m", "l", "n"],
    # Minigame: sand×1; metro abre Late. m como puente Mid→Late (no emln:
    # no hay reino Mid natural en el pool).
    "{{X}} Minigame Moons": ["m", "l", "n"],
    # Blocks / Outfit total: hay Sand en Early, pero el min(range) solo se
    # cubre desde Mid (Blocks ≥3 con Wooded; Outfit ≥2 con Lake/Wooded).
    "{{X}} Destructible Block Moons": ["m", "l", "n"],
    "{{X}} Outfit Door Moons": ["m", "l", "n"],
}

SPECIAL_KINGDOM_FRAGMENTS: list[tuple[str, str]] = [
    ("coin coffer", "wooded"),
    ("deep woods", "wooded"),
    ("ty-foo", "snow"),
    ("ty foo", "snow"),
    ("ruined dragon", "ruined"),
    ("cloud kingdom", "cloud"),
    ("jaxi", "sand"),
    ("bird moon", "sand"),
]


def unique_ascending(values: list[int]) -> list[int]:
    return sorted({int(v) for v in values})


def unique_progression(values: list[str]) -> list[str]:
    """Lockout: progression = zonas unicas e/m/l/n (orden ZONE_ORDER)."""
    present = {z for z in values if z in ZONE_ORDER}
    out = [z for z in ZONE_ORDER if z in present]
    return out if out else ["m"]


def kingdom_to_zone(kingdom: str, story_order: list[str], ceilings: dict[str, str]) -> str:
    # Cloud = boss entre Wooded y Lost: Mid narrativo (no Late con Metro).
    if kingdom == "cloud":
        return "m"
    if kingdom not in story_order:
        return "n"
    ki = story_order.index(kingdom)
    for zone in ZONE_ORDER:
        if ki <= story_order.index(ceilings[zone]):
            return zone
    return "n"


def zones_hit_by_kingdoms(
    kingdoms: set[str] | list[str],
    story_order: list[str],
    ceilings: dict[str, str],
) -> set[str]:
    """Zonas e/m/l/n con ≥1 reino de la goal (no el span continuo rellenado)."""
    return {
        kingdom_to_zone(k, story_order, ceilings)
        for k in kingdoms
        if k in story_order
    }


def covers_all_progression_zones(zones_hit: set[str]) -> bool:
    return set(ZONE_ORDER) <= zones_hit


def next_zone(zone: str) -> str:
    i = ZONE_ORDER.index(zone) if zone in ZONE_ORDER else len(ZONE_ORDER) - 1
    return ZONE_ORDER[min(i + 1, len(ZONE_ORDER) - 1)]


# Puentes solo en reinos frontera (inicio/fin de zona e/m/l/n).
# Cap/Cascade e | Sand e+m | Lake e+m | Wooded m | Lost m+l |
# Metro m+l (puente Mid→Late) | Snow l | Seaside l+n | Luncheon l+n | resto n.
KINGDOM_BORDER_PROGRESSION: dict[str, list[str]] = {
    "cap": ["e"],
    "cascade": ["e"],
    "sand": ["e", "m"],
    "lake": ["e", "m"],
    "wooded": ["m"],
    "cloud": ["m"],
    "lost": ["m", "l"],
    "metro": ["m", "l"],
    "snow": ["l"],
    "seaside": ["l", "n"],
    "luncheon": ["l", "n"],
    "ruined": ["n"],
    "bowser": ["n"],
    "moon": ["n"],
}


def kingdom_span(start_zone: str) -> tuple[str, str]:
    """Fallback zona→zona si no hay reino (legacy span_from_kingdoms)."""
    if start_zone not in ZONE_ORDER:
        return "m", "l"
    if start_zone == "n":
        return "n", "n"
    return start_zone, next_zone(start_zone)


def expand_zones_forward(
    zones_hit: set[str],
    *,
    kingdoms: set[str] | None = None,
) -> list[str]:
    """Mono-reino → progression frontera; multi → zonas naturales."""
    if kingdoms and len(kingdoms) == 1:
        k = next(iter(kingdoms))
        if k in KINGDOM_BORDER_PROGRESSION:
            return unique_progression(KINGDOM_BORDER_PROGRESSION[k])
    if not zones_hit:
        return ["m"]
    return unique_progression(list(zones_hit))


def pair_progression(start: str, end: str, n: int) -> list[str]:
    """Zonas unicas de start..end; n limita cuantas se muestrean si hace falta."""
    if start not in ZONE_ORDER:
        start = "n"
    if end not in ZONE_ORDER:
        end = start
    si, ei = ZONE_ORDER.index(start), ZONE_ORDER.index(end)
    if ei < si:
        ei = si
    zones = ZONE_ORDER[si : ei + 1]
    if n <= 1:
        return [zones[0]]
    if len(zones) == 1:
        return [zones[0]]
    if len(zones) >= 4:
        return pair_progression_global(n, start=zones[0])
    if n >= len(zones):
        return list(zones)
    # n=2 y span de 3 (p.ej. e..l): extremos
    return [zones[0], zones[-1]]


def pair_progression_global(n: int, *, start: str = "e") -> list[str]:
    if start not in ZONE_ORDER:
        start = "e"
    zones = ZONE_ORDER[ZONE_ORDER.index(start) :]
    if n <= 1:
        return [zones[0]]
    if n >= len(zones):
        return list(zones)
    idxs = [round(i * (len(zones) - 1) / (n - 1)) for i in range(n)]
    for i in range(1, len(idxs)):
        if idxs[i] <= idxs[i - 1]:
            idxs[i] = min(idxs[i - 1] + 1, len(zones) - 1)
    for i in range(len(idxs) - 2, -1, -1):
        if idxs[i] >= idxs[i + 1]:
            idxs[i] = max(idxs[i + 1] - 1, 0)
    idxs[0] = 0
    idxs[-1] = len(zones) - 1
    return unique_progression([zones[i] for i in idxs])


def fit_letter_sequence(seq: list[str], n: int) -> list[str]:
    """Zonas unicas de seq; n limita cuantas se muestrean (sin repetir)."""
    uniq = unique_progression(seq)
    if n <= 1:
        return [uniq[0]]
    if n >= len(uniq):
        return uniq
    idxs = [round(i * (len(uniq) - 1) / (n - 1)) for i in range(n)]
    for i in range(1, len(idxs)):
        if idxs[i] <= idxs[i - 1]:
            idxs[i] = min(idxs[i - 1] + 1, len(uniq) - 1)
    return unique_progression([uniq[i] for i in idxs])


def letters_from_moons(
    moons: list[dict],
    story_order: list[str],
    ceilings: dict[str, str],
) -> list[str]:
    """Una letra por luna, ordenadas por zona."""
    counts: Counter[str] = Counter()
    for m in moons:
        k = m.get("kingdom")
        if k in story_order:
            counts[kingdom_to_zone(k, story_order, ceilings)] += 1
    seq: list[str] = []
    for z in ZONE_ORDER:
        seq.extend([z] * counts[z])
    return seq


def kingdoms_from_goal_lista(goal: str, obj: dict) -> set[str]:
    """Reinos de la lista contable (Activate Levers/P/GP, souvenirs, etc.)."""
    try:
        from goal_list_lib import build_goal_lista
    except ImportError:
        return set()
    slug, _ = parse_kingdom_prefixed_goal(goal)
    mentioned = kingdom_mentioned_in_goal(goal)
    kingdom = slug or mentioned
    items = build_goal_lista(goal, obj, kingdom=kingdom)
    return {str(x["kingdom"]) for x in items if x.get("kingdom")}


def capture_entry(goal: str) -> dict | None:
    gl = goal.lower()
    caps = sorted(
        (
            c
            for c in CAPTURE_LIST
            if c.get("reinos") and not c.get("postgame") and not c.get("transport")
        ),
        key=lambda c: len(c["name"]),
        reverse=True,
    )
    for cap in caps:
        name = cap["name"].lower()
        if name in gl or name.replace("-", " ") in gl:
            return cap
    return None


def kingdom_mentioned_in_goal(goal: str) -> str | None:
    for display, slug in KINGDOM_GOAL_PREFIXES:
        if slug == "moon":
            if re.search(
                r"(?<![A-Za-z])Moon(?![A-Za-z])\s+(Moons|Regional Coins|Kingdom)",
                goal,
            ):
                return "moon"
            continue
        if re.search(rf"(?<![A-Za-z]){re.escape(display)}(?![A-Za-z])", goal):
            return slug
    return None


def filter_moons_for_goal(goal: str, moons: list[dict], story_order: list[str]) -> list[dict]:
    """Si la goal nombra un reino, quedarse solo con lunas de ese reino."""
    slug, _ = parse_kingdom_prefixed_goal(goal)
    mentioned = kingdom_mentioned_in_goal(goal)
    filt = slug or mentioned
    if filt and filt in story_order:
        narrowed = [m for m in moons if m.get("kingdom") == filt]
        if narrowed:
            return narrowed
    return list(moons)


_NON_POWER_MOON_GOALS = frozenset(
    {
        "lake seed planted",
        "wooded seed moon",
        "correct wooded sphynx question",
        "defeat bowser in cloud kingdom",
    }
)


def _is_non_power_moon_goal(goal: str) -> bool:
    gl = goal.lower()
    if "pixel" in gl or gl.startswith("look at ") or "klepto" in gl:
        return True
    if gl.startswith(("wear ", "purchase ", "activate ")):
        return True
    return gl in _NON_POWER_MOON_GOALS


def _pool_only_score(group: dict, n_goals: int) -> int:
    # Solo pools dedicados (1 goal), no umbrellas flora/nature/…
    return 0 if group.get("apply_moon_tag") is False and n_goals == 1 else 1


def _consider_goal_moons(
    best: dict[str, list[dict]],
    best_key: dict[str, tuple[int, int, int]],
    *,
    goal: str,
    selected: list[dict],
    pool_only: int,
) -> None:
    kingdoms = {m["kingdom"] for m in selected if m.get("kingdom")}
    if not kingdoms:
        return
    key = (pool_only, len(kingdoms), len(selected))
    prev = best_key.get(goal)
    if prev is None or key < prev:
        best[goal] = selected
        best_key[goal] = key


def _process_group_goal_moons(
    best: dict[str, list[dict]],
    best_key: dict[str, tuple[int, int, int]],
    group: dict,
    story_like: list[str],
) -> None:
    raw_moons = group_moons(group)
    if not raw_moons:
        return
    n_goals = sum(
        1
        for o in group.get("objectives") or []
        if isinstance(o, dict) and o.get("goal")
    )
    pool_only = _pool_only_score(group, n_goals)
    for obj in group.get("objectives") or []:
        goal = obj.get("goal") if isinstance(obj, dict) else None
        if not goal:
            continue
        g = str(goal)
        if _is_non_power_moon_goal(g):
            continue
        selected = filter_moons_for_goal(g, raw_moons, story_like)
        _consider_goal_moons(
            best, best_key, goal=g, selected=selected, pool_only=pool_only
        )


def build_goal_moons() -> dict[str, list[dict]]:
    """goal → lunas del grupo pool (apply_moon_tag=False) o el mas especifico."""
    best: dict[str, list[dict]] = {}
    # (pool_only? 0:1, n_kingdoms, n_moons) — menor gana
    best_key: dict[str, tuple[int, int, int]] = {}
    story_like = list(KINGDOM_COLUMNS) + ["cloud", "ruined"]

    for group in load_bingo_groups():
        _process_group_goal_moons(best, best_key, group, story_like)
    return best


def progression_from_moons(
    moons: list[dict],
    n: int,
    story_order: list[str],
    ceilings: dict[str, str],
) -> list[str]:
    """Zonas de las lunas; mono-zona → span a la siguiente (puente Rush)."""
    del n  # range y progression son independientes
    kingdoms = {m["kingdom"] for m in moons if m.get("kingdom") in story_order}
    if not kingdoms:
        return ["m"]
    return expand_zones_forward(
        zones_hit_by_kingdoms(kingdoms, story_order, ceilings),
        kingdoms=kingdoms,
    )


def range_from_kingdom_counts(
    moons: list[dict],
    story_order: list[str],
) -> list[int]:
    """Umbrales = acumulado de lunas por reino (orden historia).

    2 reinos (Dorrie lake×1 + seaside×2): [1, 2, 3] (curado; acumulado sería [1, 3]).
    3 reinos (1+1+1) aunque solo 2 zonas: [1, 2, 3].
    """
    counts: Counter[str] = Counter()
    for m in moons:
        k = m.get("kingdom")
        if k in story_order:
            counts[k] += 1
    if not counts:
        return [1]
    cumul: list[int] = []
    running = 0
    for k in story_order:
        if k not in counts:
            continue
        running += int(counts[k])
        cumul.append(running)
    return unique_ascending(cumul)


def _kingdoms_from_goal_name(goal: str, story_order: list[str]) -> set[str] | None:
    """Reinos del nombre; set vacío = no match; None = agregado global (saltar)."""
    if goal in GLOBAL_AGGREGATE_GOALS:
        return None
    slug, _ = parse_kingdom_prefixed_goal(goal)
    if slug and slug in story_order:
        return {slug}
    mentioned = kingdom_mentioned_in_goal(goal)
    if mentioned and mentioned in story_order:
        return {mentioned}
    return set()


def _kingdoms_from_board_categories(obj: dict, story_order: list[str]) -> set[str]:
    cats = list(obj.get("board_categories") or []) + list(
        obj.get("line_categories") or []
    )
    return {c for c in cats if c in story_order}


def _kingdoms_from_special_fragments(gl: str, story_order: list[str]) -> set[str]:
    for frag, kingdom in SPECIAL_KINGDOM_FRAGMENTS:
        if frag in gl and kingdom in story_order:
            return {kingdom}
    return set()


def fallback_kingdoms(
    goal: str,
    obj: dict,
    story_order: list[str],
) -> set[str]:
    # Agregados globales: no parsear {{X}} Moon Rocks como reino Moon.
    named = _kingdoms_from_goal_name(goal, story_order)
    if named:  # non-empty set → match; None/empty → seguir
        return named

    lista_k = kingdoms_from_goal_lista(goal, obj)
    if lista_k:
        return {k for k in lista_k if k in story_order}

    gl = goal.lower()
    if re.search(r"(?<![a-z])cloud(?![a-z])", gl):
        return {"cloud"}
    if re.search(r"(?<![a-z])ruined(?![a-z])", gl):
        return {"ruined"}

    bk = _kingdoms_from_board_categories(obj, story_order)
    if bk:
        return bk

    cap = capture_entry(goal)
    if cap:
        return {k for k in cap["reinos"] if k in story_order}

    special = _kingdoms_from_special_fragments(gl, story_order)
    if special:
        return special

    if goal in GLOBAL_FROM_CAP or goal in GLOBAL_FROM_MID or "binocular" in gl:
        return {k for k in KINGDOM_COLUMNS if k in story_order}

    return set()


def span_from_kingdoms(
    kingdoms: set[str],
    story_order: list[str],
    ceilings: dict[str, str],
) -> tuple[str, str, str]:
    playable = [k for k in kingdoms if k in story_order]
    if not playable:
        return "m", "m", "same"

    if len(playable) == 1:
        k = playable[0]
        border = KINGDOM_BORDER_PROGRESSION.get(k)
        if border:
            return border[0], border[-1], "kingdom"
        start = kingdom_to_zone(k, story_order, ceilings)
        return start, start, "kingdom"

    zones = sorted(
        {kingdom_to_zone(k, story_order, ceilings) for k in playable},
        key=lambda z: ZONE_ORDER.index(z),
    )
    start, end = zones[0], zones[-1]
    span = ZONE_ORDER[ZONE_ORDER.index(start) : ZONE_ORDER.index(end) + 1]
    if len(span) == 1:
        return start, end, "same"
    if len(span) == 2:
        return start, end, "adjacent"
    if len(span) >= 4:
        return start, end, "global"
    return start, end, "wide"


def apply_objective(
    goal: str,
    obj: dict,
    *,
    goal_moons: dict[str, list[dict]],
    story_order: list[str],
    ceilings: dict[str, str],
) -> tuple[list[str], list[int] | None]:
    ranges = obj.get("range")
    new_range = unique_ascending(list(ranges)) if ranges else None
    if new_range == []:
        new_range = [1]

    override = PROGRESSION_OVERRIDES.get(goal)
    if override is not None:
        if new_range is None:
            return unique_progression([override[0]]), None
        return unique_progression(list(override)), new_range

    moons = goal_moons.get(goal) or []

    if moons:
        kingdoms = {
            str(m["kingdom"]) for m in moons if m.get("kingdom") in story_order
        }
        zones_hit = zones_hit_by_kingdoms(kingdoms, story_order, ceilings)
        prog = expand_zones_forward(zones_hit, kingdoms=kingdoms)
        if new_range is None:
            return prog, None
        if goal in RANGE_PRESERVE:
            new_range = list(RANGE_PRESERVE[goal])
        elif len(zones_hit) == 2 and len(kingdoms) >= 2:
            # 2 zonas naturales + 2+ reinos → range acumulado (Dorrie, etc.).
            # No si el 2º zona solo viene del span mono-reino.
            new_range = range_from_kingdom_counts(moons, story_order)
        return prog, new_range

    kingdoms = fallback_kingdoms(goal, obj, story_order)
    zones_hit = zones_hit_by_kingdoms(kingdoms, story_order, ceilings)
    # Mono-zona → +siguiente (puente Rush); Cap solo → sin puente; multi = natural.
    return expand_zones_forward(zones_hit, kingdoms=kingdoms), new_range


def primary_icon(objective: dict) -> str:
    icons = objective.get("icons", [])
    return icons[0] if icons else ""


def weighting_for_progression(progression: list[str]) -> int:
    """Peso Lockout (1-100) segun zonas.

    Prioriza puentes adyacentes (e,m / m,l / l,n) para que Rush avance ~1 reino
    y Mid no se vacíe al abrir Late. Baja globals emln para que no rellenen
    mitad de partida con Cap/Cascade/Sand otra vez.
    """
    zones = set(progression or [])
    if not zones:
        return 100
    # Puentes mono-reino / adyacentes (tras expand_zones_forward).
    if zones in ({"e"}, {"m"}, {"e", "m"}):
        return 100
    if zones == {"m", "l"}:
        return 100
    if zones == {"l", "n"}:
        return 95
    if zones == {"e", "m", "l"}:
        return 85
    if zones == {"m", "l", "n"}:
        return 85
    # Globals / very wide: limitan backtracking Early a mitad de run.
    if zones == {"e", "m", "l", "n"}:
        return 55
    # Exclusivas residuales (overrides / goals raras sin span).
    if zones == {"l"}:
        return 70
    if zones == {"n"}:
        return 60
    if "m" in zones:
        return 80
    if "l" in zones:
        return 75
    return 70


def sort_key(objective: dict) -> tuple:
    from catalog_lib import objective_goal_sort_key

    return objective_goal_sort_key(objective.get("goal", ""))


def sort_objectives(data: dict) -> None:
    data["objectives"].sort(key=sort_key)
    for i, obj in enumerate(data["objectives"], 1):
        obj["orden"] = i


def sort_combined_json() -> dict:
    """Ordena Combined ({{X}}+alfa) y reescribe orden 1..N. Devuelve el dict."""
    path = stamp_combined_filename_today()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    sort_objectives(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return data


def _set_objective_range_fields(
    obj: dict, new_p: list[str], new_r: list[int] | None
) -> None:
    obj["progression"] = new_p
    if new_r is None:
        obj.pop("range", None)
        obj.pop("progressive_ranges", None)
        return
    obj["range"] = new_r
    # progressive_ranges solo si hay varios umbrales Y varios progression
    if len(new_r) > 1 and len(new_p) > 1:
        obj["progressive_ranges"] = True
    else:
        obj.pop("progressive_ranges", None)


def _apply_weighting(obj: dict, new_w: int) -> int:
    """Escribe weighting (omite default 100). Devuelve el valor previo efectivo."""
    old_w = obj.get("weighting", 100)
    if new_w == 100:
        obj.pop("weighting", None)
    else:
        obj["weighting"] = new_w
    return old_w


def _update_combined_objective(
    obj: dict,
    *,
    goal_moons: dict[str, list[dict]],
    story_order: list[str],
    ceilings: dict[str, str],
) -> tuple | None:
    if obj.get("disabled"):
        return None
    goal = obj["goal"]
    old_p = list(obj.get("progression") or [])
    old_r = list(obj["range"]) if obj.get("range") else None
    new_p, new_r = apply_objective(
        goal,
        obj,
        goal_moons=goal_moons,
        story_order=story_order,
        ceilings=ceilings,
    )
    _set_objective_range_fields(obj, new_p, new_r)
    new_w = weighting_for_progression(new_p)
    old_w = _apply_weighting(obj, new_w)
    if old_p != new_p or old_r != new_r or old_w != new_w:
        return (goal, old_p, new_p, old_r, new_r)
    return None


def main() -> None:
    clear_runtime_caches()
    meta = load_meta()
    story_order = list(meta["story_order"])
    ceilings = dict(meta["run_tier_ceiling"])
    goal_moons = build_goal_moons()

    stamp_combined_filename_today()
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    changed = []
    for obj in data["objectives"]:
        change = _update_combined_objective(
            obj,
            goal_moons=goal_moons,
            story_order=story_order,
            ceilings=ceilings,
        )
        if change is not None:
            changed.append(change)

    JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Orden Combined ({{X}}+alfa + campo orden 1..N); antes vivía en
    # export_csv.py, absorbido aquí para que Combined quede siempre ordenado.
    sorted_data = sort_combined_json()
    objectives_sorted = sorted_data["objectives"]
    by_icon: dict[str, list[str]] = defaultdict(list)
    for obj in objectives_sorted:
        icon = primary_icon(obj)
        g = obj.get("goal", "")
        if icon and g:
            by_icon[icon].append(g)
    dupes = sum(1 for goals in by_icon.values() if len(goals) > 1)
    con_rangos = sum(1 for obj in objectives_sorted if obj.get("range"))
    print(f"\nJSON ordenado: {JSON_PATH.name}")
    print(f"Objetivos: {len(objectives_sorted)} (con rangos: {con_rangos})")
    print(f"orden: 1..{len(objectives_sorted)}")
    print(f"Iconos duplicados: {dupes} ({len(by_icon)} iconos distintos)")

    clear_runtime_caches()
    counts = normalize_bingo_groups_file()
    print(f"bingo_groups sync: {counts}")
    print(f"Actualizados: {len(changed)} objetivos")

    clear_runtime_caches()
    by = load_combined_objectives_by_goal()
    prog_c = Counter(
        tuple(o.get("progression") or []) for o in by.values() if not o.get("disabled")
    )
    print("\nDistribucion progression:")
    for k, v in sorted(prog_c.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {v:3d}  {list(k)}")

    weight_c = Counter(
        int(o.get("weighting") or 100)
        for o in by.values()
        if not o.get("disabled")
    )
    print("\nDistribucion weighting:")
    for k, v in sorted(weight_c.items()):
        print(f"  {v:3d}  weight={k}")

    print("\nEjemplos (conteo lunas -> prog):")
    samples = [
        "{{X}} Cactus/Tree Moons",
        "{{X}} Bullet Bill Moons",
        "{{X}} Bloom Flower Moon[[s]]",
        "{{X}} Cage Moon[[s]]",
        "{{X}} Sphynx Moons",
        "{{X}} Sand Moons",
        "{{X}} Goomba Moon[[s]]",
        "{{X}} 8-Bit Moons",
        "{{X}} Glydon Moon[[s]]",
        "{{X}} Fire Bro Moon[[s]]",
        "{{X}} Hammer Bro Moons",
        "{{X}} Total Moons",
    ]
    for g in samples:
        o = by.get(g)
        if not o:
            print(f"  MISSING {g}")
            continue
        moons = goal_moons.get(g) or []
        kc = Counter(m["kingdom"] for m in moons if m.get("kingdom"))
        detail = ",".join(f"{k}×{kc[k]}" for k in story_order if k in kc)
        print(
            f"  {g}: [{detail}] prog={o.get('progression')} range={o.get('range')}"
        )


if __name__ == "__main__":
    main()
