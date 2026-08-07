"""Exporta capturas del juego con lunas relacionadas (una captura principal por luna).

Reglas:
  - Cada luna tiene como mucho UNA captura principal (forma normal / tematica).
  - Capturas multi-reino: se listan todas las lunas de todos los reinos.
  - Incluye lunas donde la captura es requisito O solo tematica (p. ej. Frog Pond,
    Love/Goombette, Fishing con Lakitu).
  - Subarea: la captura/tematica aplica a ambas lunas del par cuando es
    la misma. Si cada luna pide captura distinta (p. ej. BB + Goomba en
    Underground Temple), no se unifican. Tipos (8bit, chest, shards…) no
    se copian entre el par.
  - Lista las 52 capturas in-game (wiki). Acceso/transporte (Mini Rocket,
    Taxi, Manhole, Pole): moons del grupo bingo se anexan aqui aunque el
    contenido tematico sea otra captura (p. ej. Fog = Paragoomba + Mini
    Rocket; High-Rise = Mini Rocket + Pole). Rocket Flower no es captura
    wiki. goal=true solo si cuentan para la goal Combined de esa fila.
  - Fire Bro + Hammer Bro: filas distintas (wiki); goals Combined separadas.
    Unique Captures las cuenta como una (merge_into).
  - Capturas especiales (cactus, tree, meat, bowser statue…): tipo=especial.
  - Normales con < CAPTURE_TAG_MIN lunas: tipo=minoritaria (solo `captures`).
  - Normales con ≥ CAPTURE_TAG_MIN: tipo=normal (tag concreta / moon_tag).
  - objectives[]: goal(s) Combined dedicada(s) si existen (Capture X / Moon Get /
    {{X}} Total Moons). Varios grupos con el mismo `capture` aportan goals extra
    (Pokio = Bowser's Pokio + Pokio Hole). Vacio = sin goal propia
    (sigue en Unique Captures si aplica).
  - En cada luna, goal=true|false: si cuenta para alguna goal Combined de la
    fila (union de pools bingo_groups). Sin goal propia → todas false
    (p. ej. Meat, Broode's).

Salida: catalog/capturas_lunas.json (formato tipo bingo_groups / goals_referencia).

Usage:
  python export_capturas_lunas.py
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path

from catalog_lib import (
    BINGO_GROUPS_PATH,
    CAPTURE_NAME_TO_TAG,
    CAPTURE_TAG_MIN,
    CATALOG_DIR,
    KINGDOM_COLUMNS,
    KINGDOM_DISPLAY,
    ROOT,
    build_matrix_moon_registry,
    enrich_moon_ref_odyssey,
    group_moons,
    load_catalog,
    load_combined_objectives_by_goal,
    load_sub_area_levels,
    objective_ref_from_combined,
    write_catalog_json,
)
from fill_captures_cappy import MARIOWIKI_URLS, fetch, parse_mariowiki_table

OUT_JSON = CATALOG_DIR / "capturas_lunas.json"

# Lista in-game. postgame=True → fuera del CSV salvo que haya lunas in-scope.
# reinos_juego: donde puede aparecer la captura (no solo el primer encuentro).
CAPTURE_LIST: list[dict] = [
    {"id": 1, "name": "Frog", "reinos": ["cap"], "postgame": False},
    {"id": 2, "name": "Spark pylon", "reinos": ["cap", "metro", "bowser", "moon"], "postgame": False},
    {"id": 3, "name": "Paragoomba", "reinos": ["cap", "wooded"], "postgame": False},
    {"id": 4, "name": "Chain Chomp", "reinos": ["cascade"], "postgame": False},
    {"id": 5, "name": "Big Chain Chomp", "reinos": ["cascade"], "postgame": False, "special": True},
    # Big Chain Chomp: 0 lunas → goal Capture Big Chain Chomp (Cascade).
    {"id": 6, "name": "Broode's Chain Chomp", "reinos": ["cascade"], "postgame": False, "special": True},
    {"id": 7, "name": "T-Rex", "reinos": ["cascade", "wooded", "metro"], "postgame": False},
    {"id": 8, "name": "Binoculars", "reinos": [
        "sand", "cap", "cascade", "lake", "wooded", "lost",
        "metro", "seaside", "luncheon", "bowser", "moon",
    ], "postgame": False, "special": True},
    # Binoculars: 0 lunas. Primer reino = sand (3 ubicaciones). Conteos:
    # cap1 cascade1 sand3 | lake1 wooded2 lost1 | metro1 snow0 seaside≥3
    # | luncheon1 bowser1 moon1 → techos e/m/l/n=5/9/13/16 → rango [3,5,7,9].
    {"id": 9, "name": "Bullet Bill", "reinos": ["sand", "metro"], "postgame": False},
    {"id": 10, "name": "Moe-Eye", "reinos": ["sand"], "postgame": False},
    # Cactus: sand#36+#40 (goal Cactus/Tree con Tree wooded#34). No special:
    # enforce_special_single_moon dejaría solo 1 luna.
    {"id": 11, "name": "Cactus", "reinos": ["sand"], "postgame": False},
    {"id": 12, "name": "Goomba", "reinos": ["sand", "wooded", "snow", "seaside", "luncheon", "bowser"], "postgame": False},
    {"id": 13, "name": "Knucklotec's Fist", "reinos": ["sand"], "postgame": False, "special": True},
    {"id": 14, "name": "Mini Rocket", "reinos": ["sand", "wooded", "metro", "seaside"], "postgame": False, "transport": True},
    {"id": 15, "name": "Glydon", "reinos": ["sand", "wooded", "lost", "seaside", "bowser"], "postgame": False},
    {"id": 16, "name": "Lakitu", "reinos": ["sand", "lake", "snow", "bowser"], "postgame": False},
    {"id": 17, "name": "Zipper", "reinos": ["lake"], "postgame": False},
    {"id": 18, "name": "Cheep Cheep", "reinos": ["lake", "seaside"], "postgame": False},
    {"id": 19, "name": "Puzzle Part (Lake Kingdom)", "reinos": ["lake"], "postgame": False, "special": True},
    {"id": 20, "name": "Poison Piranha Plant", "reinos": ["wooded"], "postgame": False, "special": True},
    # Poison Piranha: 0 lunas → Capture Poison Piranha Plant (Wooded).
    {"id": 21, "name": "Uproot", "reinos": ["wooded", "seaside"], "postgame": False},
    # Fire Bro: fila propia (wiki). Unique Captures fusiona con Hammer Bro.
    {"id": 22, "name": "Fire Bro", "reinos": ["wooded", "luncheon"], "postgame": False, "merge_into": 39},
    {"id": 23, "name": "Sherm", "reinos": ["wooded", "metro"], "postgame": False},
    {"id": 24, "name": "Coin Coffer", "reinos": ["wooded"], "postgame": False, "special": True},
    {"id": 25, "name": "Tree", "reinos": ["wooded"], "postgame": False, "special": True},
    {"id": 26, "name": "Boulder", "reinos": ["wooded"], "postgame": False, "special": True},
    # Boulder: 0 lunas (Deep Woods) → Capture Boulder (Wooded).
    {"id": 27, "name": "Picture Match Part (Goomba)", "reinos": ["cloud"], "postgame": True, "special": True},
    {"id": 28, "name": "Tropical Wiggler", "reinos": ["lost"], "postgame": False},
    {"id": 29, "name": "Pole", "reinos": ["metro", "wooded"], "postgame": False, "transport": True},
    # Pole: barras → swinging_pole (como Mini Rocket/Taxi/Manhole).
    {"id": 30, "name": "Manhole", "reinos": ["metro"], "postgame": False, "transport": True},
    # Manhole: acceso sub_area; goal Metro Manhole Moons.
    {"id": 31, "name": "Taxi", "reinos": ["metro"], "postgame": False, "transport": True},
    {"id": 32, "name": "RC Car", "reinos": ["metro"], "postgame": False},
    {"id": 33, "name": "Ty-foo", "reinos": ["snow"], "postgame": False, "special": True},
    {"id": 34, "name": "Shiverian Racer", "reinos": ["snow"], "postgame": False},
    # Cheep Cheep nieve: 0 Moon Get in-scope → Capture Snow Cheep Cheep (como Boulder).
    {"id": 35, "name": "Cheep Cheep (Snow Kingdom)", "reinos": ["snow"], "postgame": False, "special": True},
    {"id": 36, "name": "Gushen", "reinos": ["seaside"], "postgame": False},
    {"id": 37, "name": "Lava Bubble", "reinos": ["luncheon"], "postgame": False},
    {"id": 38, "name": "Volbonan", "reinos": ["luncheon"], "postgame": False},
    {"id": 39, "name": "Hammer Bro", "reinos": ["luncheon"], "postgame": False},
    {"id": 40, "name": "Meat", "reinos": ["luncheon"], "postgame": False, "special": True},
    # Meat: luncheon#3 Big Pot; solo Unique Captures (sin Capture Meat).
    {"id": 41, "name": "Fire Piranha Plant", "reinos": ["luncheon"], "postgame": False},
    # Fire Piranha: #32 linternas + Magma Swamp #37+#38.
    {"id": 42, "name": "Pokio", "reinos": ["bowser"], "postgame": False},
    {"id": 43, "name": "Jizo", "reinos": ["bowser"], "postgame": False},
    {"id": 44, "name": "Bowser statue", "reinos": ["moon"], "postgame": False, "special": True},
    {"id": 45, "name": "Parabones", "reinos": ["moon"], "postgame": False, "special": True},
    # Banzai Bill: #11+#13 (goal). No special: enforce_special_single_moon dejaría 1.
    {"id": 46, "name": "Banzai Bill", "reinos": ["moon"], "postgame": False},
    {"id": 47, "name": "Chargin' Chuck", "reinos": ["moon"], "postgame": False, "special": True},
    # Chargin' Chuck: 0 lunas → Capture Chargin' Chuck (Moon).
    {"id": 48, "name": "Bowser", "reinos": ["moon"], "postgame": True, "special": True},
    {"id": 49, "name": "Letter", "reinos": ["metro"], "postgame": True, "special": True},
    {"id": 50, "name": "Puzzle Part (Metro Kingdom)", "reinos": ["metro"], "postgame": True, "special": True},
    {"id": 51, "name": "Picture Match Part (Mario)", "reinos": ["mushroom"], "postgame": True, "special": True},
    {"id": 52, "name": "Yoshi", "reinos": ["mushroom"], "postgame": True, "special": True},
]

CAPTURE_BY_ID = {c["id"]: c for c in CAPTURE_LIST}
SPECIAL_CAPTURE_IDS = {c["id"] for c in CAPTURE_LIST if c.get("special")}
# Capturas wiki que Unique Captures cuenta como una (p. ej. Fire+Hammer Bro).
# El JSON de capturas lista ambas filas; solo la lista Unique Captures fusiona.
CAPTURE_MERGE_INTO: dict[int, int] = {
    int(c["id"]): int(c["merge_into"])
    for c in CAPTURE_LIST
    if c.get("merge_into") is not None
}
CAPTURE_MERGE_DISPLAY: dict[int, str] = {
    39: "Fire/Hammer Bro",
}

# Goal Combined dedicada por captura (CSV columna objetivo). Cerrado por ahora.
CAPTURE_OBJECTIVE: dict[int, str] = {
    1: "{{X}} Cap Frog Moons",
    2: "{{X}} Spark Pylon Moons",
    3: "{{X}} Paragoomba Moons",
    4: "{{X}} Cascade Chain Chomp Moons",
    5: "Capture Big Chain Chomp",
    7: "{{X}} T-Rex Moons",
    8: "Capture {{X}} Binoculars",
    9: "{{X}} Bullet Bill Moons",
    10: "{{X}} Sand Moe-Eye Moons",
    11: "{{X}} Cactus/Tree Moons",
    12: "{{X}} Goomba Moon[[s]]",
    14: "{{X}} Mini Rocket Moons",
    15: "{{X}} Glydon Moon[[s]]",
    16: "{{X}} Lakitu-Fishing Moon[[s]]",
    17: "{{X}} Lake Zipper Moons",
    18: "{{X}} Cheep Cheep Moons",
    19: "{{X}} Puzzle Moon[[s]]",
    20: "Capture Poison Piranha Plant",
    21: "{{X}} Wooded Uproot Moons",
    22: "{{X}} Fire Bro Moon[[s]]",
    23: "{{X}} Sherm Moons",
    24: "{{X}} Special Seed Moon[[s]]",
    25: "{{X}} Cactus/Tree Moons",
    26: "Capture Boulder",
    28: "{{X}} Lost Tropical Wiggler Moons",
    29: "{{X}} Swinging Pole Moon[[s]]",
    30: "{{X}} Metro Manhole Moons",
    31: "{{X}} Metro Taxi Moons",
    32: "{{X}} Metro RC Car Moons",
    33: "{{X}} Snow Ty-Foo Moons",
    34: "{{X}} Snow Shiverian Racer Moon[[s]]",
    35: "Capture Snow Cheep Cheep",
    36: "{{X}} Seaside Gushen Moons",
    37: "{{X}} Luncheon Lava Bubble Moons",
    38: "{{X}} Luncheon Volbonan Moons",
    39: "{{X}} Hammer Bro Moon[[s]]",
    41: "{{X}} Luncheon Fire Piranha Plant Moons",
    # Pokio: primary + Pokio Hole (mismo capture en bingo_groups → 2 objectives).
    42: "{{X}} Bowser's Pokio Moons",
    43: "{{X}} Bowser's Jizo Moons",
    44: "Bowser Statue Moon",
    45: "Moon Parabones Moon",
    46: "{{X}} Moon Banzai Bill Moon[[s]]",
    47: "Capture Chargin' Chuck",
}

# Forzar captura principal (kingdom, moon) → id.
# Multilunas con captura (no confundir 1ª/2ª):
#   cascade#2 Broode → Broode's Chomp | sand#4 Knucklotec → Fist (2ª; 1ª=Harriet)
#   wooded#4 Torkdrift → Uproot (2ª; 1ª=Spewart sin captura)
#   metro#1 Mechawiggler → Sherm | luncheon#3 Big Pot → Meat (1ª; 2ª=Cookatiel/Lava Bubble)
#   seaside#5 Mollusque → Gushen | snow#5 Bound Bowl → Shiverian Racer
# Story sand#2 Moon Shards: habitat Moe-Eye (plataformas invisibles)
CURATED_PRIMARY: dict[tuple[str, int], int] = {
    ("cascade", 1): 4,
    ("cascade", 2): 6,
    ("sand", 2): 10,  # Moon Shards in the Sand: Moe-Eye
    ("sand", 4): 13,
    ("wooded", 4): 21,
    ("wooded", 3): 23,  # Path to Secret Flower Field: cañon con Sherm
    ("metro", 1): 23,  # Mechawiggler: Sherm (tanque)
    ("metro", 41): 23,  # Under Siege: Sherm (taxi = transporte)
    ("metro", 42): 23,
    ("seaside", 5): 36,  # Mollusque: Gushen (no Cheep Cheep)
    ("lake", 16): 18,  # Lake Cheep Cheep Moon (captures+npc)
    ("lake", 18): 18,  # Captain Toad: Cheep Cheep (camino oficial; GP alt)
    ("lake", 20): 19,  # A Successful Repair Job: Puzzle Part (Lake)
    ("wooded", 19): 22,  # Fire in the Cave: Fire Bro
    ("luncheon", 31): 22,  # Light the Two Flames: Fire Bro requerido
    ("sand", 36): 11,  # Among the Five Cactuses
    ("sand", 40): 11,  # Wandering Cactus
    ("snow", 23): 34,  # Snowline Circuit Class S
    ("wooded", 47): 21,  # Walking on Clouds: Uproot (beanstalk = acceso)
    ("wooded", 48): 21,  # Above the Clouds: Uproot (beanstalk = acceso)
    ("luncheon", 3): 40,  # Big Pot (1ª multiluna): unica luna Meat
    ("luncheon", 4): 37,  # Cascading Magma: linterna con LB
    ("luncheon", 5): 37,  # Cookatiel (2ª): pelea en Lava Bubble, no Meat
    ("luncheon", 8): 37,  # Jutting Crag: cañón LB
    ("luncheon", 23): 37,  # Taking Notes: Swimming in Magma
    ("luncheon", 27): 37,  # olla Strong Simmer
    ("luncheon", 28): 37,  # olla Extreme Simmer
    ("luncheon", 36): 37,  # Taking Notes: Big Pot Swim
    ("luncheon", 39): 37,  # Magma Narrow Path
    ("luncheon", 40): 37,  # Crossing to the Magma
    # snow#26/#27 = sub_area agua helada (scarecrow abre → mario).
    ("snow", 5): 34,
    ("wooded", 31): 7,
    ("wooded", 32): 7,
    ("wooded", 10): 21,
    ("wooded", 11): 21,  # Tucked Away: Uproot stretch
    ("wooded", 13): 21,  # Nut 'Round the Corner
    ("wooded", 14): 21,  # Climb the Cliff to Get the Nut
    ("wooded", 15): 21,  # Nut in the Red Maze
    ("wooded", 16): 21,  # Nut at the Dead End
    ("wooded", 24): 21,  # Nut Planted in the Tower (par #25)
    ("moon", 9): 44,
    ("moon", 11): 46,  # Around the Barrier Wall
    ("moon", 13): 46,  # Fly to the Treasure Chest and Back
    ("seaside", 1): 36,
    ("seaside", 3): 36,
    ("seaside", 10): 18,  # Underwater Highway Tunnel: Cheep Cheep rompe ladrillos
    ("seaside", 11): 18,  # Shh! It's a Shortcut!
    ("seaside", 12): 18,  # Gap in the Ocean Trench
    ("seaside", 13): 18,  # Slip Through the Nesting Spot
    ("seaside", 39): 18,  # Looking Back in the Dark Waterway (alcoba tunel faro)
    ("wooded", 34): 25,  # mover el arbol
    ("lost", 15): 28,
    ("cap", 8): 2,  # Push-Block Peril — subarea electricidad
    ("cap", 9): 2,  # Hidden Among the Push-Blocks
    ("metro", 39): 2,  # Rewiring — Wire Neighborhood
    ("metro", 40): 2,  # Off the Beaten Wire
    ("wooded", 41): 3,  # Fog subarea: Paragoomba (cohete solo transporte)
    ("wooded", 42): 3,  # Nut Hidden in the Fog
    ("metro", 49): 7,  # T-Rex Chase (scooter = transporte; tematica T-Rex)
    ("metro", 50): 7,  # Big Jump: Escape!
    ("luncheon", 14): 37,  # linterna: Lava Bubble (forma normal)
    ("luncheon", 32): 41,  # linternas lejanas: Fire Piranha
    ("luncheon", 37): 41,  # Magma Swamp shards (Fire Piranha en sala)
    ("luncheon", 38): 41,  # Magma Swamp corner
    ("moon", 10): 45,
    ("sand", 47): 9,  # Underground Treasure Chest: Bullet Bill (no Goomba)
    ("sand", 48): 12,  # Goomba Tower Assembly
    ("wooded", 44): 12,  # Flower Road Reach: torre Goomba (#43 = carrera, sin captura)
    ("snow", 1): 12,  # Icicle Cavern: tag Goomba (story); no cuenta en Goomba Moons
    ("snow", 18): 12,  # Ice-Dodging Goomba Stack (sí en Goomba Moons)
    ("bowser", 2): 42,  # Smart Bombing: Pokio (story; no cuenta en Pokio Moons)
    ("bowser", 4): 42,  # Showdown: Pokio (multi; no cuenta en Pokio Moons)
    ("bowser", 9): 42,  # Past the Moving Wall: Pokio
    ("bowser", 26): 2,  # Found Behind Bars!: Spark Pylon (no Pokio)
    ("sand", 54): 10,  # Invisible Maze: Moe-Eye
    ("sand", 55): 10,
    # snow#26/#27 = sub_area agua helada (scarecrow abre → mario); sin captura.
}

# Lunas del par Lockout que NO heredan la captura del sibling.
NO_SUBAREA_CAPTURE: set[tuple[str, int]] = {
    ("wooded", 43),  # Flower Road Run: llegar al final; Goomba solo en #44
}

# Lunas que no deben asignarse a captura (transporte/camino, no contenido).
# Si una del par Lockout esta aqui, el sibling tambien se excluye.
EXCLUDE_PRIMARY: set[tuple[str, int]] = {
    ("metro", 14),  # basura en tejado; spark/pole solo para llegar
    ("sand", 29),  # TC2: fuera de pool Moe-Eye (captures sin captura de lista)
    # Mini Rocket solo lleva a la subarea; contenido sin captura de lista:
    ("sand", 60),  # Mini Rocket → plataformas sin Cappy
    ("sand", 61),  # Above Strange Neighborhood (bloques ocultos)
    ("metro", 45),  # Hanging from a High-Rise (barras/nubes)
    ("metro", 46),  # Vaulting Up a High-Rise
    ("metro", 43),  # Rotating Maze: Manhole = acceso
    ("metro", 44),
    ("sand", 13),  # On the Lone Pillar: sin captura
    ("snow", 24),  # Rocket Flower dash (transporte/plataformas)
    ("snow", 25),
    # Cheep Cheep / Lava Bubble: lake#3 Crossing = transporte.
    # LB contenido (cañón/notes/narrow) → CURATED; Magma Swamp = plataformas.
    # lake#16/#18 y seaside#10–#13 = Cheep Cheep de contenido (CURATED).
    # snow#26/#27 = sub_area agua helada (cappy).
    ("lake", 3),
    ("seaside", 23),  # Sea Gardening: Gushen solo acelera el crecimiento
    ("seaside", 24),
    ("seaside", 25),
    ("seaside", 26),
    ("snow", 26),  # Jump 'n' Swim: sub_area scarecrow, sin captura
    ("snow", 27),  # Freezing Water Near the Ceiling: idem
    ("luncheon", 29),  # Alcove Behind Pillars: sin captura
    ("luncheon", 37),  # Magma Swamp: plataformas/shards, no LB
    ("luncheon", 38),
    ("wooded", 27),  # Bloom Flower Field: Cappy, no Uproot
    ("wooded", 6),  # Back Way Up the Mountain: Uproot = acceso al 8-bit
    ("lost", 6),  # Avoiding Fuzzies Inside the Wall: 8-bit (puerta), no Wiggler
    # Lakitu de transporte sobre veneno (no pesca) → captures sin lakitu_fishing:
    ("bowser", 10),  # Above the Poison Swamp
}

# Deep Woods: pares Lockout no coinciden con tematica de captura.
_WOOD_SKIP_LOCKOUT = {
    frozenset({30, 31}),
    frozenset({32, 33}),
    frozenset({34, 35}),
}
# Pares tematicos extra (Deep Woods T-Rex brook + hard rock).
_SUBAREA_EXTRA_GROUPS: list[frozenset[tuple[str, int]]] = [
    frozenset({("wooded", 31), ("wooded", 32)}),
]


def load_subarea_groups() -> list[frozenset[tuple[str, int]]]:
    """Pares de lunas de la misma subarea bingo (Level con exactamente 2 lunas)."""
    levels = load_sub_area_levels()
    groups: list[frozenset[tuple[str, int]]] = []
    for g in levels:
        kingdom = g["kingdom"]
        moons = [int(m) for m in g["moons"]]
        if len(moons) == 2:
            groups.append(frozenset((kingdom, m) for m in moons))
    if groups:
        return groups

    # Fallback: overrides Deep Woods tematicos.
    return list(_SUBAREA_EXTRA_GROUPS)


def expand_excludes(
    excludes: set[tuple[str, int]],
    groups: list[frozenset[tuple[str, int]]],
) -> set[tuple[str, int]]:
    """Si una luna del par esta excluida, excluir ambas."""
    out = set(excludes)
    changed = True
    while changed:
        changed = False
        for group in groups:
            if group & out and group - out:
                out |= set(group)
                changed = True
    return out


def resolve_group_capture(
    group: frozenset[tuple[str, int]],
    moon_to_capture: dict[tuple[str, int], int],
) -> int | None:
    """Captura unica del par, o None si hay conflicto / nada que propagar."""
    curated = {CURATED_PRIMARY[m] for m in group if m in CURATED_PRIMARY}
    if len(curated) > 1:
        return None  # p. ej. sand#47 BB vs #48 Goomba
    if len(curated) == 1:
        return next(iter(curated))
    assigned = {moon_to_capture[m] for m in group if m in moon_to_capture}
    if len(assigned) != 1:
        return None
    return next(iter(assigned))


def _clear_non_curated(
    group: frozenset[tuple[str, int]],
    moon_to_capture: dict[tuple[str, int], int],
) -> None:
    for m in group:
        if m not in CURATED_PRIMARY:
            moon_to_capture.pop(m, None)


def _should_skip_subarea_assign(
    m: tuple[str, int],
    registry: dict[tuple[str, int], dict],
    moon_to_capture: dict[tuple[str, int], int],
) -> bool:
    """True si no hay que imponer captura al sibling (story/multi sin curated)."""
    if m not in registry:
        return True
    tags = set(registry[m].get("tags", []))
    return bool(
        tags & {"story_moon", "multi_moon"}
        and m not in CURATED_PRIMARY
        and m not in moon_to_capture
    )


def _assign_subarea_capture(
    group: frozenset[tuple[str, int]],
    cap: int,
    registry: dict[tuple[str, int], dict],
    moon_to_capture: dict[tuple[str, int], int],
) -> None:
    for m in group:
        if m in NO_SUBAREA_CAPTURE:
            moon_to_capture.pop(m, None)
            continue
        if _should_skip_subarea_assign(m, registry, moon_to_capture):
            continue
        moon_to_capture[m] = cap


def apply_subarea_capture_groups(
    registry: dict[tuple[str, int], dict],
    moon_to_capture: dict[tuple[str, int], int],
    excludes: set[tuple[str, int]],
    groups: list[frozenset[tuple[str, int]]],
) -> dict[int, list[str]]:
    """Propaga captura/tematica al sibling si el par comparte una sola captura.

    No unifica si ya hay capturas distintas. No propaga capturas especiales
    (1 luna). No impone captura a story/multi salvo curated.
    """
    for group in groups:
        if group & excludes:
            _clear_non_curated(group, moon_to_capture)
            continue
        cap = resolve_group_capture(group, moon_to_capture)
        if cap is None or cap in SPECIAL_CAPTURE_IDS:
            continue
        _assign_subarea_capture(group, cap, registry, moon_to_capture)

    return rebuild_by_capture(registry, moon_to_capture)


def rebuild_by_capture(
    registry: dict[tuple[str, int], dict],
    moon_to_capture: dict[tuple[str, int], int],
) -> dict[int, list[str]]:
    by_capture: dict[int, list[str]] = defaultdict(list)
    for (kingdom, moon), cap_id in sorted(
        moon_to_capture.items(),
        key=lambda kv: (KINGDOM_COLUMNS.index(kv[0][0]), kv[0][1]),
    ):
        entry = registry.get((kingdom, moon))
        if not entry:
            continue
        by_capture[cap_id].append(moon_label(kingdom, moon, entry["name"]))
    return by_capture


def _parse_moon_key_from_label(label: str) -> tuple[str, int] | None:
    m = re.match(r"^(\w+)#(\d+)", label)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def _existing_keys_from_labels(labels: list[str]) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for label in labels:
        key = _parse_moon_key_from_label(label)
        if key:
            keys.add(key)
    return keys


def _moon_label_sort_key(lab: str) -> tuple[int, int]:
    kd = lab.split("#", 1)[0]
    kd_i = KINGDOM_COLUMNS.index(kd) if kd in KINGDOM_COLUMNS else 99
    m = re.match(r"^\w+#(\d+)", lab)
    return kd_i, int(m.group(1)) if m else 0


def _append_group_raw_moons(
    cap_id: int,
    raws: list,
    by_capture: dict[int, list[str]],
    registry: dict[tuple[str, int], dict],
    existing: set[tuple[str, int]],
) -> None:
    for raw in raws:
        if not isinstance(raw, dict) or "kingdom" not in raw or "moon" not in raw:
            continue
        key = (str(raw["kingdom"]), int(raw["moon"]))
        if key in existing:
            continue
        entry = registry.get(key)
        name = (
            (entry or {}).get("name")
            or raw.get("name")
            or f"Moon {key[1]}"
        )
        by_capture.setdefault(cap_id, []).append(
            moon_label(key[0], key[1], str(name))
        )
        existing.add(key)


def attach_group_capture_moons(
    by_capture: dict[int, list[str]],
    registry: dict[tuple[str, int], dict],
) -> None:
    """Anexa moons[] de bingo_groups con `capture` (acceso/transporte).

    No pisa la captura principal de contenido: la misma luna puede listarse
    bajo Paragoomba (contenido) y Mini Rocket (transporte). Rocket Flower
    no es captura wiki → no tiene fila aqui.
    """
    if not BINGO_GROUPS_PATH.exists():
        return
    name_to_id = {str(c["name"]): int(c["id"]) for c in CAPTURE_LIST}
    for group in load_catalog(BINGO_GROUPS_PATH).get("groups", []):
        cap_name = str(group.get("capture") or "")
        cap_id = name_to_id.get(cap_name)
        if cap_id is None:
            continue
        existing = _existing_keys_from_labels(by_capture.get(cap_id, []))
        raws = list(group.get("moons") or []) + list(group.get("tag_only_moons") or [])
        _append_group_raw_moons(cap_id, raws, by_capture, registry, existing)
        if cap_id in by_capture:
            by_capture[cap_id].sort(key=_moon_label_sort_key)


def enforce_special_single_moon(
    _registry: dict[tuple[str, int], dict],
    moon_to_capture: dict[tuple[str, int], int],
) -> None:
    """Capturas especiales: como mucho 1 luna (preferir curated)."""
    by_cap: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for key, cap_id in moon_to_capture.items():
        if cap_id in SPECIAL_CAPTURE_IDS:
            by_cap[cap_id].append(key)
    for cap_id, keys in by_cap.items():
        if len(keys) <= 1:
            continue
        curated = [k for k in keys if CURATED_PRIMARY.get(k) == cap_id]
        keep = curated[0] if curated else min(keys, key=lambda k: (k[0], k[1]))
        for k in keys:
            if k != keep:
                del moon_to_capture[k]


NAME_PRIMARY: list[tuple[int, re.Pattern[str]]] = [
    (6, re.compile(r"multi moon atop the falls|madame broode", re.I)),
    (34, re.compile(r"bound bowl|class\s*s", re.I)),
    (32, re.compile(r"\brc\s+car\b|remotely captured car", re.I)),
    (43, re.compile(r"\bjizo\b", re.I)),
    (42, re.compile(r"pokio|poking your nose|poking the|spinning tower", re.I)),
    (46, re.compile(r"banzai", re.I)),
    (9, re.compile(r"bullet\s+bill", re.I)),
    (4, re.compile(r"chain\s+chomp|chomp through|nice shot with the chain", re.I)),
    (7, re.compile(r"dinosaur|t-?rex|(?:motor scooter|big jump):\s*escape", re.I)),
    (1, re.compile(r"\bfrog\b", re.I)),
    (12, re.compile(r"goomba|love in the|love by the|love above", re.I)),
    (16, re.compile(r"\bfishing\b|quite a catch", re.I)),
    (18, re.compile(r"cheep\s+cheep", re.I)),
    (15, re.compile(r"glydon|soaring over", re.I)),
    (11, re.compile(r"cactus", re.I)),
    (10, re.compile(r"invisible\s+maze|transparent\s+maze|moe[- ]eye|moon shards in the sand", re.I)),
    (21, re.compile(r"stretch|uproot", re.I)),
    (28, re.compile(r"wiggler|fuzzies|twist.?n.?turn", re.I)),
    (36, re.compile(r"gushen|jetstream|fly through the narrow valley|glass is half full", re.I)),
    (37, re.compile(r"lava\s+bubble|simmer|cascading magma|magma narrow|magma swamp|crossing to the magma", re.I)),
    (38, re.compile(r"fork\s+flick|volbonan", re.I)),
    (22, re.compile(r"fire\s+bro|fire in the cave", re.I)),
    (39, re.compile(r"cheese rocks|hammer\s+bro|golden turnip recipe 3", re.I)),
    (40, re.compile(r"big pot on the volcano|dive in!", re.I)),
    (41, re.compile(r"fire\s+piranha|far-off lanterns", re.I)),
    (24, re.compile(r"treasure made from coins|coin coffer", re.I)),
    (33, re.compile(r"ty-?foo|blowing and sliding", re.I)),
    (17, re.compile(r"unzip|zipper", re.I)),
    (30, re.compile(r"manhole|rotating maze", re.I)),
    (31, re.compile(r"\btaxi\b", re.I)),
    (29, re.compile(r"\bpole\b", re.I)),
    (44, re.compile(r"under the bowser statue", re.I)),
    (25, re.compile(r"moving tree|beneath the roots", re.I)),
    (2, re.compile(r"rewiring|beaten wire|spark pylon", re.I)),
    (3, re.compile(r"poison tide|wandering in the fog|nut hidden in the fog", re.I)),
    (13, re.compile(r"hole in the desert|knucklotec", re.I)),
    (23, re.compile(r"\bsherm\b|pest problem|under siege|sharpshooting|path to the secret flower", re.I)),
    (19, re.compile(r"successful repair|puzzle\s+part", re.I)),
]

# Entidades en descripcion con verbo capture/use/as (refuerzo).
DESC_ENTITIES: list[tuple[int, str]] = [
    (6, r"broode'?s?\s+chain\s+chomp|chain\s+chompikins"),
    (5, r"big\s+chain\s+chomp"),
    (4, r"chain\s+chomp"),
    (13, r"knucklotec"),
    (18, r"cheep\s+cheeps?|purple\s+cheep"),
    (3, r"paragoombas?"),
    (45, r"parabones"),
    (9, r"bullet\s+bills?"),
    (46, r"banzai\s+bills?"),
    (34, r"shiverian\s+racers?"),
    (28, r"tropical\s+wigglers?"),
    (32, r"rc\s+cars?"),
    (2, r"spark\s+pylons?"),
    (10, r"moe[- ]eyes?|invisible\s+maze|transparent\s+maze"),
    (16, r"lakitus?"),
    (15, r"glydons?"),
    (23, r"sherms?"),
    (24, r"coin\s+coffers?"),
    (22, r"fire\s+bros?"),
    (39, r"hammer\s+bros?"),
    (33, r"ty[- ]foos?"),
    (36, r"gushens?"),
    (37, r"lava\s+bubbles?"),
    (40, r"(?:slab\s+of\s+)?meat"),
    (42, r"pokios?"),
    (43, r"jizos?"),
    (30, r"manholes?"),
    (31, r"taxis?"),
    (17, r"zippers?"),
    (8, r"binoculars?"),
    (11, r"cactu(?:s|ses)"),
    (12, r"goombas?|goombette"),
    (7, r"t-?rex(?:es)?"),
    (1, r"frogs?"),
    (25, r"trees?"),
    (26, r"boulders?"),
    (21, r"uproots?"),
    (38, r"volbonans?"),
    (41, r"fire\s+piranha"),
    (20, r"poison\s+piranha"),
    (19, r"puzzle\s+part"),
    (44, r"bowser\s+statue"),
]

NON_LIST_RIDES = re.compile(
    r"\bjaxi\b|\bdorrie\b|motor\s+scooter|rocket\s+flower|mini\s+rocket",
    re.I,
)

TRANSPORT_CAPTURE_IDS = {
    c["id"] for c in CAPTURE_LIST if c.get("transport")
}


def _group_goal_names(group: dict) -> list[str]:
    return [
        str(o.get("goal") or "")
        for o in group.get("objectives") or []
        if o.get("goal")
    ]


def _group_moon_keys(group: dict) -> set[tuple[str, int]]:
    return {
        (str(m["kingdom"]), int(m["moon"]))
        for m in group_moons(group)
        if "kingdom" in m and "moon" in m
    }


def _merge_group_into_pools(
    goals: list[str],
    moons: set[tuple[str, int]],
    is_pool: bool,
    pools: dict[str, set[tuple[str, int]]],
    pool_only: dict[str, set[tuple[str, int]]],
) -> None:
    for goal in goals:
        if is_pool:
            pool_only.setdefault(goal, set()).update(moons)
        pools.setdefault(goal, set()).update(moons)


def load_capture_goal_moon_pools() -> dict[str, set[tuple[str, int]]]:
    """goal Combined → lunas del pool tematico (bingo_groups).

    Usa grupos de un solo objetivo, o grupos con `capture` (evita umbrella
    captures/reinos/flora que mezclan varios goals).

    Si varios grupos declaran el mismo goal, prefiere el pool
    (apply_moon_tag=False); si no, une moons[].
    """
    if not BINGO_GROUPS_PATH.exists():
        return {}
    pools: dict[str, set[tuple[str, int]]] = {}
    pool_only: dict[str, set[tuple[str, int]]] = {}
    for group in load_catalog(BINGO_GROUPS_PATH).get("groups", []):
        goals = _group_goal_names(group)
        if not goals:
            continue
        moons = _group_moon_keys(group)
        is_pool = group.get("apply_moon_tag") is False and len(goals) == 1
        if len(goals) == 1:
            g0 = goals[0]
            if is_pool and moons:
                pool_only.setdefault(g0, set()).update(moons)
            pools.setdefault(g0, set()).update(moons)
            continue
        if group.get("capture") and moons:
            _merge_group_into_pools(goals, moons, is_pool, pools, pool_only)
    for goal, moons in pool_only.items():
        pools[goal] = moons
    return pools


def goals_for_capture_row(cap_id: int, cap_name: str) -> list[str]:
    """Goals Combined de una fila captura (primary + extras del mismo capture).

    Primary = CAPTURE_OBJECTIVE. Extras = otros objectives de bingo_groups con
    el mismo nombre `capture` (p. ej. Pokio Hole junto a Bowser's Pokio).
    """
    ordered: list[str] = []
    seen: set[str] = set()
    primary = CAPTURE_OBJECTIVE.get(cap_id, "") or ""
    if primary:
        ordered.append(primary)
        seen.add(primary)
    if not BINGO_GROUPS_PATH.exists():
        return ordered
    for group in load_catalog(BINGO_GROUPS_PATH).get("groups", []):
        if str(group.get("capture") or "") != cap_name:
            continue
        for o in group.get("objectives") or []:
            goal = str(o.get("goal") or "")
            if goal and goal not in seen:
                ordered.append(goal)
                seen.add(goal)
    return ordered


def moon_label(kingdom: str, moon: int, name: str) -> str:
    return f"{kingdom}#{moon} {name}"


_SCORE_SPECIFIC_IDS = frozenset({6, 13, 34, 32, 40})


def _score_theme_bonus(cap_id: int, name: str) -> int:
    bonus = 0
    if re.search(r"\bfishing\b", name, re.I):
        if cap_id == 16:
            bonus += 40
        elif cap_id == 18:
            bonus -= 40
    if re.search(r"\blove\b", name, re.I) and cap_id == 12:
        bonus += 40
    return bonus


def _score_penalties(cap_id: int, name: str, description: str) -> int:
    penalty = 0
    if cap_id in TRANSPORT_CAPTURE_IDS:
        penalty -= 200
    if cap_id == 14 and re.search(r"rocket\s+flower", f"{name} {description}", re.I):
        penalty -= 100
    if cap_id == 25 and re.search(r"\bon a tree\b", name, re.I):
        penalty -= 30
    return penalty


def score_candidate(
    cap_id: int,
    kingdom: str,
    name: str,
    description: str,
    *,
    from_name: bool,
    from_desc: bool,
) -> int:
    """Mayor = mejor candidata a captura principal."""
    meta = CAPTURE_BY_ID[cap_id]
    score = 0
    if from_name:
        score += 50
    if from_desc:
        score += 20
    if kingdom in meta["reinos"]:
        score += 15
    if cap_id in _SCORE_SPECIFIC_IDS:
        score += 5
    score += _score_theme_bonus(cap_id, name)
    score += _score_penalties(cap_id, name, description)
    return score


def pick_primary(
    kingdom: str,
    moon: int,
    name: str,
    description: str,
) -> int | None:
    key = (kingdom, moon)
    if key in EXCLUDE_PRIMARY:
        return None
    if key in CURATED_PRIMARY:
        return CURATED_PRIMARY[key]

    if NON_LIST_RIDES.search(name):
        return None

    candidates: dict[int, tuple[bool, bool]] = {}

    for cap_id, pattern in NAME_PRIMARY:
        if pattern.search(name):
            candidates[cap_id] = (True, candidates.get(cap_id, (False, False))[1])

    blob = f"{name}. {description}"
    for cap_id, ent in DESC_ENTITIES:
        req = re.compile(
            rf"(?:captur(?:e|es|ed|ing)|as\s+an?|use)\s+(?:\w+\s+){{0,8}}(?:{ent})",
            re.I,
        )
        if req.search(blob):
            name_hit, _ = candidates.get(cap_id, (False, False))
            candidates[cap_id] = (name_hit, True)

    if not candidates:
        return None

    ranked = sorted(
        candidates.items(),
        key=lambda item: score_candidate(
            item[0],
            kingdom,
            name,
            description,
            from_name=item[1][0],
            from_desc=item[1][1],
        ),
        reverse=True,
    )
    best_id, best_score_pair = ranked[0]
    best_score = score_candidate(
        best_id,
        kingdom,
        name,
        description,
        from_name=best_score_pair[0],
        from_desc=best_score_pair[1],
    )
    if best_score < 10:
        return None
    if best_id in TRANSPORT_CAPTURE_IDS:
        return None
    return best_id


def load_guides() -> dict[str, dict[int, dict[str, str]]]:
    guides: dict[str, dict[int, dict[str, str]]] = {}
    for kingdom in KINGDOM_COLUMNS:
        url = MARIOWIKI_URLS.get(kingdom)
        if not url:
            guides[kingdom] = {}
            continue
        print(f"  Mario Wiki: {KINGDOM_DISPLAY.get(kingdom, kingdom)}...")
        try:
            guides[kingdom] = parse_mariowiki_table(fetch(url))
        except Exception as exc:  # noqa: BLE001
            print(f"    AVISO: {exc}")
            guides[kingdom] = {}
        time.sleep(0.3)
    return guides


def _kingdom_sort_key(kv: tuple[tuple[str, int], dict]) -> tuple[int, int]:
    kingdom, moon = kv[0]
    try:
        return (KINGDOM_COLUMNS.index(kingdom), moon)
    except ValueError:
        return (len(KINGDOM_COLUMNS), moon)


def _assign_primary_captures(
    registry: dict[tuple[str, int], dict],
    guides: dict[str, dict[int, dict[str, str]]],
    excludes: set[tuple[str, int]],
) -> tuple[dict[tuple[str, int], int], int]:
    moon_to_capture: dict[tuple[str, int], int] = {}
    skipped = 0
    for (kingdom, moon), entry in sorted(registry.items(), key=_kingdom_sort_key):
        name = entry["name"]
        guide = guides.get(kingdom, {}).get(moon) or {}
        desc = guide.get("description", "")
        if (kingdom, moon) in excludes:
            continue
        if (kingdom, moon) not in CURATED_PRIMARY:
            if NON_LIST_RIDES.search(name) or NON_LIST_RIDES.search(desc):
                continue
        primary = pick_primary(kingdom, moon, name, desc)
        if primary is None:
            if "captures" in entry["tags"]:
                skipped += 1
            continue
        moon_to_capture[(kingdom, moon)] = primary
    return moon_to_capture, skipped


def parse_moon_label(
    label: str,
    registry: dict[tuple[str, int], dict],
    *,
    counts_for_goal: bool,
) -> dict[str, object]:
    m = re.match(r"^([a-z]+)#(\d+) (.+)$", label.strip())
    if m:
        ref: dict[str, object] = {
            "kingdom": m.group(1),
            "moon": int(m.group(2)),
            "name": m.group(3),
            "goal": counts_for_goal,
        }
        return enrich_moon_ref_odyssey(ref, registry)
    return {"label": label, "goal": counts_for_goal}


def capture_kind(n_objectives: int, n_moons: int) -> str:
    if n_objectives and n_moons:
        return "both"
    if n_objectives:
        return "objectives"
    if n_moons:
        return "moons"
    return "empty"


def moon_tag_for(name: str) -> str:
    if name in CAPTURE_NAME_TO_TAG:
        return CAPTURE_NAME_TO_TAG[name]
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _kingdoms_from_labels(moon_labels: list[str], meta: dict) -> list[str]:
    kingdoms_found: list[str] = []
    for label in moon_labels:
        k = label.split("#", 1)[0]
        if k not in kingdoms_found:
            kingdoms_found.append(k)
    return kingdoms_found or list(meta.get("reinos") or [])


def _n_moons_for_tipo(
    meta: dict,
    moon_labels: list[str],
    primary_goal: str,
    by_capture: dict[int, list[str]],
) -> int:
    n_for_tipo = len(moon_labels)
    if (
        primary_goal
        and not meta.get("special")
        and not meta.get("transport")
        and not meta.get("postgame")
    ):
        peers = [cid for cid, g in CAPTURE_OBJECTIVE.items() if g == primary_goal]
        if len(peers) > 1:
            n_for_tipo = sum(len(by_capture.get(cid, [])) for cid in peers)
    return n_for_tipo


def _capture_tipo(meta: dict, n_for_tipo: int) -> str:
    if meta.get("transport"):
        return "transporte"
    if meta.get("postgame"):
        return "postgame"
    if meta.get("special"):
        return "especial"
    if n_for_tipo >= CAPTURE_TAG_MIN:
        return "normal"
    return "minoritaria"


def _build_capture_moons(
    moon_labels: list[str],
    goals: list[str],
    goal_pools: dict[str, set[tuple[str, int]]],
    registry: dict[tuple[str, int], dict],
) -> list[dict[str, object]]:
    pool: set[tuple[str, int]] = set()
    for goal in goals:
        pool |= goal_pools.get(goal, set())
    moons: list[dict[str, object]] = []
    for label in moon_labels:
        m = re.match(r"^(\w+)#(\d+)\s+", label.strip())
        key = (m.group(1), int(m.group(2))) if m else ("", 0)
        moons.append(
            parse_moon_label(label, registry, counts_for_goal=key in pool)
        )
    return moons


def _build_capture_row(
    meta: dict,
    by_capture: dict[int, list[str]],
    goal_pools: dict[str, set[tuple[str, int]]],
    combined: dict,
    registry: dict[tuple[str, int], dict],
) -> dict[str, object]:
    cap_id = meta["id"]
    moon_labels = by_capture.get(cap_id, [])
    kingdoms_found = _kingdoms_from_labels(moon_labels, meta)
    goals = goals_for_capture_row(int(cap_id), str(meta["name"]))
    primary_goal = goals[0] if goals else ""
    n_for_tipo = _n_moons_for_tipo(meta, moon_labels, primary_goal, by_capture)
    tipo = _capture_tipo(meta, n_for_tipo)
    moons = _build_capture_moons(moon_labels, goals, goal_pools, registry)
    n_goal_moons = sum(1 for moon in moons if moon.get("goal") is True)
    objectives: list[dict] = [
        objective_ref_from_combined(goal, combined.get(goal)) for goal in goals
    ]
    row: dict[str, object] = {
        "id": int(cap_id),
        "capture": meta["name"],
        "tipo": tipo,
        "kind": capture_kind(len(objectives), len(moons)),
        "n_objectives": len(objectives),
        "n_moons": len(moons),
        "n_goal_moons": n_goal_moons,
        "objectives": objectives,
        "moons": moons,
    }
    if kingdoms_found:
        row["kingdom"] = kingdoms_found[0]
    if tipo == "normal":
        row["moon_tag"] = moon_tag_for(str(meta["name"]))
    if int(cap_id) == 8:
        from goal_list_lib import curated_list

        lista = curated_list("binoculars")
        row["pool"] = "lista"
        row["n_lista"] = len(lista)
        row["lista"] = lista
    return row


def _print_capturas_summary(
    rows: list[dict[str, object]],
    moon_to_capture: dict[tuple[str, int], int],
    skipped: int,
) -> None:
    print(f"\nExportado: {OUT_JSON.relative_to(ROOT).as_posix()}")
    print(
        f"Capturas listadas: {len(rows)} "
        f"(wiki={len(CAPTURE_LIST)}; transporte/postgame incluidos)"
    )
    print(f"Lunas asignadas: {len(moon_to_capture)}")
    vacias = sum(1 for r in rows if int(r["n_moons"]) == 0)
    if vacias:
        print(f"Capturas sin lunas: {vacias}")
    transport_n = sum(1 for r in rows if r["tipo"] == "transporte")
    postgame_n = sum(1 for r in rows if r["tipo"] == "postgame")
    if transport_n or postgame_n:
        print(f"Transporte: {transport_n}; postgame/fuera: {postgame_n}")
    if skipped:
        print(f"Lunas con tag captures sin asignar: {skipped}")
    dup_check: dict[tuple[str, int], list[int]] = defaultdict(list)
    for (k, m), cap_id in moon_to_capture.items():
        dup_check[(k, m)].append(cap_id)
    multi = {km: ids for km, ids in dup_check.items() if len(ids) > 1}
    if multi:
        print(f"AVISO: lunas con varias capturas: {len(multi)}")


def main() -> None:
    print("Cargando lunas y guias...")
    registry = build_matrix_moon_registry()
    guides = load_guides()
    subarea_groups = load_subarea_groups()
    excludes = expand_excludes(EXCLUDE_PRIMARY, subarea_groups)
    excludes -= set(CURATED_PRIMARY)

    moon_to_capture, skipped = _assign_primary_captures(registry, guides, excludes)
    apply_subarea_capture_groups(
        registry, moon_to_capture, excludes, subarea_groups
    )
    enforce_special_single_moon(registry, moon_to_capture)
    by_capture = rebuild_by_capture(registry, moon_to_capture)
    attach_group_capture_moons(by_capture, registry)
    goal_pools = load_capture_goal_moon_pools()
    combined = load_combined_objectives_by_goal(include_disabled=True)

    rows: list[dict[str, object]] = [
        _build_capture_row(meta, by_capture, goal_pools, combined, registry)
        for meta in CAPTURE_LIST
    ]

    n_with_moons = sum(1 for r in rows if int(r["n_moons"]) > 0)
    n_with_goal = sum(1 for r in rows if int(r["n_objectives"]) > 0)
    payload = {
        "_definition": (
            "Capturas in-game (wiki) con lunas in-scope asignadas. "
            "Formato alineado con bingo_groups / goals_referencia: "
            "id (wiki), capture, tipo, kind, n_objectives, n_moons, n_goal_moons, "
            "objectives[{goal,range,progression,…}], moons[{kingdom,moon,name,goal}], kingdom "
            "(primer reino; el resto se ve en moons/lista), "
            "moon_tag si tipo=normal. moons[].goal=true si la luna cuenta para "
            "alguna goal Combined de la captura (union de pools); false si solo "
            "es captura tematica / sin goal propia. Una captura puede listar "
            "2+ goals (Pokio + Pokio Hole). Acceso/transporte: moons del grupo "
            "bingo anexadas (pueden repetir en captura de contenido; "
            "Rocket Flower no es captura). Binoculars: pool=lista + lista[] "
            "(ubicaciones). Una captura principal por luna. "
            "tipo=normal|especial|minoritaria|transporte|postgame."
        ),
        "_note": "Regenerar con export_capturas_lunas.py o regenerate_all.py.",
        "n_captures": len(rows),
        "n_with_moons": n_with_moons,
        "n_with_goal": n_with_goal,
        "captures": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    write_catalog_json(OUT_JSON, payload)

    legacy_csv = ROOT / "capturas-lunas.csv"
    if legacy_csv.exists():
        legacy_csv.unlink()
        print(f"Eliminado: {legacy_csv.name}")

    _print_capturas_summary(rows, moon_to_capture, skipped)


if __name__ == "__main__":
    main()
