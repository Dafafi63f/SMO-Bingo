"""Exporta capturas del juego con lunas relacionadas (una captura principal por luna).

Reglas:
  - Cada luna tiene como mucho UNA captura principal (forma normal / tematica).
  - Capturas multi-reino: se listan todas las lunas de todos los reinos.
  - moons[] = captura real (asignacion primaria / curated) + tematica del pool
    bingo_groups de las goals de la fila (transporte, tag_only, multiluna…).
    goal=true si cuenta en alguna goal Combined de la fila; goal=false lleva
    tag=true (tematica sin contar en la goal).
  - Subarea: la captura/tematica aplica a ambas lunas del par cuando es
    la misma. Si cada luna pide captura distinta (p. ej. BB + Goomba en
    Underground Temple), no se unifican. Tipos (8bit, chest, shards…) no
    se copian entre el par.
  - Lista las capturas in-game in-scope (sin Picture Match / postgame Bowser,
    Letter, Puzzle Metro, Yoshi). Acceso/transporte (Mini Rocket, Taxi,
    Manhole, Pole): moons del grupo bingo en la fila de captura wiki. Rocket
    Flower no es captura wiki.
  - Fire Bro + Hammer Bro: filas y goals Combined distintas; Unique Captures
    también las cuenta por separado.
  - Capturas especiales (``special``): ≤2 lunas asignadas (Meat, Boulder,
    Fire Bro, RC Car, capturas Moon…). Excepción: Binoculars (muchas
    ubicaciones; no special). Transporte no usa special. tipo=especial.
  - Normales con < CAPTURE_TAG_MIN lunas: tipo=minoritaria (solo `captures`).
  - Normales con ≥ CAPTURE_TAG_MIN: tipo=normal (tag concreta / moon_tag).
  - CAPTURE_NO_CONCRETE_TAGS (p. ej. Moe-Eye n=3): tipo=minoritaria pese al
    umbral; grupo con apply_moon_tag=False.
  - objectives[]: goal(s) Combined de bingo_groups con el mismo `capture`
    (Pokio = Bowser's Pokio + Pokio Hole). Vacio = sin goal propia.

Salida: Catalog/capturas_lunas.json (formato tipo bingo_groups / goals_referencia).

Usage:
  python export_capturas_lunas.py
"""
from __future__ import annotations

import re
from collections import defaultdict

from catalog_lib import (
    BINGO_GROUPS_PATH,
    CAPTURE_NAME_TO_TAG,
    CAPTURE_NO_CONCRETE_TAGS,
    CAPTURE_TAG_MIN,
    CATALOG_DIR,
    KINGDOM_COLUMNS,
    ROOT,
    _resolve_bingo_group_moons_raw,
    build_matrix_moon_registry,
    enrich_moon_ref_odyssey,
    group_moons,
    load_bingo_groups,
    load_combined_objectives_by_goal,
    load_sub_area_levels,
    objective_ref_from_combined,
    write_catalog_json,
)
from mariowiki_guides import load_capture_guides

OUT_JSON = CATALOG_DIR / "capturas_lunas.json"

# Lista in-game in-scope (sin postgame / Picture Match).
# reinos: donde puede aparecer la captura (no solo el primer encuentro).
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
        "sand", "cascade", "lake", "wooded", "lost",
        "metro", "seaside", "luncheon", "bowser", "moon",
    ], "postgame": False},
    # Binoculars: excepción a special pese a 0 lunas (ubicaciones en
    # BINOCULARS_LISTA → capturas_lunas.lista[]; no lists.binoculars).
    # Primer reino = sand (3 ubicaciones). Conteos:
    # cap0+cascade0 (postgame) sand3 | lake1 wooded2 lost1 | metro1
    # snow0 seaside≥3 | luncheon1 bowser1 moon1 → techos e/m/l/n=4/8/12/14
    # → rango [3,6,9,12].
    {"id": 9, "name": "Bullet Bill", "reinos": ["sand", "metro"], "postgame": False},
    {"id": 10, "name": "Moe-Eye", "reinos": ["sand"], "postgame": False},
    # Cactus = Tree (goal Cactus/Tree); ≤2 lunas → special.
    {"id": 11, "name": "Cactus", "reinos": ["sand"], "postgame": False, "special": True},
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
    {"id": 22, "name": "Fire Bro", "reinos": ["wooded", "luncheon"], "postgame": False, "special": True},
    {"id": 23, "name": "Sherm", "reinos": ["wooded", "metro"], "postgame": False},
    {"id": 24, "name": "Coin Coffer", "reinos": ["wooded"], "postgame": False, "special": True},
    {"id": 25, "name": "Tree", "reinos": ["wooded"], "postgame": False, "special": True},
    {"id": 26, "name": "Boulder", "reinos": ["wooded"], "postgame": False, "special": True},
    # Boulder: 0 lunas (Deep Woods) → Capture Boulder (Wooded).
    {"id": 28, "name": "Tropical Wiggler", "reinos": ["lost"], "postgame": False},
    {"id": 29, "name": "Pole", "reinos": ["metro", "wooded"], "postgame": False, "transport": True},
    # Pole: barras → swinging_pole (como Mini Rocket/Taxi/Manhole).
    {"id": 30, "name": "Manhole", "reinos": ["metro"], "postgame": False, "transport": True},
    # Manhole: acceso sub_area; goal Metro Manhole Moons.
    {"id": 31, "name": "Taxi", "reinos": ["metro"], "postgame": False, "transport": True},
    {"id": 32, "name": "RC Car", "reinos": ["metro"], "postgame": False, "special": True},
    {"id": 33, "name": "Ty-foo", "reinos": ["snow"], "postgame": False},
    {"id": 34, "name": "Shiverian Racer", "reinos": ["snow"], "postgame": False, "special": True},
    # Cheep Cheep nieve: 0 Moon Get in-scope → Capture Snow Cheep Cheep (como Boulder).
    {"id": 35, "name": "Cheep Cheep (Snow Kingdom)", "reinos": ["snow"], "postgame": False, "special": True},
    {"id": 36, "name": "Gushen", "reinos": ["seaside"], "postgame": False},
    {"id": 37, "name": "Lava Bubble", "reinos": ["luncheon"], "postgame": False},
    {"id": 38, "name": "Volbonan", "reinos": ["luncheon"], "postgame": False, "special": True},
    {"id": 39, "name": "Hammer Bro", "reinos": ["luncheon"], "postgame": False},
    {"id": 40, "name": "Meat", "reinos": ["luncheon"], "postgame": False, "special": True},
    # Meat: luncheon#3 Big Pot (1ª multiluna); goal Luncheon Multi-Moon[[s]].
    {"id": 41, "name": "Fire Piranha Plant", "reinos": ["luncheon"], "postgame": False},
    # Fire Piranha: #32 linternas + Magma Swamp #37+#38.
    {"id": 42, "name": "Pokio", "reinos": ["bowser"], "postgame": False},
    {"id": 43, "name": "Jizo", "reinos": ["bowser"], "postgame": False},
    {"id": 44, "name": "Bowser statue", "reinos": ["moon"], "postgame": False, "special": True},
    {"id": 45, "name": "Parabones", "reinos": ["moon"], "postgame": False, "special": True},
    # Moon Kingdom: capturas exclusivas = special (Banzai Bill 2 lunas curated).
    {"id": 46, "name": "Banzai Bill", "reinos": ["moon"], "postgame": False, "special": True},
    {"id": 47, "name": "Chargin' Chuck", "reinos": ["moon"], "postgame": False, "special": True},
    # Chargin' Chuck: 0 lunas → Capture Chargin' Chuck (Moon).
]

