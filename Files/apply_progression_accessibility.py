"""Ajusta progression/range del Combined para Rush/Ascend/Summit.

Lockout schema: progression = zonas unicas e/m/l/n (sin repetidos).
No se alinea a len(range); progressive_ranges escala los umbrales
dentro de esas zonas solo si hay 2+ progression (si solo hay una zona,
los valores de range son equiprobables).

Con lunas (grupo bingo mas especifico):
  Cada luna aporta la zona de su reino. Un solo reino → progression de frontera
    (solo e | e+m | m+l | l+n | n; sin m/l sueltos → puente continuo).
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
  (Blocks / Hint-Arts / Warp-Painting → m,l,n). Si solo cubren
  2–3 zonas, progression = esas.
  Prefijo de reino / puente frontera → 1–2 zonas (no forzar emln).
  Overrides puntuales (Tourist, Minigame, Seeds, Warp-Painting, Lake Hint Art, …) ganan.
  Tras el pase principal: {{X}} Foo Regional Coins hereda progression de
  {{X}} Foo Moons / Moon[[s]] (salvo override; p. ej. Sand Jaxi/Ruins Regional=e).

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
    _CLOUD_KINGDOM,
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
GOAL_MINIGAME_MOONS = "{{X}} Minigame Moons"

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
        GOAL_MINIGAME_MOONS,
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
    "{{X}} Total Multi-Moons": [3, 6, 9, 12],
    "{{X}} Bullet Bill Moons": [2, 4],
    "{{X}} Cheep Cheep Moons": [2, 4, 6],
    "{{X}} Critter Moon[[s]]": [1, 2, 3],
    "{{X}} Dorrie Moon[[s]]": [1, 2, 3],
    "{{X}} Rabbit Chase Moon[[s]]": [1, 3, 5],
    "{{X}} Rocket Flower Moons": [2, 4, 6],
    "{{X}} Sand Bird Moons": [2, 3],
    "{{X}} Sand Jaxi Moons": [2, 4, 6],
    "{{X}} Sand Oasis Moons": [3, 6],
    "{{X}} Sand Ruins Moons": [4, 6, 8, 10],
    GOAL_MINIGAME_MOONS: [2, 4, 6, 8],
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
    "{{X}} Metro Night Moons": [2, 4, 6],  # 5 noche base + #51 pintura
}

PROGRESSION_OVERRIDES: dict[str, list[str]] = {
    # Estaciones: cap1 cascade1 sand3 lake1 wooded2 lost1 metro1 snow0
    # seaside≥3 luncheon1 bowser1 moon1 → techos 5/9/13/16 → rango [3,5,7,9]
    "Capture {{X}} Binoculars": ["e", "m", "l", "n"],
    # Warp paintings: progression = reino de ENTRADA (outbound), no destino.
    # Cadena fija: Sand→Metro, Lake/Wooded→Sand|Luncheon, Snow/Seaside→Cascade,
    # Metro|Snow/Seaside→Lake|Wooded, Luncheon→Mushroom.
    # Sin m/l sueltos: puente adyacente (m,l o l,n).
    # Metro WP: cuenta en Night → individuales lost/m (entrada Sand = Mid).
    "Metro Warp-Painting Moon": ["m"],
    "Sand Warp-Painting Moon": ["m", "l"],  # entra desde Lake/Wooded (1º fork)
    "Luncheon Warp-Painting Moon": ["m", "l"],  # entra desde Lake/Wooded (2º)
    "Cascade Warp-Painting Moon": ["l", "n"],  # entra desde Snow/Seaside
    "Lake Warp-Painting Moon": ["m", "l"],  # entra desde Metro (m,l) o Snow/Seaside
    "Wooded Warp-Painting Moon": ["m", "l"],  # entra desde Metro o Snow/Seaside
    "Mushroom Warp-Painting Moon": ["l"],  # entra desde Luncheon; luna base → l
    # Techos por entrada: e=1 m=3 l=6 n=7 → rango [2,3,4] desde Mid (sin Early:
    # primer warp usable en cadena Lake/Wooded → Sand|Luncheon).
    "{{X}} Warp-Painting Moons": ["m", "l", "n"],
    # Multireino a pie: todas las zonas aunque falten lunas en alguna (puente Rush).
    GOAL_MARIO_MOONS: ["e", "m", "l", "n"],
    GOAL_CAPPY_MOONS: ["e", "m", "l", "n"],
    # Turista: solo Late/Night (l,n), sin e/m del reino (cascade≠e).
    GOAL_TOURIST_MOONS: ["l", "n"],
    # key: sand(e) + lost(l) + metro(l) + luncheon×2(n)
    "{{X}} Key Moon[[s]]": ["e", "m", "l", "n"],
    # Mirar Hint-Arts: primeras en Lake/Wooded → sin Early (min 2).
    "Look at {{X}} Hint-Arts": ["m", "l", "n"],
    # Hint Art de Lake: world_peace → Mid.
    "Lake Hint Art Moon": ["m"],
    # Seaside/Snow Hint Art: luna base → Late (no Night del puente l,n).
    "Seaside Hint Art Moon": ["l"],
    "Snow Hint Art Moon": ["l"],
    # Seeds: NTT = plaza Sand (fijo 1); solo Early.
    # Seeds Planted: sand/e + metro/l + seaside (prefijo) → e,l.
    "{{X}} Seed Moon (No Time Travel)": ["e"],
    "{{X}} Seeds Planted": ["e", "l"],
    # Pixels 8-bit (no Power Moons). Cat Mario/Peach: 2/reino excl. Cloud/Ruined
    # → techos e/m/l/n = 6/12/18/24 → rango [3,6,9,12].
    # Pixel Luigis: coin Hint Art; sin Cloud/Snow/Ruined Toad/Mushroom → 15 total.
    "{{X}} Pixel Cat Marios/Peaches": ["e", "m", "l", "n"],
    "{{X}} Pixel Luigis": ["e", "m", "l", "n"],
    # Story events (no Moon Get de story_moon group).
    # Metro noche: tramo post-Wooded con Lost / Cloud (no Metro día l,n).
    # Pool solo base → Mid (no partir a Late).
    "{{X}} Metro Night Moons": ["m"],
    "{{X}} Metro Girder Moon[[s]]": ["m"],  # range [1,2,3] ⊆ noche (#8–#10)
    "Metro Shop Moon": ["m"],  # #27 noche
    "Metro City Hall Moon": ["m"],  # #34 City Hall Lost & Found (noche)
    "Metro Moon Rock": ["m"],  # base al llegar; bucket lost (noche)
    # 1 = Pest (noche); 2 = +Festival (día). Puente Mid↔Late.
    "{{X}} Metro Multi-Moon[[s]]": ["m", "l"],
    # Checkpoints Metro: 3/5 night lost/m; 7/9 día metro/l.
    "{{X}} Metro Checkpoints": ["m", "l"],
    "Correct Wooded Sphynx Question": ["e"],
    "Correct Moon Sphynx Question": ["n"],
    "Defeat Bowser in Cloud Kingdom": ["m"],
    "Defeat Madame Broode in Moon Kingdom": ["n"],
    "Defeat Ruined Dragon": ["n"],
    # Totales / pools multi-reino que tocan las 4 zonas → siempre emln
    # (da igual len(range)); weighting ~55. No restringir a e,m.
    "All Regional Coins in {{X}} Small Kingdom[[s]]": ["e", "m", "l", "n"],
    # --- Multi-reino / curados: compacto desde individuales (avail→borde) ---
    "{{X}} Beanstalk Moons": ["m", "n"],
    "{{X}} Cactus/Tree Moons": ["e"],
    "{{X}} Cage Moon[[s]]": ["m"],
    "{{X}} Cheep Cheep Moons": ["m", "l"],
    "{{X}} Destructible Block Moons": ["e", "m"],
    "{{X}} Dog Moon[[s]]": ["m", "n"],
    "{{X}} Dorrie Moon[[s]]": ["e", "l", "n"],
    "{{X}} Fire Bro Moon[[s]]": ["e", "l"],
    # Glydon: wooded/m + lost→l (puente) + seaside/n; range [1,2,3].
    "{{X}} Glydon Moon[[s]]": ["m", "l", "n"],
    "{{X}} Ground Pound Moons": ["m", "l"],
    "{{X}} Hidden Timer Moon[[s]]": ["e", "l"],
    # Checkpoints Wooded: 2 base→e; 4+ mid/wp→m (Iron Road mid route).
    "{{X}} Wooded Checkpoints": ["e", "m"],
    # Checkpoints Luncheon: 2–4 base→l; 6–8 Peak Climb mid→n.
    "{{X}} Luncheon Checkpoints": ["l", "n"],
    # Hybrid 2D: cascade/wp→e, snow/base→l, ruined/wp→n (umbrales 2/4/6).
    "{{X}} Hybrid 2D Sub-Area Moons": ["e", "l", "n"],
    "{{X}} Koopa Trace-Walking Moon[[s]]": ["e", "n"],
    "{{X}} Lurker/Rumble Moon[[s]]": ["e", "m", "l"],
    "{{X}} Mini Rocket Moons": ["m", "l"],
    "{{X}} NPC Moons": ["m", "l", "n"],
    "{{X}} Puzzle Moon[[s]]": ["m", "n"],
    # Ice Cave 4 purple (base/e) + templo 7 (mid/m); umbrales 4/8/11 → e,m.
    "{{X}} Sand Ice Regional Coins": ["e", "m"],
    # Jaxi / Ruins purple: accesibles en base (no dependen de wp).
    "{{X}} Sand Jaxi Regional Coins": ["e"],
    "{{X}} Sand Ruins Regional Coins": ["e"],
    # Totales Sand: mismo Early que Sand Moons (también vía sync sibling;
    # override por si el sync no aplica).
    "{{X}} Sand Regional Coins": ["e"],
    "{{X}} Shiny Rock Moon[[s]]": ["e", "n"],
    "{{X}} Slots Moon[[s]]": ["e", "l"],
    # Snow Sub-Area: 2 base→l; 4+ (wp)→n. Mitad l/l/n/n deja thr4 en l;
    # individuales iguala lockout→prog si queda invertido.
    "{{X}} Snow Sub-Area Moons": ["l", "n"],
    "{{X}} Spark Pylon Moons": ["e", "l"],
    # Pole: metro mid→l luego wooded wp→m; Combined ordena m,l (no l,m).
    "{{X}} Swinging Pole Moon[[s]]": ["m", "l"],
    "{{X}} Switch Moon[[s]]": ["m", "l"],
    "{{X}} T-Rex Moons": ["e", "l"],
    # Traped: seaside→l luego wooded→e; Combined ordena e,l. Solo l evita
    # thr1 invertido (thr2 queda prog e < lock l = normal).
    "{{X}} Traped Chest Moon[[s]]": ["l"],
    # Poochy: bowser n, metro l, snow l, luncheon n — orden de pool no caben
    # en unique e/m/l/n; individuales iguala lockout si invertido.
    "{{X}} Poochy Moon[[s]]": ["l", "n"],
    "{{X}} Wooden Crate Moon[[s]]": ["e", "l"],
    "Activate {{X}} Ground-Pound Switches": ["l", "n"],
    "Activate {{X}} Levers": ["e", "m", "l"],
    "Call Jaxi from {{X}} Stand[[s]]": ["e"],
    # Minigame: trofeos + carrera Snow (Bound Bowl / Class S).
    GOAL_MINIGAME_MOONS: ["e", "m", "l", "n"],
    # Outfit total: Sand/Lake/Wooded base → Early; 4 umbrales → e,m,l,n 1:1.
    "{{X}} Outfit Door Moons": ["e", "m", "l", "n"],
    # Lake Ledge Grab (#24+#25) = base → Early; +snow#12 → Late.
    "{{X}} Ledge Grab Moons": ["e", "l"],
}

SPECIAL_KINGDOM_FRAGMENTS: list[tuple[str, str]] = [
    ("coin coffer", "wooded"),
    ("deep woods", "wooded"),
    ("ty-foo", "snow"),
    ("ty foo", "snow"),
    ("ruined dragon", "ruined"),
    ("cloud kingdom", "lost"),
    ("metro night", "lost"),
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
    # Boss entre Wooded y Lost (goal "…Cloud Kingdom"): Mid narrativo.
    # Slug interno _CLOUD_KINGDOM; en catálogo es "lost".
    if kingdom == _CLOUD_KINGDOM:
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


# Puentes mono-reino (un reino ancla por combo de progression):
# Puente continuo (sin m ni l sueltos en mono-reino):
#   e: Cap+Cascade                         (2)
#   e,m: Sand+Lake+Wooded                  (3; Lake/Wooded peso menor en Rush)
#   m: Lost (+Cloud Kingdom + Metro noche hasta 1ª multi)
#   l: Metro día (sin Endgame; n queda para Snow/Seaside/Luncheon/…)
#   l,n: Snow+Seaside+Luncheon(+Mushroom)
#   n: Ruined+Bowser+Moon
# Sin puente m,l mono-reino: Lost=m y Metro=l quedan zonas sueltas.
KINGDOM_BORDER_PROGRESSION: dict[str, list[str]] = {
    "cap": ["e"],
    "cascade": ["e"],
    "sand": ["e", "m"],
    "lake": ["e", "m"],
    "wooded": ["e", "m"],
    "lost": ["m"],
    "metro": ["l"],
    "snow": ["l", "n"],
    "seaside": ["l", "n"],
    "luncheon": ["l", "n"],
    "mushroom": ["l", "n"],
    "ruined": ["n"],
    "bowser": ["n"],
    "moon": ["n"],
}

# Fork Mid: mismo puente e,m que Sand, pero no deben abrir Rush Early.
FORK_MID_KINGDOMS = frozenset({"lake", "wooded"})
# Fork Late: mismo puente l,n que Snow/Seaside; Luncheon/Mushroom pesan menos.
# Metro día es solo l (sin n).
FORK_LATE_KINGDOMS = frozenset({"luncheon", "mushroom"})

# revisit = base del siguiente reino (peso / momento de run).
REVISIT_NEXT_KINGDOM: dict[str, str] = {
    "cap": "sand",
    "cascade": "sand",
    "lost": "metro",
}
# Cap/Cascade pesan siempre con Sand (su revisit ≡ Sand base).
WEIGHT_KINGDOM_ALIAS: dict[str, str] = {
    "cap": "sand",
    "cascade": "sand",
}

# Disponibilidad → momento de run (menor = antes).
# revisit no va aquí: se remapea a base del siguiente reino.
AVAILABILITY_RANK: dict[str, int] = {
    "base": 0,
    "mid_story": 1,
    "world_peace": 2,
    "postgame": 3,
}
# Resta al peso del puente: base > mid_story > world_peace dentro del mismo progression.
AVAILABILITY_WEIGHT_PENALTY: dict[int, int] = {
    0: 0,
    1: 10,
    2: 20,
    3: 30,
}


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


def narrow_moons_for_fixed_goal(goal: str, moons: list[dict]) -> list[dict]:
    """Si el pool es el dump del reino, quedarse con la luna de la fija.

    build_goal_moons a menudo asigna todas las lunas del reino a Shop/Toad/
    Festival/…; para mid_story vs base hace falta la luna concreta.
    """
    if not moons or len(moons) <= 1:
        return moons
    gl = goal.lower()
    name = lambda m: str(m.get("name") or "").lower()
    needles: tuple[str, ...] = ()
    if "warp-painting" in gl or "warp painting" in gl:
        needles = ("secret path",)
    elif "hint art" in gl or "hint-art" in gl:
        needles = ("art",)
    elif "captain toad" in gl:
        needles = ("captain toad",)
    elif "shop" in gl and "seed" not in gl:
        needles = ("shopping",)
    elif "festival" in gl:
        needles = ("celebrating",)
    elif "sheep" in gl:
        needles = ("sheep",)
    elif "outfit door" in gl:
        needles = ("outfit", "costume", "rewiring", "beaten wire")
    if not needles:
        return moons
    hit = [m for m in moons if any(n in name(m) for n in needles)]
    return hit or moons


def item_availability_label(m: dict, registry: dict | None = None) -> str:
    """base / mid_story / world_peace / revisit (revisit ≈ base del puente)."""
    return moon_availability(m, registry)


def _availability_rank_label(availability: str) -> int:
    av = (availability or "base").strip().lower()
    if av == "revisit":
        return AVAILABILITY_RANK["base"]
    return AVAILABILITY_RANK.get(av, 2)


def _item_threshold_weight(m: dict) -> int:
    """Unidades que aporta el ítem al umbral (lunas=1; clusters regional=total)."""
    if m.get("total") is not None:
        try:
            return max(1, int(m["total"]))
        except (TypeError, ValueError):
            return 1
    if m.get("odyssey_units") is not None:
        try:
            return max(1, int(m["odyssey_units"]))
        except (TypeError, ValueError):
            return 1
    return 1


def limiting_availability_for_threshold(
    items: list[dict],
    threshold: int | None,
    kingdom: str,
    *,
    registry: dict | None = None,
    multi_kingdom: bool = False,
) -> str:
    """Disponibilidad limitante para el umbral.

    - Mono-reino: las unidades más fáciles del reino hasta cubrir el umbral
      (base cuenta aunque el JSON liste mid/wp antes). Clusters regionales
      aportan ``total`` monedas.
    - Multi-reino: prefijo acumulativo del pool hasta el umbral; la más
      tardía del reino (o del prefijo) manda.
    """
    if not items:
        return "base"
    if threshold is None:
        return item_availability_label(items[0], registry)
    need = int(threshold)
    if need < 1:
        return "base"

    def _rank(m: dict) -> int:
        return _availability_rank_label(item_availability_label(m, registry))

    if multi_kingdom and kingdom:
        # Prefijo acumulativo del pool (orden historia / grupo); clusters
        # regionales aportan ``total``. Luego filtra al reino asignado.
        taken: list[dict] = []
        acc = 0
        for m in items:
            taken.append(m)
            acc += _item_threshold_weight(m)
            if acc >= need:
                break
        matched = [
            m for m in taken if str(m.get("kingdom") or "") == kingdom
        ]
        pool = matched if matched else taken
        if not pool:
            return "base"
        return item_availability_label(max(pool, key=_rank), registry)

    k_moons = [
        m
        for m in items
        if kingdom and str(m.get("kingdom") or "") == kingdom
    ]
    # Mono: unidades más fáciles hasta cubrir el umbral.
    pool = k_moons if k_moons else list(items)
    ranked = sorted(pool, key=_rank)
    taken = []
    acc = 0
    for m in ranked:
        taken.append(m)
        acc += _item_threshold_weight(m)
        if acc >= need:
            break
    if not taken:
        return "base"
    return item_availability_label(max(taken, key=_rank), registry)


# Tourist: siempre Late/Night; no hereda e/m del reino (p.ej. cascade).
TOURIST_PROGRESSION_BORDER = ["l", "n"]


def progression_from_kingdom_availability(
    kingdom: str,
    availability: str,
    *,
    border: list[str] | None = None,
) -> str:
    """1ª zona del puente si base/revisit; 2ª si mid_story/world_peace."""
    zones = list(border) if border is not None else list(
        KINGDOM_BORDER_PROGRESSION.get(kingdom) or []
    )
    if not zones:
        return ""
    if len(zones) == 1:
        return zones[0]
    av = (availability or "base").strip().lower()
    if av == "revisit":
        av = "base"
    if av in {"mid_story", "world_peace"}:
        return zones[1]
    return zones[0]


def progression_letter_for_threshold(
    kingdom: str,
    items: list[dict],
    threshold: int | None,
    *,
    registry: dict | None = None,
    multi_kingdom: bool = False,
    border: list[str] | None = None,
) -> str:
    """Letra e/m/l/n del umbral: reino + disponibilidad limitante."""
    if not kingdom:
        return ""
    avail = limiting_availability_for_threshold(
        items,
        threshold,
        kingdom,
        registry=registry,
        multi_kingdom=multi_kingdom,
    )
    return progression_from_kingdom_availability(
        kingdom, avail, border=border
    )


def mono_kingdom_progression(
    kingdom: str,
    *,
    goal: str,
    ranges: list[int] | None,
    moons: list[dict],
    obj: dict | None = None,
    registry: dict | None = None,
) -> list[str] | None:
    """Progression mono-reino según disponibilidad / nº de rangos.

    - 1 zona de borde → esa zona.
    - Warp-Painting → None (overrides / reino de entrada; no destino).
    - Varios rangos → letras por umbral (base→1ª, mid/wp→2ª) compactadas.
    - Fija / 1 rango: base → 1ª zona; mid_story / world_peace / … → 2ª.
    """
    if "Warp-Painting" in goal:
        return None
    border = KINGDOM_BORDER_PROGRESSION.get(kingdom)
    if not border:
        return None
    if len(border) == 1:
        return list(border)
    n_range = len(ranges) if ranges else 1
    pool = narrow_moons_for_fixed_goal(goal, moons) if moons else []
    if n_range >= 2 and pool and ranges:
        letters = [
            progression_letter_for_threshold(
                kingdom, pool, int(thr), registry=registry
            )
            for thr in ranges
        ]
        return unique_progression([z for z in letters if z])
    probe = obj if obj is not None else {"goal": goal, "range": ranges}
    rank = goal_availability_rank(probe, pool, registry=registry)
    if rank >= AVAILABILITY_RANK["mid_story"]:
        return [border[1]]
    return [border[0]]


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
    story_like = list(KINGDOM_COLUMNS) + ["ruined"]

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
    # Antes del prefijo "Metro …": noche → bucket lost (Rush post-Wooded).
    if "Metro Night" in goal and "lost" in story_order:
        return {"lost"}
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
    if re.search(r"(?<![a-z])ruined(?![a-z])", gl):
        return {"ruined"}

    # Goal "Defeat Bowser in Cloud Kingdom" → slug de catálogo lost.
    if "cloud kingdom" in gl:
        return {"lost"}

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


def apply_objective(
    goal: str,
    obj: dict,
    *,
    goal_moons: dict[str, list[dict]],
    story_order: list[str],
    ceilings: dict[str, str],
    registry: dict | None = None,
) -> tuple[list[str], list[int] | None]:
    ranges = obj.get("range")
    new_range = unique_ascending(list(ranges)) if ranges else None
    if new_range == []:
        new_range = [1]

    override = PROGRESSION_OVERRIDES.get(goal)
    if override is not None:
        # Puente completo aunque no haya range (fijas tipo Warp-Painting / story).
        if goal in RANGE_PRESERVE:
            new_range = list(RANGE_PRESERVE[goal])
        return unique_progression(list(override)), new_range

    moons = goal_moons.get(goal) or []

    if moons:
        kingdoms = {
            str(m["kingdom"]) for m in moons if m.get("kingdom") in story_order
        }
        if len(kingdoms) == 1:
            mono = mono_kingdom_progression(
                next(iter(kingdoms)),
                goal=goal,
                ranges=new_range,
                moons=moons,
                obj=obj,
                registry=registry,
            )
            if mono is not None:
                prog = mono
            else:
                zones_hit = zones_hit_by_kingdoms(kingdoms, story_order, ceilings)
                prog = expand_zones_forward(zones_hit, kingdoms=kingdoms)
        else:
            zones_hit = zones_hit_by_kingdoms(kingdoms, story_order, ceilings)
            prog = expand_zones_forward(zones_hit, kingdoms=kingdoms)
        if new_range is None:
            return prog, None
        if goal in RANGE_PRESERVE:
            new_range = list(RANGE_PRESERVE[goal])
        elif len(kingdoms) >= 2:
            zones_hit = zones_hit_by_kingdoms(kingdoms, story_order, ceilings)
            if len(zones_hit) == 2:
                # 2 zonas naturales + 2+ reinos → range acumulado (Dorrie, etc.).
                new_range = range_from_kingdom_counts(moons, story_order)
        return prog, new_range

    kingdoms = fallback_kingdoms(goal, obj, story_order)
    if len(kingdoms) == 1:
        mono = mono_kingdom_progression(
            next(iter(kingdoms)),
            goal=goal,
            ranges=new_range,
            moons=moons,
            obj=obj,
            registry=registry,
        )
        if mono is not None:
            return mono, new_range
    zones_hit = zones_hit_by_kingdoms(kingdoms, story_order, ceilings)
    return expand_zones_forward(zones_hit, kingdoms=kingdoms), new_range


def primary_icon(objective: dict) -> str:
    icons = objective.get("icons", [])
    return icons[0] if icons else ""


def _coerce_disponibilidad_labels(raw) -> list[str]:
    """Una o varias ventanas (missable: p.ej. base+world_peace, no revisit)."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip().lower() for x in raw if str(x).strip()]
    s = str(raw).strip().lower()
    return [s] if s else []


