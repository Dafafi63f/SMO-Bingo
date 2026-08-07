"""Recalcula `range` de objectives en catalog/bingo_groups.json.

Inventa escalones e/m/l/n coherentes. Goals de umbral fijo usan un solo
valor en range[] (p. ej. NTT [1]); los progresivos usan 4 escalones.

No toca bingo_lineas.json ni Combined.

Usage:
  python fix_bingo_group_ranges.py
  python fix_bingo_group_ranges.py --apply
"""
from __future__ import annotations

import argparse

from ranges_tools import SINGLE_VALUE_OK
from catalog_lib import (
    BINGO_GROUPS_PATH,
    KINGDOM_COLUMNS,
    KINGDOM_DISPLAY,
    ZONE_ORDER,
    build_matrix_moon_registry,
    kingdom_index,
    load_catalog,
    load_combined_objectives_by_goal,
    load_meta,
    load_range_tiers,
    load_scope,
    load_sub_area_levels,
    sum_moon_odyssey_units,
    write_catalog_json,
)

FULL_PROGRESSION = list(ZONE_ORDER)  # e, m, l, n
RANGE_LEN = 4


def finalize_range(goal: str, suggested: list[int]) -> list[int]:
    """Umbral uniforme → [N]; progresivos → 4 escalones e/m/l/n."""
    if not suggested:
        return suggested
    vals = _nondecreasing([int(x) for x in suggested])
    if len(set(vals)) == 1:
        return [vals[0]]
    if goal in SINGLE_VALUE_OK:
        return vals
    out = vals[:RANGE_LEN]
    while len(out) < RANGE_LEN:
        out.append(out[-1] if out else 1)
    return out[:RANGE_LEN]


def _nondecreasing(values: list[int]) -> list[int]:
    out = list(values)
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1])
    return out


def load_sub_area_pairs() -> list[frozenset[tuple[str, int]]]:
    """Pares oficiales Level (exactamente 2 lunas) del grupo sub_area."""
    pairs: list[frozenset[tuple[str, int]]] = []
    for lv in load_sub_area_levels():
        kingdom = lv.get("kingdom")
        moons = lv.get("moons") or []
        if not kingdom or len(moons) != 2:
            continue
        pairs.append(frozenset((str(kingdom), int(m)) for m in moons))
    return pairs


def moon_keys_of(group: dict) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for m in group.get("moons") or []:
        try:
            keys.add((str(m["kingdom"]), int(m["moon"])))
        except (KeyError, TypeError, ValueError):
            continue
    return keys


def count_sub_area_pairs(
    keys: set[tuple[str, int]], pairs: list[frozenset[tuple[str, int]]]
) -> int:
    if not keys or not pairs:
        return 0
    return sum(1 for p in pairs if p.issubset(keys))


def _moon_progression_key(
    key: tuple[str, int], story_order: list[str]
) -> tuple[int, int]:
    kingdom, moon = key
    try:
        ki = kingdom_index(story_order, kingdom)
    except ValueError:
        ki = len(story_order)
    return ki, moon


def _keys_in_sub_area_pairs(
    keys: set[tuple[str, int]], pairs: list[frozenset[tuple[str, int]]]
) -> set[tuple[str, int]]:
    paired: set[tuple[str, int]] = set()
    for p in pairs:
        if p.issubset(keys):
            paired |= set(p)
    return paired


def has_standalone_before_subarea_pair(
    keys: set[tuple[str, int]],
    pairs: list[frozenset[tuple[str, int]]],
    *,
    story_order: list[str],
) -> bool:
    """True si hay luna suelta del pool en un reino anterior al del par sub_area.

    Mismo reino no cuenta (p. ej. Sand Jaxi #24 antes del par #58+#59): ahí
    el mínimo sigue siendo 2. Solo exime goals multireino con acceso temprano
    (Fire Bro en Wooded antes del par Hammer Bro en Luncheon).
    """
    if not keys:
        return False
    paired = _keys_in_sub_area_pairs(keys, pairs)
    if not paired:
        return False
    standalone = keys - paired
    if not standalone:
        return False
    pair_kingdoms = {k for k, _ in paired}
    try:
        earliest_pair_ki = min(kingdom_index(story_order, k) for k in pair_kingdoms)
    except ValueError:
        return False
    for kingdom, _moon in standalone:
        try:
            if kingdom_index(story_order, kingdom) < earliest_pair_ki:
                return True
        except ValueError:
            continue
    return False


def effective_sub_area_pair_count(
    keys: set[tuple[str, int]],
    pairs: list[frozenset[tuple[str, int]]],
    *,
    story_order: list[str],
) -> int:
    """Pares sub_area que obligan mínimo 2: sin luna suelta en reino anterior."""
    n = count_sub_area_pairs(keys, pairs)
    if n <= 0:
        return 0
    if has_standalone_before_subarea_pair(keys, pairs, story_order=story_order):
        return 0
    return n


# Moons necesarios para alimentar la Odyssey y salir del reino (smo.wiki).
# Cap/Moon/Cloud = 0 (sin peaje de salida).
KINGDOM_EXIT_MOONS: dict[str, int] = {
    "cap": 0,
    "cascade": 5,
    "sand": 16,
    "lake": 8,
    "wooded": 16,
    "cloud": 0,
    "lost": 10,
    "metro": 20,
    "snow": 10,
    "seaside": 10,
    "luncheon": 18,
    "ruined": 3,
    "bowser": 8,
    "moon": 0,
}