CAPTURE_BY_ID = {c["id"]: c for c in CAPTURE_LIST}
SPECIAL_CAPTURE_IDS = {c["id"] for c in CAPTURE_LIST if c.get("special")}
# Compat: ya no hay merges wiki→Unique (Fire/Hammer Bro van separados).
CAPTURE_MERGE_INTO: dict[int, int] = {}
CAPTURE_MERGE_DISPLAY: dict[int, str] = {}

# Ubicaciones Binoculars (fuente Catalog/capturas_lunas.json; no goal_lists).
# Cap + Cascade fuera (postgame); mismo criterio que stickers Moon/Mushroom.
BINOCULARS_LISTA: list[dict] = [
    {"kingdom": "sand", "id": 1, "id_list": 1, "name": "Sand binocular 1", "disponibilidad": "base"},
    {"kingdom": "sand", "id": 2, "id_list": 2, "name": "Sand binocular 2", "disponibilidad": "base"},
    {"kingdom": "sand", "id": 3, "id_list": 3, "name": "Sand binocular 3", "disponibilidad": "base"},
    {"kingdom": "lake", "id": 4, "id_list": 4, "name": "Lake binocular", "disponibilidad": "base"},
    {"kingdom": "wooded", "id": 5, "id_list": 5, "name": "Wooded binocular 1", "disponibilidad": "base"},
    {"kingdom": "wooded", "id": 6, "id_list": 6, "name": "Wooded binocular 2", "disponibilidad": "mid_story"},
    {"kingdom": "lost", "id": 7, "id_list": 7, "name": "Lost binocular", "disponibilidad": "base"},
    {"kingdom": "metro", "id": 8, "id_list": 8, "name": "Metro binocular", "disponibilidad": "mid_story"},
    {"kingdom": "seaside", "id": 9, "id_list": 9, "name": "Seaside binocular 1", "disponibilidad": "base"},
    {"kingdom": "seaside", "id": 10, "id_list": 10, "name": "Seaside binocular 2", "disponibilidad": "base"},
    {"kingdom": "seaside", "id": 11, "id_list": 11, "name": "Seaside binocular 3", "disponibilidad": "base"},
    {"kingdom": "luncheon", "id": 12, "id_list": 12, "name": "Luncheon binocular", "disponibilidad": "base"},
    {"kingdom": "bowser", "id": 13, "id_list": 13, "name": "Bowser's binocular", "disponibilidad": "base"},
    {"kingdom": "moon", "id": 14, "id_list": 14, "name": "Moon binocular", "disponibilidad": "base"},
]