def earliest_disponibilidad(raw, default: str = "base") -> str:
    """Para progression/umbrales: la ventana más temprana."""
    labels = _coerce_disponibilidad_labels(raw)
    if not labels:
        return default
    return min(
        labels,
        key=lambda av: 0
        if av in {"base", "revisit"}
        else 1
        if av == "mid_story"
        else 2
        if av == "world_peace"
        else 3,
    )


def moon_availability(
    moon: dict, registry: dict | None = None
) -> str:
    """availability wiki/matriz (base / revisit / mid_story / world_peace / …).

    Si disponibilidad es lista (varias ventanas missable), usa la más temprana.
    """
    avail = moon.get("availability") or moon.get("disponibilidad")
    if avail is None and registry is not None and moon.get("moon") is not None:
        k = str(moon.get("kingdom") or "")
        entry = registry.get((k, int(moon["moon"])))
        if entry:
            avail = entry.get("availability")
    if isinstance(avail, (list, tuple)):
        return earliest_disponibilidad(avail)
    return str(avail or "base")


def kingdom_for_weighting(moon: dict, registry: dict | None = None) -> str:
    """Reino para weighting: revisit→siguiente; Cap/Cascade→Sand."""
    k = str(moon.get("kingdom") or "")
    if not k:
        return ""
    if moon_availability(moon, registry) == "revisit":
        k = REVISIT_NEXT_KINGDOM.get(k, k)
    return WEIGHT_KINGDOM_ALIAS.get(k, k)