def invent_count_range(cap: int, *, min_early: int | None = None) -> list[int]:
    """Inventa e/m/l/n con paso constante, paridad uniforme y holgura.

    Nunca exige el 100% del pool (salvo pools 1–3 / casos sub_area explícitos):
    early ~15–20% (o min_early si se pasa), nightmare ~55–65%.

    min_early: suelo del early (p. ej. requisito de salida del reino + extras).
    """
    if cap <= 0:
        return []
    if cap == 1:
        return [1, 1, 1, 1]
    if cap == 2:
        return [1, 1, 2, 2]
    if cap == 3:
        return [1, 2, 3, 3]
    if min_early is None:
        if cap == 4:
            return [1, 2, 3, 3]
        if cap == 5:
            return [2, 2, 4, 4]
        if cap == 6:
            return [2, 2, 4, 4]
        if cap == 7:
            return [1, 3, 5, 5]
    # Pools enormes
    if cap >= 80 and min_early is None:
        return [20, 40, 60, 70] if cap < 100 else [20, 40, 60, 80]

    # Techo blando: ~60% del pool y siempre < cap
    soft_hi = max(2, min(cap - 1, int(cap * 0.60 + 0.5)))
    # Early cómodo: ~18%, o el suelo pedido (salida de reino + extras)
    lo_target = max(1, min(soft_hi - 3, int(cap * 0.18 + 0.5)))
    if min_early is not None:
        # Debe quedar holgura hasta soft_hi (al menos 1 escalón útil)
        loft = min(min_early, soft_hi - 2)
        loft = max(1, loft)
        lo_target = max(lo_target, loft)
        # Si el peaje de salida es alto, subir un poco el techo (hasta ~70%)
        soft_hi = max(soft_hi, min(cap - 1, loft + max(6, int(cap * 0.35))))
        soft_hi = min(soft_hi, cap - 1)
        hi_target = soft_hi
    else:
        hi_target = soft_hi

    # Alinear paridad preferente (todo-par) en los targets
    if hi_target % 2:
        hi_target = max(lo_target + 2, hi_target - 1)
    if lo_target % 2 and hi_target % 2 == 0:
        # subir early a par (más holgado que bajar por debajo del min_early)
        lo_target = lo_target + 1 if lo_target + 1 <= hi_target - 2 else max(2, lo_target - 1)

    preferred_steps = (2, 4, 6, 8, 10, 12, 14, 16, 20, 1, 3, 5)
    span = max(3, hi_target - lo_target)
    ideal_step = max(2, int(span / 3 + 0.5))
    if ideal_step % 2:
        down, up = ideal_step - 1, ideal_step + 1
        ideal_step = (
            down
            if down >= 2 and abs(down - span / 3) <= abs(up - span / 3)
            else up
        )

    best: tuple | None = None
    best_vals: list[int] | None = None
    floor_early = min_early if min_early is not None else 1

    for step in preferred_steps:
        max_start = soft_hi - 3 * step
        if max_start < floor_early:
            continue
        start = hi_target - 3 * step
        start = max(floor_early, min(start, max_start))
        candidates = {start, max(floor_early, min(max_start, lo_target))}
        if step % 2 == 0:
            for base in (start, lo_target, max_start, floor_early):
                even_s = base if base % 2 == 0 else base + 1
                if floor_early <= even_s <= max_start:
                    candidates.add(even_s)
            snapped = max(step, (max(start, step) // step) * step)
            if floor_early <= snapped <= max_start:
                candidates.add(snapped)
        for cand in candidates:
            if not (floor_early <= cand <= max_start):
                continue
            vals = [cand + i * step for i in range(RANGE_LEN)]
            if vals[-1] > soft_hi or vals[-1] >= cap:
                continue
            if vals[0] < floor_early:
                continue
            key = _arith_score(vals, lo_target, hi_target, ideal_step, step, cap)
            if best is None or key > best:
                best = key
                best_vals = vals

    if best_vals is not None:
        return best_vals
    # Fallback: meseta desde floor_early hasta soft_hi (todo par si cabe)
    hi = soft_hi if soft_hi % 2 == 0 else soft_hi - 1
    start = max(floor_early, hi - 6)
    if start % 2:
        start += 1
    if start > hi:
        start = hi if hi % 2 == 0 else max(floor_early, hi - 1)
    return [start, start + 2, start + 4, min(hi, start + 6)]


def kingdom_min_early(kingdom: str, cap: int) -> int:
    """Early > peaje de salida: extras, no solo lo mínimo para avanzar."""
    exit_req = KINGDOM_EXIT_MOONS.get(kingdom, 0)
    if exit_req <= 0:
        # Cap / Moon: un puñado por encima de “pasar de largo”
        return max(4, min(cap - 2, int(cap * 0.35 + 0.5)))
    # Al menos +2 sobre el peaje; en reinos grandes un poco más de holgura
    extras = 2 if exit_req < 12 else (4 if exit_req < 18 else 6)
    return min(cap - 2, exit_req + extras)


def _arith_score(
    vals: list[int],
    lo_target: int,
    hi_target: int,
    ideal_step: int,
    step: int,
    cap: int,
) -> tuple:
    start, hi = vals[0], vals[-1]
    uniform_parity = all(v % 2 == start % 2 for v in vals)
    all_even = all(v % 2 == 0 for v in vals)
    all_odd = all(v % 2 == 1 for v in vals)
    return (
        1 if uniform_parity else 0,
        1 if step % 2 == 0 else 0,
        2 if all_even else (1 if all_odd else 0),
        1 if hi < cap else 0,  # nunca el máximo del pool
        -abs(step - ideal_step),
        -abs(hi - hi_target),
        -abs(start - lo_target) * 2,
        1 if step > 1 and start % step == 0 else 0,
        hi,
    )


def invent_pool_range(cap: int, n_pairs: int) -> list[int]:
    """Rango de pool de lunas; si hay pares sub_area, el mínimo es 2.

    Evita umbrales de 1 cuando entrar a una subárea implica (o debería)
    sacar las 2 lunas del nivel en la misma visita.
      - par puro (2): [2,2,2,2]
      - 2+1 (3):     [2,2,3,3]
      - 2+2 (4):     [2,2,4,4]
      - 2+1+1 (4):   [2,2,3,3]  (meseta; no pedimos 1)
    """
    if n_pairs <= 0:
        return invent_count_range(cap)
    if cap == 2 and n_pairs >= 1:
        return [2, 2, 2, 2]
    if cap == 3 and n_pairs == 1:
        return [2, 2, 3, 3]
    if cap == 4 and n_pairs == 2:
        return [2, 2, 4, 4]
    if cap == 4 and n_pairs == 1:
        return [2, 2, 3, 3]
    if cap == 5 and n_pairs >= 1:
        return [2, 2, 4, 4]
    if cap == 7 and n_pairs >= 1:
        return [2, 4, 6, 6]
    base = invent_count_range(cap)
    if not base:
        return base
    if base[0] >= 2:
        return base
    return _invent_arith_with_floor(cap, lo=2)


def _invent_arith_with_floor(cap: int, *, lo: int) -> list[int]:
    """Progresión aritmética con start ≥ lo, nightmare < cap (~60%)."""
    if cap <= lo:
        return [lo] * RANGE_LEN
    base = invent_count_range(cap)
    if base and base[0] >= lo and base[-1] < cap:
        return base
    soft_hi = max(lo + 1, min(cap - 1, int(cap * 0.60 + 0.5)))
    # Meseta par bajo el techo
    hi = soft_hi if soft_hi % 2 == 0 else soft_hi - 1
    start = max(lo if lo % 2 == 0 else lo + 1, hi - 4)
    if start % 2:
        start += 1
    return [start, start, hi, hi]


# Regional coins por reino: 4 valores distintos, salto solo +5 o +10.
# Mínimos según densidad/tamaño típico del reino (100 purple coins c/u).
KINGDOM_REGIONAL_RANGES: dict[str, list[int]] = {
    "cap": [25, 30, 35, 40],       # +5; reino chico
    "cascade": [30, 35, 40, 45],   # +5
    "sand": [40, 50, 60, 70],      # +10; grande y denso
    "lake": [25, 30, 35, 40],      # +5
    "wooded": [50, 60, 70, 80],    # +10; muchas purple accesibles
    "lost": [25, 30, 35, 40],      # +5
    "metro": [40, 50, 60, 70],     # +10
    "snow": [25, 30, 35, 40],      # +5; más repartidas/escondidas
    "seaside": [40, 50, 60, 70],   # +10
    "luncheon": [30, 40, 50, 60],  # +10
    "bowser": [25, 30, 35, 40],    # +5
    "moon": [20, 25, 30, 35],      # +5; pocas y tardías
}


def invent_regionals_range(
    *,
    kingdom: str | None = None,
    cap_hint: int | None = None,
) -> list[int]:
    """Regional coins: 4 umbrales distintos, salto solo 5 o 10."""
    if kingdom and kingdom in KINGDOM_REGIONAL_RANGES:
        return list(KINGDOM_REGIONAL_RANGES[kingdom])

    # Fallback genérico (no reino): +5 o +10, 4 valores distintos
    if cap_hint is None or cap_hint <= 0:
        return [25, 30, 35, 40]
    hi = max(35, int(round(cap_hint / 5) * 5))
    step = 10 if hi >= 60 else 5
    start = hi - 3 * step
    if start < 20:
        start = 20 if step == 10 else 25
        hi = start + 3 * step
    return [start, start + step, start + 2 * step, start + 3 * step]


# Reinos con isla inbound + Secret Path in-scope (grupo painting en sync).
# Incluye mushroom (Yoshi's House vía Luncheon), como mushroom#39.
# Fuera de catálogo: snow#33, seaside#49 (outbound postgame), bowser#43 (créditos).
PAINTING_CHECKPOINT_KINGDOMS: frozenset[str] = frozenset(
    {"cascade", "sand", "lake", "wooded", "metro", "luncheon", "mushroom"}
)

# Destino (isla inbound) → zona del reino de ENTRADA (como Warp-Painting Moon).
# Sand→Metro(e); Lake/Wooded→Sand|Luncheon(m); Snow/Seaside→Cascade(l);
# Metro|Snow/Seaside→Lake|Wooded(l); Luncheon→Mushroom(n).
PAINTING_CHECKPOINT_PROGRESSION: dict[str, str] = {
    "metro": "e",
    "sand": "m",
    "luncheon": "m",
    "cascade": "l",
    "lake": "l",
    "wooded": "l",
    "mushroom": "n",
}

# All Checkpoints: Secret Path / isla fuera de alcance (no hay “todos” jugables).
ALL_CHECKPOINTS_EXCLUDED_KINGDOMS: frozenset[str] = frozenset(
    {"snow", "seaside", "bowser"}
)

# Checkpoints por reino.
# total ≈ banderas en catálogo (isla inbound solo si reino ∈ PAINTING_CHECKPOINT_KINGDOMS).
# soft = no exigir la pintura en rangos.
# odyssey (meta) = tooltip Cascade: la Odyssey cuenta en el slot del basin
# (Waterfall Basin pre-story y Odyssey son el mismo CP).
# Missables SMO (Mario Wiki): Cascade Waterfall Basin→Odyssey; Metro City Outskirts→Main St
# y Construction Access→NDC Hall Plaza (bandera distinta pre/post story; CPs separados).
KINGDOM_CHECKPOINT_META: dict[str, dict] = {
    "cap": {"total": 2, "odyssey": False},
    "cascade": {"total": 5, "odyssey": True},
    "sand": {"total": 9, "odyssey": False},
    "lake": {"total": 6, "odyssey": False},
    "wooded": {"total": 9, "odyssey": False},
    "lost": {"total": 3, "odyssey": False},
    "metro": {"total": 11, "odyssey": False},
    "snow": {"total": 2, "odyssey": False},
    "seaside": {"total": 8, "odyssey": False},
    "luncheon": {"total": 9, "odyssey": False},
    "bowser": {"total": 10, "odyssey": False},
    "moon": {"total": 4, "odyssey": False},
    # Solo isla inbound (Yoshi's House); resto del reino es postgame.
    "mushroom": {"total": 1, "odyssey": False},
}

# Nombres en juego al tocar la bandera (Mario Wiki / Checkpoint Flag locations).
KINGDOM_CHECKPOINT_NAMES: dict[str, list[str]] = {
    "cap": [
        "Central Plaza",
        "Top-Hat Tower",
    ],
    "cascade": [
        "Waterfall Basin / Odyssey",
        "Stone Bridge",
        "Top of the Big Stump",
        "Fossil Falls Heights",
        "Island in the Sky",
    ],
    "sand": [
        "Tostarena Town",
        "Tostarena Ruins Entrance",
        "Tostarena Ruins Sand Pillar",
        "Tostarena Ruins Round Tower",
        "Moe-Eye Habitat",
        "Jaxi Ruins",
        "Tostarena Northwest Reaches",
        "Desert Oasis",
        "Southwestern Floating Island",
    ],
    "lake": [
        "Underwater Entrance",
        "Courtyard",
        "Water Plaza Entrance",
        "Water Plaza Display Window",
        "Water Plaza Terrace",
        "Viewing Balcony",
    ],
    "wooded": [
        "Iron Road: Entrance",
        "Iron Road: Halfway Point",
        "Sky Garden Tower",
        "Forest Charging Station",
        "Summit Path",
        "Iron Mountain Path, Station 8",
        "Secret Flower Field Entrance",
        "Observation Deck",
        "Iron Cage",
    ],
    "lost": [
        "Swamp Hill",
        "Mountainside Platform",
        "Rocky Mountain Summit",
    ],
    "metro": [
        "City Outskirts",
        "Main Street Entrance",
        "Rooftop Garden",
        "Construction Site",
        "Construction Access",
        "NDC Hall Plaza",
        "NDC Hall Rooftop",
        "Mayor Pauline Commemorative Park",
        "Outdoor Café",
        "Heliport",
        "Isolated Rooftop",
    ],
    "snow": [
        "Above the Ice Well",
        "Corner of the Freezing Sea",
    ],
    "seaside": [
        "Beach House",
        "Lighthouse",
        "Hot Spring Island",
        "Rolling Canyon",
        "Above Rolling Canyon",
        "Glass Palace",
        "Ocean Trench West",
        "Ocean Trench East",
    ],
    "luncheon": [
        "Peronza Plaza",
        "Path to the Meat Plateau",
        "Meat Plateau",
        "Volcano Cave Entrance",
        "Start of the Peak Climb",
        "Top of the Peak Climb",
        "Salt-Pile Isle",
        "Remote Island in the Lava",
        "Floating Sky Island",
    ],
    "bowser": [
        "Third Courtyard (Front)",
        "Third Courtyard (Rear)",
        "Second Courtyard",
        "Souvenir Shop",
        "Main Courtyard Entrance",
        "Main Courtyard",
        "Outer Wall",
        "Inner Wall",
        "Beneath the Keep",
        "Showdown Arena",
    ],
    "moon": [
        "Ringing-Bells Plateau",
        "Quiet Wall",
        "Ever-After Hill",
        "Wedding Hall",
    ],
    "mushroom": [
        "Yoshi's House",
    ],
}

# Slot donde la bandera de la Odyssey sustituye a la temporal del basin (Cascade).
KINGDOM_CHECKPOINT_ODYSSEY_SLOT: dict[str, int] = {
    "cascade": 1,
}

# Rangos fijos: 4 distintos o dos pares [a,a,b,b].
# Nunca exigen la pintura; Odyssey solo donde ayuda (cascade).
KINGDOM_CHECKPOINT_RANGES: dict[str, list[int]] = {
    "cap": [2],       # Nunca pedir 1 (CP inicial gratis)
    "cascade": [2, 3, 4],      # 5 − Island in the Sky (pintura); max 4 en mapa
    "snow": [2],               # 2 CPs; CP1 casi gratis al llegar (como Cap)
    "seaside": [2, 4, 6],         # sin 8; Diving Platform (Secret Path) fuera
    "sand": [4, 5, 6, 7],      # 4 distintos; 9 − pintura
    "lake": [2, 3, 4, 5],      # 4 distintos; 6 − pintura
    "wooded": [4, 5, 6, 7],
    "lost": [2, 2, 3, 3],      # 2 pares
    "metro": [3, 5, 7, 9],
    "luncheon": [3, 4, 5, 6],
    "bowser": [4, 6, 8, 10],  # 10; sin Island in the Sky (Secret Path fuera)
    "moon": [2, 2, 3, 3],
}

CHECKPOINT_TOOLTIP = "Completed on Final Checkpoint Touch."
CHECKPOINT_TOOLTIP_ODYSSEY = (
    "Completed on Final Checkpoint Touch. "
    "Odyssey counts as a checkpoint; the warp-painting island flag is not required."
)
CHECKPOINT_TOOLTIP_NO_PAINTING = (
    "Completed on Final Checkpoint Touch. "
    "The warp-painting island flag is not required for top values."
)

# Goals con override fijo (no reinventar).
# Cap CP: el 1º es gratis. Story/multi de reinos grandes: NO override
# (pedir X parciales tiene sentido; no hace falta historia entera para salir).
TRIVIAL_GOAL_RANGE_OVERRIDES: dict[str, list[int]] = {
    "{{X}} Cap Checkpoints": [2],
    "{{X}} Snow Checkpoint[[s]]": [2],  # CP1 gratis al llegar
    "{{X}} Seaside Checkpoints": [2, 4, 6],
    "{{X}} Total Checkpoints": [15, 30, 45, 60],
    "All Checkpoints in {{X}} Kingdom[[s]]": [2, 3],  # min 1 = Cap/Mushroom barato
    "Activate {{X}} Levers": [2, 3, 4, 5],  # 6 en lista; 1 gratis en ruta
    "Call Jaxi from {{X}} Stands": [1, 3, 5, 7],  # 9 stands; compra 30c cuenta como 1
    "Activate {{X}} P-Switch[[es]]": [2, 3, 4],  # 1 = Lake acceso barato
    "Activate {{X}} Ground-Pound Switch[[es]]": [2, 3, 4],  # 1 = Lost peaje
    "{{X}} Sand Story Moon[[s]]": [2],  # #1 peaje historia
    "{{X}} Wooded Story Moon[[s]]": [2],  # #1 Road to Sky Garden
    "{{X}} Total Multi-Moons": [3, 6, 9],
    "{{X}} Total Regional Coins": [75, 150, 225, 300],
    "{{X}} Deep Woods Regional Coins": [3, 6, 9],
    "{{X}} 8-Bit Regional Coins": [6, 12, 18, 24],
    "{{X}} Snow Shiveria Regional Coins": [10, 20, 30, 37],
    "{{X}} Snow Shiveria Moons": [4, 8, 12],  # pool 18; mismo patrón que Overworld
    "{{X}} Snow Overworld Moons": [4, 8, 12],  # pool 15 (sin Secret Path #33; Hint Art → shiveria)
    "{{X}} Snow Overworld Regional Coins": [4, 8, 13],
    "{{X}} Sand Ruins Regional Coins": [5, 10, 15],  # 16 purple; sin Ice Cave (solo sand_ice)
    "{{X}} Sand Ice Regional Coins": [4, 8, 11],
    "{{X}} Sand Jaxi Regional Coins": [4, 8, 12],
    "{{X}} Sand Tostarena Regional Coins": [8, 16, 24, 29],
    "{{X}} Sand Ruins Moons": [3, 6, 9],
    "{{X}} Sand Oasis Moons": [3, 6],
    "{{X}} Sand Pyramid Moons": [2, 4, 6],
    "{{X}} Sub-Area Regional Coins": [12, 24, 36, 48],
    "{{X}} Total Story Moons": [4, 8, 12, 16],
    "{{X}} Unique Life Up Hearts": [3, 6, 9, 12],
    # Seaside: 4 sellos; pedir 1–4 parcial tiene sentido (no hace falta historia entera)
    "{{X}} Seaside Story Moons": [2, 3, 4],
    "{{X}} Snow Story Moons": [2, 3, 4],
    "{{X}} Metro Story Moons": [3, 4, 5],
    "{{X}} Luncheon Story Moons": [2, 3],
    "{{X}} Bowser's Story Moons": [2, 3],
    "{{X}} NPC Moons": [2, 3, 4],
    "{{X}} Tourist Moons": [1, 2, 3, 4],
    "{{X}} Metro Girder Moon[[s]]": [1, 2, 3],
    "{{X}} Cappy Moons": [3, 6, 9, 12],
    "{{X}} Fauna Moons": [3, 6, 9, 12],
    "{{X}} Flora Moons": [2, 4, 6, 8],
    "{{X}} Nature Moons": [5, 10, 15, 20],
    "{{X}} Sand Jaxi Moons": [2, 4, 6],
    "{{X}} Sand Moe-Eye Moons": [2, 3],
    "{{X}} Sand Tostarena Moons": [3, 6, 9, 12],
    "{{X}} Spark Pylon Moons": [2, 4],
    "{{X}} Moon Banzai Bill Moon[[s]]": [1, 2],
    "{{X}} Sub-Area Moons": [20, 24, 28, 32],  # guía bingo 84 lunas / 42 pares
    # Reino >4 pares: min 4 lunas (2 subáreas), nunca el total
    "{{X}} Cap Sub-Area Moons": [2, 4, 6],
    "{{X}} Cascade Sub-Area Moons": [2, 4, 6],
    "{{X}} Sand Sub-Area Moons": [4, 6, 8],  # 4 pares (sin Ice Cave #49+#50)
    "{{X}} Lake Sub-Area Moons": [2, 4],
    "{{X}} Wooded Sub-Area Moons": [4, 6, 8],
    "{{X}} Metro Sub-Area Moons": [4, 6, 8, 10],
    "{{X}} Snow Sub-Area Moons": [2, 4, 6, 8],
    "{{X}} Seaside Sub-Area Moons": [2, 4, 6],
    "{{X}} Luncheon Sub-Area Moons": [4, 6, 8, 10],
    "{{X}} Bowser's Sub-Area Moons": [2, 4, 6, 8],
    "{{X}} Souvenirs": [6, 8, 10, 12],
    "{{X}} Stickers": [5, 7, 9],
    "Purchase {{X}} Costume Sets": [3, 6, 9, 12],
    "Purchase {{X}} Hats": [3, 6, 9, 12],
    "{{X}} Swinging Pole Moon[[s]]": [1, 3],
    "{{X}} Hidden Timer Moon[[s]]": [1, 3],
    "{{X}} Goomba Moon[[s]]": [2, 4, 6],
    "{{X}} Snow Goomba Moons": [2],
    "{{X}} Seaside Gushen Moons": [2, 4, 6],
    "{{X}} Luncheon Lava Bubble Moons": [2, 3],
    "{{X}} Fire Bro Moon[[s]]": [1, 2],
    "{{X}} Hammer Bro Moon[[s]]": [2, 3],
    "{{X}} Luncheon Fire Piranha Plant Moons": [2, 3],
    "{{X}} Hybrid 2D Sub-Area Moons": [2, 4, 6],
    "{{X}} Bullet Bill Moons": [2, 4],
    "{{X}} Critter Moons": [1, 2, 3],
    "{{X}} Dorrie Moon[[s]]": [1, 2, 3],
    "{{X}} Rabbit Chase Moons": [1, 3, 5],
    "{{X}} Rocket Flower Moons": [2, 4, 6],
    "{{X}} Sand Bird Moons": [2, 3],
    "{{X}} Cascade Chasm Lifts Moons": [2],
    "{{X}} Cascade Chain Chomp Moons": [2],
    "{{X}} Wooded Uproot Moons": [4, 6, 8],
    "{{X}} Seaside Uproot Moons": [2],
    "{{X}} Lurker/Rumble Moon[[s]]": [1, 2, 3, 4],
    "{{X}} Seaside Komboo Moons": [2, 4],
    "{{X}} Sherm Moons": [2, 4, 6],
    "{{X}} Seaside Maw-Ray Moon[[s]]": [1, 2, 3, 4],
    "{{X}} Bowser's Pokio Moons": [2, 4],
    "{{X}} Bowser's Stairface Ogre Moons": [1, 2, 3],
    "{{X}} Shiny Rock Moon[[s]]": [1, 2, 3, 4],
    "{{X}} Pokio Hole Moon[[s]]": [1, 2, 3],
    "{{X}} Snow Bitefrost Moons": [2],
    "{{X}} Rocket Flower Moons": [2, 4, 6],
    "{{X}} Talkatoos": [4, 6, 8, 10],
    "{{X}} Timer Challenge Moons": [4, 8, 12, 16],
    "{{X}} Outfit Door Moons": [2, 4, 6, 8],
    "{{X}} Pixel Cat Marios/Peaches": [5, 10, 15, 20],
    "{{X}} Seed Moon (No Time Travel)": [1],
    "{{X}} Seeds Planted": [3, 6, 9],
    "{{X}} Special Seed Moon[[s]]": [1, 2, 3],
    # Lost: peaje Odyssey = 10; early por encima del default
    "{{X}} Lost Moons": [12, 14, 16, 18],
}


def invent_checkpoint_range(
    n: int | None = None,
    *,
    kingdom: str | None = None,
) -> list[int]:
    """Checkpoints por reino: no forzar pintura; Odyssey solo si ayuda."""
    if kingdom and kingdom in KINGDOM_CHECKPOINT_RANGES:
        return list(KINGDOM_CHECKPOINT_RANGES[kingdom])

    # Fallback genérico desde un tope (sin reino): 4 distintos o [a,a,b,b]
    if n is None or n <= 0:
        return [1, 1, 1, 1]
    soft = max(1, n - 1)  # asumir que el último podría ser pintura
    if soft == 1:
        return [1, 1, 1, 1]
    if soft == 2:
        return [1, 1, 2, 2]
    if soft == 3:
        return [2, 2, 3, 3]
    if soft == 4:
        return [1, 2, 3, 4]
    if soft == 5:
        return [2, 3, 4, 5]
    if soft == 6:
        return [3, 4, 5, 6]
    if soft == 7:
        return [4, 5, 6, 7]
    # soft >= 8: 4 distintos con paso 2 si cabe
    hi = soft if soft % 2 == 0 else soft - 1
    start = max(2, hi - 6)
    if start % 2:
        start += 1
    return [start, start + 2, start + 4, start + 6]


def checkpoint_tooltip_for(kingdom: str | None) -> str:
    if not kingdom:
        return CHECKPOINT_TOOLTIP
    meta = KINGDOM_CHECKPOINT_META.get(kingdom) or {}
    if meta.get("odyssey"):
        return CHECKPOINT_TOOLTIP_ODYSSEY
    if kingdom in PAINTING_CHECKPOINT_KINGDOMS:
        return CHECKPOINT_TOOLTIP_NO_PAINTING
    return CHECKPOINT_TOOLTIP


def invent_from_existing_max(current: list[int], *, soft_cap: int | None = None) -> list[int]:
    """Si no hay pool de lunas, inventa a partir del máximo previo (o 4 por defecto)."""
    vals = [int(v) for v in current if int(v) > 0]
    hi = max(vals) if vals else 4
    if soft_cap is not None and soft_cap > 0:
        hi = min(hi, soft_cap) if vals else soft_cap
    return invent_count_range(hi)


def invent_count_range_for_len(cap: int, n: int) -> list[int]:
    """Rango inventado con exactamente n escalones (p. ej. progression e/l/n)."""
    if n <= 0:
        return []
    full = invent_count_range(cap)
    if n == len(full):
        return full
    if n == 1:
        return [full[0]]
    if n > len(full):
        out = list(full)
        while len(out) < n:
            out.append(out[-1])
        return out[:n]
    if n == 2:
        return [full[0], full[-1]]
    if n == 3:
        lo, hi = full[0], full[-1]
        if hi <= lo:
            return [lo, lo, hi]
        mid = lo + (hi - lo) // 2
        if mid <= lo:
            mid = lo + 1
        if mid >= hi:
            mid = hi - 1
        return [lo, mid, hi]
    indices = [int(round(i * (len(full) - 1) / (n - 1))) for i in range(n)]
    out = [full[i] for i in indices]
    return _nondecreasing(out)


def format_step(values: list[int]) -> str:
    if len(values) < 2:
        return ""
    steps = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    if len(set(steps)) == 1 and steps[0] > 0:
        return f"+{steps[0]}"
    if all(s >= 0 for s in steps):
        return "irregular"
    return ""


def _looks_like_moon_count_goal(goal: str) -> bool:
    g = goal.lower()
    if "moon" not in g:
        return False
    if any(
        x in g
        for x in (
            "question",
            "defeat",
            "win ",
            "call jaxi",
            "regional coin",
            "checkpoint",
        )
    ):
        return False
    return True


def _is_kingdom_moons_goal(goal: str, kingdom: str) -> bool:
    display = KINGDOM_DISPLAY.get(kingdom, kingdom)
    candidates = [
        "{{X}} " + display + " Moons",
        "{{X}} " + kingdom.capitalize() + " Moons",
    ]
    if kingdom == "bowser":
        candidates.append("{{X}} Bowser's Moons")
    return goal in candidates


def _is_kingdom_regionals_goal(goal: str, kingdom: str) -> bool:
    display = KINGDOM_DISPLAY.get(kingdom, kingdom)
    candidates = [
        "{{X}} " + display + " Regional Coins",
        "{{X}} " + kingdom.capitalize() + " Regional Coins",
    ]
    if kingdom == "bowser":
        candidates.append("{{X}} Bowser's Regional Coins")
    return goal in candidates


def _is_checkpoint_goal(goal: str) -> bool:
    return "checkpoint" in goal.lower()


def _is_regionals_goal(goal: str) -> bool:
    return "regional coin" in goal.lower()


def _moons_for_goal(
    goal: str,
    group: dict,
    *,
    is_kingdom: bool,
    moons_by_goal: dict[str, list[dict]],
) -> list[dict]:
    """Lunas del grupo temático; en reinos, las del grupo temático con el mismo goal."""
    if not is_kingdom:
        return list(group.get("moons") or [])
    return list(moons_by_goal.get(goal) or [])


def suggest_for_objective(
    *,
    gid: str,
    group: dict,
    obj: dict,
    allowed: set[str],
    combined: dict[str, dict],
    tiers: dict,
    pairs: list[frozenset[tuple[str, int]]],
    moons_by_goal: dict[str, list[dict]],
    registry: dict[tuple[str, int], dict],
) -> tuple[list[int] | None, str]:
    del allowed  # inventamos sin atarnos a disponibilidad por zona
    if obj.get("disabled"):
        return None, "disabled"
    goal = str(obj.get("goal") or "")
    if not goal:
        return None, "skip"
    current = list(obj.get("range") or [])
    moons = group.get("moons") or []
    n_moons = len(moons)
    is_kingdom = gid in KINGDOM_COLUMNS

    # Objetivos binarios / sin {{X}} → no inventar rango numérico
    if "{{X}}" not in goal and not current:
        return None, "skip"

    # Overrides de goals triviales (no pedir umbrales gratis)
    if goal in TRIVIAL_GOAL_RANGE_OVERRIDES:
        return list(TRIVIAL_GOAL_RANGE_OVERRIDES[goal]), "trivial_override"

    # --- Checkpoints ---
    if _is_checkpoint_goal(goal):
        if is_kingdom:
            return invent_checkpoint_range(kingdom=gid), "invent_checkpoint"
        hint = max(current) if current else 4
        return invent_checkpoint_range(int(hint)), "invent_checkpoint"

    # --- Regionals ---
    if _is_regionals_goal(goal) or (
        is_kingdom and _is_kingdom_regionals_goal(goal, gid)
    ):
        hint = None
        if is_kingdom:
            display = KINGDOM_DISPLAY[gid]
            kr = (tiers.get("kingdom_regionals") or {}).get(display) or {}
            rr = kr.get("range") or []
            if rr:
                hint = max(int(x) for x in rr)
            elif current:
                hint = max(current)
            return invent_regionals_range(kingdom=gid, cap_hint=hint), "invent_regionals"
        if current:
            hint = max(current)
        return invent_regionals_range(cap_hint=hint), "invent_regionals"

    # --- Kingdom main moons ({{X}} cuenta unidades Odyssey; multi ×3) ---
    if is_kingdom and _is_kingdom_moons_goal(goal, gid):
        if n_moons:
            cap = sum_moon_odyssey_units(moons, registry)
            off = combined.get(goal) or {}
            prog_n = len(
                off.get("progression") or obj.get("progression") or FULL_PROGRESSION
            )
            if prog_n != RANGE_LEN:
                return (
                    invent_count_range_for_len(cap, prog_n),
                    "invent_kingdom_moons_odyssey",
                )
            return (
                invent_count_range(
                    cap, min_early=kingdom_min_early(gid, cap)
                ),
                "invent_kingdom_moons_odyssey",
            )
        if current:
            return invent_from_existing_max(current), "invent_from_max"
        return None, "skip"

    # --- Contadores de lunas (temático o sub-objetivo de reino con pool conocido) ---
    pool_moons = _moons_for_goal(
        goal, group, is_kingdom=is_kingdom, moons_by_goal=moons_by_goal
    )
    if pool_moons and _looks_like_moon_count_goal(goal):
        keys = {(str(m["kingdom"]), int(m["moon"])) for m in pool_moons}
        n_pairs = effective_sub_area_pair_count(
            keys, pairs, story_order=load_meta()["story_order"]
        )
        src = "invent_pool" if not is_kingdom else "invent_sub_pool"
        if n_pairs:
            src = "invent_subarea_pair" if not is_kingdom else "invent_sub_subarea"
        return invent_pool_range(len(pool_moons), n_pairs), src

    # --- Sub-objetivos de reino sin pool resuelto ---
    if is_kingdom and _looks_like_moon_count_goal(goal):
        off = combined.get(goal) or {}
        src = list(off.get("range") or current or [])
        if src:
            return invent_from_existing_max(src), "invent_sub"
        return invent_count_range(3), "invent_sub_default"

    # --- Listas curadas (boss fights, etc.) ---
    if goal in (
        "{{X}} Boss Fights",
        "{{X}} Broodal Fights",
        "{{X}} Kingdom Boss Fight[[s]]",
    ):
        from goal_list_lib import build_goal_lista

        lista = build_goal_lista(goal, obj, kingdom=gid if is_kingdom else None)
        if lista:
            off = combined.get(goal) or {}
            prog = list(obj.get("progression") or off.get("progression") or FULL_PROGRESSION)
            n_prog = len(prog) if prog else RANGE_LEN
            return invent_count_range_for_len(len(lista), n_prog), "invent_lista_pool"

    # --- Otros contadores (freerunning, captures, talkatoo, sphynx, etc.) ---
    if "{{X}}" in goal:
        off = combined.get(goal) or {}
        src = list(off.get("range") or current or [])
        gl = goal.lower()
        if "freerunning" in gl:
            return [4, 6, 8, 10], "invent_other"
        if "talkatoo" in gl:
            return [9, 11, 13, 15], "invent_other"
        if "unique capture" in gl:
            return [14, 16, 18, 20], "invent_other"
        if "binocular" in gl:
            return [2, 4, 6, 8], "invent_other"
        if "sphynx" in gl or "question" in gl:
            return [4, 6, 8, 10], "invent_other"
        if "jaxi" in gl and "stand" in gl:
            return [1, 3, 5, 7], "invent_other"
        if "no time travel" in gl and "seed" in gl:
            return [1], "invent_other"
        if "seeds planted" in gl:
            return [2, 4, 6, 8], "invent_other"
        if src:
            return invent_from_existing_max(src), "invent_other"
        return invent_count_range(4), "invent_other_default"

    if current:
        return invent_from_existing_max(current), "invent_keep_shape"
    return None, "skip"


def _index_moons_by_goal(bingo: dict) -> dict[str, list[dict]]:
    """goal → moons de grupos temáticos (unión si varios declaran el mismo)."""
    out: dict[str, list[dict]] = {}
    for group in bingo.get("groups") or []:
        gid = str(group.get("id") or "")
        if gid in KINGDOM_COLUMNS:
            continue
        moons = group.get("moons") or []
        if not moons:
            continue
        for obj in group.get("objectives") or []:
            goal = str((obj or {}).get("goal") or "")
            if not goal:
                continue
            prev = out.get(goal)
            if prev is None:
                out[goal] = list(moons)
                continue
            seen = {(m.get("kingdom"), m.get("moon")) for m in prev}
            for m in moons:
                key = (m.get("kingdom"), m.get("moon"))
                if key not in seen:
                    prev.append(m)
                    seen.add(key)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    allowed = load_scope()
    combined = load_combined_objectives_by_goal()
    tiers = load_range_tiers()
    bingo = load_catalog(BINGO_GROUPS_PATH)
    pairs = load_sub_area_pairs()
    moons_by_goal = _index_moons_by_goal(bingo)
    registry = build_matrix_moon_registry()

    changes: list[tuple[str, str, list[int], list[int], str]] = []
    by_source: dict[str, int] = {}
    bad_len = 0

    for group in bingo.get("groups") or []:
        gid = str(group.get("id") or "")
        for obj in group.get("objectives") or []:
            if not isinstance(obj, dict) or not obj.get("goal"):
                continue
            goal = str(obj["goal"])
            current = list(obj.get("range") or [])
            suggested, source = suggest_for_objective(
                gid=gid,
                group=group,
                obj=obj,
                allowed=allowed,
                combined=combined,
                tiers=tiers,
                pairs=pairs,
                moons_by_goal=moons_by_goal,
                registry=registry,
            )
            by_source[source] = by_source.get(source, 0) + 1
            if suggested is None:
                continue
            suggested = finalize_range(goal, suggested)
            combined_obj = combined.get(goal) or {}
            expected_prog = list(
                combined_obj.get("progression")
                or obj.get("progression")
                or FULL_PROGRESSION
            )
            if goal not in SINGLE_VALUE_OK and len(suggested) != RANGE_LEN:
                bad_len += 1
            if suggested != list(obj.get("range") or []) or list(
                obj.get("progression") or []
            ) != expected_prog:
                changes.append(
                    (gid, goal, list(obj.get("range") or []), suggested, source)
                )
            if args.apply:
                obj["range"] = suggested
                obj["progression"] = expected_prog
                if len(suggested) >= 2 and len(expected_prog) > 1:
                    obj["progressive_ranges"] = True
                else:
                    obj.pop("progressive_ranges", None)
                if source == "invent_checkpoint" and gid in KINGDOM_COLUMNS:
                    tip = checkpoint_tooltip_for(gid)
                    if obj.get("tooltip") != tip:
                        obj["tooltip"] = tip

    print(f"Cambios (rango y/o progression→e,m,l,n): {len(changes)}")
    print("Por fuente:", ", ".join(f"{k}={v}" for k, v in sorted(by_source.items())))
    print(f"Pares sub_area cargados: {len(pairs)}")
    if bad_len:
        print(f"AVISO: {bad_len} rangos sin longitud 4")
    for gid, goal, cur, sug, src in changes:
        step = format_step(sug)
        print(
            f"  [{gid}] {goal}\n"
            f"    {cur} -> {sug}  ({src}{', ' + step if step else ''})"
        )

    if args.apply:
        from catalog_lib import finalize_bingo_groups_doc

        write_catalog_json(BINGO_GROUPS_PATH, finalize_bingo_groups_doc(bingo))
        print(f"Escrito: {BINGO_GROUPS_PATH}")
    else:
        print("Modo informe. Usa --apply para escribir bingo_groups.json.")


if __name__ == "__main__":
    main()