# Peleas de jefe con captura (goal_lists bosses; enlace moon = multiluna pareada).
CAPTURE_BOSSES_LISTA: list[dict] = [
    {
        "capture_id": 6,
        "kingdom": "cascade",
        "id": 2,
        "id_list": 2,
        "name": "Madame Broode (Broodal)",
        "disponibilidad": "base",
        "moon": 2,
    },
    {
        "capture_id": 6,
        "kingdom": "moon",
        "id": 19,
        "id_list": 19,
        "name": "Madame Broode (Broodal, rematch)",
        "disponibilidad": "base",
    },
    {
        "capture_id": 13,
        "kingdom": "sand",
        "id": 4,
        "id_list": 4,
        "name": "Knucklotec (Boss)",
        "disponibilidad": "mid_story",
        "moon": 4,
    },
    {
        "capture_id": 21,
        "kingdom": "wooded",
        "id": 7,
        "id_list": 7,
        "name": "Torkdrift (Boss)",
        "disponibilidad": "mid_story",
        "moon": 4,
    },
    {
        "capture_id": 23,
        "kingdom": "metro",
        "id": 10,
        "id_list": 10,
        "name": "Mecha Wiggler (Boss)",
        "disponibilidad": "base",
        "moon": 1,
    },
    {
        "capture_id": 36,
        "kingdom": "seaside",
        "id": 12,
        "id_list": 12,
        "name": "Mollusque-Lanceur (Boss)",
        "disponibilidad": "base",
        "moon": 5,
    },
    {
        "capture_id": 37,
        "kingdom": "luncheon",
        "id": 14,
        "id_list": 14,
        "name": "Cookatiel (Boss)",
        "disponibilidad": "mid_story",
        "moon": 5,
    },
    {
        "capture_id": 42,
        "kingdom": "bowser",
        "id": 18,
        "id_list": 18,
        "name": "RoboBrood (Broodal)",
        "disponibilidad": "base",
        "moon": 4,
    },
]


def _lista_item(raw: dict, source: str) -> dict:
    out = {k: v for k, v in raw.items() if k != "capture_id"}
    out["source"] = source
    return out


def _lista_for_capture(cap_id: int) -> list[dict]:
    if int(cap_id) == 8:
        return [_lista_item(x, "binoculars") for x in BINOCULARS_LISTA]
    out: list[dict] = []
    for raw in CAPTURE_BOSSES_LISTA:
        if int(raw["capture_id"]) != int(cap_id):
            continue
        out.append(_lista_item(raw, "bosses"))
    return out


def _attach_row_arrays(
    row: dict[str, object],
    *,
    objectives: list[dict],
    lista: list[dict],
    moons: list[dict],
) -> None:
    """En capturas_lunas omitir claves cuyo valor sería []. Orden: objectives → moons → lista."""
    if objectives:
        row["objectives"] = objectives
    if moons:
        row["moons"] = moons
    if lista:
        row["n_lista"] = len(lista)
        row["lista"] = lista
        if int(row["n_moons"]) == 0:
            row["pool"] = "lista"


def _capturas_global_stats(rows: list[dict[str, object]]) -> dict[str, int]:
    """Totales de cabecera (objectives, lista, moons[] listados/únicos/goal)."""
    n_objectives_total = 0
    n_lista_total = 0
    n_goal_moons = 0
    n_goal_false = 0
    n_moons_listed = 0
    unique_keys: set[tuple[str, int]] = set()
    unique_goal_true: set[tuple[str, int]] = set()
    for row in rows:
        n_objectives_total += int(row.get("n_objectives") or 0)
        lista = row.get("lista") or []
        n_lista_total += len(lista)
        for moon in row.get("moons") or []:
            n_moons_listed += 1
            key = (str(moon["kingdom"]), int(moon["moon"]))
            unique_keys.add(key)
            if moon.get("goal") is True:
                n_goal_moons += 1
                unique_goal_true.add(key)
            else:
                n_goal_false += 1
    return {
        "n_objectives_total": n_objectives_total,
        "n_lista_total": n_lista_total,
        "n_moons_listed": n_moons_listed,
        "n_moons_unique": len(unique_keys),
        "n_goal_moons": n_goal_moons,
        "n_goal_moons_unique": len(unique_goal_true),
        "n_goal_false": n_goal_false,
    }