def alias_weight_kingdom(kingdom: str) -> str:
    """Alias de reino sin luna (goals fijas Cap/Cascade→Sand)."""
    return WEIGHT_KINGDOM_ALIAS.get(kingdom, kingdom)


def moon_availability_rank(moon: dict, registry: dict | None = None) -> int:
    """Rank 0..3: revisit cuenta como base (del siguiente reino)."""
    avail = moon_availability(moon, registry)
    if avail == "revisit":
        return AVAILABILITY_RANK["base"]
    return AVAILABILITY_RANK.get(avail, 2)


def goal_moons_needed(obj: dict, moons: list[dict]) -> int:
    """Cuántas lunas del pool hacen falta para el umbral más bajo (o 1 si fija)."""
    ranges = obj.get("range")
    if ranges:
        return max(1, min(int(x) for x in ranges))
    return 1 if moons else 0


def _limiting_moons(
    obj: dict, moons: list[dict], registry: dict | None = None
) -> list[dict]:
    """Lunas del umbral mínimo, las más tempranas primero."""
    if not moons:
        return []
    need = goal_moons_needed(obj, moons)
    ordered = sorted(moons, key=lambda m: moon_availability_rank(m, registry))
    return ordered[: min(need, len(ordered))]


def goal_availability_rank(
    obj: dict,
    moons: list[dict],
    *,
    registry: dict | None = None,
) -> int:
    """Momento de run de la goal: rank del umbral mínimo (lunas más fáciles primero)."""
    gl = str(obj.get("goal") or "")
    # Ubicacion: Moon Rock al llegar. Talkatoo: avail real de la lista.
    if "Moon Rock" in gl:
        return AVAILABILITY_RANK["base"]
    # Warp-Painting: entrada (no destino); Hint Art usa avail real de la luna.
    if "Warp-Painting" in gl:
        return AVAILABILITY_RANK["mid_story"]
    limiting = _limiting_moons(obj, moons, registry)
    if not limiting:
        return AVAILABILITY_RANK["base"]
    return max(moon_availability_rank(m, registry) for m in limiting)


def weighting_kingdoms(
    obj: dict,
    moons: list[dict],
    fallback: set[str],
    *,
    registry: dict | None = None,
) -> set[str]:
    """Reinos para weighting (revisit→siguiente; Cap/Cascade→Sand)."""
    limiting = _limiting_moons(obj, moons, registry)
    if limiting:
        return {kingdom_for_weighting(m, registry) for m in limiting if m.get("kingdom")}
    return {alias_weight_kingdom(k) for k in fallback if k}


def weighting_progression(
    obj_progression: list[str],
    obj: dict,
    moons: list[dict],
    weight_kingdoms: set[str],
    *,
    registry: dict | None = None,
) -> list[str]:
    """Si el umbral es solo revisit, usar el puente del reino siguiente (peso)."""
    limiting = _limiting_moons(obj, moons, registry)
    if limiting and all(
        moon_availability(m, registry) == "revisit" for m in limiting
    ):
        if len(weight_kingdoms) == 1:
            k = next(iter(weight_kingdoms))
            border = KINGDOM_BORDER_PROGRESSION.get(k)
            if border:
                return list(border)
    return list(obj_progression)


def weighting_for_progression(
    progression: list[str],
    *,
    kingdoms: set[str] | None = None,
    availability_rank: int = 0,
) -> int:
    """Peso Lockout (1-100) segun zonas, fork de reino y momento base/mid/wp.

    Prioriza puentes adyacentes (e,m / m,l / l,n). Lake/Wooded (e,m) y
    Luncheon/Mushroom (l,n) pesan menos que el otro brazo del fork.
    Dentro del mismo progression: base > mid_story > world_peace (más peso =
    más probable en el pool → Rush se llena antes con goals tempranas).
    """
    zones = set(progression or [])
    if not zones:
        base = 100
    else:
        ks = {str(k) for k in (kingdoms or set())}
        if zones == {"e", "m"} and ks and ks <= FORK_MID_KINGDOMS:
            base = 70
        elif zones == {"l", "n"} and ks and ks <= FORK_LATE_KINGDOMS:
            base = 75
        elif zones in ({"e"}, {"m"}, {"l"}, {"e", "m"}):
            base = 100
        elif zones == {"m", "l"}:
            base = 100
        elif zones == {"l", "n"}:
            base = 95
        elif zones == {"e", "m", "l"}:
            base = 85
        elif zones == {"m", "l", "n"}:
            base = 85
        elif zones == {"e", "m", "l", "n"}:
            base = 55
        elif zones == {"n"}:
            base = 60
        elif "m" in zones:
            base = 80
        elif "l" in zones:
            base = 75
        else:
            base = 70

    # Globals multi-zona: no aplicar penalización mid/wp (ya están bajos).
    if zones == {"e", "m", "l", "n"}:
        return base

    penalty = AVAILABILITY_WEIGHT_PENALTY.get(int(availability_rank), 20)
    return max(1, min(100, base - penalty))