# Goal Combined dedicada por captura (CSV columna objetivo). Cerrado por ahora.
CAPTURE_OBJECTIVE: dict[int, str] = {
    1: "{{X}} Cap Frog Moons",
    2: "{{X}} Spark Pylon Moons",
    3: "{{X}} Paragoomba Moons",
    4: "{{X}} Cascade Chain Chomp Moons",
    5: "Capture Big Chain Chomp",
    6: "Defeat Madame Broode in Moon Kingdom",
    7: "{{X}} T-Rex Moons",
    8: "Capture {{X}} Binoculars",
    9: "{{X}} Bullet Bill Moons",
    10: "{{X}} Sand Moe-Eye Moons",
    11: "{{X}} Cactus/Tree Moons",
    12: "{{X}} Goomba Moon[[s]]",
    13: "{{X}} Sand Multi-Moon[[s]]",
    14: "{{X}} Mini Rocket Moons",
    15: "{{X}} Glydon Moon[[s]]",
    16: "{{X}} Lakitu-Fishing Moon[[s]]",
    17: "{{X}} Lake Zipper Moons",
    18: "{{X}} Cheep Cheep Moons",
    19: "{{X}} Puzzle Moon[[s]]",
    20: "Capture Poison Piranha Plant",
    21: "{{X}} Seaside Uproot Moons",
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
    39: "{{X}} Hammer Bro Moons",
    40: "{{X}} Luncheon Multi-Moon[[s]]",
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
# Story sand#2 Moon Shards: habitat Moe-Eye (plataformas invisibles; fuera del
# pool Combined Sand Moe-Eye Moons → goal:false en capturas).
CURATED_PRIMARY: dict[tuple[str, int], int] = {
    ("cascade", 1): 4,
    ("cascade", 2): 6,
    ("sand", 2): 10,  # Moon Shards: Moe-Eye (no cuenta en goal Combined)
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
    # wooded#47/#48 Cloud Walking: beanstalk (sin fila Uproot)
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
    ("wooded", 10): 21,  # nuts: captura Uproot, goal:false (pool = Seaside)
    ("wooded", 11): 21,
    ("wooded", 13): 21,
    ("wooded", 14): 21,
    ("wooded", 15): 21,
    ("wooded", 16): 21,
    ("wooded", 24): 21,
    ("wooded", 25): 21,  # Stretching Your Legs: sin goal de momento
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
    ("metro", 6): 30,  # Powering Up the Station: manhole story (no goal)
    ("wooded", 41): 3,  # Fog subarea: Paragoomba (cohete solo transporte)
    ("wooded", 42): 3,  # Nut Hidden in the Fog
    ("wooded", 33): 24,  # Coin Coffer: Special Seed moon
    ("luncheon", 2): 39,  # Under the Cheese Rocks: Hammer Bro
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
    ("sand", 29): 10,  # TC2: Moe-Eye (sí en pool Sand Moe-Eye Moons)
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
    # Mini Rocket solo lleva a la subarea; contenido sin captura de lista:
    ("sand", 60),  # Mini Rocket → plataformas sin Cappy
    ("sand", 61),  # Above Strange Neighborhood (bloques ocultos)
    ("metro", 45),  # Hanging from a High-Rise (barras/nubes)
    ("metro", 46),  # Vaulting Up a High-Rise
    ("metro", 43),  # Rotating Maze: Manhole = acceso
    ("metro", 44),
    ("sand", 13),  # On the Lone Pillar: sin captura
    # BB opcional (wiki dice "capture Bullet Bill"); tag/goal = mario, no bullet_bill.
    ("sand", 7),   # On the Leaning Pillar
    ("sand", 11),  # On Top of the Stone Archway
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
    # Meta `capture` vive en specs; load_bingo_groups() la reinyecta.
    name_to_id = {
        str(c["name"]).casefold(): int(c["id"]) for c in CAPTURE_LIST
    }
    for group in load_bingo_groups():
        cap_name = str(group.get("capture") or "")
        cap_id = name_to_id.get(cap_name.casefold())
        if cap_id is None:
            continue
        existing = _existing_keys_from_labels(by_capture.get(cap_id, []))
        raws = list(group.get("moons") or []) + list(group.get("tag_only_moons") or [])
        _append_group_raw_moons(cap_id, raws, by_capture, registry, existing)
        if cap_id in by_capture:
            by_capture[cap_id].sort(key=_moon_label_sort_key)


def _skip_goal_pool_attachment(
    key: tuple[str, int], cap_id: int, existing: set[tuple[str, int]]
) -> bool:
    if key in existing:
        return True
    if cap_id in CAPTURE_GOAL_POOL_CURATED_ONLY:
        return CURATED_PRIMARY.get(key) != cap_id
    return False


def _attach_one_goal_pool_key(
    by_capture: dict[int, list[str]],
    cap_id: int,
    key: tuple[str, int],
    registry: dict[tuple[str, int], dict],
    existing: set[tuple[str, int]],
) -> None:
    entry = registry.get(key)
    name = (entry or {}).get("name") or f"Moon {key[1]}"
    by_capture.setdefault(cap_id, []).append(
        moon_label(key[0], key[1], str(name))
    )
    existing.add(key)


def attach_capture_goal_pool_moons(
    by_capture: dict[int, list[str]],
    registry: dict[tuple[str, int], dict],
    goal_pools: dict[str, set[tuple[str, int]]],
) -> None:
    """Anexa lunas del pool tematico de cada goal Combined de la fila capture."""
    for meta in CAPTURE_LIST:
        cap_id = int(meta["id"])
        goals = goals_for_capture_row(cap_id, str(meta["name"]))
        existing = _existing_keys_from_labels(by_capture.get(cap_id, []))
        for goal in goals:
            for key in goal_pools.get(goal, set()):
                if _skip_goal_pool_attachment(key, cap_id, existing):
                    continue
                _attach_one_goal_pool_key(
                    by_capture, cap_id, key, registry, existing
                )
        if cap_id in by_capture:
            by_capture[cap_id].sort(key=_moon_label_sort_key)


def enforce_special_single_moon(
    _registry: dict[tuple[str, int], dict],
    moon_to_capture: dict[tuple[str, int], int],
) -> None:
    """Capturas ``special``: ≤1 luna auto; si hay varias curated, se conservan todas."""
    by_cap: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for key, cap_id in moon_to_capture.items():
        if cap_id in SPECIAL_CAPTURE_IDS:
            by_cap[cap_id].append(key)
    for cap_id, keys in by_cap.items():
        if len(keys) <= 1:
            continue
        curated = [k for k in keys if CURATED_PRIMARY.get(k) == cap_id]
        if len(curated) > 1:
            keep = set(curated)
        elif curated:
            keep = {curated[0]}
        else:
            keep = {min(keys, key=lambda k: (k[0], k[1]))}
        for k in keys:
            if k not in keep:
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


def _group_goal_pool_moon_keys(group: dict) -> set[tuple[str, int]]:
    """Lunas que cuentan para goals Combined (excluye tag_only goal=false)."""
    return {
        (str(m["kingdom"]), int(m["moon"]))
        for m in group_moons(group)
        if "kingdom" in m and "moon" in m and m.get("goal") is not False
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


# multilunas por reino → goal Combined dedicada (grupo multi_moon; ver sync SPEC).
_MULTI_MOON_GOAL_BY_KINGDOM: dict[str, str] = {
    "sand": "{{X}} Sand Multi-Moon[[s]]",
    "wooded": "{{X}} Wooded Multi-Moon[[s]]",
    "metro": "{{X}} Metro Multi-Moon[[s]]",
    "luncheon": "{{X}} Luncheon Multi-Moon[[s]]",
    "snow": "Snow Multi-Moon",
    "seaside": "Seaside Multi-Moon",
}

# Curated en pool captures que siguen tag-only (multiluna/story sin goal Combined de fila).
CURATED_GOAL_FALSE_KEYS: frozenset[tuple[str, int]] = frozenset({
    ("cascade", 2),   # Broode multiluna
    ("luncheon", 4),  # Cascading Magma (story; LB de acceso)
    ("luncheon", 5),  # Cookatiel (boss multiluna; lista)
    ("wooded", 4),    # Torkdrift multiluna (sin uproot#4 en grupo)
    ("wooded", 10),   # nuts wooded: captura Uproot, no Seaside Uproot Moons
    ("wooded", 11),
    ("wooded", 13),
    ("wooded", 14),
    ("wooded", 15),
    ("wooded", 16),
    ("wooded", 24),
    ("wooded", 25),   # Stretching Your Legs: sin goal de momento
    ("bowser", 2),    # Smart Bombing (story Pokio)
    ("bowser", 4),    # RoboBrood multiluna (sin pokio#2/#4 en grupo)
    ("luncheon", 2),  # Under the Cheese Rocks (story; sin hammer_bro#2)
    ("metro", 6),     # Powering Up the Station (story; manhole acceso)
})

# Pool Combined compartido entre capturas: solo anexar lunas curated de la fila.
CAPTURE_GOAL_POOL_CURATED_ONLY: frozenset[int] = frozenset({19})  # Puzzle Part Lake

# Misma goal Combined, capturas distintas: la luna del otro tipo = goal:false.
CAPTURE_PEER_GOAL_FALSE_KEYS: dict[int, frozenset[tuple[str, int]]] = {
    11: frozenset({("wooded", 34)}),  # Cactus: tree moon tag-only
    25: frozenset({("sand", 36), ("sand", 40)}),  # Tree: cactus moons tag-only
}


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
    for group in load_bingo_groups():
        goals = _group_goal_names(group)
        if not goals:
            continue
        moons = _group_goal_pool_moon_keys(group)
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


def compute_real_capture_moon_keys(
    *,
    registry: dict | None = None,
    fetch_guides: bool = True,
) -> frozenset[tuple[str, int]]:
    """Lunas con captura real (requisito), no solo tematica o transporte.

    Criterio: asignacion primaria + la luna esta en el pool de alguna goal
    Combined de esa captura (bingo_groups). El resto vive en otros grupos.
    """
    registry = registry or build_matrix_moon_registry()
    guides = load_capture_guides() if fetch_guides else {k: {} for k in KINGDOM_COLUMNS}
    subarea_groups = load_subarea_groups()
    excludes = expand_excludes(EXCLUDE_PRIMARY, subarea_groups)
    excludes -= set(CURATED_PRIMARY)
    moon_to_capture, _ = _assign_primary_captures(registry, guides, excludes)
    apply_subarea_capture_groups(
        registry, moon_to_capture, excludes, subarea_groups
    )
    enforce_special_single_moon(registry, moon_to_capture)
    goal_pools = load_capture_goal_moon_pools()
    name_by_id = {int(c["id"]): str(c["name"]) for c in CAPTURE_LIST}
    real: set[tuple[str, int]] = set()
    for key, cap_id in moon_to_capture.items():
        cap_name = name_by_id.get(int(cap_id), "")
        goals = goals_for_capture_row(int(cap_id), cap_name)
        pool: set[tuple[str, int]] = set()
        for goal in goals:
            pool |= goal_pools.get(goal, set())
        if key in pool:
            real.add(key)
    return frozenset(real)


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
    # capture no se persiste en bingo_groups.json → load_bingo_groups().
    want = cap_name.casefold()
    for group in load_bingo_groups():
        if str(group.get("capture") or "").casefold() != want:
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
        if not counts_for_goal:
            ref["tag"] = True
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
    from catalog_lib import _slugify_capture_name

    name = str(meta.get("name") or meta.get("capture") or "")
    if name and _slugify_capture_name(name) in CAPTURE_NO_CONCRETE_TAGS:
        return "minoritaria"
    if n_for_tipo >= CAPTURE_TAG_MIN:
        return "normal"
    return "minoritaria"


def _parse_tag_only_key(raw: object) -> tuple[str, int] | None:
    if not isinstance(raw, dict):
        return None
    try:
        return (str(raw["kingdom"]), int(raw["moon"]))
    except (KeyError, TypeError, ValueError):
        return None


def _tag_only_keys_from_group(group: dict, want: str) -> set[tuple[str, int]]:
    if str(group.get("capture") or "").casefold() != want:
        return set()
    keys: set[tuple[str, int]] = set()
    for raw in group.get("tag_only_moons") or []:
        key = _parse_tag_only_key(raw)
        if key:
            keys.add(key)
    for m in group_moons(group):
        if m.get("goal") is False and "kingdom" in m and "moon" in m:
            keys.add((str(m["kingdom"]), int(m["moon"])))
    return keys


def _capture_tag_only_keys(cap_name: str) -> set[tuple[str, int]]:
    """tag_only_moons de grupos bingo con el mismo capture (goal=false)."""
    if not BINGO_GROUPS_PATH.exists():
        return set()
    want = cap_name.casefold()
    keys: set[tuple[str, int]] = set()
    for group in load_bingo_groups():
        keys |= _tag_only_keys_from_group(group, want)
    return keys


_CURATED_MOON_CAPTURES = frozenset(
    {
        "meat",
        "bowser statue",
        "broode's chain chomp",
    }
)

_CURATED_MOON_CAPTURE_IDS = frozenset(
    int(c["id"])
    for c in CAPTURE_LIST
    if str(c["name"]).casefold() in _CURATED_MOON_CAPTURES
)


def curated_capture_pool_moon_keys() -> frozenset[tuple[str, int]]:
    """Lunas curated en capturas_lunas (multiluna/tag) que cuentan en pool captures."""
    return frozenset(
        key
        for key, cap_id in CURATED_PRIMARY.items()
        if int(cap_id) in _CURATED_MOON_CAPTURE_IDS
    )


def _curated_keys_for_capture(cap_id: int) -> set[tuple[str, int]]:
    return {key for key, cid in CURATED_PRIMARY.items() if int(cid) == int(cap_id)}


def _moon_key_from_label(label: str) -> tuple[str, int] | None:
    m = re.match(r"^(\w+)#(\d+)\s+", label.strip())
    if not m:
        return None
    return (m.group(1), int(m.group(2)))


def _moon_in_capture_pool(
    key: tuple[str, int],
    *,
    real_keys: frozenset[tuple[str, int]],
    tag_only: set[tuple[str, int]],
    curated: set[tuple[str, int]],
    pool: set[tuple[str, int]],
) -> bool:
    return (
        key in real_keys
        or key in tag_only
        or key in curated
        or key in pool
    )


def _capture_moon_counts_for_goal(
    key: tuple[str, int],
    *,
    tag_only: set[tuple[str, int]],
    pool: set[tuple[str, int]],
    curated: set[tuple[str, int]],
    primary_goal: str,
    cap_id: int | None,
) -> bool:
    if key in tag_only:
        return False
    if key in pool:
        return True
    if key not in curated or key in CURATED_GOAL_FALSE_KEYS or not primary_goal:
        return False
    kingdom_multi_goal = _MULTI_MOON_GOAL_BY_KINGDOM.get(key[0])
    capture_goal = CAPTURE_OBJECTIVE.get(int(cap_id), "") if cap_id is not None else ""
    counts = kingdom_multi_goal == primary_goal or capture_goal == primary_goal
    if cap_id is not None:
        peer_false = CAPTURE_PEER_GOAL_FALSE_KEYS.get(int(cap_id))
        if peer_false and key in peer_false:
            return False
    return counts


def _build_capture_moons(
    moon_labels: list[str],
    goals: list[str],
    goal_pools: dict[str, set[tuple[str, int]]],
    registry: dict[tuple[str, int], dict],
    *,
    real_keys: frozenset[tuple[str, int]],
    cap_name: str,
    cap_id: int | None = None,
) -> list[dict[str, object]]:
    pool: set[tuple[str, int]] = set()
    for goal in goals:
        pool |= goal_pools.get(goal, set())
    tag_only = _capture_tag_only_keys(cap_name)
    curated = _curated_keys_for_capture(int(cap_id)) if cap_id is not None else set()
    primary_goal = goals[0] if goals else ""
    moons: list[dict[str, object]] = []
    for label in moon_labels:
        key = _moon_key_from_label(label)
        if key is None:
            continue
        if not _moon_in_capture_pool(
            key,
            real_keys=real_keys,
            tag_only=tag_only,
            curated=curated,
            pool=pool,
        ):
            continue
        counts_for_goal = _capture_moon_counts_for_goal(
            key,
            tag_only=tag_only,
            pool=pool,
            curated=curated,
            primary_goal=primary_goal,
            cap_id=cap_id,
        )
        moons.append(
            parse_moon_label(label, registry, counts_for_goal=counts_for_goal)
        )
    return moons


def _build_capture_row(
    meta: dict,
    by_capture: dict[int, list[str]],
    goal_pools: dict[str, set[tuple[str, int]]],
    combined: dict,
    registry: dict[tuple[str, int], dict],
    *,
    real_keys: frozenset[tuple[str, int]],
) -> dict[str, object]:
    cap_id = meta["id"]
    moon_labels = by_capture.get(cap_id, [])
    kingdoms_found = _kingdoms_from_labels(moon_labels, meta)
    goals = goals_for_capture_row(int(cap_id), str(meta["name"]))
    primary_goal = goals[0] if goals else ""
    n_for_tipo = _n_moons_for_tipo(meta, moon_labels, primary_goal, by_capture)
    tipo = _capture_tipo(meta, n_for_tipo)
    moons = _build_capture_moons(
        moon_labels,
        goals,
        goal_pools,
        registry,
        real_keys=real_keys,
        cap_name=str(meta["name"]),
        cap_id=int(cap_id),
    )
    n_goal_moons = sum(1 for moon in moons if moon.get("goal") is True)
    objectives: list[dict] = [
        objective_ref_from_combined(goal, combined.get(goal)) for goal in goals
    ]
    lista = _lista_for_capture(int(cap_id))
    row: dict[str, object] = {
        "id": int(cap_id),
        "capture": meta["name"],
        "tipo": tipo,
        "kind": capture_kind(len(objectives), len(moons)),
        "n_objectives": len(objectives),
        "n_moons": len(moons),
        "n_goal_moons": n_goal_moons,
    }
    if kingdoms_found:
        row["kingdom"] = kingdoms_found[0]
    if tipo == "normal":
        row["moon_tag"] = moon_tag_for(str(meta["name"]))
    _attach_row_arrays(row, objectives=objectives, lista=lista, moons=moons)
    return row


def build_capturas_export_rows(
    *,
    registry: dict | None = None,
    refresh_wiki: bool = False,
    fetch_guides: bool = True,
) -> tuple[
    list[dict[str, object]],
    dict[tuple[str, int], int],
    int,
    frozenset[tuple[str, int]],
]:
    """Filas capturas_lunas + asignación primaria + lunas reales (pool wiki)."""
    registry = registry or build_matrix_moon_registry()
    guides = load_capture_guides(refresh=refresh_wiki, quiet=not refresh_wiki)
    subarea_groups = load_subarea_groups()
    excludes = expand_excludes(EXCLUDE_PRIMARY, subarea_groups)
    excludes -= set(CURATED_PRIMARY)

    moon_to_capture, skipped = _assign_primary_captures(registry, guides, excludes)
    apply_subarea_capture_groups(
        registry, moon_to_capture, excludes, subarea_groups
    )
    enforce_special_single_moon(registry, moon_to_capture)
    real_keys = compute_real_capture_moon_keys(
        registry=registry, fetch_guides=fetch_guides
    )
    by_capture = rebuild_by_capture(registry, moon_to_capture)
    goal_pools = load_capture_goal_moon_pools()
    attach_group_capture_moons(by_capture, registry)
    attach_capture_goal_pool_moons(by_capture, registry, goal_pools)
    combined = load_combined_objectives_by_goal(include_disabled=True)

    rows: list[dict[str, object]] = [
        _build_capture_row(
            meta, by_capture, goal_pools, combined, registry, real_keys=real_keys
        )
        for meta in CAPTURE_LIST
    ]
    return rows, moon_to_capture, skipped, real_keys


def resolve_capturas_hub_moon_keys(
    *,
    registry: dict | None = None,
    refresh_wiki: bool = False,
    fetch_guides: bool = True,
) -> frozenset[tuple[str, int]]:
    """Claves únicas en moons[] del hub capturas (= n.moons del grupo captures)."""
    rows, _, _, _ = build_capturas_export_rows(
        registry=registry,
        refresh_wiki=refresh_wiki,
        fetch_guides=fetch_guides,
    )
    keys: set[tuple[str, int]] = set()
    for row in rows:
        for moon in row.get("moons") or []:
            keys.add((str(moon["kingdom"]), int(moon["moon"])))
    return frozenset(keys)


def resolve_capturas_hub_moons(
    *,
    registry: dict | None = None,
    refresh_wiki: bool = False,
    fetch_guides: bool = True,
) -> list[dict]:
    """Pool hub capturas (164): pool wiki + temáticas listadas en capturas_lunas."""
    registry = registry or build_matrix_moon_registry()
    keys = resolve_capturas_hub_moon_keys(
        registry=registry,
        refresh_wiki=refresh_wiki,
        fetch_guides=fetch_guides,
    )
    return [
        {
            "kingdom": kingdom,
            "moon": moon,
            "name": str(
                (registry.get((kingdom, moon)) or {}).get("name") or f"Moon {moon}"
            ),
        }
        for kingdom, moon in sorted(keys, key=lambda k: (k[0], k[1]))
    ]


def _captures_bingo_group() -> dict | None:
    return next(
        (g for g in load_bingo_groups() if g.get("id") == "captures"),
        None,
    )


def _captures_group_n_block() -> dict[str, int]:
    """Bloque n del grupo captures en bingo_groups (fuente de verdad del pool)."""
    group = _captures_bingo_group()
    if not group:
        return {}
    raw = group.get("n")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("objectives", "moons", "goal", "tag", "odyssey_units", "lista"):
        if raw.get(key) is not None:
            out[key] = int(raw[key])
    return out


def _captures_pool_n_moons() -> int:
    """Lunas del pool wiki/tag captures (~133; subset del hub de 164)."""
    from fill_captures_cappy import resolve_captures_pool_moon_keys

    return len(resolve_captures_pool_moon_keys())


def _validate_capturas_group_alignment(
    *,
    n_objectives_total: int,
    n_moons_total: int,
    n_lista_total: int,
    group_n: dict[str, int],
) -> None:
    """Alinea contadores con bingo_groups captures; falla si el grupo está obsoleto."""
    if not group_n:
        return
    checks = (
        ("objectives", n_objectives_total, int(group_n.get("objectives") or 0)),
        ("moons", n_moons_total, int(group_n.get("moons") or 0)),
        ("lista", n_lista_total, int(group_n.get("lista") or 0)),
    )
    bad = [
        f"{field}: capturas={got} vs grupo={want}"
        for field, got, want in checks
        if want and got != want
    ]
    if bad:
        raise SystemExit(
            "capturas_lunas desincronizado con bingo_groups captures "
            f"({'; '.join(bad)}). Ejecuta normalize_bingo_groups_file() "
            "o regenerate_all.py (paso progression) antes de exportar."
        )


def _print_capturas_summary(
    rows: list[dict[str, object]],
    moon_to_capture: dict[tuple[str, int], int],
    skipped: int,
    *,
    n_moons_pool: int,
) -> None:
    print(f"\nExportado: {OUT_JSON.relative_to(ROOT).as_posix()}")
    print(
        f"Capturas listadas: {len(rows)} "
        f"(wiki={len(CAPTURE_LIST)}; transporte incluidos)"
    )
    n_assigned = len(moon_to_capture)
    print(f"Lunas asignadas (captura principal): {n_assigned}")
    print(f"Pool wiki captures (n_moons_pool): {n_moons_pool}")
    if n_assigned < n_moons_pool:
        print(
            f"AVISO: asignadas ({n_assigned}) < pool wiki ({n_moons_pool}) "
            "(faltan lunas del pool)"
        )
    elif n_assigned > n_moons_pool:
        print(
            f"Nota: asignadas ({n_assigned}) > pool wiki ({n_moons_pool}) "
            "(extras fuera del subset wiki; OK)"
        )
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


def main(*, refresh_wiki: bool = False) -> None:
    print("Cargando lunas y guias...")
    rows, moon_to_capture, skipped, _real_keys = build_capturas_export_rows(
        refresh_wiki=refresh_wiki,
    )

    n_with_moons = sum(1 for r in rows if int(r["n_moons"]) > 0)
    n_with_goal = sum(1 for r in rows if int(r["n_objectives"]) > 0)
    n_blank_moons = sum(1 for r in rows if int(r["n_moons"]) == 0)
    n_blank_goal = sum(1 for r in rows if int(r["n_objectives"]) == 0)
    n_blank_both = sum(
        1
        for r in rows
        if int(r["n_moons"]) == 0 and int(r["n_objectives"]) == 0
    )
    n_moons_pool = _captures_pool_n_moons()
    group_n = _captures_group_n_block()
    global_stats = _capturas_global_stats(rows)
    n_moons_total = int(global_stats["n_moons_unique"])
    _validate_capturas_group_alignment(
        n_objectives_total=int(global_stats["n_objectives_total"]),
        n_moons_total=n_moons_total,
        n_lista_total=int(global_stats["n_lista_total"]),
        group_n=group_n,
    )
    payload = {
        "_definition": (
            "Capturas in-game (wiki) con lunas in-scope asignadas. "
            "Formato alineado con bingo_groups / goals_referencia: "
            "id (wiki), capture, tipo, kind, n_objectives, n_moons, n_goal_moons "
            "[, n_lista], kingdom, moon_tag (si normal), pool (si lista), "
            "objectives[], moons[] (si hay lunas), "
            "lista[] (source=binoculars|bosses). Orden de arrays: objectives → moons → lista. "
            "Campos array vacíos se omiten (solo en capturas_lunas). "
            "Cabecera: n (= bingo_groups captures.n: objectives/moons/lista/goal/tag), "
            "n_moons_pool (subset wiki/tag captures, ~133), "
            "n_moons_listed (Σ entradas moons[]; incluye duplicados entre filas), "
            "n_goal_moons / n_goal_moons_unique / n_goal_false (desglose moons[]). "
            "moons[]: captura real + tematica de goals bingo_groups de la fila; "
            "goal=true cuenta en goal Combined; goal=false lleva tag=true. "
            "y transporte viven en bingo_groups. Una captura puede listar 2+ "
            "goals (Pokio + Pokio Hole). "
            "lista[]: ubicaciones Binoculars o peleas jefe+captura (ids goal_lists; "
            "moon = multiluna cuando aplica). pool=lista si solo hay lista (sin moons). "
            "Una captura principal por luna. "
            "tipo=normal|especial|minoritaria|transporte|postgame. "
            "n_blank_moons / n_blank_goal / n_blank_both = filas sin moons[], "
            "sin objectives[], o ambos vacíos."
        ),
        "_note": "Regenerar con export_capturas_lunas.py o regenerate_all.py.",
        "n": group_n,
        "n_captures": len(rows),
        "n_moons_pool": n_moons_pool,
        "n_moons_listed": global_stats["n_moons_listed"],
        "n_goal_moons": global_stats["n_goal_moons"],
        "n_goal_moons_unique": global_stats["n_goal_moons_unique"],
        "n_goal_false": global_stats["n_goal_false"],
        "n_with_moons": n_with_moons,
        "n_with_goal": n_with_goal,
        "n_blank_moons": n_blank_moons,
        "n_blank_goal": n_blank_goal,
        "n_blank_both": n_blank_both,
        "captures": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    write_catalog_json(OUT_JSON, payload)

    legacy_csv = ROOT / "capturas-lunas.csv"
    if legacy_csv.exists():
        legacy_csv.unlink()
        print(f"Eliminado: {legacy_csv.name}")

    _print_capturas_summary(
        rows, moon_to_capture, skipped, n_moons_pool=n_moons_pool
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-wiki",
        action="store_true",
        help="Descargar Mario Wiki y actualizar mariowiki_capture_guides.json.",
    )
    args = parser.parse_args()
    main(refresh_wiki=args.refresh_wiki)