def sort_key(objective: dict) -> tuple:
    from catalog_lib import objective_goal_sort_key

    return objective_goal_sort_key(objective.get("goal", ""))


def _is_regional_goal(goal: str) -> bool:
    return goal.endswith(" Regional Coins") or goal.startswith(
        "All Regional Coins in "
    )


def strip_moontype_from_regional_categories(obj: dict) -> bool:
    """Regional coins no llevan categoría moontype (solo regionalcoins + reino/zona)."""
    goal = str(obj.get("goal") or "")
    if not _is_regional_goal(goal):
        return False
    changed = False
    for key in ("board_categories", "line_categories"):
        cats = obj.get(key)
        if not isinstance(cats, list) or "moontype" not in cats:
            continue
        obj[key] = [c for c in cats if c != "moontype"]
        changed = True
    return changed


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
        obj.pop("individual_limit", None)
        return
    obj["range"] = new_r
    # progressive_ranges solo si hay varios umbrales Y varios progression
    if len(new_r) > 1 and len(new_p) > 1:
        obj["progressive_ranges"] = True
    else:
        obj.pop("progressive_ranges", None)
    # individual_limit solo con 3+ umbrales
    if len(new_r) >= 3:
        obj["individual_limit"] = 2
    else:
        obj.pop("individual_limit", None)


def sync_regional_progression_from_sibling_moons(
    objectives: list[dict],
    *,
    goal_moons: dict[str, list[dict]],
    story_order: list[str],
    registry: dict | None = None,
) -> list[tuple]:
    """{{X}} Foo Regional Coins hereda progression de {{X}} Foo Moons / Moon[[s]].

    Misma lógica que Sand Moons=e → Sand Regional=e. Overrides explícitos
    (p. ej. Sand Jaxi/Ruins Regional solo e) ganan y no se tocan.
    """
    by_goal = {str(o.get("goal") or ""): o for o in objectives}
    changed: list[tuple] = []
    for obj in objectives:
        goal = str(obj.get("goal") or "")
        if not goal.endswith(" Regional Coins"):
            continue
        if goal in PROGRESSION_OVERRIDES:
            continue
        base = goal[: -len(" Regional Coins")]
        sib = by_goal.get(f"{base} Moons") or by_goal.get(f"{base} Moon[[s]]")
        if not sib:
            continue
        new_p = unique_progression(list(sib.get("progression") or []))
        old_p = list(obj.get("progression") or [])
        old_r = list(obj["range"]) if obj.get("range") else None
        old_w = obj.get("weighting", 100)
        if old_p == new_p:
            continue
        _set_objective_range_fields(obj, new_p, old_r)
        moons = goal_moons.get(goal) or []
        if moons:
            fallback_ks = {
                str(m["kingdom"])
                for m in moons
                if m.get("kingdom") in story_order
            }
        else:
            fallback_ks = fallback_kingdoms(goal, obj, story_order)
        kingdoms = weighting_kingdoms(
            obj, moons, fallback_ks, registry=registry
        )
        avail_rank = goal_availability_rank(obj, moons, registry=registry)
        weight_prog = weighting_progression(
            new_p, obj, moons, kingdoms, registry=registry
        )
        new_w = weighting_for_progression(
            weight_prog, kingdoms=kingdoms, availability_rank=avail_rank
        )
        _apply_weighting(obj, new_w)
        if old_p != new_p or old_w != new_w:
            changed.append((goal, old_p, new_p, old_r, old_r))
    return changed


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
    registry: dict | None = None,
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
        registry=registry,
    )
    _set_objective_range_fields(obj, new_p, new_r)
    moons = goal_moons.get(goal) or []
    if moons:
        fallback_ks = {
            str(m["kingdom"]) for m in moons if m.get("kingdom") in story_order
        }
    else:
        fallback_ks = fallback_kingdoms(goal, obj, story_order)
    kingdoms = weighting_kingdoms(
        obj, moons, fallback_ks, registry=registry
    )
    avail_rank = goal_availability_rank(obj, moons, registry=registry)
    weight_prog = weighting_progression(
        new_p, obj, moons, kingdoms, registry=registry
    )
    new_w = weighting_for_progression(
        weight_prog, kingdoms=kingdoms, availability_rank=avail_rank
    )
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
    from catalog_lib import build_matrix_moon_registry

    registry = build_matrix_moon_registry()

    stamp_combined_filename_today()
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    changed = []
    for obj in data["objectives"]:
        if strip_moontype_from_regional_categories(obj):
            changed.append(
                (str(obj.get("goal") or ""), "moontype", "removed from categories")
            )
        change = _update_combined_objective(
            obj,
            goal_moons=goal_moons,
            story_order=story_order,
            ceilings=ceilings,
            registry=registry,
        )
        if change is not None:
            changed.append(change)

    synced = sync_regional_progression_from_sibling_moons(
        data["objectives"],
        goal_moons=goal_moons,
        story_order=story_order,
        registry=registry,
    )
    changed.extend(synced)

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
