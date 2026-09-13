"""Shared helpers for SMO bingo moon catalogs and tier counts.

Cache policy: clear_runtime_caches() limpia caches en memoria (tags de
captura/grupo, goal_lists, …), __pycache__/ del repo y el agent-tools
temporal de Cursor para este proyecto. Se registra en atexit al importar
este módulo, así que casi cualquier script del repo (todos importan
catalog_lib) limpia solo al salir del proceso. Otros módulos pueden
registrar su propio clear con register_cache_clear(fn) (p. ej.
goal_list_lib). regenerate_all.py también la llama como último paso.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent
ROOT = FILES_DIR.parent
BINGOS_DIR = ROOT / "Bingos"
CATALOG_DIR = ROOT / "Catalog"
CAPTURES_LUNAS_JSON = CATALOG_DIR / "capturas_lunas.json"
MARIOWIKI_CAPTURE_GUIDES_JSON = "mariowiki_capture_guides.json"
MOON_NAMES_WIKI_JSON = MARIOWIKI_CAPTURE_GUIDES_JSON
GOAL_X = "{{X}}"
_MOON_PLACEHOLDER_PREFIX = "Moon "


def _is_moon_number_placeholder(name: str) -> bool:
    rest = name[len(_MOON_PLACEHOLDER_PREFIX) :]
    return name.startswith(_MOON_PLACEHOLDER_PREFIX) and rest.isdigit()
GOAL_X_PREFIX = "{{X}} "
GOAL_UNIQUE_CAPTURES = "{{X}} Unique Captures"
# Captura normal con ≥N lunas → tag concreta junto a `captures`.
# Especial o minoritaria (<N) → basta `captures`.
CAPTURE_TAG_MIN = 3
# Capturas con ≥CAPTURE_TAG_MIN lunas+goal que aun asi no reciben tag concreta
# en lunas (basta `captures`). Grupos: apply_moon_tag=False.
CAPTURE_NO_CONCRETE_TAGS: frozenset[str] = frozenset()

# Pool Moe-Eye: tag moe_eye sin captures (goal #2 tag_only).
MOE_EYE_MOON_KEYS: frozenset[tuple[str, int]] = frozenset(
    {
        ("sand", 2),
        ("sand", 29),
        ("sand", 54),
        ("sand", 55),
    }
)
# Nombre en capturas_lunas.json → tag canónica (alineada con grupos cuando existe).
CAPTURE_NAME_TO_TAG: dict[str, str] = {
    "Frog": "frog",
    "Spark pylon": "spark_pylon",
    "Paragoomba": "paragoomba",
    "Chain Chomp": "chain_chomp",
    "Big Chain Chomp": "chain_chomp",
    "Broode's Chain Chomp": "chain_chomp",
    "T-Rex": "t_rex",
    "Bullet Bill": "bullet_bill",
    "Moe-Eye": "moe_eye",
    "Goomba": "goomba",
    "Glydon": "glydon",
    "Lakitu": "lakitu_fishing",
    "Zipper": "zipper",
    "Cheep Cheep": "cheep_cheep",
    "Cheep Cheep (Snow Kingdom)": "cheep_cheep",  # 0 lunas → Capture Snow Cheep Cheep
    "Uproot": "uproot",
    "Sherm": "sherm",
    "Tropical Wiggler": "tropical_wiggler",
    "Manhole": "manhole",
    "RC Car": "rc_car",
    "Shiverian Racer": "shiverian_racer",
    "Gushen": "gushen",
    "Lava Bubble": "lava_bubble",
    "Volbonan": "volbonan",
    "Fire Bro": "fire_bro",
    "Hammer Bro": "hammer_bro",
    "Fire Piranha Plant": "fire_piranha_plant",
    "Cactus": "cactus_tree",
    "Tree": "cactus_tree",
    "Pokio": "pokio",
    "Jizo": "jizo",
}
SCOPE_PATH = CATALOG_DIR / "scope.json"  # legado
META_PATH = CATALOG_DIR / "meta.json"  # legado → project.json
PROJECT_PATH = CATALOG_DIR / "project.json"
AVAILABILITY_PATH = CATALOG_DIR / "kingdom_availability.json"  # legado → project.json
RANGE_TIERS_PATH = CATALOG_DIR / "kingdom_range_tiers.json"  # legado → project.json
BINGOS_DIR.mkdir(exist_ok=True)
# Combined: Super Mario Odyssey-Combined-YYYY-MM-DD.json (fecha = última update del repo).
# Referencias lockout: misma fecha LOCKOUT_REFERENCE_DATE en todos (última update lockout.live).
COMBINED_GLOB = "Super Mario Odyssey-Combined-????-??-??.json"
COMBINED_NAME_PREFIX = "Super Mario Odyssey-Combined-"
_COMBINED_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Bump al re-exportar Short/Default/Long/All Kingdoms desde lockout.live.
LOCKOUT_REFERENCE_DATE = "2026-08-08"


def discover_combined_path() -> Path:
    """Ruta del Combined datado (si hay varios, el de fecha más reciente)."""
    matches = sorted(BINGOS_DIR.glob(COMBINED_GLOB))
    if matches:
        return matches[-1]
    return BINGOS_DIR / f"{COMBINED_NAME_PREFIX}{date.today().isoformat()}.json"


def stamp_combined_filename_today(today: str | None = None) -> Path:
    """Renombra Combined a YYYY-MM-DD de hoy y actualiza JSON_PATH.

    Llamar al regenerar / al escribir Combined para que el nombre refleje
    la última update del proyecto.
    """
    global JSON_PATH
    day = today or date.today().isoformat()
    if not _COMBINED_DATE_RE.fullmatch(day):
        raise ValueError(f"Fecha Combined inválida: {day!r} (esperado YYYY-MM-DD)")
    bingos = BINGOS_DIR.resolve()
    target = (BINGOS_DIR / f"{COMBINED_NAME_PREFIX}{day}.json").resolve()
    if not target.is_relative_to(bingos):
        raise ValueError(f"Ruta Combined fuera de Bingos/: {target}")
    matches = sorted(BINGOS_DIR.glob(COMBINED_GLOB))
    if not matches:
        raise FileNotFoundError(f"No hay Combined en {BINGOS_DIR} ({COMBINED_GLOB})")
    current = matches[-1].resolve()
    if not current.is_relative_to(bingos):
        raise ValueError(f"Combined actual fuera de Bingos/: {current}")
    if current != target:
        current.replace(target)
    for extra in BINGOS_DIR.glob(COMBINED_GLOB):
        extra_res = extra.resolve()
        if extra_res != target and extra_res.is_relative_to(bingos):
            extra.unlink()
    JSON_PATH = target
    return target


def lockout_reference_path(set_label: str) -> Path:
    """JSON de referencia lockout.live datado con LOCKOUT_REFERENCE_DATE."""
    return BINGOS_DIR / f"Super Mario Odyssey-{set_label}-{LOCKOUT_REFERENCE_DATE}.json"


# Fuente de verdad de objetivos (editar solo el Combined datado).
JSON_PATH = discover_combined_path()
# Referencias lockout.live (no modificar contenido a mano). AK = más completo /
# umbrales altos; Short/Default/Long = cobertura menor, rangos más blandos.
ALL_KINGDOMS_REFERENCE_PATH = lockout_reference_path("All Kingdoms")
SHORT_GOALS_REFERENCE_PATH = lockout_reference_path("Short Goals")
DEFAULT_GOALS_REFERENCE_PATH = lockout_reference_path("Default")
LONG_GOALS_REFERENCE_PATH = lockout_reference_path("Long Goals")
# Norma Combined: totales de lunas por reino salto +2; regionales salto +5.
MOON_TOTAL_STEP = 2
REGIONAL_COIN_STEP = 5

ZONE_ORDER = ["e", "m", "l", "n"]

# Reino boss entre Wooded y Lost: solo variable interna / nombre de goal
# ("Defeat Bowser in Cloud Kingdom"). En JSON/CSV el slug es siempre "lost".
_CLOUD_KINGDOM = "cloud"
_CATALOG_KINGDOM_ALIAS = {_CLOUD_KINGDOM: "lost"}

# Tramo Rush post-Wooded: Cloud + Lost + Metro noche (base, hasta 1ª multi).
# Goals/progresión: metro noche → lost. Tags de luna: kingdom=metro + tag night
# (grupo metro_night). Refs de luna siguen kingdom="metro".
_METRO = "metro"
_METRO_NIGHT_AVAIL = frozenset({"base"})
_METRO_NIGHT_MOON_KEYS_CACHE: frozenset[tuple[str, int]] | None = None

# mushroom#39 (Secret Path vía pintura Luncheon): progresión/catálogo → luncheon.
# Nº sintético #50 (luncheon ya tiene #39 Magma Narrow Path). Refs bingo/painting
# siguen kingdom="mushroom" moon=39.
MUSHROOM_SECRET_PATH: tuple[str, int] = ("mushroom", 39)
LUNAS_CATALOG_SYNTHETIC: dict[tuple[str, int], tuple[str, int]] = {
    MUSHROOM_SECRET_PATH: ("luncheon", 50),
}


def metro_night_moon_keys() -> frozenset[tuple[str, int]]:
    """Lunas Metro del tramo lost (grupo metro_night + girder #13 + multi #1)."""
    global _METRO_NIGHT_MOON_KEYS_CACHE
    if _METRO_NIGHT_MOON_KEYS_CACHE is not None:
        return _METRO_NIGHT_MOON_KEYS_CACHE
    from sync_objective_moon_groups import OBJECTIVE_MOON_GROUP_SPECS

    keys: set[tuple[str, int]] = set()
    for gid in ("night", "girder", "metro_night", "metro_girder"):
        for pair in OBJECTIVE_MOON_GROUP_SPECS.get(gid, {}).get("moons") or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                keys.add((str(pair[0]), int(pair[1])))
    keys.add((_METRO, 1))  # Pest Problem (cierra el tramo)
    _METRO_NIGHT_MOON_KEYS_CACHE = frozenset(keys)
    return _METRO_NIGHT_MOON_KEYS_CACHE


def catalog_kingdom(kingdom: str | None) -> str:
    """Slug de reino para catálogos (JSON/CSV): cloud → lost."""
    if not kingdom:
        return ""
    k = str(kingdom)
    return _CATALOG_KINGDOM_ALIAS.get(k, k)


def is_metro_night(
    kingdom: str | None,
    disponibilidad: str | None = None,
    moon: int | None = None,
) -> bool:
    """True si es luna/tramo Metro noche (progresión goal → lost)."""
    k = catalog_kingdom(kingdom)
    if k != _METRO:
        return False
    if moon is not None:
        if (k, int(moon)) in metro_night_moon_keys():
            return True
        return disponibilidad in _METRO_NIGHT_AVAIL
    return disponibilidad in _METRO_NIGHT_AVAIL


def catalog_kingdom_for_moon(
    kingdom: str | None,
    disponibilidad: str | None = None,
    moon: int | None = None,
) -> str:
    """Reino de goal/progresión: cloud→lost; metro noche→lost; mushroom#39→luncheon.

    No reescribe kingdom físico en refs de bingo/painting (siguen metro/mushroom).
    """
    k = catalog_kingdom(kingdom)
    if is_metro_night(k, disponibilidad, moon=moon):
        return "lost"
    if moon is not None and (k, int(moon)) in LUNAS_CATALOG_SYNTHETIC:
        return LUNAS_CATALOG_SYNTHETIC[(k, int(moon))][0]
    return k


def lunas_catalog_ref(kingdom: str | None, moon: int | None) -> tuple[str, int]:
    """Identidad en lunas-objetivos/zonas: mushroom#39 → luncheon#50 (sintético)."""
    k = catalog_kingdom(kingdom)
    m = int(moon or 0)
    return LUNAS_CATALOG_SYNTHETIC.get((k, m), (k, m))


def apply_lunas_catalog_tags(
    tags: set[str] | list[str] | None,
    *,
    kingdom: str,
    moon: int,
    allowed: set[str] | frozenset[str] | None = None,
) -> set[str]:
    """Tags de luna para catálogo: reino sintético (luncheon) sin slug mushroom."""
    physical = catalog_kingdom(kingdom)
    catalog_k, _catalog_m = lunas_catalog_ref(physical, moon)
    out = normalize_moon_tags(
        tags, kingdom=physical, moon=moon, allowed=allowed
    )
    if catalog_k != physical:
        out.discard(physical)
        out.add(catalog_k)
        if allowed is not None:
            out = {t for t in out if t in allowed or t == catalog_k}
    return out


def remap_cloud_slugs_for_export(data: object) -> object:
    """Al escribir JSON: alias cloud→lost (no reescribe kingdom de lunas metro)."""
    if isinstance(data, dict):
        out: dict = {}
        for key, value in data.items():
            if key == _CLOUD_KINGDOM:
                continue
            if key == "kingdom" and isinstance(value, str):
                out[key] = catalog_kingdom(value)
            elif key == "id" and value == _CLOUD_KINGDOM:
                out[key] = "lost"
            elif key == "story_order" and isinstance(value, list):
                seen: set[str] = set()
                order: list[str] = []
                for item in value:
                    slug = catalog_kingdom(item) if isinstance(item, str) else item
                    if isinstance(slug, str):
                        if slug in seen:
                            continue
                        seen.add(slug)
                        order.append(slug)
                    else:
                        order.append(slug)
                out[key] = order
            elif key == "_boss_only_kingdoms":
                if isinstance(value, dict):
                    out[key] = {
                        catalog_kingdom(k): v
                        for k, v in value.items()
                        if k != _CLOUD_KINGDOM
                    }
                elif isinstance(value, list):
                    out[key] = [
                        catalog_kingdom(x)
                        for x in value
                        if catalog_kingdom(x) != "lost"
                    ]
                else:
                    out[key] = remap_cloud_slugs_for_export(value)
            elif key == "reinos" and isinstance(value, list):
                out[key] = [
                    catalog_kingdom(x) if isinstance(x, str) else x for x in value
                ]
            else:
                out[key] = remap_cloud_slugs_for_export(value)
        return out
    if isinstance(data, list):
        return [remap_cloud_slugs_for_export(x) for x in data]
    return data


# Orden narrativo (sin slug cloud: el boss Cloud Kingdom → lost en catálogo).
STORY_ORDER = [
    "cap",
    "cascade",
    "sand",
    "lake",
    "wooded",
    "lost",
    "metro",
    "snow",
    "seaside",
    "luncheon",
    "ruined",
    "bowser",
    "moon",
]

# Sin reinos boss-only en catálogo (Cloud Kingdom se cataloga como lost).
BOSS_ONLY_KINGDOMS = frozenset()
# Reinos solo postgame (fuera de alcance salvo FORCE_IN_SCOPE, p. ej. mushroom#39).
POSTGAME_KINGDOMS = frozenset({"mushroom"})

# Reinos con Power Moons en catálogos / CSV.
KINGDOM_COLUMNS = [k for k in STORY_ORDER if k not in BOSS_ONLY_KINGDOMS]


def ensure_unique_ascending_range(ranges: list[int]) -> list[int]:
    """Valores de range unicos y ascendentes (sin duplicados para bingo)."""
    return sorted({int(x) for x in ranges})


def align_numeric_range_to_progression(
    ranges: list[int],
    progression: list[str] | None = None,
) -> list[int]:
    """Range sin duplicados; no se rellena para igualar len(progression)."""
    del progression
    if not ranges:
        return list(ranges)
    return ensure_unique_ascending_range(ranges)


KINGDOM_DISPLAY = {
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
    "bowser": "Bowser's",
    "moon": "Moon",
    "mushroom": "Mushroom",
}

# Tras completar TODA la historia/multilunas del reino → world_peace.
FINAL_STORY_MARKERS: dict[str, tuple[str, ...]] = {
    "cascade": ("multi moon atop the falls",),
    "sand": ("the hole in the desert",),
    "lake": ("broodals over the lake",),
    "wooded": ("defend the secret flower field",),
    "metro": ("a traditional festival",),
    "snow": ("the bound bowl grand prix",),
    "seaside": ("the glass is half full",),
    "luncheon": ("cookatiel showdown",),
    "ruined": ("battle with the lord of lightning",),
    "bowser": ("showdown at bowser's castle",),
}

# Reinos con 2 multilunas: tras la 1ª el mapa cambia → mid_story.
# Incluye la 1ª multi y beats de historia que enganchan la 2ª (wiki a veces
# no cita la 1ª multi en el prereq del multi final).
MID_STORY_MARKERS: dict[str, tuple[str, ...]] = {
    "sand": ("showdown on the inverted pyramid",),
    "wooded": (
        "flower thieves of sky garden",
        "path to the secret flower field",
    ),
    "metro": (
        "new donk city's pest problem",
        "powering up the station",
    ),
    "luncheon": (
        "big pot on the volcano",
        "climb up the cascading magma",
    ),
}

# Grupos grandes en bingo_groups.json (id → objetivo Combined).
# Ya no hay archivos *-moons.json para estas listas.
CATALOG_GOALS: dict[str, str] = {
    "8bit": "{{X}} 8-Bit Moons",
    "music_note": "{{X}} Music Note Moons",
    "timer_challenge": "{{X}} Timer Challenge Moons",
    "moon_shard": "{{X}} Moon Shard Moons",
    "ground_pound": "{{X}} Ground Pound Moons",
    "treasure_chest": "{{X}} Treasure Chest Moons",
    "sub_area": "{{X}} Sub-Area Moons",  # Level con exactamente 2 lunas
    "shiny_rocks": "{{X}} Shiny Rock Moon[[s]]",
    "captain_toad": "{{X}} Captain Toad Moons",
}

# id de grupo → moon_tag particular (large=true en bingo_groups).
PRIMARY_TAGS: dict[str, str] = {
    "8bit": "8bit",
    "music_note": "music_note",
    "timer_challenge": "timer_challenge",
    "moon_shard": "moon_shard",
    "ground_pound": "ground_pound",
    "treasure_chest": "treasure_chest",
    "sub_area": "sub_area",
    "shiny_rocks": "shiny_rocks",
    "captain_toad": "captain_toad",
}

VIRTUAL_PRIMARY_TAGS: dict[str, str] = {}

# Grupos con >= este n_lunas pueden usar moon_tag particular (sin 'group').
GROUP_LARGE_MIN = 15
# Existencia tematica: >= GROUP_MIN_MOONS lunas O >=1 objetivo relacionado.
GROUP_MIN_MOONS = 3
GROUP_MOON_TAG = "group"
BINGO_GROUPS_PATH = CATALOG_DIR / "bingo_groups.json"
BINGO_LINEAS_PATH = CATALOG_DIR / "bingo_lineas.json"

# Tags story/action viven en bingo_groups (grupos moon_tag); sin JSON items[] aparte.
MOON_TAG_CATALOGS = frozenset()

# --- Reglas de combinación de tags por luna ---
#
# Paraguas fauna/flora (umbral = CAPTURE_TAG_MIN):
#   < umbral → solo paraguas
#   ≥ umbral → solo concreta (sin fauna/flora)
# seeds es tag/grupo propio (no entra en flora).
# Grupos tematicos con ≤2 lunas: apply_moon_tag=False (goal OK; sin tag micro;
#   usar paraguas natural si existe: treasure_chest, sub_area, captures, shiveria…).
# Excepción n=3 sin tag concreta: ver CAPTURE_NO_CONCRETE_TAGS (Moe-Eye).
TAG_CONTEXT = frozenset(
    {
        "sub_area",
        "group",
        "fauna",
        "flora",
        "npc",
        "outfit_door",
        "switch",
        "mini_rocket",
        "manhole",
        "beanstalk",
        "rocket_flower",
        "shiveria",
        "overworld",
        "ty_foo",
        "maw_ray",
        "komboo",
        "tostarena",
        "ruins",
        "oasis",
        "pyramid",
        "ice",
        "deep_woods",
    }
)
# Acceso concreto (transporte / outfit door): basta esa tag; sin sub_area encima.
# La omisión de sub_area depende de tags que acompañan (estas), no de ser
# sub_area en sí: el resto del pool Sub-Area sí lleva la tag.
# manhole/spark_pylon: sub_area solo si estan en el grupo sub_area
# (#43+#44 / Push-Block / Wire); no #35 Sewer ni #26 Behind Bars.
# (Rocket Flower / zipper = contenido, no acceso → fuera.)
ACCESS_DROPS_SUB_AREA = frozenset(
    {
        "mini_rocket",
        "beanstalk",
        "outfit_door",
    }
)
UMBRELLA_MOON_TAGS = frozenset({"fauna", "flora"})
# Grupos con moons[] omitido en JSON (n.moons se conserva; pool en tags/catálogo).
OMIT_MOONS_GROUP_IDS = frozenset({"captures", "sub_area"})
# Capturas de planta: NO añaden flora (basta captures + tag concreta).
# flora queda para nut/bloom/cactus no-captura, etc. (turnips → seeds)
CAPTURE_UMBRELLA: dict[str, str] = {}
# Si hay captura de planta concreta, no apilar flora.
PLANT_CAPTURE_TAGS = frozenset({"uproot", "cactus_tree"})
TAG_STORY = frozenset({"story_moon", "multi_moon", "boss"})
# Multi-Moon: 1 Power Moon física → 3 unidades al depositar en la Odyssey.
MULTI_MOON_ODYSSEY_UNITS = 3
KINGDOM_MOONS_ODYSSEY_TOOLTIP = "Multi-Moons count as 3."
# Acción: captura / Cappy / Mario a pie (pool curado). captures+cappy pueden
# coexistir solo en ALLOW_CAPTURES_AND_CAPPY; mario es XOR con ambas.
# mario NO es residual: solo MARIO_MOONS (lunas sin otra tag tematica).
TAG_ACTION = frozenset({"captures", "cappy", "mario"})
TAG_CAPTURES_AND_CAPPY = frozenset({"captures", "cappy"})
# Pool tag/goal mario: "en medio de la nada" (solo reino + mario).
MARIO_MOONS: frozenset[tuple[str, int]] = frozenset(
    {
        ("cascade", 5),   # On Top of the Rubble
        ("cascade", 8),   # Across the Floating Isles
        ("sand", 6),   # Alcove in the Ruins
        ("sand", 7),   # On the Leaning Pillar
        ("sand", 11),  # On Top of the Stone Archway
        ("sand", 13),  # On the Lone Pillar
        ("lost", 1),      # Atop a Propeller Pillar
        ("lost", 2),      # Below the Cliff's Edge
        ("lost", 8),      # Enjoying the View of Forgotten Isle
        ("metro", 11),    # Glittering Above the Pool
        ("metro", 12),    # Dizzying Heights
        ("luncheon", 6),  # Piled on the Salt
        ("luncheon", 7),  # Lurking in the Pillar's Shadow
        ("bowser", 7),    # From the Side Above the Castle Gate
        ("moon", 1),      # Shining Above the Moon
        ("moon", 14),     # Up in the Rafters
    }
)
# Pool tag/goal rocket_flower: dash con Rocket Flower (sin tag cappy).
ROCKET_FLOWER_MOONS: frozenset[tuple[str, int]] = frozenset(
    {
        ("seaside", 31),  # Taking Notes: Ocean Surface Dash
        ("snow", 24),     # Dashing Over Cold Water!
        ("snow", 25),     # Dashing Above and Beyond!
        ("moon", 6),      # Cliffside Treasure Chest
        ("bowser", 37),   # Dashing Above the Clouds
        ("bowser", 38),   # Dashing Through the Clouds
    }
)
TAG_KINGDOM = frozenset(KINGDOM_COLUMNS) | frozenset({"mushroom"})
# cloud: no tag de reino (sin lunas en alcance).
TAG_OBTAIN = frozenset(
    {
        "8bit",
        "music_note",
        "timer_challenge",
        "moon_shard",
        "ground_pound",
        "treasure_chest",
        "shiny_rocks",
    }
)

# Alias → canónico snake_case (concepto luna / unificacion).
# checkpoint/checkpoints: solo board↔line Combined (NO tag de luna).
# bosses → boss: board/line y también tag de luna (peleas con Moon Get).
TAG_ALIASES: dict[str, str] = {
    "captaintoad": "captain_toad",
    "hintart": "hint_art",
    "hintart_kingdom": "hint_art_kingdom",
    "multimoon": "multi_moon",
    "multimoons": "multi_moon",
    "storymoon": "story_moon",
    "storymoons": "story_moon",
    "subarea": "sub_area",
    "moonsubarea": "sub_area",
    "outfitdoor": "outfit_door",
    "bosses": "boss",
    "checkpoints": "checkpoint",  # board/line, no moon tag
    "destructible_blocks_capture": "blocks",
    "npc_moons": "npc",
    "koopa": "npc",
    "seed_moon": "seeds",
    "golden_turnip": "seeds",  # grupo retirado → seeds
    "minigames": "minigame",
    "pokio_hole": "pokio",
}

# TAG_ALIASES solo para bingo/goal/luna/tag; no para grupo/lista/captura/zona.
BOARD_LINE_TAG_ALIASES = frozenset({"bosses", "checkpoints"})

# Slug → canónico en palabras_inventario (unifica capas bingo/grupo/tag/lista/captura).
# TAG_ALIASES se aplica antes; aquí capturas, listas plurales y ids de grupo legacy.
PALABRA_ALIASES: dict[str, str] = {
    "cheep_cheep_snow_kingdom": "cheep_cheep",
    "cascade_chain_chomp": "chain_chomp",
    "sand_birds": "birds",
    "lost_tropical_wiggler": "tropical_wiggler",
    "lost_butterfly": "butterfly",
    "lost_trapeetle": "trapeetle",
    "sand_jaxi": "jaxi",
    "sand_moe_eye": "moe_eye",
    "sand_tostarena": "tostarena",
    "sand_oasis": "oasis",
    "sand_ruins": "ruins",
    "sand_pyramid": "pyramid",
    "wooded_flower_road": "flower_road",
    "sand_ice": "ice",
    "wooded_pipe": "pipe",
    "metro_girder": "girder",
    "metro_night": "night",
    "metro_trash": "trash",
    "metro_manhole": "manhole",
    "metro_taxi": "taxi",
    "metro_motor_scooter": "motor_scooter",
    "metro_rc_car": "rc_car",
    "metro_minigames": "minigame",
    "luncheon_lantern": "lantern",
    "luncheon_volbonan": "volbonan",
    "snow_shiveria": "shiveria",
    "snow_overworld": "overworld",
    "snow_ty_foo": "ty_foo",
    "snow_bitefrost": "bitefrost",
    "cascade_chasm_lifts": "chasm_lifts",
    "ruined_roulette": "roulette",
    "wooded_uproot": "uproot",
    "seaside_uproot": "uproot",
    "snow_goomba": "goomba",
    "cap_frog": "frog",
    "lake_zipper": "zipper",
    "pokio_hole": "pokio",
    "bosses": "boss",
    "moon_rocks": "moonrock",
    "talkatoos": "talkatoo",
    "regionals": "regionalcoins",
    "shops": "shop",
    "shopping": "shop",
    "checkpoints": "checkpoint",
    "levers": "lever",
    "life_up_hearts": "life_up",
    "sphynxes": "sphynx",
    "ground_pound_switches": "ground_pound",
    "jaxi_stands": "jaxi",
    "pixel_cat_marios": "8bit",
    "pixel_cat_peaches": "8bit",
    "pixel_luigis": "8bit",
    "girders": "girder",
}

# Tags demasiado especificas (pocas lunas) → generica de contexto.
# Fauna/flora concretos mayoritarios NO van aqui (los pone apply_bingo_group_tags).
TAG_RARE_FALLBACK: dict[str, str] = {
    # Coin Coffer / Puzzle Part: sin tag micro (n≤2); → captures.
    "puzzle_part": "captures",
    "coin_coffer": "captures",
    # cheep_cheep: Lake+Seaside ≥3 → tag concreta (no colapsar)
    # manhole = acceso (tag manhole; sub_area solo via grupo sub_area)
    "rc_car": "captures",
    "volbonan": "captures",
    # motor_scooter: tag propia (TC2 + Free Parking); Escape → t_rex/captures
    # sub-areas / zonas (el par ya lleva sub_area)
    # ty_foo: tag propia (Wind-Chill + Blowing); no es sub_area
    # rocket_flower: tag propia (Cold Water Dash + Cliffside); no colapsar
    # pipe: tag concreta (Flooding + Peculiar Pipes); no colapsar a sub_area
    # minijuegos
    "jump_rope": "minigame",
    "volleyball": "minigame",
    "slots": "minigame",
    "metro_minigames": "minigame",
}


def canonicalize_tag(tag: str) -> str:
    """Normaliza alias y, si aplica, fallback de tag rara → generica."""
    tag = TAG_ALIASES.get(tag, tag)
    return TAG_RARE_FALLBACK.get(tag, tag)


def canonicalize_tag_list(tags: list | None) -> list[str]:
    """Lista de tags canónicas, sin duplicados, orden estable."""
    if not tags:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = canonicalize_tag(str(raw))
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def canonicalize_palabra(
    word: str | None,
    *,
    uso: str | None = None,
    moon_tag: str | None = None,
) -> str | None:
    """Unifica slugs duplicados entre bingo/grupo/tag/lista/captura/zona.

    - TAG_ALIASES + PALABRA_ALIASES (captaintoad→captain_toad, etc.).
    - Grupo con prefijo reino_* y moon_tag: id → moon_tag canónico
      (p. ej. cascade_chain_chomp + chain_chomp → chain_chomp;
      sand_jaxi + jaxi → jaxi).
    """
    if not word:
        return None
    w = word
    if not (uso in ("grupo", "lista", "captura", "zona") and w in BOARD_LINE_TAG_ALIASES):
        w = TAG_ALIASES.get(w, w)
    w = PALABRA_ALIASES.get(w, w)
    if uso == "grupo" and moon_tag:
        mt = canonicalize_tag(moon_tag)
        stripped = strip_kingdom_prefix_from_id(w)
        if stripped == mt:
            return mt
    return w


def _slugify_capture_name(name: str) -> str:
    if name in CAPTURE_NAME_TO_TAG:
        return CAPTURE_NAME_TO_TAG[name]
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s


_CAPTURE_TAG_BY_MOON: dict[tuple[str, int], str | None] | None = None


def clear_capture_tag_cache() -> None:
    global _CAPTURE_TAG_BY_MOON
    _CAPTURE_TAG_BY_MOON = None


def _capture_row_display_name(row: dict) -> str:
    return (
        row.get("capture")
        or row.get("name")
        or row.get("captura")
        or ""
    ).strip()


def _moon_key_from_raw(moon: object) -> tuple[str, int] | None:
    if not isinstance(moon, dict):
        return None
    if "kingdom" not in moon or "moon" not in moon:
        return None
    return (str(moon["kingdom"]), int(moon["moon"]))


def _ingest_capture_row(
    row: dict,
    moons_by_tag: dict[str, set[tuple[str, int]]],
    moon_to_tag: dict[tuple[str, int], str],
) -> None:
    name = _capture_row_display_name(row)
    if not name:
        return
    tag = _slugify_capture_name(name)
    for moon in row.get("moons") or []:
        key = _moon_key_from_raw(moon)
        if key is None:
            continue
        # Cuenta para el umbral de familia aunque no etiquete la luna.
        moons_by_tag.setdefault(tag, set()).add(key)
        if isinstance(moon, dict) and moon.get("goal") is False:
            # tag:true = concreta aunque no cuente en goal (p. ej. wooded#25 Uproot).
            if moon.get("tag") is not True:
                continue
        moon_to_tag[key] = tag


def load_capture_tag_by_moon() -> dict[tuple[str, int], str | None]:
    """(reino, luna) → tag concreta de captura, o None si especial/minoritaria.

    Fuente: Catalog/capturas_lunas.json. El umbral ≥CAPTURE_TAG_MIN se aplica por
    tag unificada (p. ej. los 3 Chomps → `chomp`), no por fila suelta:
    variantes especial/minoritaria del mismo slug reciben la tag si la
    familia llega al mínimo. Si no, basta `captures`.
    CAPTURE_NO_CONCRETE_TAGS (Moe-Eye): nunca tag concreta pese al umbral.

    Lunas con `goal: false` no reciben tag concreta salvo `tag: true`
    (p. ej. wooded#25 Uproot): basta `captures` u otra tag del grupo donde sí cuenten.
    """
    global _CAPTURE_TAG_BY_MOON
    if _CAPTURE_TAG_BY_MOON is not None:
        return _CAPTURE_TAG_BY_MOON

    moons_by_tag: dict[str, set[tuple[str, int]]] = {}
    moon_to_tag: dict[tuple[str, int], str] = {}
    if CAPTURES_LUNAS_JSON.exists():
        data = json.loads(CAPTURES_LUNAS_JSON.read_text(encoding="utf-8"))
        for row in data.get("captures") or []:
            if isinstance(row, dict):
                _ingest_capture_row(row, moons_by_tag, moon_to_tag)

    majority = {
        tag
        for tag, moons in moons_by_tag.items()
        if len(moons) >= CAPTURE_TAG_MIN and tag not in CAPTURE_NO_CONCRETE_TAGS
    }
    mapping: dict[tuple[str, int], str | None] = {
        key: (tag if tag in majority else None) for key, tag in moon_to_tag.items()
    }
    _apply_capture_subgroup_tag_overrides(mapping)
    _CAPTURE_TAG_BY_MOON = mapping
    return mapping


def _apply_capture_subgroup_tag_overrides(
    mapping: dict[tuple[str, int], str | None],
) -> None:
    """Subgrupos de captura con moon_tag propio distinto del id de grupo."""
    if not BINGO_GROUPS_PATH.exists():
        return
    for group in load_bingo_groups():
        if group.get("apply_moon_tag") is False:
            continue
        if not group.get("capture"):
            continue
        moon_tag = group.get("moon_tag")
        if not moon_tag:
            continue
        tag = str(moon_tag)
        if tag in CAPTURE_NO_CONCRETE_TAGS:
            continue
        for raw in group_moons(group):
            key = (str(raw["kingdom"]), int(raw["moon"]))
            if key in mapping:
                mapping[key] = tag


def majority_capture_tags() -> frozenset[str]:
    """Slugs de captura concreta (normal mayoritaria)."""
    return frozenset(t for t in load_capture_tag_by_moon().values() if t)


def _add_specific_capture_tags(out: set[str], kingdom: str, moon: int) -> None:
    if "captures" not in out:
        return
    specific = load_capture_tag_by_moon().get((kingdom, moon))
    if not specific:
        return
    out.add(specific)
    umbrella = CAPTURE_UMBRELLA.get(specific)
    if umbrella:
        out.add(umbrella)


def _apply_moon_tag_policy(out: set[str]) -> None:
    # Captura de planta (uproot/cactus_tree): sin flora encima.
    if "captures" in out and out & PLANT_CAPTURE_TAGS:
        out.discard("flora")
    # Acceso concreto (mini_rocket / beanstalk / outfit_door): sin sub_area.
    if out & ACCESS_DROPS_SUB_AREA:
        out.discard("sub_area")
    # nature: solo grupo/goal agregado; en lunas usamos fauna o flora.
    out.discard("nature")
    # Moe-Eye: tag concreta del grupo; no duplicar captures en esas lunas.
    if "moe_eye" in out:
        out.discard("captures")
    # transport: solo grupo/goals (Beanstalk + Mini Rocket); en lunas
    # usamos beanstalk / mini_rocket (Rocket Flower = flora, fuera del paraguas).
    out.discard("transport")
    # 8-bit: la luna es el segmento 2D; captura solo de acceso no cuenta.
    if "8bit" in out:
        out.discard("captures")
        out -= majority_capture_tags() | PLANT_CAPTURE_TAGS
    # Captura especial (Coin Coffer, Meat, …): special_capture_moons XOR captures.
    if "special_capture_moons" in out:
        out.discard("captures")
    # Puerta con outfit: outfit_door, nunca npc.
    if "outfit_door" in out:
        out.discard("npc")


def normalize_moon_tags(
    tags: set[str] | list[str] | None,
    *,
    kingdom: str | None = None,
    moon: int | None = None,
    allowed: set[str] | frozenset[str] | None = None,
) -> set[str]:
    """Tags de luna canónicas para CSV/inventario.

    - Aplica TAG_ALIASES y TAG_RARE_FALLBACK
    - Omite 'group' legado
    - Añade reino si se indica
    - Si hay `captures` y captura normal mayoritaria: añade la tag concreta
    - Si allowed: solo tags presentes en la lista permitida (+ reino)
    """
    out: set[str] = set()
    for raw in tags or []:
        tag = canonicalize_tag(str(raw))
        if not tag or tag == GROUP_MOON_TAG:
            continue
        out.add(tag)
    if kingdom:
        out.add(kingdom)
    if kingdom and moon is not None:
        _add_specific_capture_tags(out, kingdom, moon)
    _apply_moon_tag_policy(out)
    if allowed is not None:
        out = {t for t in out if t in allowed or t == kingdom}
    return out


def collect_allowed_moon_tags(
    registry: dict[tuple[str, int], dict] | None = None,
) -> frozenset[str]:
    """Conjunto de tags de luna permitidas (= las que existen en el registro)."""
    if registry is None:
        registry = build_matrix_moon_registry()
    allowed: set[str] = set()
    for (kingdom, moon), entry in registry.items():
        allowed |= apply_lunas_catalog_tags(
            entry.get("tags") or [], kingdom=kingdom, moon=moon
        )
    return frozenset(allowed)


# Cache de tags de contexto = ids de grupos pequenos (+ legacy group/sub_area).
_GROUP_CONTEXT_TAGS_CACHE: frozenset[str] | None = None
_CATALOG_TAG_IDS_CACHE: frozenset[str] | None = None


def strip_kingdom_prefix_from_id(group_id: str) -> str:
    """Quita el prefijo de reino del id (cap_frog → frog) para no duplicar tag.

    Renombres:
    - Prefijo de reino (`pokio` → `bowser_pokio`): solo cambia el id del grupo;
      la tag concreta sigue siendo el sufijo (`pokio`). No retaggear lunas.
    - Si id y tag coinciden (sin prefijo, o moon_tag == id) y se renombra el
      concepto: hay que cambiar ambos (grupo + tag en maps/CSV/lunas).
    """
    gid = str(group_id)
    for kingdom in sorted(KINGDOM_COLUMNS, key=len, reverse=True):
        prefix = f"{kingdom}_"
        if gid.startswith(prefix) and len(gid) > len(prefix):
            return gid[len(prefix) :]
    return gid


def clear_group_context_tags_cache() -> None:
    global _GROUP_CONTEXT_TAGS_CACHE, _METRO_NIGHT_MOON_KEYS_CACHE, _CATALOG_TAG_IDS_CACHE
    _GROUP_CONTEXT_TAGS_CACHE = None
    _METRO_NIGHT_MOON_KEYS_CACHE = None
    _CATALOG_TAG_IDS_CACHE = None
    clear_capture_tag_cache()


_EXTRA_CACHE_CLEARS: list = []


def register_cache_clear(fn) -> None:
    """Otros módulos (p. ej. goal_list_lib) registran su clear aquí."""
    if fn not in _EXTRA_CACHE_CLEARS:
        _EXTRA_CACHE_CLEARS.append(fn)


def clear_runtime_caches() -> None:
    """Limpia caches en memoria, __pycache__, .pytest_cache y agent-tools temporal.

    Cuándo: tras cualquier script Python del repo (exports, sync, one-shots,
    -c). Casi todos importan catalog_lib → se registra en atexit, así que al
    salir del proceso se limpia solo. Si un comando NO importa catalog_lib,
    ejecutar a mano:
      python -c "from catalog_lib import clear_runtime_caches; clear_runtime_caches()"
    regenerate_all.py ya limpia como último paso.
    """
    clear_group_context_tags_cache()
    clear_catalog_moon_caches()
    for fn in _EXTRA_CACHE_CLEARS:
        try:
            fn()
        except Exception:
            pass
    for path in ROOT.rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    for path in ROOT.rglob(".pytest_cache"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    agent_tools = (
        Path.home()
        / ".cursor"
        / "projects"
        / "c-Users-34681-Documents-Videojuegos-SMO-Bingo"
        / "agent-tools"
    )
    if agent_tools.is_dir():
        shutil.rmtree(agent_tools, ignore_errors=True)


# Al importar catalog_lib: vaciar caches en memoria/__pycache__ al salir del
# proceso (antes vivía en clear_caches.py; absorbido aquí).
atexit.register(clear_runtime_caches)


def _group_is_large_particular(group: dict, particular: object, n: int) -> bool:
    return bool(
        particular
        and particular != GROUP_MOON_TAG
        and (
            n >= GROUP_LARGE_MIN
            or group.get("large") is True
            or group.get("umbrella") is True
            or particular in UMBRELLA_MOON_TAGS
        )
    )


def _add_small_group_context_ids(tags: set[str]) -> None:
    if not BINGO_GROUPS_PATH.exists():
        return
    for group in load_bingo_groups():
        gid = group.get("id")
        if not gid or group.get("apply_moon_tag") is False:
            continue
        particular = group.get("moon_tag") or group.get("tag")
        n = len(group.get("moons") or [])
        if _group_is_large_particular(group, particular, n):
            continue
        # Misma tag que en lunas: sin prefijo de reino (cap_frog → frog).
        tags.add(strip_kingdom_prefix_from_id(str(gid)))


def load_group_context_tags() -> frozenset[str]:
    """Tags de contexto de grupo: no cuentan como metodo de obtencion.

    Incluye TAG_CONTEXT, ids de grupos pequenos y capturas concretas
    mayoritarias (van junto a `captures`, no como obtain aparte).
    """
    global _GROUP_CONTEXT_TAGS_CACHE
    if _GROUP_CONTEXT_TAGS_CACHE is not None:
        return _GROUP_CONTEXT_TAGS_CACHE
    tags: set[str] = set(TAG_CONTEXT)
    _add_small_group_context_ids(tags)
    tags |= majority_capture_tags()
    _GROUP_CONTEXT_TAGS_CACHE = frozenset(tags)
    return _GROUP_CONTEXT_TAGS_CACHE

# Pares de métodos de obtención que no pueden coexistir en la misma luna.
INCOMPATIBLE_TAG_PAIRS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset(pair)
        for pair in (
            ("captures", "cappy"),
            ("captures", "mario"),
            ("cappy", "mario"),
            ("captures", "special_capture_moons"),
            ("story_moon", "multi_moon"),
        )
    }
)

# Excepción: palanca/hold Cappy + captura de contenido → ambas tags de acción.
ALLOW_CAPTURES_AND_CAPPY: frozenset[tuple[str, int]] = frozenset(
    {
        ("wooded", 19),  # Fire in the Cave: Cappy + Fire Bro
        ("luncheon", 2),  # Under the Cheese Rocks: Lever + Hammer Bro
        ("sand", 55),  # Skull Sign: hold Cappy + Moe-Eye
    }
)

# Implicaciones de tags de luna (los obtain pequenos ya no son tags).
IMPLIED_TAGS: dict[str, set[str]] = {}


# Combinaciones de obtención válidas (más de un método).
ALLOWED_MULTI_OBTAIN: frozenset[frozenset[str]] = frozenset(
    {
        frozenset(combo)
        for combo in (
            {"8bit", "treasure_chest"},
            {"8bit", "music_note"},
            {"8bit", "moon_shard"},
            {"8bit", "timer_challenge"},
            {"moon_shard", "story_moon"},
        )
    }
)


def _obtain_tags(tag_set: set[str]) -> set[str]:
    return (
        tag_set
        - load_group_context_tags()
        - TAG_STORY
        - TAG_ACTION
        - TAG_KINGDOM
    )


def _incompatible_pair_issues(
    tag_set: set[str],
    *,
    kingdom: str | None,
    moon: int | None,
) -> list[str]:
    issues: list[str] = []
    for pair in INCOMPATIBLE_TAG_PAIRS:
        if not pair.issubset(tag_set):
            continue
        if (
            pair == TAG_CAPTURES_AND_CAPPY
            and kingdom is not None
            and moon is not None
            and (kingdom, moon) in ALLOW_CAPTURES_AND_CAPPY
        ):
            continue
        a, b = sorted(pair)
        issues.append(f"incompatible: {a} + {b}")
    return issues


def _implied_tag_issues(tag_set: set[str]) -> list[str]:
    issues: list[str] = []
    for tag, required in IMPLIED_TAGS.items():
        if tag in tag_set and not required.issubset(tag_set):
            missing = ", ".join(sorted(required - tag_set))
            issues.append(f"{tag} requiere tambien: {missing}")
    return issues


def _capture_specific_tag_issue(
    tag_set: set[str],
    *,
    kingdom: str | None,
    moon: int | None,
) -> str | None:
    if "captures" not in tag_set or not kingdom or moon is None:
        return None
    specific = load_capture_tag_by_moon().get((kingdom, moon))
    if specific and specific not in tag_set:
        return f"captures requiere tambien: {specific}"
    return None


def _multi_obtain_issue(tag_set: set[str]) -> str | None:
    obtain = _obtain_tags(tag_set)
    if len(obtain) <= 1:
        return None
    if any(
        combo.issubset(obtain) and obtain.issubset(combo)
        for combo in ALLOWED_MULTI_OBTAIN
    ):
        return None
    return "multiples metodos de obtencion: " + ", ".join(sorted(obtain))


def tag_combination_violations(
    tags: set[str] | list[str],
    *,
    kingdom: str | None = None,
    moon: int | None = None,
) -> list[str]:
    """Return human-readable issues for an invalid tag set."""
    tag_set = set(tags)
    issues = _incompatible_pair_issues(tag_set, kingdom=kingdom, moon=moon)
    issues.extend(_implied_tag_issues(tag_set))
    capture_issue = _capture_specific_tag_issue(
        tag_set, kingdom=kingdom, moon=moon
    )
    if capture_issue:
        issues.append(capture_issue)
    multi_issue = _multi_obtain_issue(tag_set)
    if multi_issue:
        issues.append(multi_issue)
    return issues


def merge_tags_safely(
    existing: set[str] | list[str],
    new_tags: set[str] | list[str],
) -> set[str]:
    """Union of tags, dropping additions that would create invalid combinations."""
    merged = set(existing) | set(new_tags)
    if not tag_combination_violations(merged):
        return merged

    result = set(existing)
    for tag in sorted(new_tags):
        candidate = result | {tag}
        if not tag_combination_violations(candidate):
            result = candidate
    return result

SKIP_CATALOGS = {
    "project.json",
    "meta.json",  # legado
    "kingdom_availability.json",  # legado
    "kingdom_range_tiers.json",  # legado
    MOON_NAMES_WIKI_JSON,
    MARIOWIKI_CAPTURE_GUIDES_JSON,
    "bingo_groups.json",  # grupos de objetivo; tags via apply_bingo_group_tags
    "bingo_lineas.json",  # categorias board/line Combined (no tags de luna)
    "goal_icons.json",  # iconos de goals Combined
    "goals_referencia.json",  # referencia goals + lunas/lista
    "goals_individuales.json",  # umbrales expandidos desde referencia
    "goal_lists.json",  # listas contables (sub_area_levels → sub_area_levels_data.py)
    "goal_tooltips.json",  # tooltips unicos Combined
    "zonas_inventario.json",  # inventario por zone (+ fuente zone)
    "zonas_revision.json",  # cola de revisión de zones
    "capturas_lunas.json",  # hub captura↔lunas/goals
    "tags_inventario.json",  # inventario de tags
    "palabras_inventario.json",  # slugs × usos (bingo/grupo/tag/…)
    "items_goals.json",  # ítem → goals Combined (id reino/source/nº)
    "lunas-objetivos.json",  # export tags por luna
    "lunas-objetivos.csv",  # vista CSV derivada del JSON
}

# Claves de proyecto que no deben repetirse en cada catalogo de lunas.
CATALOG_META_ONLY_KEYS = frozenset(
    {
        "story_order",
        "run_tier_ceiling",
        "in_scope_moons",
        "in_scope_moon_count",
        "in_scope_odyssey_units",
        "in_scope_odyssey_units_by_kingdom",
        "scope_allowed",
    }
)

CATALOG_GOAL_SET = set(CATALOG_GOALS.values())

GOAL_TO_TAG: dict[str, str] = {
    goal: tag
    for stem, goal in CATALOG_GOALS.items()
    for tag in (
        PRIMARY_TAGS.get(stem) or VIRTUAL_PRIMARY_TAGS.get(stem),
    )
    if tag
}

MATRIX_SKIP_TIPOS = {"reino_total", "reino_regional", "global"}

# Longest display names first (Bowser's before Moon, etc.)
KINGDOM_GOAL_PREFIXES: list[tuple[str, str]] = sorted(
    ((display, slug) for slug, display in KINGDOM_DISPLAY.items()),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

GLOBAL_AGGREGATE_GOALS = {
    "{{X}} Total Moons",
    "{{X}} Moon Rocks",  # total soft; no confundir con reino Moon (Moon Rocks ≠ Moon + Rocks)
    "{{X}} Total Regional Coins",
    "{{X}} Total Checkpoints",
    "{{X}} Total Multi-Moons",
    "{{X}} Total Story Moons",
    GOAL_UNIQUE_CAPTURES,
    "{{X}} Unique Life Up Hearts",
    "{{X}} Souvenirs",
    "{{X}} Stickers",
}

TIPO_SORT = {
    "cross_reino": 0,
    "cross_reino_pendiente": 1,
    "reino_exclusivo": 2,
    "reino_total": 3,
    "reino_regional": 4,
    "global": 5,
}


def load_project() -> dict:
    """Config unica: meta + availability + range_tiers."""
    if PROJECT_PATH.exists():
        return load_catalog(PROJECT_PATH)
    # Compat: ensamblar desde archivos legados si existen
    project: dict = {
        "_definition": "Config unica (ensamblada desde legados).",
        "meta": {},
        "availability": {},
        "range_tiers": {},
    }
    if META_PATH.exists():
        project["meta"] = load_catalog(META_PATH)
    if AVAILABILITY_PATH.exists():
        project["availability"] = load_catalog(AVAILABILITY_PATH)
    if RANGE_TIERS_PATH.exists():
        project["range_tiers"] = load_catalog(RANGE_TIERS_PATH)
    return project


def save_project(project: dict) -> None:
    write_catalog_json(PROJECT_PATH, project)


def load_scope() -> set[str]:
    """Disponibilidades de luna en alcance (base/mid_story/revisit/world_peace)."""
    meta = load_meta()
    allowed = meta.get("scope_allowed")
    if allowed:
        return set(allowed)
    if SCOPE_PATH.exists():
        with open(SCOPE_PATH, encoding="utf-8") as f:
            return set(json.load(f)["allowed"])
    return {"base", "mid_story", "revisit", "world_peace"}


def load_meta() -> dict:
    project = load_project()
    meta = project.get("meta")
    if meta:
        return meta
    if META_PATH.exists():
        with open(META_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_meta(meta: dict) -> None:
    """Actualiza la seccion meta de project.json (p. ej. in_scope_moons)."""
    project = load_project()
    project["meta"] = meta
    save_project(project)


def load_kingdom_availability() -> dict:
    project = load_project()
    avail = project.get("availability")
    if avail:
        return avail
    if AVAILABILITY_PATH.exists():
        return load_catalog(AVAILABILITY_PATH)
    return {}


def load_range_tiers() -> dict:
    project = load_project()
    tiers = project.get("range_tiers")
    if tiers:
        return tiers
    if RANGE_TIERS_PATH.exists():
        return load_catalog(RANGE_TIERS_PATH)
    return {}


POSTGAME_NAME_MARKERS = ("Regular Cup", "Master Cup")

# Tras créditos / Peach Castle. No confundir con world_peace (paz del reino).
POSTGAME_PREREQ_MARKERS = (
    "complete the game",
    "talk to the toad at peach",
    "peach's castle",
    "a tourist in the mushroom kingdom",
)

# Cadenas de turista: Mushroom + Round-the-World fuera (postgame).
# metro#52 / cascade#19 / luncheon#48 / moon#25 sí entran (run normal).
EXCLUDED_NAME_MARKERS = (
    "A Tourist in the Mushroom Kingdom",
    "'Round-the-World Tourist",
    "Round-the-World Tourist",
)


def _parse_wiki_moon_table(raw: dict) -> dict[str, dict[int, dict[str, str]]]:
    """Tabla kingdom → moon → {name,type,prerequisite,description}."""
    result: dict[str, dict[int, dict[str, str]]] = {}
    for kingdom, moons in raw.items():
        if str(kingdom).startswith("_") or not isinstance(moons, dict):
            continue
        parsed: dict[int, dict[str, str]] = {}
        for num, value in moons.items():
            try:
                moon_num = int(num)
            except (TypeError, ValueError):
                continue
            if isinstance(value, str):
                parsed[moon_num] = {
                    "name": value,
                    "type": "",
                    "prerequisite": "",
                    "description": "",
                }
            else:
                parsed[moon_num] = {
                    "name": str(value.get("name") or ""),
                    "type": str(value.get("type") or ""),
                    "prerequisite": str(value.get("prerequisite") or ""),
                    "description": str(value.get("description") or ""),
                }
        result[kingdom] = parsed
    return result


def load_wiki_moon_meta() -> dict[str, dict[int, dict[str, str]]]:
    """Meta wiki (mariowiki_capture_guides.json) para alcance y disponibilidad."""
    global _WIKI_MOON_META_CACHE
    if _WIKI_MOON_META_CACHE is not None:
        return _WIKI_MOON_META_CACHE

    path = CATALOG_DIR / MARIOWIKI_CAPTURE_GUIDES_JSON
    if not path.is_file():
        raise FileNotFoundError(
            f"Falta {MARIOWIKI_CAPTURE_GUIDES_JSON}. "
            "Regenerar: python Files/mariowiki_guides.py --refresh"
        )
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    result = _parse_wiki_moon_table(raw)
    _WIKI_MOON_META_CACHE = result
    return result


_WIKI_MOON_META_CACHE: dict[str, dict[int, dict[str, str]]] | None = None
_MERGE_CATALOG_MOONS_CACHE: dict[tuple[str, int], dict] | None = None
_MATRIX_MOON_REGISTRY_CACHE: dict[tuple[str, int], dict] | None = None


def clear_catalog_moon_caches() -> None:
    global _WIKI_MOON_META_CACHE, _MERGE_CATALOG_MOONS_CACHE, _MATRIX_MOON_REGISTRY_CACHE
    _WIKI_MOON_META_CACHE = None
    _MERGE_CATALOG_MOONS_CACHE = None
    _MATRIX_MOON_REGISTRY_CACHE = None


# Lunas postgame / fuera de cutoff que entran por excepcion.
FORCE_IN_SCOPE_MOONS: frozenset[tuple[str, int]] = frozenset(
    {
        ("mushroom", 39),  # Secret Path via pintura Luncheon
        ("moon", 25),  # Tourist Moon (cadena; #15+ suelen ser postgame por nombre)
    }
)

# Lunas in-scope que no deben listarse en lunas-objetivos (vacío: mushroom#39
# entra como luncheon#50 vía LUNAS_CATALOG_SYNTHETIC).
LUNAS_CATALOG_EXCLUDE: frozenset[tuple[str, int]] = frozenset()

# Secret Path no jugables en run normal (wiki prereq None, pero fuera de alcance).
# snow#33 / seaside#49: outbound postgame; bowser#43: tras créditos.
FORCE_OUT_OF_SCOPE_MOONS: frozenset[tuple[str, int]] = frozenset(
    {
        ("snow", 33),
        ("seaside", 49),
        ("bowser", 43),
    }
)

# Secret Path (luna en destino): unlock más temprano de la pintura origen
# (run normal). Forks Metro/Snow/Seaside → Wooded|Lake|Cascade según ruta.
#
# Origen → unlock outbound (bingo; smo.wiki Warp Painting):
#   Lake: None → base
#   Wooded: Flower Thieves → mid_story
#   Sand: Showdown → mid_story origen (destino Metro ≈ mid)
#   Metro: Pest Problem → mid_story
#   Snow / Seaside: Bound Bowl / Glass → world_peace
#   Luncheon / Mushroom: None → base
#   Cascade / Bowser: complete the game → postgame
#
# Destinos desde Metro/Snow/Seaside (tabla de rutas):
#   wooded#49 / lake#26: Metro mid | Snow WP | Seaside WP → earliest mid_story
#   cascade#18: solo Snow/Seaside WP → world_peace
# sand#62 / luncheon#47: Lake None (base) gana a Wooded mid
SECRET_PATH_AVAILABILITY: dict[tuple[str, int], str] = {
    ("cascade", 18): "world_peace",  # Snow WP o Seaside WP
    ("sand", 62): "base",  # Lake None (también Wooded mid)
    ("luncheon", 47): "base",  # Lake None (también Wooded mid)
    ("lake", 26): "mid_story",  # Metro Pest (también Snow/Seaside WP)
    ("wooded", 49): "mid_story",  # Metro Pest (también Snow/Seaside WP)
    # Sand Showdown (mid) + isla aislada (no desde overworld Metro)
    ("metro", 51): "mid_story",
    ("mushroom", 39): "base",  # Luncheon None
}

# Wiki «None»+ref / «intended after… skilled jumps»: early por trick; bingo sin clips.
# Wooded tras Flower Thieves (Sherms, Station 8, flower roads, ascensor).
# Revisados y NO override (intended sigue base): sand IP-clip (#10/#14/#46),
# luncheon salt-clip (#43/#44) y Golden Turnip #17 (tras Cheese Rocks = base);
# wooded #17/#24/#25 (intended tras Road to Sky Garden = aún base).
# Luncheon #31/#34: wiki cita Big Pot, pero spawnean tras #2 (antes de la 1ª multi)
# → base (mismo criterio que “antes de multi = base”).
AVAILABILITY_OVERRIDES: dict[tuple[str, int], str] = {
    ("wooded", 5): "mid_story",  # Behind the Rock Wall (Sherm / nut clip)
    ("wooded", 6): "mid_story",  # Back Way Up the Mountain (8-bit Station 8)
    ("wooded", 12): "mid_story",  # Over the Cliff's Edge (Summit Path)
    ("wooded", 18): "mid_story",  # Nut on the Tall Fence (Station 8)
    ("wooded", 43): "mid_story",  # Flower Road Run
    ("wooded", 44): "mid_story",  # Flower Road Reach
    ("wooded", 45): "mid_story",  # Elevator Escalation
    ("wooded", 46): "mid_story",  # Elevator Blind Spot (Sherm)
    ("luncheon", 31): "base",  # Light the Two Flames (tras #2, antes Big Pot)
    ("luncheon", 34): "base",  # Treasure Chest in the Veggies (tras #2, antes Big Pot)
}


def wiki_moon_in_scope(
    kingdom: str,
    moon: int,
    wiki_entry: dict[str, str] | None,
    rules: dict | None = None,
) -> bool:
    if (kingdom, int(moon)) in FORCE_IN_SCOPE_MOONS:
        return True
    if (kingdom, int(moon)) in FORCE_OUT_OF_SCOPE_MOONS:
        return False
    if kingdom in BOSS_ONLY_KINGDOMS:
        return False
    if kingdom in POSTGAME_KINGDOMS:
        return False
    if wiki_entry is None:
        return False
    if rules is None:
        rules = load_kingdom_availability()

    scope_moons = rules.get("kingdoms", {}).get(kingdom, {}).get("scope_moons")
    if scope_moons is not None:
        return int(moon) in {int(x) for x in scope_moons}

    name = wiki_entry.get("name", "")
    moon_type = wiki_entry.get("type", "")
    prerequisite = wiki_entry.get("prerequisite", "")
    if is_postgame_wiki_entry(name, prerequisite, moon_type):
        return False
    if is_postgame_moon(kingdom, moon, rules):
        return False
    return True


def compute_in_scope_limits(
    wiki_meta: dict[str, dict[int, dict[str, str]]] | None = None,
    rules: dict | None = None,
) -> dict[str, int]:
    if wiki_meta is None:
        wiki_meta = load_wiki_moon_meta()
    if rules is None:
        rules = load_kingdom_availability()

    limits: dict[str, int] = {}
    for kingdom in KINGDOM_COLUMNS:
        moons = wiki_meta.get(kingdom, {})
        in_scope = [
            moon
            for moon, entry in moons.items()
            if wiki_moon_in_scope(kingdom, moon, entry, rules)
        ]
        limits[kingdom] = max(in_scope) if in_scope else 0
    return limits


def moon_odyssey_units(tags: set[str] | list[str] | None) -> int:
    """Unidades Odyssey al depositar (multi_moon cuenta ×3)."""
    if tags and "multi_moon" in tags:
        return MULTI_MOON_ODYSSEY_UNITS
    return 1


def moon_ref_odyssey_units(
    ref: dict,
    registry: dict[tuple[str, int], dict],
) -> int:
    key = (str(ref["kingdom"]), int(ref["moon"]))
    entry = registry.get(key)
    return moon_odyssey_units(entry.get("tags") if entry else None)


def goal_moon_count_mode(goal: str, obj: dict, *, moonish: bool = False) -> str | None:
    """Cómo interpreta {{X}} una goal de conteo de lunas.

    - odyssey_units: totales de reino / {{X}} Total Moons global (tooltip multi×3).
    - physical_moons: pool temático o Multi-Moon[[s]] / Total Multi-Moons
      (1 por multiluna en lista; no unidades Odyssey).
    """
    tip = obj.get("tooltip") or ""
    low = goal.lower()
    # Multilunas: siempre Moon Get físico (1 entrada = 1), nunca ×3 Odyssey.
    # Incluye Total Multi-Moons aunque el tooltip diga "count as 3" por error.
    if "multi-moon" in low or goal.startswith("All Multi-Moons"):
        return "physical_moons"
    if KINGDOM_MOONS_ODYSSEY_TOOLTIP in tip:
        return "odyssey_units"
    if (moonish or "moon" in low) and GOAL_X in goal and "moon" in low:
        return "physical_moons"
    return None


def enrich_moon_ref_odyssey(
    ref: dict,
    registry: dict[tuple[str, int], dict],
) -> dict:
    """Completa name, disponibilidad y odyssey_units (multi ×3) desde el registry.

    Orden: kingdom, moon, name, disponibilidad, goal, tag[, odyssey_units].
    `goal` / `tag` (bool) se conservan si vienen en el ref.
    """
    try:
        kingdom = str(ref["kingdom"])
        moon = int(ref["moon"])
    except (KeyError, TypeError, ValueError):
        return dict(ref)

    entry = registry.get((kingdom, moon))
    name = str(ref.get("name") or "").strip()
    if not name or name == "?":
        name = str((entry or {}).get("name") or f"Moon {moon}")

    out: dict = {"kingdom": kingdom, "moon": moon, "name": name}
    if entry is not None:
        out["disponibilidad"] = str(
            ref.get("disponibilidad")
            or entry.get("availability")
            or "base"
        )
    elif ref.get("disponibilidad") not in (None, ""):
        out["disponibilidad"] = str(ref["disponibilidad"])

    if "goal" in ref:
        out["goal"] = bool(ref["goal"])
    if "tag" in ref:
        out["tag"] = bool(ref["tag"])

    units = moon_ref_odyssey_units(out, registry)
    if units != 1:
        out["odyssey_units"] = units
    return out


def sum_moon_odyssey_units(
    moons: list[dict],
    registry: dict[tuple[str, int], dict],
) -> int:
    return sum(moon_ref_odyssey_units(m, registry) for m in moons)


def compute_in_scope_moon_totals(
    registry: dict[tuple[str, int], dict] | None = None,
) -> dict[str, int | dict[str, int]]:
    """Totales in-scope: lunas físicas vs unidades Odyssey (multi×3)."""
    if registry is None:
        registry = build_matrix_moon_registry()
    moon_count_by_kingdom: dict[str, int] = {}
    odyssey_units_by_kingdom: dict[str, int] = {}
    for (kingdom, _moon), entry in registry.items():
        moon_count_by_kingdom[kingdom] = moon_count_by_kingdom.get(kingdom, 0) + 1
        odyssey_units_by_kingdom[kingdom] = (
            odyssey_units_by_kingdom.get(kingdom, 0)
            + moon_odyssey_units(entry.get("tags"))
        )
    return {
        "moon_count": len(registry),
        "odyssey_units": sum(odyssey_units_by_kingdom.values()),
        "moon_count_by_kingdom": moon_count_by_kingdom,
        "odyssey_units_by_kingdom": odyssey_units_by_kingdom,
    }


def refresh_in_scope_odyssey_meta(meta: dict | None = None) -> dict:
    """Actualiza totales in-scope: lunas físicas vs unidades Odyssey (multi×3)."""
    if meta is None:
        meta = load_meta()
    totals = compute_in_scope_moon_totals(build_matrix_moon_registry())
    meta["in_scope_moon_count"] = totals["moon_count"]
    meta["in_scope_moons"] = dict(
        sorted(
            totals["moon_count_by_kingdom"].items(),
            key=lambda kv: (
                KINGDOM_COLUMNS.index(kv[0]) if kv[0] in KINGDOM_COLUMNS else 99,
                kv[0],
            ),
        )
    )
    meta["in_scope_odyssey_units"] = totals["odyssey_units"]
    meta["in_scope_odyssey_units_by_kingdom"] = totals["odyssey_units_by_kingdom"]
    project = load_project()
    project["meta"] = meta
    project["n_in_scope_moons"] = int(totals["moon_count"])
    ordered: dict = {}
    for key in ("_definition", "_note", "n_in_scope_moons"):
        if key in project:
            ordered[key] = project[key]
    for key, value in project.items():
        if key not in ordered:
            ordered[key] = value
    save_project(ordered)
    return meta


def _normalize_prerequisite(prerequisite: str) -> str:
    return re.sub(r"\s+", " ", prerequisite).strip().lower()


def _prereq_requires_marker(prerequisite: str, marker: str) -> bool:
    """True si el prereq exige el marcador (no solo una alternativa tras «or»)."""
    if not marker or marker not in prerequisite:
        return False
    if " or " not in prerequisite:
        return True
    # «A or B»: solo cuenta si todas las ramas exigen el marcador.
    return all(marker in part for part in prerequisite.split(" or "))


def _prereq_requires_any_marker(
    prerequisite: str, markers: list[str] | tuple[str, ...]
) -> bool:
    return any(_prereq_requires_marker(prerequisite, m) for m in markers)


def _is_peach_moon(name: str) -> bool:
    low = name.lower()
    return low.startswith(("peach in the ", "peach in bowser"))


def is_postgame_wiki_entry(
    name: str,
    prerequisite: str = "",
    moon_type: str = "",
) -> bool:
    """Moon Rock, cups, Peach, turista y prereqs post-créditos."""
    if "Moon Rock" in (moon_type or ""):
        return True
    if any(marker in name for marker in POSTGAME_NAME_MARKERS):
        return True
    if any(marker in name for marker in EXCLUDED_NAME_MARKERS):
        return True
    if _is_peach_moon(name):
        return True
    prereq = _normalize_prerequisite(prerequisite)
    return any(marker in prereq for marker in POSTGAME_PREREQ_MARKERS)


def _is_painting_or_hint_art_moon(
    name: str,
    tags: set[str] | list[str] | None = None,
) -> bool:
    """Pinturas y pistas artisticas: requieren acceso desde otro reino.

    Detectamos por nombre (ya no hay tags obtain painting/hint_art).
    """
    del tags  # API compat con callers que pasan tags
    low = name.lower()
    return (
        low.startswith("secret path to")
        or ("found with" in low and "art" in low)
        or low.endswith("kingdom art")
    )


def _clean_wiki_prerequisite(wiki_entry: dict[str, str] | None) -> str:
    prerequisite = _normalize_prerequisite(
        (wiki_entry or {}).get("prerequisite", "")
    )
    # Quitar restos de refs wiki que a veces quedan en el texto.
    prerequisite = re.sub(r"<ref[^>]*>.*?</ref>", " ", prerequisite, flags=re.I | re.S)
    return re.sub(r"\s+", " ", prerequisite).strip()


def _availability_for_simple_kingdom(
    kingdom: str,
    moon: int,
    kingdom_rules: dict,
) -> str | None:
    if kingdom in BOSS_ONLY_KINGDOMS:
        return "base"
    if kingdom == "cap":
        return "revisit"
    if kingdom == "cascade":
        if moon in kingdom_rules.get("base_moons", []):
            return "base"
        if moon in kingdom_rules.get("revisit_moons", []):
            return "revisit"
        return "world_peace"
    if kingdom == "lost":
        if moon == kingdom_rules.get("revisit_moon"):
            return "revisit"
        return "base"
    if kingdom == "moon":
        return "base"
    return None


def _story_markers_for(
    kingdom: str,
    kingdom_rules: dict,
    *,
    final: bool,
) -> list[str]:
    key = "final_story_markers" if final else "mid_story_markers"
    defaults = FINAL_STORY_MARKERS if final else MID_STORY_MARKERS
    markers = list(kingdom_rules.get(key, []))
    markers.extend(defaults.get(kingdom, ()))
    return [m.lower() for m in markers]


def _availability_from_prerequisite(
    prerequisite: str,
    kingdom: str,
    kingdom_rules: dict,
) -> str:
    if prerequisite == "second visit":
        return "revisit"
    final_markers = _story_markers_for(kingdom, kingdom_rules, final=True)
    if final_markers and _prereq_requires_any_marker(prerequisite, final_markers):
        return "world_peace"
    if "or second visit" in prerequisite:
        return "world_peace"
    mid_markers = _story_markers_for(kingdom, kingdom_rules, final=False)
    if mid_markers and _prereq_requires_any_marker(prerequisite, mid_markers):
        return "mid_story"
    # Wiki «None» / prereq temprano = al llegar o antes de la 1ª multi.
    return "base"


def infer_availability(
    kingdom: str,
    moon: int,
    name: str,
    wiki_entry: dict[str, str] | None,
    rules: dict | None = None,
    tags: set[str] | list[str] | None = None,
) -> str:
    """base / mid_story / revisit / world_peace según patrón del reino.

    - Grandes con 2 multilunas (Sand/Wooded/Metro/Luncheon):
      base → mid_story (tras 1ª multi) → world_peace (tras 2ª).
    - Pequeños: Cap solo revisit; Cascade base→WP→revisit; Lost base→revisit.
    - Resto con historia: base → world_peace.
    - Pinturas Secret Path: SECRET_PATH_AVAILABILITY (cache wiki suele ser «None»).
    - Hint Art: prereq wiki (final → WP; 1ª multi → mid_story; None → base).
    """
    del tags  # API compat
    if rules is None:
        rules = load_kingdom_availability()

    kingdom_rules = rules.get("kingdoms", {}).get(kingdom, {})
    prerequisite = _clean_wiki_prerequisite(wiki_entry)

    key = (kingdom, int(moon))
    if key in AVAILABILITY_OVERRIDES:
        return AVAILABILITY_OVERRIDES[key]

    # Pinturas Secret Path: override curado (cache wiki suele ser «None»).
    if name.lower().startswith("secret path to"):
        return SECRET_PATH_AVAILABILITY.get(key, "base")

    simple = _availability_for_simple_kingdom(kingdom, moon, kingdom_rules)
    if simple is not None:
        return simple

    return _availability_from_prerequisite(prerequisite, kingdom, kingdom_rules)


def is_postgame_moon(kingdom: str, moon: int, rules: dict | None = None) -> bool:
    if rules is None:
        rules = load_kingdom_availability()
    cutoff = rules.get("kingdoms", {}).get(kingdom, {}).get("postgame_from_moon")
    return cutoff is not None and moon >= cutoff


def collect_tag_combination_violations() -> list[tuple[str, int, str, list[str]]]:
    """Return [(kingdom, moon, name, issues), ...] for invalid tag sets."""
    registry = build_matrix_moon_registry()
    violations: list[tuple[str, int, str, list[str]]] = []
    for (kingdom, moon), entry in sorted(registry.items()):
        tags = normalize_moon_tags(entry["tags"], kingdom=kingdom, moon=moon)
        issues = tag_combination_violations(tags, kingdom=kingdom, moon=moon)
        if issues:
            violations.append((kingdom, moon, entry["name"], issues))
    return violations


def availability_violations(item: dict, rules: dict | None = None) -> list[str]:
    if rules is None:
        rules = load_kingdom_availability()

    kingdom = item["kingdom"]
    moon = item["moon"]
    tier = item.get("availability", "base")
    kingdom_rules = rules.get("kingdoms", {}).get(kingdom)
    issues: list[str] = []

    if kingdom_rules is None:
        return issues

    if is_postgame_moon(kingdom, moon, rules):
        issues.append(f"{kingdom}#{moon} es postgame (>= {kingdom_rules['postgame_from_moon']})")
        return issues

    if not kingdom_rules.get(tier, False):
        # Pinturas: mid_story/WP por unlock de otro reino (p. ej. lake#26).
        if tier in ("mid_story", "world_peace") and _is_painting_or_hint_art_moon(
            item.get("name", ""), item.get("tags")
        ):
            return issues
        allowed = [
            t
            for t in ("base", "mid_story", "revisit", "world_peace")
            if kingdom_rules.get(t)
        ]
        issues.append(
            f"{kingdom}#{moon} usa '{tier}' pero el reino solo permite: {', '.join(allowed) or 'ninguno'}"
        )
    return issues


def collect_availability_violations() -> list[tuple[str, str, list[str]]]:
    """Return [(catalog_file, moon_key, issues), ...]."""
    rules = load_kingdom_availability()
    violations: list[tuple[str, str, list[str]]] = []

    for path in sorted(CATALOG_DIR.glob("*.json")):
        if path.name in SKIP_CATALOGS:
            continue
        catalog = load_catalog(path)
        for item in catalog.get("items", []):
            issues = availability_violations(item, rules)
            if issues:
                key = f"{item['kingdom']}#{item['moon']}"
                violations.append((path.name, key, issues))
    return violations


def kingdom_tier_order(kingdom: str, rules: dict | None = None) -> list[str]:
    if rules is None:
        rules = load_kingdom_availability()
    kingdom_rules = rules.get("kingdoms", {}).get(kingdom, {})
    return kingdom_rules.get(
        "tier_order", ["base", "mid_story", "revisit", "world_peace"]
    )


def tier_sort_key(kingdom: str, tier: str, rules: dict | None = None) -> int:
    order = kingdom_tier_order(kingdom, rules)
    try:
        return order.index(tier)
    except ValueError:
        return len(order)


def kingdom_availability_summary(registry: dict) -> dict[str, dict[str, int]]:
    """Count moons per kingdom/tier from a moon registry."""
    from collections import defaultdict

    summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entry in registry.values():
        summary[entry["kingdom"]][entry["availability"]] += 1
    return {k: dict(v) for k, v in summary.items()}


def is_postgame_item(item: dict, rules: dict | None = None) -> bool:
    if rules is None:
        rules = load_kingdom_availability()

    kingdom = item["kingdom"]
    moon = item["moon"]
    name = item.get("name", "")

    if is_postgame_moon(kingdom, moon, rules):
        return True
    if is_postgame_wiki_entry(name):
        return True
    return False


def in_scope(item: dict, allowed: set[str]) -> bool:
    return item.get("availability", "base") in allowed


def load_catalog(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_flat_json_value(value: object) -> bool:
    """Escalar o lista/dict solo de escalares (objeto 'hoja' compactable)."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return True
    if isinstance(value, list):
        return all(
            isinstance(x, (str, int, float, bool)) or x is None for x in value
        )
    if isinstance(value, dict):
        # Multilinea solo si hay estructuras anidadas (p. ej. moons[] en
        # goals_referencia). orden+goal con solo escalares → una linea.
        return all(_is_flat_json_value(v) for v in value.values())
    return False


# Resúmenes: multilinea (un campo por linea); subdicts by_* compactos.
MULTILINE_DICT_KEYS = frozenset(
    {"pool_summary", "lista_summary", "moons_summary"}
)


def _fmt_catalog_scalar_list(
    value: list,
    level: int,
    *,
    indent: int,
    multiline: bool,
) -> str:
    pad = " " * (indent * level)
    pad_in = " " * (indent * (level + 1))
    if not value:
        return "[]"
    if not multiline or len(value) <= 1:
        return (
            "["
            + ", ".join(json.dumps(x, ensure_ascii=False) for x in value)
            + "]"
        )
    lines = [f"{pad_in}{json.dumps(x, ensure_ascii=False)}" for x in value]
    return "[\n" + ",\n".join(lines) + "\n" + pad + "]"


def _fmt_catalog_json_value(
    value: object,
    level: int,
    *,
    indent: int,
    multi_keys: frozenset[str],
    key: str | None = None,
) -> str:
    pad = " " * (indent * level)
    pad_in = " " * (indent * (level + 1))

    if isinstance(value, dict):
        if not value:
            return "{}"
        force_multiline = bool(key and key in MULTILINE_DICT_KEYS)
        if _is_flat_json_value(value) and not force_multiline:
            inner = ", ".join(
                f"{json.dumps(k, ensure_ascii=False)}: "
                f"{json.dumps(v, ensure_ascii=False)}"
                for k, v in value.items()
            )
            return "{" + inner + "}"
        lines = [
            f"{pad_in}{json.dumps(k, ensure_ascii=False)}: "
            f"{_fmt_catalog_json_value(v, level + 1, indent=indent, multi_keys=multi_keys, key=str(k))}"
            for k, v in value.items()
        ]
        return "{\n" + ",\n".join(lines) + "\n" + pad + "}"

    if isinstance(value, list):
        if not value:
            return "[]"
        if all(isinstance(x, (str, int, float, bool)) or x is None for x in value):
            return _fmt_catalog_scalar_list(
                value,
                level,
                indent=indent,
                multiline=bool(key and key in multi_keys),
            )
        lines = [
            f"{pad_in}{_fmt_catalog_json_value(x, level + 1, indent=indent, multi_keys=multi_keys)}"
            for x in value
        ]
        return "[\n" + ",\n".join(lines) + "\n" + pad + "]"

    return json.dumps(value, ensure_ascii=False)


def dumps_catalog_json(
    data: object,
    *,
    indent: int = 2,
    multiline_string_list_keys: frozenset[str] | None = None,
) -> str:
    """JSON legible: estructura con indent, objetos hoja en una sola linea.

    Ejemplo items/moons:
      {"kingdom": "sand", "moon": 12, "name": "...", "tags": ["sand"]}

    multiline_string_list_keys: claves cuyas listas de strings (len>1) van
    una por linea (p. ej. goals en goal_icons).
    """
    multi_keys = multiline_string_list_keys or frozenset()
    return (
        _fmt_catalog_json_value(
            data, 0, indent=indent, multi_keys=multi_keys
        )
        + "\n"
    )


def write_catalog_json(
    path: Path,
    data: object,
    *,
    multiline_string_list_keys: frozenset[str] | None = None,
) -> None:
    """Escribe catalogo JSON con objetos internos compactos."""
    data = remap_cloud_slugs_for_export(data)
    root = os.path.realpath(str(ROOT))
    target = os.path.realpath(str(path))
    text = dumps_catalog_json(
        data, multiline_string_list_keys=multiline_string_list_keys
    )
    # open solo en la rama validada (sanitizer reconocible por SAST).
    if target == root or target.startswith(root + os.sep):
        if path.is_file():
            try:
                if path.read_text(encoding="utf-8") == text:
                    return
            except OSError:
                pass
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        return
    raise ValueError(f"Path fuera del repo: {path}")


BINGO_GROUPS_DEFINITION = (
    "Grupos de bingo: 'objectives', 'moons' y 'lista' son listas "
    "independientes. objectives[] = {goal, range, progression, …} "
    "desde Combined (tooltip/icons/cats → goals_referencia / "
    "goal_icons / bingo_lineas). "
    "moons[] = {kingdom, moon, name, disponibilidad, goal, tag"
    "[, odyssey_units]}; multi_moon añade odyssey_units:3. "
    "goal/tag (bool): cuenta para Combined del grupo / la luna lleva "
    "alguna tag del grupo (id, moon_tag o aggregate; p. ej. fauna en "
    "lunas de familias <umbral aunque el paraguas no retaguee). "
    "tag_only (SPEC): lunas con tag del grupo pero goal=false; "
    "van en moons[] junto al pool de goals. "
    "lista[] = union de elementos de goal_lists.json para objectives "
    "con pool lista (lista_source + cada item: kingdom, source, id, "
    "id_list, name, disponibilidad). Zone → Catalog/zonas_inventario.json. "
    "kind = combo de has (8): goals | moons | lista | goals+moons | "
    "goals+lista | moons+lista | todo | nada (kind usa goals = pool "
    "objectives[]). "
    "kind_goal_tag = eq | gt | na (n.goal ==|> n.tag; na = sin moons). "
    "tag_inventario (bool, grupo): id en Catalog/tags_inventario.json "
    "(false = solo grupo bingo; revisar; distinto de moons[].tag). "
    "Por grupo: has={objectives,moons,lista} (bool = pool no vacío) + "
    "n={objectives,moons,goal,tag,lista[,odyssey_units]} (conteos; "
    "goal/tag = suma de moons[].goal/tag; "
    "odyssey_units solo si el pool incluye multilunas ≠ moons). "
    "orden = id numerico 1..N tras ordenar por id (slug). "
    "Meta operativa (moon_tag/capture/apply_moon_tag/tag_only_moons/…) "
    "vive en Files/sync_objective_moon_groups.py (OBJECTIVE_MOON_GROUP_SPECS), "
    "no en este JSON; load_bingo_groups() la reinyecta al usarla. "
    "Cobertura incompleta OK por ahora."
)

BINGO_GROUPS_NOTE = (
    "Cabecera: n_groups; n_groups_<kind> (solo si >0; 8 combos has); "
    "n_groups_goal_eq_tag|gt_tag|tag_na (solo si >0; kind_goal_tag); "
    "n_groups_with_objectives|moons|lista (= grupos con has.X true); "
    "n_objectives_total / n_moons_total / n_lista_total "
    "(unicos en todo el file, sin duplicar entre grupos; "
    "n_lista_total = goal_lists.n_items + binoculars (capturas_lunas); "
    "cada ítem aparece ≥1 vez entre grupos, sin duplicar en el total). "
    "n_groups_sin_tag_inventario (solo si >0; grupos con tag_inventario=false). "
    "Por grupo: id, orden, kind, kind_goal_tag, tag_inventario, has, n, "
    "objectives[], moons_summary/lista_summary (si moons[]/lista[] "
    "omitidos; by_kingdom como goals_referencia), moons[], "
    "lista_source (si lista[] no vacía), lista[]. "
    "moons[]/lista[] omitidos en JSON si OMIT_MOONS / goals_only (n.* "
    "calculado). Sin meta al final (moon_tag/kingdom/capture/_note → specs). "
    "Al normalizar, objectives y lista se regeneran desde Combined / "
    "goal_lists (salvo goals_only en SPEC: moons/lista[] vacíos, n.lista "
    "calculado). Orden: "
    "groups por id; goals {{X}}+alpha "
    "(reinos: orden curado); moons sin reordenar; "
    "lista[] = reino(historia) -> source alfa -> id_list."
)

# kind JSON → clave de cabecera n_groups_*
_GROUP_KIND_HEADER: dict[str, str] = {
    "todo": "n_groups_todo",
    "goals+moons": "n_groups_goals_moons",
    "goals+lista": "n_groups_goals_lista",
    "moons+lista": "n_groups_moons_lista",
    "goals": "n_groups_goals",
    "moons": "n_groups_moons",
    "lista": "n_groups_lista",
    "nada": "n_groups_nada",
}

_GROUP_KIND_HEADER_ORDER: tuple[str, ...] = tuple(_GROUP_KIND_HEADER.values())


# kind_goal_tag JSON → clave de cabecera n_groups_*
_GROUP_GOAL_TAG_KIND_HEADER: dict[str, str] = {
    "eq": "n_groups_goal_eq_tag",
    "gt": "n_groups_goal_gt_tag",
    "na": "n_groups_goal_tag_na",
}

_GROUP_GOAL_TAG_KIND_HEADER_ORDER: tuple[str, ...] = tuple(
    _GROUP_GOAL_TAG_KIND_HEADER.values()
)


def finalize_bingo_groups_doc(bingo: dict) -> dict:
    """Cabecera n_groups + conteos por kind / gaps / totales de pool."""
    groups = list(bingo.get("groups") or [])
    kind_counts = dict.fromkeys(_GROUP_KIND_HEADER, 0)
    goal_tag_counts = dict.fromkeys(_GROUP_GOAL_TAG_KIND_HEADER, 0)
    for g in groups:
        kind = str(g.get("kind") or "nada")
        if kind in kind_counts:
            kind_counts[kind] += 1
        else:
            kind_counts["nada"] += 1
        gtk = str(g.get("kind_goal_tag") or group_goal_tag_kind(g))
        if gtk in goal_tag_counts:
            goal_tag_counts[gtk] += 1

    bingo["n_groups"] = len(groups)
    for kind, header_key in _GROUP_KIND_HEADER.items():
        n = kind_counts[kind]
        if n:
            bingo[header_key] = n
        else:
            bingo.pop(header_key, None)

    for gtk, header_key in _GROUP_GOAL_TAG_KIND_HEADER.items():
        n = goal_tag_counts[gtk]
        if n:
            bingo[header_key] = n
        else:
            bingo.pop(header_key, None)
    bingo.pop("n_groups_goal_lt_tag", None)

    # Legacy keys ya no se escriben.
    for legacy in (
        "n_groups_both",
        "n_groups_empty",
        "n_groups_objectives",
        "n_groups_without_goals",
        "n_groups_without_moons",
        "n_groups_without_lista",
    ):
        bingo.pop(legacy, None)

    # Mismo criterio que filtrar has.objectives / has.moons / has.lista.
    bingo["n_groups_with_objectives"] = sum(
        1 for g in groups if group_has_pool(g, "objectives")
    )
    bingo.pop("n_groups_with_goals", None)
    bingo["n_groups_with_moons"] = sum(
        1 for g in groups if group_has_pool(g, "moons")
    )
    bingo["n_groups_with_lista"] = sum(
        1 for g in groups if group_has_pool(g, "lista")
    )
    bingo.pop("n_groups_with_tag", None)
    n_sin_tag_inv = sum(1 for g in groups if g.get("tag_inventario") is False)
    if n_sin_tag_inv:
        bingo["n_groups_sin_tag_inventario"] = n_sin_tag_inv
    else:
        bingo.pop("n_groups_sin_tag_inventario", None)
    bingo.pop("n_groups_tag_false", None)

    # Totales únicos en todo el file (una goal/luna/ítem lista no se cuenta 2×).
    from goal_list_lib import list_item_match_key

    uniq_goals: set[str] = set()
    uniq_moons: set[tuple[str, int]] = set()
    uniq_lista: set[tuple] = set()
    combined_by_goal = load_combined_objectives_by_goal()
    for g in groups:
        for o in g.get("objectives") or []:
            if isinstance(o, dict) and o.get("goal"):
                uniq_goals.add(str(o["goal"]))
        for m in _resolve_bingo_group_moons_raw(g):
            uniq_moons.add((str(m["kingdom"]), int(m["moon"])))
        src_hint = str(g.get("lista_source") or "") or None
        lista_items, _ = _resolve_bingo_group_lista_items(g, combined_by_goal)
        for it in lista_items:
            list_name = str(it.get("source") or "") or None
            if not list_name and src_hint and "+" not in src_hint:
                list_name = src_hint
            # Cuenta ítems únicos con source (goal_lists + binoculars en captures).
            if not list_name:
                continue
            uniq_lista.add(list_item_match_key(it, list_name=list_name))
    bingo["n_objectives_total"] = len(uniq_goals)
    bingo["n_moons_total"] = len(uniq_moons)
    bingo["n_lista_total"] = len(uniq_lista)

    bingo["_definition"] = BINGO_GROUPS_DEFINITION
    bingo["_note"] = BINGO_GROUPS_NOTE

    header_keys = (
        "_definition",
        "_note",
        "n_groups",
        *_GROUP_KIND_HEADER_ORDER,
        *_GROUP_GOAL_TAG_KIND_HEADER_ORDER,
        "n_groups_with_objectives",
        "n_groups_with_moons",
        "n_groups_with_lista",
        "n_groups_sin_tag_inventario",
        "n_objectives_total",
        "n_moons_total",
        "n_lista_total",
        "groups",
    )
    ordered: dict = {}
    for key in header_keys:
        if key in bingo:
            ordered[key] = bingo[key]
    for key, value in bingo.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def load_bingo_group_moon_keys() -> set[tuple[str, int]]:
    """Lunas que pertenecen a algun grupo de bingo (tag generica 'group')."""
    if not BINGO_GROUPS_PATH.exists():
        return set()
    catalog = load_catalog(BINGO_GROUPS_PATH)
    keys: set[tuple[str, int]] = set()
    for group in catalog.get("groups", []):
        for raw in group_moons(group):
            keys.add((raw["kingdom"], int(raw["moon"])))
    return keys


# Campos de objetivo Combined que se copian a objectives[] de grupos/capturas.
# Tooltip, icons y board/line van en goals_referencia / goal_icons / bingo_lineas.
OBJECTIVE_REF_FIELDS = (
    "goal",
    "range",
    "progression",
    "individual_limit",
    "progressive_ranges",
    "weighting",
)


def objective_goal_sort_key(goal: str) -> tuple:
    """{{X}}… primero, luego alfabetico (como Combined / sort_combined_json)."""
    return (0 if goal.startswith(GOAL_X) else 1, goal.lower())


def kingdom_story_index(kingdom: str) -> int:
    """Índice de reino en orden de historia (incluye ruined/mushroom)."""
    k = str(kingdom or "")
    if k in STORY_ORDER:
        return STORY_ORDER.index(k)
    if k == "mushroom":
        return len(STORY_ORDER)  # postgame, tras moon
    return 200


def natural_name_key(name: str) -> tuple:
    """Alfabetico con numeros naturales (path 2 < path 10)."""
    parts = re.split(r"(\d+)", (name or "").lower())
    out: list[tuple] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            out.append((0, int(part)))
        else:
            out.append((1, part))
    return tuple(out)


def _entity_id_sort_key(item: dict, k_ord: int) -> tuple | None:
    empty_name: tuple = ()
    for key in ("moon", "checkpoint", "id_list", "id"):
        val = item.get(key)
        if val is None:
            continue
        try:
            return (k_ord, 0, int(val), 0, empty_name)
        except (TypeError, ValueError):
            continue
    moons = item.get("moons")
    if isinstance(moons, list) and moons:
        try:
            return (k_ord, 0, int(min(int(m) for m in moons)), 0, empty_name)
        except (TypeError, ValueError):
            return None
    return None


def _entity_shop_sort_key(
    item: dict, k_ord: int, name_key: tuple
) -> tuple | None:
    if "regional" not in item and "coins" not in item:
        return None
    if "regional" in item:
        try:
            return (k_ord, 1, 0, int(item["regional"]), name_key)
        except (TypeError, ValueError):
            pass
    if "coins" in item:
        try:
            return (k_ord, 1, 1, int(item["coins"]), name_key)
        except (TypeError, ValueError):
            pass
    return None


def entity_sort_key(item: dict) -> tuple:
    """Orden proyecto: reino (historia) → id numerico → precio → nombre.

    Ids prioritarios: moon, checkpoint, id_list, id.
    Tienda: regional antes que coins, luego importe, luego nombre.

    Siempre (k_ord, bucket, a, b, name_key) — misma longitud en todos los caminos.
    """
    k_ord = kingdom_story_index(str(item.get("kingdom") or ""))
    id_key = _entity_id_sort_key(item, k_ord)
    if id_key is not None:
        return id_key
    name = str(item.get("name") or item.get("capture") or item.get("level") or "")
    name_key = natural_name_key(name)
    shop_key = _entity_shop_sort_key(item, k_ord, name_key)
    if shop_key is not None:
        return shop_key
    return (k_ord, 2, 0, 0, name_key)


def objective_goal(raw: object) -> str | None:
    """Extrae el texto goal de un string legado o de un objeto {goal: ...}."""
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        goal = raw.get("goal")
        if goal:
            return str(goal)
    return None


def group_objectives(group: dict) -> list[str]:
    """Textos goal de los objetivos Combined del grupo.

    Compat: lista de strings, lista de objetos, o 'goal' legado.
    """
    raw = group.get("objectives")
    if isinstance(raw, list):
        goals: list[str] = []
        for item in raw:
            goal = objective_goal(item)
            if goal:
                goals.append(goal)
        return goals
    legacy = group.get("goal")
    if legacy:
        return [str(legacy)]
    return []


def load_combined_objectives_by_goal(*, include_disabled: bool = True) -> dict[str, dict]:
    """Indice goal → objeto Combined (activo o todos)."""
    if not JSON_PATH.exists():
        return {}
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for obj in data.get("objectives", []):
        goal = obj.get("goal")
        if not goal:
            continue
        if not include_disabled and obj.get("disabled"):
            continue
        out[str(goal)] = obj
    return out


def sort_category_list(tags: list | None) -> list[str]:
    """Tags canónicas, unicas, orden alfabetico estable."""
    return sorted(canonicalize_tag_list(tags))


def objective_ref_from_combined(goal: str, combined: dict | None = None) -> dict:
    """Objetivo ligero: goal + range/progression (+ limits). Sin tooltip/icons/cats.

    En catálogo, weighting siempre se escribe (default 100 si Combined lo omite).
    Combined sigue omitiendo 100 al guardar el bingo.
    """
    if combined is None:
        combined = load_combined_objectives_by_goal().get(goal)
    ref: dict = {"goal": goal}
    if not combined:
        return ref
    for key in OBJECTIVE_REF_FIELDS:
        if key == "goal":
            continue
        if key == "weighting":
            try:
                ref["weighting"] = int(combined.get("weighting", 100))
            except (TypeError, ValueError):
                ref["weighting"] = 100
            continue
        if key not in combined or combined[key] in (None, "", []):
            continue
        ref[key] = combined[key]
    return ref


def _capture_name_to_goal() -> dict[str, str]:
    """captura Combined → goal (lazy; evita import circular al cargar catalog_lib)."""
    from export_capturas_lunas import CAPTURE_LIST, CAPTURE_OBJECTIVE

    out: dict[str, str] = {}
    for meta in CAPTURE_LIST:
        goal = CAPTURE_OBJECTIVE.get(int(meta["id"]))
        if goal:
            name = str(meta["name"])
            out[name] = str(goal)
            out[name.casefold()] = str(goal)
    return out


def _captures_umbrella_goal_names(
    active: dict[str, dict],
    capture_goals: dict[str, str],
) -> list[str]:
    names = {g for g in capture_goals.values() if g in active}
    # Subgoals de specs con capture (p. ej. snow_goomba / pokio_hole).
    # La meta `capture` no se persiste en bingo_groups.json al normalizar.
    from sync_objective_moon_groups import OBJECTIVE_MOON_GROUP_SPECS, _spec_goals

    for spec in OBJECTIVE_MOON_GROUP_SPECS.values():
        if not spec.get("capture"):
            continue
        for goal in _spec_goals(spec):
            if goal in active:
                names.add(goal)
    # Goal global de capturar X cosas distintas (no está en CAPTURE_OBJECTIVE).
    if GOAL_UNIQUE_CAPTURES in active:
        names.add(GOAL_UNIQUE_CAPTURES)
    return sorted(names, key=objective_goal_sort_key)


def _capture_group_goal_names(
    group: dict,
    active: dict[str, dict],
    capture_goals: dict[str, str],
) -> list[str]:
    existing = group_objectives(group)
    listed = [g for g in existing if g in active]
    # Spec/listado del grupo gana (p. ej. Seaside vs Lake Cheep Cheep).
    if listed:
        return listed
    key = str(group.get("capture") or "")
    mapped = capture_goals.get(key) or capture_goals.get(key.casefold())
    if mapped and mapped in active:
        return [mapped]
    return []


def resolve_group_goal_names(
    group: dict,
    combined_by_goal: dict[str, dict] | None = None,
    *,
    capture_goals: dict[str, str] | None = None,
) -> list[str]:
    """Goals actuales del grupo segun Combined (fuente de verdad).

    - Grupo `captures`: todos los CAPTURE_OBJECTIVE activos en Combined
      + {{X}} Unique Captures (goal global, no ligada a una captura concreta).
    - Grupo con `capture`: el goal mapeado si existe en Combined.
    - Resto: goals listados que sigan existiendo (activos) en Combined.
    Goals renombrados/desactivados/huérfanos se descartan o sustituyen.
    """
    if combined_by_goal is None:
        combined_by_goal = load_combined_objectives_by_goal(include_disabled=False)
    active = {
        g: o for g, o in combined_by_goal.items() if not o.get("disabled")
    }
    gid = str(group.get("id") or "")
    if capture_goals is None:
        capture_goals = _capture_name_to_goal()

    if gid == "captures":
        return _captures_umbrella_goal_names(active, capture_goals)
    if group.get("capture"):
        return _capture_group_goal_names(group, active, capture_goals)
    return [g for g in group_objectives(group) if g in active]


def group_objective_refs(group: dict, combined_by_goal: dict[str, dict] | None = None) -> list[dict]:
    """Lista de objetos objetivo {goal, ...} siempre desde Combined activo."""
    if combined_by_goal is None:
        combined_by_goal = load_combined_objectives_by_goal()
    active = {
        g: o for g, o in combined_by_goal.items() if not o.get("disabled")
    }
    refs: list[dict] = []
    seen: set[str] = set()
    for goal in resolve_group_goal_names(group, active):
        if goal in seen:
            continue
        seen.add(goal)
        combined = active.get(goal) or combined_by_goal.get(goal)
        if not combined or combined.get("disabled"):
            continue
        refs.append(objective_ref_from_combined(goal, combined))
    return refs


def group_moons(group: dict) -> list[dict]:
    """Lunas del grupo (lista; kingdom físico; independiente de objectives)."""
    raw = group.get("moons")
    if not isinstance(raw, list):
        return []
    return [
        m
        for m in raw
        if isinstance(m, dict) and "kingdom" in m and "moon" in m
    ]


def group_lista(group: dict) -> list[dict]:
    """Elementos lista[] del grupo (pool goal_lists; independiente de moons)."""
    raw = group.get("lista")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def group_has_pools(group: dict) -> dict[str, bool]:
    """Flags de pools: has.objectives / has.moons / has.lista (legacy has_* / goals)."""
    raw = group.get("has")
    if isinstance(raw, dict):
        has_objectives = raw.get("objectives")
        if has_objectives is None:
            has_objectives = raw.get("goals")
        return {
            "objectives": bool(has_objectives),
            "moons": bool(raw.get("moons")),
            "lista": bool(raw.get("lista")),
        }
    return {
        "objectives": bool(group.get("has_goals")),
        "moons": bool(group.get("has_moons")),
        "lista": bool(group.get("has_lista")),
    }


def group_has_pool(group: dict, pool: str) -> bool:
    return bool(group_has_pools(group).get(pool))


def group_n_pools(group: dict) -> dict[str, int]:
    """Conteos: n.objectives / n.moons / n.lista [/ n.odyssey_units]."""
    raw = group.get("n")
    if isinstance(raw, dict):
        out: dict[str, int] = {
            "objectives": int(raw.get("objectives") or 0),
            "moons": int(raw.get("moons") or 0),
            "lista": int(raw.get("lista") or 0),
        }
        if raw.get("odyssey_units") is not None:
            out["odyssey_units"] = int(raw["odyssey_units"])
        return out
    out = {
        "objectives": int(group.get("n_objectives") or 0),
        "moons": int(group.get("n_moons") or 0),
        "lista": int(group.get("n_lista") or 0),
    }
    if group.get("n_odyssey_units") is not None:
        out["odyssey_units"] = int(group["n_odyssey_units"])
    return out


def group_n_pool(group: dict, key: str) -> int:
    return int(group_n_pools(group).get(key) or 0)


def build_group_has_n(
    *,
    n_objectives: int,
    n_moons: int,
    n_lista: int,
    n_odyssey_units: int | None = None,
    n_goal: int = 0,
    n_tag: int = 0,
) -> tuple[dict[str, bool], dict[str, int]]:
    """Construye has{} y n{} de un grupo (odyssey_units solo si ≠ n_moons)."""
    has = {
        "objectives": bool(n_objectives),
        "moons": bool(n_moons),
        "lista": bool(n_lista),
    }
    n: dict[str, int] = {
        "objectives": int(n_objectives),
        "moons": int(n_moons),
        "goal": int(n_goal),
        "tag": int(n_tag),
    }
    if n_odyssey_units is not None and int(n_odyssey_units) != int(n_moons):
        n["odyssey_units"] = int(n_odyssey_units)
    n["lista"] = int(n_lista)
    return has, n


def catalog_tag_ids() -> frozenset[str]:
    """Ids de tag en Catalog/tags_inventario.json."""
    global _CATALOG_TAG_IDS_CACHE
    if _CATALOG_TAG_IDS_CACHE is not None:
        return _CATALOG_TAG_IDS_CACHE
    path = CATALOG_DIR / "tags_inventario.json"
    tags: set[str] = set()
    if path.is_file():
        for row in load_catalog(path).get("tags") or []:
            if isinstance(row, dict) and row.get("tag"):
                tags.add(str(row["tag"]))
    _CATALOG_TAG_IDS_CACHE = frozenset(tags)
    return _CATALOG_TAG_IDS_CACHE


def group_id_has_catalog_tag(group_id: str | None) -> bool:
    """True si el id del grupo es una tag de tags_inventario (no minoritario)."""
    gid = str(group_id or "").strip()
    if not gid:
        return False
    return gid in catalog_tag_ids()


def group_kind(group: dict) -> str:
    """Tipo de grupo según pools presentes.

    goals | moons | lista | goals+moons | goals+lista | moons+lista |
    todo | nada.
    """
    objs = group.get("objectives")
    if isinstance(objs, list):
        has_objectives = bool(objs)
    else:
        has_objectives = group_has_pool(group, "objectives") or bool(
            group_n_pool(group, "objectives")
        )
    if "moons" in group or isinstance(group.get("moons"), list):
        has_moons = bool(group_moons(group))
    else:
        has_moons = group_has_pool(group, "moons") or bool(
            group_n_pool(group, "moons")
        )
    if "lista" in group or isinstance(group.get("lista"), list):
        has_lista = bool(group_lista(group))
    else:
        has_lista = group_has_pool(group, "lista") or bool(
            group_n_pool(group, "lista")
        )
    parts: list[str] = []
    if has_objectives:
        parts.append("goals")
    if has_moons:
        parts.append("moons")
    if has_lista:
        parts.append("lista")
    if not parts:
        return "nada"
    if len(parts) == 3:
        return "todo"
    if len(parts) == 1:
        return parts[0]
    return "+".join(parts)


def group_goal_tag_kind(group: dict) -> str:
    """eq | gt | na según n.goal vs n.tag (na = sin moons)."""
    n = group.get("n")
    if not isinstance(n, dict):
        n = {
            "moons": len(group_moons(group)),
            "goal": sum(1 for m in group_moons(group) if m.get("goal")),
            "tag": sum(1 for m in group_moons(group) if m.get("tag")),
        }
    if int(n.get("moons") or 0) <= 0:
        return "na"
    goal = int(n.get("goal") or 0)
    tag = int(n.get("tag") or 0)
    if goal > tag:
        return "gt"
    return "eq"


_BINGO_GROUP_META_KEYS = (
    "kingdom",
    "moon_tag",
    "tag",
    "large",
    "umbrella",
    "internal",
    "extra_tags",
    "capture",
    "apply_moon_tag",
    "tag_only_moons",
    "_definition",
    "_note",
    "_source",
)

_BINGO_GROUP_SKIP_UNKNOWN = frozenset(
    {
        "goal",
        "objectives",
        "moons",
        "lista",
        "lista_source",
        "tag_only_moons",
        "kind",
        "kind_goal_tag",
        "tag_inventario",
        "has",
        "n",
        "has_goals",
        "has_moons",
        "has_lista",
        "id",
        "orden",
        "n_objectives",
        "n_moons",
        "n_lista",
        "n_odyssey_units",
        "n_objetivos",
        "n_lunas",
    }
)


def _copy_bingo_group_meta(group: dict, out: dict) -> None:
    for key in _BINGO_GROUP_META_KEYS:
        if key in group and group[key] not in (None, "", [], False):
            value = group[key]
            if key == "extra_tags" and isinstance(value, list):
                value = sort_category_list(value)
            out[key] = value
        # apply_moon_tag=False sí se persiste (omite etiquetar lunas).
        elif key == "apply_moon_tag" and group.get(key) is False:
            out[key] = False


def _copy_bingo_group_unknown_keys(group: dict, out: dict) -> None:
    # internal=False no se escribe; True si.
    # Resto de claves desconocidas (sin goal legado ni vacios ni contadores viejos).
    skip = set(out) | _BINGO_GROUP_SKIP_UNKNOWN
    for key, value in group.items():
        if key in skip or value in (None, "", []):
            continue
        out[key] = value


def _bingo_group_goals_only(group: dict) -> bool:
    """True si el SPEC marca goals_only (solo objectives[]; sin moons/lista)."""
    if group.get("goals_only"):
        return True
    gid = str(group.get("id") or "")
    if not gid:
        return False
    return bool(_spec_for_bingo_group(gid).get("goals_only"))


def _bingo_group_omit_moons(group: dict) -> bool:
    """True si moons[] se omite en JSON pero n.moons refleja el pool."""
    if group.get("omit_moons"):
        return True
    gid = str(group.get("id") or "")
    if gid in OMIT_MOONS_GROUP_IDS:
        return True
    return bool(_spec_for_bingo_group(gid).get("omit_moons"))


def _count_preserve_list_order(items: list[dict], key_fn) -> dict[str, int]:
    """Cuenta por clave conservando el orden de primera aparición."""
    counts: dict[str, int] = {}
    for item in items:
        key = key_fn(item)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _summary_disp_label(item: dict) -> str:
    disp = item.get("disponibilidad")
    if isinstance(disp, list):
        return "+".join(str(x) for x in disp)
    return str(disp or "")


def _sort_summary_by_disponibilidad(counts: dict[str, int]) -> dict[str, int]:
    disp_order = {"base": 0, "mid_story": 1, "world_peace": 2, "revisit": 3}

    def sort_key(label: str) -> tuple:
        if "+" in label:
            parts = label.split("+")
            return (min(disp_order.get(p, 99) for p in parts), label)
        return (disp_order.get(label, 99), label)

    return {k: counts[k] for k in sorted(counts, key=sort_key)}


def summarize_bingo_moons_pool(
    moons: list[dict],
    *,
    odyssey_units: int | None = None,
) -> dict:
    """Resumen de moons[] omitido (misma forma que goals_referencia.pool_summary)."""
    by_kingdom = _count_preserve_list_order(
        moons, lambda m: str(m.get("kingdom") or "")
    )
    by_disp = _sort_summary_by_disponibilidad(
        _count_preserve_list_order(moons, _summary_disp_label)
    )
    out: dict = {"n_moons": len(moons)}
    if odyssey_units is not None and int(odyssey_units) != len(moons):
        out["n_odyssey_units"] = int(odyssey_units)
    if by_kingdom:
        out["by_kingdom"] = by_kingdom
    if by_disp:
        out["by_disponibilidad"] = by_disp
    return out


def _lista_regional_total(lista: list[dict], lista_source: str | None) -> int | None:
    if lista_source != "regionals":
        return None
    total = sum(int(item.get("total") or 0) for item in lista if "total" in item)
    return total or None


def summarize_bingo_lista_pool(
    lista: list[dict], *, regional_total: int | None = None
) -> dict:
    """Resumen de lista[] omitida (misma forma que goals_referencia.lista_summary)."""
    by_kingdom = _count_preserve_list_order(
        lista, lambda item: str(item.get("kingdom") or "")
    )
    by_disp = _sort_summary_by_disponibilidad(
        _count_preserve_list_order(lista, _summary_disp_label)
    )
    out: dict = {"n_items": len(lista)}
    if regional_total is not None:
        out["regional_total"] = int(regional_total)
    if by_kingdom:
        out["by_kingdom"] = by_kingdom
    if by_disp:
        out["by_disponibilidad"] = by_disp
    return out


def _resolve_bingo_group_moons_raw(group: dict) -> list[dict]:
    """Pool de lunas para normalizar/contar aunque moons[] esté omitido en JSON."""
    moons_raw = group_moons(group)
    if moons_raw:
        return moons_raw
    gid = str(group.get("id") or "")
    spec = _spec_for_bingo_group(gid)
    if spec.get("moons") or spec.get("name_patterns"):
        from sync_objective_moon_groups import resolve_moons

        return resolve_moons(spec, build_matrix_moon_registry())
    if gid == "captures" or str(group.get("moon_tag") or "") == "captures":
        from export_capturas_lunas import resolve_capturas_hub_moons

        return resolve_capturas_hub_moons()
    return []


def _resolve_bingo_group_lista_items(
    group: dict, combined_by_goal: dict[str, dict] | None = None
) -> tuple[list[dict], str | None]:
    """lista[] efectiva aunque esté omitida en JSON (goals_only)."""
    lista = group_lista(group)
    if lista:
        return lista, str(group.get("lista_source") or "") or None
    if group_n_pool(group, "lista") <= 0:
        return [], None
    from goal_list_lib import build_bingo_group_lista

    objectives = group_objective_refs(group, combined_by_goal or {})
    return build_bingo_group_lista(group, objectives, combined_by_goal=combined_by_goal)


def _spec_for_bingo_group(group_id: str) -> dict:
    from sync_objective_moon_groups import (
        GROUP_ID_RENAMES,
        OBJECTIVE_MOON_GROUP_SPECS,
    )

    gid = str(group_id) or ""
    spec_key = GROUP_ID_RENAMES.get(gid, gid)
    return dict(OBJECTIVE_MOON_GROUP_SPECS.get(spec_key, {}) or {})


def _tag_only_moon_keys(group: dict) -> set[tuple[str, int]]:
    """Claves (kingdom, moon) de tag_only: en el grupo o en el SPEC."""
    out: set[tuple[str, int]] = set()
    for raw in group.get("tag_only_moons") or []:
        if not isinstance(raw, dict):
            continue
        try:
            out.add((str(raw["kingdom"]), int(raw["moon"])))
        except (KeyError, TypeError, ValueError):
            continue
    if out:
        return out
    for pair in _spec_for_bingo_group(str(group.get("id") or "")).get(
        "tag_only_moons"
    ) or []:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            try:
                out.add((str(pair[0]), int(pair[1])))
            except (TypeError, ValueError):
                continue
        elif isinstance(pair, dict):
            try:
                out.add((str(pair["kingdom"]), int(pair["moon"])))
            except (KeyError, TypeError, ValueError):
                continue
    return out


def _group_moon_tag_flag_keys(group: dict) -> set[str]:
    """Tags cuya presencia en la luna pone moons[].tag=true.

    Incluye la tag que el grupo aplica (group_moon_tags) y, en paraguas con
    apply_moon_tag=False, la tag del id / moon_tag / aggregate: las lunas de
    familias minoritarias llevan el paraguas aunque el grupo no retaguee.
    """
    keys: set[str] = set(group_moon_tags(group))
    gid = str(group.get("id") or "")
    spec = _spec_for_bingo_group(gid)
    for raw in (
        group.get("moon_tag"),
        group.get("tag"),
        gid or None,
        spec.get("moon_tag"),
        spec.get("aggregate_moon_tag"),
    ):
        if not raw:
            continue
        keys.add(canonicalize_tag(str(raw)))
    for raw in spec.get("aggregate_moon_tags") or []:
        if raw:
            keys.add(canonicalize_tag(str(raw)))
    # nature es solo agregado de goals; en lunas viven fauna/flora.
    keys.discard("nature")
    keys.discard("")
    return keys


def _moon_ref_sort_key(raw: dict) -> tuple[int, int]:
    kingdom = str(raw.get("kingdom") or "")
    return (
        KINGDOM_COLUMNS.index(kingdom) if kingdom in KINGDOM_COLUMNS else 99,
        int(raw.get("moon") or 0),
    )


def _tag_only_moon_refs(
    group: dict,
    registry: dict[tuple[str, int], dict],
) -> list[dict]:
    """Refs de tag_only_moons (grupo o SPEC) para anotar con goal=false."""
    keys = _tag_only_moon_keys(group)
    if not keys:
        return []
    by_key: dict[tuple[str, int], dict] = {}
    for raw in group.get("tag_only_moons") or []:
        if not isinstance(raw, dict):
            continue
        try:
            key = (str(raw["kingdom"]), int(raw["moon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if key not in keys:
            continue
        by_key[key] = {
            "kingdom": key[0],
            "moon": key[1],
            "name": raw.get("name") or f"Moon {key[1]}",
        }
    for key in keys:
        if key in by_key:
            continue
        entry = registry.get(key) or {}
        by_key[key] = {
            "kingdom": key[0],
            "moon": key[1],
            "name": entry.get("name") or f"Moon {key[1]}",
        }
    return [by_key[k] for k in sorted(keys, key=lambda km: _moon_ref_sort_key({"kingdom": km[0], "moon": km[1]}))]


def annotate_bingo_group_moons(
    group: dict,
    moons_raw: list[dict],
    registry: dict[tuple[str, int], dict],
    *,
    has_catalog_tag: bool,
) -> list[dict]:
    """moons[] del grupo: pool de goals (goal=true) + tag_only (goal=false).

    Conserva el orden de ``moons_raw`` (SPEC / sync); tag_only al final.
    tag=true si la luna lleva alguna tag del grupo (concreta o paraguas),
    p. ej. fauna en lunas de dog/sheep aunque fauna tenga apply_moon_tag=False.
    """
    del has_catalog_tag  # la decisión es por luna vs registry, no por id solo
    tag_keys = _group_moon_tag_flag_keys(group)
    tag_only = _tag_only_moon_keys(group)
    out: list[dict] = []
    for raw in moons_raw:
        if not isinstance(raw, dict):
            continue
        try:
            key = (str(raw["kingdom"]), int(raw["moon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if key in tag_only:
            continue
        moon_tags = normalize_moon_tags(
            (registry.get(key) or {}).get("tags") or []
        )
        flagged = {
            **raw,
            # Pool de goals Combined: siempre cuenta para la goal del grupo.
            "goal": True,
            "tag": bool(tag_keys & moon_tags),
        }
        out.append(enrich_moon_ref_odyssey(flagged, registry))
    for raw in _tag_only_moon_refs(group, registry):
        key = (str(raw["kingdom"]), int(raw["moon"]))
        moon_tags = normalize_moon_tags(
            (registry.get(key) or {}).get("tags") or []
        )
        flagged = {
            **raw,
            "goal": False,
            "tag": bool(tag_keys & moon_tags),
        }
        out.append(enrich_moon_ref_odyssey(flagged, registry))
    return out


def normalize_bingo_group(
    group: dict,
    combined_by_goal: dict[str, dict] | None = None,
) -> dict:
    """Normaliza un grupo: objectives, moons y lista (goal_lists) separados."""
    if combined_by_goal is None:
        combined_by_goal = load_combined_objectives_by_goal()
    objectives = group_objective_refs(group, combined_by_goal)
    # Reinos: orden curado (Moons → Regional → Checkpoints → …).
    # Resto: {{X}} primero + alfabetico (como Combined).
    if group.get("id") not in KINGDOM_COLUMNS:
        objectives.sort(key=lambda o: objective_goal_sort_key(str(o.get("goal") or "")))
    goals_only = _bingo_group_goals_only(group)
    has_catalog_tag = group_id_has_catalog_tag(group.get("id"))
    from goal_list_lib import build_bingo_group_lista

    # Lunas: se conserva el orden; enriquecer name/disponibilidad/odyssey.
    # goals_only: moons[] vacío; lista[] omitida en JSON pero n.lista calculado.
    if goals_only:
        moons: list[dict] = []
        odyssey_units = 0
        n_goal = 0
        n_tag = 0
        lista_computed, lista_source = build_bingo_group_lista(
            group,
            objectives,
            combined_by_goal=combined_by_goal,
        )
        n_lista = len(lista_computed)
        lista: list[dict] = []
    else:
        moons_raw = _resolve_bingo_group_moons_raw(group)
        registry = build_matrix_moon_registry()
        # Inyectar flags de SPEC (apply_moon_tag) si el JSON ya los perdió.
        spec = _spec_for_bingo_group(str(group.get("id") or ""))
        work = dict(group)
        if "apply_moon_tag" not in work and "apply_moon_tag" in spec:
            work["apply_moon_tag"] = spec["apply_moon_tag"]
        if "moon_tag" not in work and spec.get("moon_tag"):
            work["moon_tag"] = spec["moon_tag"]
        moons_full = annotate_bingo_group_moons(
            work,
            moons_raw,
            registry,
            has_catalog_tag=has_catalog_tag,
        )
        odyssey_units = sum_moon_odyssey_units(moons_full, registry)
        n_goal = sum(1 for m in moons_full if m.get("goal"))
        n_tag = sum(1 for m in moons_full if m.get("tag"))
        lista_computed, lista_source = build_bingo_group_lista(
            group,
            objectives,
            combined_by_goal=combined_by_goal,
        )
        n_lista = len(lista_computed)
        lista = lista_computed
        omit_moons = _bingo_group_omit_moons(group)
        moons = [] if omit_moons else moons_full
    omit_lista = goals_only and n_lista > 0
    kind = group_kind(
        {
            "objectives": objectives,
            "moons": moons_full if not goals_only else moons,
            "lista": lista_computed,
        }
    )
    has, n = build_group_has_n(
        n_objectives=len(objectives),
        n_moons=len(moons_full) if not goals_only else len(moons),
        n_lista=n_lista,
        n_odyssey_units=odyssey_units,
        n_goal=n_goal,
        n_tag=n_tag,
    )
    kind_goal_tag = group_goal_tag_kind({"n": n, "moons": moons_full if not goals_only else moons})

    # Orden: id, orden, kind, kind_goal_tag, has, n, objectives/…
    # Meta (moon_tag/capture/_note/…) no se persiste: specs en sync.
    out: dict = {
        "id": group["id"],
    }
    if group.get("orden") is not None:
        out["orden"] = int(group["orden"])
    out["kind"] = kind
    out["kind_goal_tag"] = kind_goal_tag
    out["tag_inventario"] = group_id_has_catalog_tag(str(group.get("id") or ""))
    out["has"] = has
    out["n"] = n
    out["objectives"] = objectives
    if not goals_only and omit_moons and moons_full:
        out["moons_summary"] = summarize_bingo_moons_pool(
            moons_full, odyssey_units=odyssey_units
        )
        # Pool omitido: n.moons / moons_summary; sin moons: [].
    else:
        out["moons"] = moons
    if lista_source and lista:
        out["lista_source"] = lista_source
    if omit_lista and lista_computed:
        out["lista_summary"] = summarize_bingo_lista_pool(
            lista_computed,
            regional_total=_lista_regional_total(lista_computed, lista_source),
        )
        # Pool omitido (goals_only): n.lista / lista_summary; sin lista: [].
    else:
        out["lista"] = lista
    return out


def assign_bingo_group_orden(groups: list[dict]) -> list[dict]:
    """Tras ordenar por id (slug), asigna orden numerico 1..N."""
    groups = sorted(groups, key=lambda g: str(g.get("id") or ""))
    out: list[dict] = []
    for i, group in enumerate(groups, start=1):
        g = dict(group)
        g["orden"] = i
        out.append(g)
    return out


def normalize_bingo_groups_file() -> dict[str, int]:
    """Reescribe bingo_groups.json; objectives[] siempre desde Combined activo."""
    bingo = load_catalog(BINGO_GROUPS_PATH) if BINGO_GROUPS_PATH.exists() else {}
    combined_by_goal = load_combined_objectives_by_goal()
    capture_goals = _capture_name_to_goal()
    groups = []
    for g in bingo.get("groups", []):
        # Fijar lista de goals actual (renombres captura / captures umbrella)
        names = resolve_group_goal_names(
            g, combined_by_goal, capture_goals=capture_goals
        )
        g = {**g, "objectives": [{"goal": name} for name in names]}
        groups.append(normalize_bingo_group(g, combined_by_goal))
    groups = assign_bingo_group_orden(groups)
    counts = dict.fromkeys(_GROUP_KIND_HEADER, 0)
    for g in groups:
        kind = str(g.get("kind") or "nada")
        if kind in counts:
            counts[kind] += 1
        else:
            counts["nada"] += 1
    ordered: dict = {
        "_definition": BINGO_GROUPS_DEFINITION,
        "_note": BINGO_GROUPS_NOTE,
        "n_groups": len(groups),
        "groups": groups,
    }
    write_catalog_json(BINGO_GROUPS_PATH, finalize_bingo_groups_doc(ordered))
    clear_group_context_tags_cache()
    return counts


def _dedupe_sorted_moon_refs(moons: list) -> list[dict]:
    moon_refs: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for raw in moons:
        if not isinstance(raw, dict) or "kingdom" not in raw or "moon" not in raw:
            continue
        kingdom = str(raw["kingdom"])
        moon = int(raw["moon"])
        key = (kingdom, moon)
        if key in seen:
            continue
        seen.add(key)
        moon_refs.append(
            {
                "kingdom": kingdom,
                "moon": moon,
                "name": raw.get("name") or f"Moon {moon}",
            }
        )
    moon_refs.sort(key=entity_sort_key)
    return moon_refs


def upsert_moon_tag_group(
    group_id: str,
    moons: list[dict],
    *,
    moon_tag: str | None = None,
    note: str | None = None,
    large: bool = True,
    objectives: list | None = None,
    tag_only_moons: list[dict] | None = None,
) -> int:
    """Crea/actualiza un grupo de tag en bingo_groups (p. ej. story_moon, captures).

    moons = [{kingdom, moon, name}, ...]. Devuelve n_moons.
    Si objectives es None, conserva los objetivos ya existentes del grupo.
    """
    bingo = load_catalog(BINGO_GROUPS_PATH) if BINGO_GROUPS_PATH.exists() else {"groups": []}
    by_id = {g["id"]: g for g in bingo.get("groups", [])}
    existing = by_id.get(group_id) or {}
    tag = moon_tag or group_id
    moon_refs = _dedupe_sorted_moon_refs(moons)
    if objectives is not None:
        obj_refs = list(objectives)
    else:
        obj_refs = list(existing.get("objectives") or [])
    group: dict = {
        "id": group_id,
        "objectives": obj_refs,
        "moons": moon_refs,
        "moon_tag": tag,
    }
    if tag_only_moons is None:
        tag_only_raw = list(existing.get("tag_only_moons") or [])
    else:
        tag_only_raw = list(tag_only_moons)
    tag_only_refs = _dedupe_sorted_moon_refs(tag_only_raw)
    if tag_only_refs:
        group["tag_only_moons"] = tag_only_refs
    if large:
        group["large"] = True
    if note:
        group["_note"] = note
    by_id[group_id] = group
    combined = load_combined_objectives_by_goal()
    groups = [
        normalize_bingo_group(by_id[gid], combined) for gid in sorted(by_id)
    ]
    bingo["groups"] = assign_bingo_group_orden(groups)
    write_catalog_json(BINGO_GROUPS_PATH, finalize_bingo_groups_doc(bingo))
    clear_group_context_tags_cache()
    return len(moon_refs)


def group_moon_tags(group: dict) -> set[str]:
    """Tags de luna que aporta este grupo a cada miembro.

    Fauna/flora (paraguas, umbral = CAPTURE_TAG_MIN):
      < umbral → solo paraguas
      ≥ umbral → solo concreto
    Otros: una tag (moon_tag large/umbrella, o id sin prefijo de reino).
    apply_moon_tag=False: el grupo une lunas/goals sin etiquetar (p. ej. nature).
    """
    if group.get("apply_moon_tag") is False:
        return set()
    moons_raw = group.get("moons") or []
    # Umbral fauna/flora: solo lunas de goal (tag_only no sube el conteo →
    # p. ej. dog n=2 + sheep tag_only sigue siendo fauna, no dog).
    if moons_raw and isinstance(moons_raw[0], dict) and any(
        "goal" in m for m in moons_raw if isinstance(m, dict)
    ):
        n = sum(
            1
            for m in moons_raw
            if isinstance(m, dict) and m.get("goal") is not False
        )
    else:
        n = len(moons_raw)
        if n <= 0:
            n = group_n_pool(group, "moons")
    concrete = strip_kingdom_prefix_from_id(str(group["id"]))
    particular = group.get("moon_tag") or group.get("tag")
    if particular in UMBRELLA_MOON_TAGS:
        has_concrete = bool(
            n >= CAPTURE_TAG_MIN and concrete and concrete != particular
        )
        if has_concrete:
            return {concrete}
        return {str(particular)}
    if particular and particular != GROUP_MOON_TAG:
        # moon_tag explícito distinto del sufijo del id (p. ej. metro_minigames → minigame)
        # o grupos large/umbrella / catálogos grandes.
        if (
            particular != concrete
            or n >= GROUP_LARGE_MIN
            or group.get("large") is True
            or group.get("umbrella") is True
        ):
            return {str(particular)}
    return {concrete}


def group_moon_tag(group: dict) -> str:
    """Tag principal del grupo (compat). Preferir group_moon_tags."""
    tags = group_moon_tags(group)
    particular = group.get("moon_tag") or group.get("tag")
    if particular in tags:
        return str(particular)
    return next(iter(sorted(tags)))


# Tags en lunas concretas aunque el grupo no las aplique solo
# (apply_moon_tag=False, umbral, sin familia, etc.). Solo añade tags al
# catálogo; el pool de goals es independiente (una luna puede contar para
# la goal sin llevar la tag, o llevar la tag sin estar en ese pool).
# Omitir una tag en una luna: por la luna o por tags que la acompañan
# (p. ej. ACCESS_DROPS_SUB_AREA quita sub_area si hay mini_rocket/beanstalk/
# outfit_door) — nunca por el solo hecho de ser esa tag.
FORCE_MOON_TAGS: dict[tuple[str, int], frozenset[str]] = {
    # Puzzle Part / Lakitu transporte: sin captura concreta de lista.
    ("lake", 20): frozenset({"captures"}),
    ("bowser", 10): frozenset({"captures"}),
    # Sheep: fauna sin familia (fuera de Dog); pool Fauna vía fauna.moons.
    ("sand", 33): frozenset({"fauna"}),
    # Uproot Sky Garden (fuera de Seaside Uproot Moons).
    ("wooded", 25): frozenset({"uproot"}),
}


def _spec_explicit_moon_refs(spec: dict) -> list[dict]:
    """Refs {kingdom, moon} desde SPEC.moons (sin registry ni resolve_moons)."""
    out: list[dict] = []
    for pair in spec.get("moons") or []:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            try:
                out.append({"kingdom": str(pair[0]), "moon": int(pair[1])})
            except (TypeError, ValueError):
                continue
        elif isinstance(pair, dict) and "kingdom" in pair and "moon" in pair:
            try:
                out.append(
                    {
                        "kingdom": str(pair["kingdom"]),
                        "moon": int(pair["moon"]),
                    }
                )
            except (TypeError, ValueError):
                continue
    return out


def _group_tag_targets(group: dict) -> list[dict]:
    """Lunas a etiquetar: moons[] o, si omit_moons, SPEC.moons explícitas.

    No usa resolve_capturas_hub / build_matrix_moon_registry (recursión con
    apply_bingo_group_tags). captures sigue etiquetando vía subgrupos + FORCE;
    sub_area sí retaguea desde su lista SPEC (omit solo por ACCESS_DROPS).
    """
    tag_targets = list(group_moons(group))
    if not tag_targets and _bingo_group_omit_moons(group):
        tag_targets = _spec_explicit_moon_refs(
            _spec_for_bingo_group(str(group.get("id") or ""))
        )
    for raw in group.get("tag_only_moons") or []:
        if isinstance(raw, dict) and "kingdom" in raw and "moon" in raw:
            tag_targets.append(raw)
    return tag_targets


def _apply_tags_to_merged_moon(
    merged: dict[tuple[str, int], dict],
    raw: dict,
    tags_to_add: set[str],
    wiki: dict,
    rules: dict,
) -> None:
    key = (raw["kingdom"], int(raw["moon"]))
    kingdom, moon = key
    entry = merged.get(key)
    wiki_entry = wiki.get(kingdom, {}).get(moon)
    wiki_name = (wiki_entry or {}).get("name")
    raw_name = str(raw.get("name") or "")
    # Preferir wiki si el raw es placeholder "Moon N" (p. ej. tag_only_moons).
    if _is_moon_number_placeholder(raw_name) and wiki_name:
        name = wiki_name
    else:
        name = raw_name or wiki_name or f"Moon {moon}"
    if entry is None:
        availability = infer_availability(
            kingdom, moon, name, wiki_entry, rules, tags_to_add
        )
        merged[key] = {
            "kingdom": kingdom,
            "moon": moon,
            "name": name,
            "availability": availability,
            "tags": set(tags_to_add),
            "catalogs": {"bingo_groups"},
        }
        return
    entry["tags"] |= tags_to_add
    entry.setdefault("catalogs", set()).add("bingo_groups")
    cur = str(entry.get("name") or "")
    if wiki_name and (not cur or _is_moon_number_placeholder(cur)):
        entry["name"] = wiki_name
    elif len(name) > len(cur):
        entry["name"] = name


def apply_bingo_group_tags(merged: dict[tuple[str, int], dict]) -> None:
    """Aplica tags de cada bingo group (concreto y/o paraguas)."""
    clear_group_context_tags_cache()
    if not BINGO_GROUPS_PATH.exists():
        return
    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()

    for group in load_bingo_groups():
        tags_to_add = set(group_moon_tags(group))
        tags_to_add |= {
            canonicalize_tag(str(t))
            for t in (group.get("extra_tags") or [])
            if t
        }
        # No re-aplicar rare fallback sobre tags ya decididas por el grupo
        for raw in _group_tag_targets(group):
            _apply_tags_to_merged_moon(merged, raw, tags_to_add, wiki, rules)

    # Excepciones: tags omitidas por política/grupo → forzar en lunas concretas.
    for (kingdom, moon), tags in sorted(FORCE_MOON_TAGS.items()):
        _apply_tags_to_merged_moon(
            merged,
            {"kingdom": kingdom, "moon": moon},
            set(tags),
            wiki,
            rules,
        )


def load_typed_moon_keys() -> set[tuple[str, int]]:
    """Lunas con tag via bingo group (incluye story/action/reino/tematicos)."""
    return load_bingo_group_moon_keys()


# Objetivos Combined que no deben autoasignarse a grupos de reino
# (p. ej. bosses/extras poco utiles en el grupo reino).
KINGDOM_OBJECTIVE_EXCLUDE = frozenset(
    {
        "RoboBrood Fight",
    }
)

_TIPO_RANK = {"reino_total": 0, "reino_regional": 1, "reino_exclusivo": 2}


def load_active_combined_objectives() -> list[dict]:
    """Objetivos Combined activos (no disabled) del JSON de pagina."""
    if not JSON_PATH.exists():
        return []
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return [o for o in data.get("objectives", []) if not o.get("disabled") and o.get("goal")]


def _reino_exclusivo_priority(goal: str) -> int:
    """Orden curado dentro de reino_exclusivo.

    Checkpoints → Story → Multi con {{X}} → resto {{X}} → Multi fijo → resto fijo.
    Asi Multi fijo (Seaside/Snow) no parte el bloque {{X}}.
    """
    low = goal.lower()
    has_x = goal.startswith(GOAL_X)
    if "checkpoint" in low:
        return 0
    if "story" in low:
        return 1
    is_multi = "multi-moon" in low or "multi moon" in low
    if is_multi and has_x:
        return 2
    if has_x:
        return 3
    if is_multi:
        return 4
    return 5


def _append_kingdom_objective(
    by_kingdom: dict[str, list[tuple]],
    obj: dict,
) -> None:
    goal = str(obj["goal"])
    if goal in KINGDOM_OBJECTIVE_EXCLUDE:
        return
    tipo, reino = classify_objective(
        goal,
        obj.get("board_categories") or [],
        obj.get("line_categories") or [],
    )
    name_slug, _suffix = parse_kingdom_named_goal(goal)
    # Destinos: reino de board/line + prefijo del nombre si difiere
    # (Metro Night/Shop → lost por board, también metro por nombre).
    targets: list[tuple[str, str]] = []
    if reino and reino in by_kingdom and tipo in _TIPO_RANK:
        targets.append((reino, tipo))
    if (
        name_slug
        and name_slug in by_kingdom
        and name_slug != reino
        and tipo in _TIPO_RANK
    ):
        targets.append((name_slug, "reino_exclusivo"))
    if not targets:
        return
    for dest, dest_tipo in targets:
        sub = (
            _reino_exclusivo_priority(goal)
            if dest_tipo == "reino_exclusivo"
            else 0
        )
        by_kingdom[dest].append(
            (
                _TIPO_RANK[dest_tipo],
                sub,
                goal.lower(),
                objective_ref_from_combined(goal, obj),
            )
        )


def _dedupe_kingdom_objective_refs(
    items: list[tuple],
) -> list[dict]:
    items.sort(key=lambda pair: (pair[0], pair[1], pair[2]))
    seen: set[str] = set()
    refs: list[dict] = []
    for *_, ref in items:
        goal = ref["goal"]
        if goal in seen:
            continue
        seen.add(goal)
        refs.append(ref)
    return refs


def kingdom_objectives_from_combined() -> dict[str, list[dict]]:
    """Objetivos Combined por reino (objetos {goal, ...info})."""
    by_kingdom: dict[str, list[tuple]] = {k: [] for k in KINGDOM_COLUMNS}
    for obj in load_active_combined_objectives():
        _append_kingdom_objective(by_kingdom, obj)
    return {
        slug: _dedupe_kingdom_objective_refs(items)
        for slug, items in by_kingdom.items()
    }


def sync_kingdom_groups() -> dict[str, int]:
    """Crea/actualiza grupos de reino: lunas in-scope + objetivos Combined del reino."""
    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()
    bingo = load_catalog(BINGO_GROUPS_PATH) if BINGO_GROUPS_PATH.exists() else {"groups": []}
    by_id = {g["id"]: g for g in bingo.get("groups", [])}
    kingdom_goals = kingdom_objectives_from_combined()
    combined_by_goal = load_combined_objectives_by_goal()
    counts: dict[str, int] = {}

    for slug in KINGDOM_COLUMNS:
        moons: list[dict] = []
        for moon, entry in sorted(wiki.get(slug, {}).items()):
            if not wiki_moon_in_scope(slug, moon, entry, rules):
                continue
            moons.append(
                {
                    "kingdom": slug,
                    "moon": int(moon),
                    "name": entry["name"],
                }
            )
        moons.sort(key=lambda m: int(m["moon"]))
        display = KINGDOM_DISPLAY[slug]
        fallback_goal = f"{{{{X}}}} {display} Moons"
        objectives = kingdom_goals.get(slug) or [
            objective_ref_from_combined(fallback_goal, combined_by_goal.get(fallback_goal))
        ]
        by_id[slug] = {
            "id": slug,
            "kind": "todo",
            "objectives": objectives,
            "moons": moons,
            "kingdom": slug,
            "moon_tag": slug,
            "large": True,
            "_note": (
                f"Reino {display}: todas las lunas in-scope + objetivos Combined "
                "del reino (Moons, Checkpoints, Regional Coins, story, etc.)."
            ),
        }
        counts[slug] = len(moons)

    bingo["groups"] = [
        normalize_bingo_group(g, combined_by_goal)
        for g in assign_bingo_group_orden(
            [
                normalize_bingo_group(by_id[gid], combined_by_goal)
                for gid in sorted(by_id)
            ]
        )
    ]
    write_catalog_json(BINGO_GROUPS_PATH, finalize_bingo_groups_doc(bingo))
    clear_group_context_tags_cache()
    return counts


def attach_bingo_group_spec_meta(group: dict) -> dict:
    """Reinyecta meta operativa desde OBJECTIVE_MOON_GROUP_SPECS (no en JSON)."""
    from sync_objective_moon_groups import (
        OBJECTIVE_MOON_GROUP_SPECS,
        _apply_spec_flags,
    )

    out = dict(group)
    gid = str(out.get("id") or "")
    if gid in KINGDOM_COLUMNS and not out.get("kingdom"):
        out["kingdom"] = gid
    spec = OBJECTIVE_MOON_GROUP_SPECS.get(gid)
    if not spec:
        return out
    _apply_spec_flags(out, spec)
    # tag_only: pairs del spec (sin registry; evita recursión con merge/tags).
    # Nombres desde wiki si el placeholder sería "Moon N".
    wiki = load_wiki_moon_meta()
    tag_only: list[dict] = []
    for pair in spec.get("tag_only_moons") or []:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            kingdom = str(pair[0])
            moon = int(pair[1])
            wiki_name = (wiki.get(kingdom, {}) or {}).get(moon, {}).get("name")
            tag_only.append(
                {
                    "kingdom": kingdom,
                    "moon": moon,
                    "name": wiki_name or f"Moon {moon}",
                }
            )
        elif isinstance(pair, dict) and "kingdom" in pair and "moon" in pair:
            kingdom = str(pair["kingdom"])
            moon = int(pair["moon"])
            raw_name = pair.get("name")
            wiki_name = (wiki.get(kingdom, {}) or {}).get(moon, {}).get("name")
            if not raw_name or _is_moon_number_placeholder(str(raw_name)):
                name = wiki_name or raw_name or f"Moon {moon}"
            else:
                name = raw_name
            tag_only.append(
                {"kingdom": kingdom, "moon": moon, "name": name}
            )
    if tag_only:
        out["tag_only_moons"] = tag_only
    return out


def load_bingo_groups(*, with_spec_meta: bool = True) -> list[dict]:
    """Grupos de bingo_groups.json; con meta de specs si with_spec_meta."""
    if not BINGO_GROUPS_PATH.exists():
        return []
    groups = list(load_catalog(BINGO_GROUPS_PATH).get("groups", []))
    if not with_spec_meta:
        return groups
    return [attach_bingo_group_spec_meta(g) for g in groups]


def catalog_dict_from_group(group: dict) -> dict:
    """Catalogo sintetico (items + techos) para conteos/rangos desde un bingo group."""
    meta = load_meta()
    tag = group_moon_tag(group)
    items: list[dict] = []
    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()
    for raw in group.get("moons") or []:
        kingdom = raw["kingdom"]
        moon = int(raw["moon"])
        wiki_entry = wiki.get(kingdom, {}).get(moon)
        name = raw.get("name") or (wiki_entry or {}).get("name") or f"Moon {moon}"
        tags = {tag}
        items.append(
            {
                "kingdom": kingdom,
                "moon": moon,
                "name": name,
                "availability": infer_availability(
                    kingdom, moon, name, wiki_entry, rules, tags
                ),
                "tags": sorted(tags),
            }
        )
    return {
        "story_order": meta["story_order"],
        "run_tier_ceiling": meta["run_tier_ceiling"],
        "items": items,
    }


def load_sub_area_levels() -> list[dict]:
    """Pares Level (exactamente 2 lunas) para capturas / rangos.

    Fuente: Files/sub_area_levels_data.py (rebuild_sub_area_bingo).
    """
    from sub_area_levels_data import SUB_AREA_LEVELS

    return [dict(row) for row in SUB_AREA_LEVELS]


def write_sub_area_levels_data(levels: list[dict]) -> None:
    """Reescribe Files/sub_area_levels_data.py (tras rebuild_sub_area_bingo)."""
    from pathlib import Path
    from pprint import pformat

    rows: list[dict] = []
    for i, raw in enumerate(levels, 1):
        if not isinstance(raw, dict):
            continue
        row: dict = {
            "kingdom": str(raw.get("kingdom") or ""),
            "id_list": int(raw.get("id_list") or i),
            "level": str(raw.get("level") or ""),
            "moons": [int(m) for m in (raw.get("moons") or [])],
            "names": [str(n) for n in (raw.get("names") or [])],
        }
        if raw.get("disponibilidad"):
            row["disponibilidad"] = raw["disponibilidad"]
        rows.append(row)

    path = Path(__file__).resolve().parent / "sub_area_levels_data.py"
    text = (
        '"""Pares Level Sub-Area (exactamente 2 lunas en alcance).\n'
        "\n"
        "Fuente operativa de load_sub_area_levels / rebuild_sub_area_bingo.\n"
        "No vive en goal_lists.json (no es pool lista[] de bingo_groups).\n"
        '"""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        f"SUB_AREA_LEVELS: list[dict] = {pformat(rows, width=100, sort_dicts=False)}\n"
    )
    path.write_text(text, encoding="utf-8")



def rebuild_untyped_moons() -> int:
    """Cuenta lunas en alcance sin tags (solo reino). Ya no escribe JSON (siempre 0
    con grupos de reino en bingo_groups).
    """
    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()
    covered = load_typed_moon_keys()
    n = 0
    for kingdom in KINGDOM_COLUMNS:
        for moon, entry in wiki.get(kingdom, {}).items():
            if not wiki_moon_in_scope(kingdom, moon, entry, rules):
                continue
            if (kingdom, moon) in covered:
                continue
            n += 1
    return n


_AVAILABILITY_PRIORITY = {"base": 0, "mid_story": 1, "world_peace": 2, "revisit": 3}


def _merge_catalog_item_into(
    merged: dict[tuple[str, int], dict],
    item: dict,
    stem: str,
    primary_tag: str | None,
) -> None:
    key = (item["kingdom"], item["moon"])
    tags = set(item.get("tags", []))
    if primary_tag:
        tags.add(primary_tag)

    if key not in merged:
        merged[key] = {
            "kingdom": item["kingdom"],
            "moon": item["moon"],
            "name": item["name"],
            "availability": item.get("availability", "base"),
            "tags": tags,
            "catalogs": {stem},
        }
        return

    entry = merged[key]
    cur = str(entry.get("name") or "")
    new_name = str(item.get("name") or "")
    # Preferir nombre real sobre placeholder "Moon N".
    if new_name and (
        not cur
        or _is_moon_number_placeholder(cur)
        or (
            len(new_name) > len(cur)
            and not _is_moon_number_placeholder(new_name)
        )
    ):
        entry["name"] = new_name
    entry["tags"].update(tags)
    entry["catalogs"].add(stem)
    cur = _AVAILABILITY_PRIORITY.get(entry["availability"], 0)
    new = _AVAILABILITY_PRIORITY.get(item.get("availability", "base"), 0)
    if new > cur:
        entry["availability"] = item.get("availability", "base")


def merge_catalog_moons() -> dict[tuple[str, int], dict]:
    """Return {(kingdom, moon): merged item} with union of tags."""
    global _MERGE_CATALOG_MOONS_CACHE
    if _MERGE_CATALOG_MOONS_CACHE is not None:
        return _MERGE_CATALOG_MOONS_CACHE
    merged: dict[tuple[str, int], dict] = {}

    for path in sorted(CATALOG_DIR.glob("*.json")):
        if path.name in SKIP_CATALOGS:
            continue
        catalog = load_catalog(path)
        stem = path.stem
        primary_tag = PRIMARY_TAGS.get(stem)
        for item in catalog.get("items", []):
            _merge_catalog_item_into(merged, item, stem, primary_tag)

    apply_bingo_group_tags(merged)
    _MERGE_CATALOG_MOONS_CACHE = merged
    return merged


def build_matrix_moon_registry() -> dict[tuple[str, int], dict]:
    """Lunas catalogadas en alcance (base/mid_story/revisit/world_peace)."""
    global _MATRIX_MOON_REGISTRY_CACHE
    if _MATRIX_MOON_REGISTRY_CACHE is not None:
        return _MATRIX_MOON_REGISTRY_CACHE
    allowed = load_scope()
    catalog = merge_catalog_moons()
    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()
    registry: dict[tuple[str, int], dict] = {}

    for key, entry in catalog.items():
        kingdom = entry["kingdom"]
        moon = entry["moon"]
        wiki_entry = wiki.get(kingdom, {}).get(moon)
        if not wiki_moon_in_scope(kingdom, moon, wiki_entry, rules):
            continue
        if is_postgame_item(entry, rules):
            continue
        if not in_scope(entry, allowed):
            continue
        registry[key] = {
            "kingdom": entry["kingdom"],
            "moon": entry["moon"],
            "name": entry["name"],
            "availability": entry.get("availability", "base"),
            "tags": set(entry["tags"]),
            "catalogs": set(entry.get("catalogs", set())),
        }

    _MATRIX_MOON_REGISTRY_CACHE = registry
    return registry


def build_full_moon_registry() -> dict[tuple[str, int], dict]:
    """Alias de build_matrix_moon_registry."""
    return build_matrix_moon_registry()


def kingdom_index(story_order: list[str], kingdom: str) -> int:
    return story_order.index(kingdom)


def scoped_items_up_to_kingdom(
    items: list[dict],
    story_order: list[str],
    kingdom: str,
    allowed: set[str],
) -> list[dict]:
    limit = kingdom_index(story_order, kingdom)
    allowed_kingdoms = set(story_order[: limit + 1])
    return [
        item
        for item in items
        if item["kingdom"] in allowed_kingdoms and in_scope(item, allowed)
    ]


def count_by_kingdom(items: list[dict], tag: str, allowed: set[str]) -> dict[str, int]:
    counts = dict.fromkeys(KINGDOM_COLUMNS, 0)
    for item in items:
        if not in_scope(item, allowed):
            continue
        if tag not in item.get("tags", []):
            continue
        kingdom = item["kingdom"]
        if kingdom in counts:
            counts[kingdom] += 1
    return counts


def count_by_tag(items: list[dict], tag: str) -> int:
    return sum(1 for item in items if tag in item.get("tags", []))


def compute_tier_counts(catalog: dict, tag: str, allowed: set[str]) -> dict[str, int]:
    story_order = catalog["story_order"]
    ceilings = catalog["run_tier_ceiling"]
    items = catalog["items"]

    counts: dict[str, int] = {}
    for zone in ZONE_ORDER:
        ceiling = ceilings[zone]
        reachable = scoped_items_up_to_kingdom(items, story_order, ceiling, allowed)
        counts[zone] = count_by_tag(reachable, tag)
    return counts


def cumulative_counts_from_kingdom(
    per_kingdom: dict[str, int], story_order: list[str], ceiling: str
) -> int:
    limit = kingdom_index(story_order, ceiling)
    return sum(per_kingdom.get(k, 0) for k in story_order[: limit + 1])


def tier_counts_from_kingdom(
    per_kingdom: dict[str, int], story_order: list[str], ceilings: dict[str, str]
) -> dict[str, int]:
    return {
        zone: cumulative_counts_from_kingdom(per_kingdom, story_order, ceilings[zone])
        for zone in ZONE_ORDER
    }


def slugify_matrix_token(text: str) -> str:
    text = re.sub(r"\[\[[^\]]*\]\]", "", text)
    text = text.lower().replace("'s", "s")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_").removesuffix("_moons").removesuffix("_moon")


def goal_to_matrix_column(goal: str, tipo: str, _reino: str | None) -> str:
    if goal in GOAL_TO_TAG:
        return GOAL_TO_TAG[goal]
    slug, suffix = parse_kingdom_prefixed_goal(goal)
    if slug and suffix and tipo == "reino_exclusivo":
        mechanic = slugify_matrix_token(suffix)
        return f"{slug}_{mechanic}" if mechanic else slug
    rest = goal.removeprefix(GOAL_X_PREFIX).strip()
    return slugify_matrix_token(rest)


@dataclass(frozen=True)
class MatrixObjective:
    column_id: str
    goal: str
    tipo: str
    reino: str | None
    tag: str


def load_matrix_objectives() -> list[MatrixObjective]:
    if not JSON_PATH.exists():
        return []

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    objectives: list[MatrixObjective] = []
    seen: set[str] = set()

    for obj in data["objectives"]:
        if obj.get("disabled"):
            continue
        goal = obj.get("goal", "")
        if not goal.startswith(GOAL_X):
            continue

        board = obj.get("board_categories", [])
        line = obj.get("line_categories", [])
        tipo, reino = classify_objective(goal, board, line)
        if tipo in MATRIX_SKIP_TIPOS:
            continue

        column_id = goal_to_matrix_column(goal, tipo, reino)
        if column_id in seen:
            suffix = 2
            candidate = f"{column_id}_{suffix}"
            while candidate in seen:
                suffix += 1
                candidate = f"{column_id}_{suffix}"
            column_id = candidate
        seen.add(column_id)

        tag = GOAL_TO_TAG.get(goal, column_id)
        objectives.append(MatrixObjective(column_id, goal, tipo, reino, tag))

    objectives.sort(
        key=lambda item: (
            TIPO_SORT.get(item.tipo, 99),
            item.reino or "",
            item.column_id,
        )
    )
    return objectives


def moon_matches_objective(entry: dict, objective: MatrixObjective, scoped: bool) -> bool:
    if not scoped:
        return False
    if objective.reino and entry["kingdom"] != objective.reino:
        return False
    return objective.tag in entry.get("tags", set())


def parse_kingdom_prefixed_goal(goal: str) -> tuple[str | None, str | None]:
    if not goal.startswith(GOAL_X_PREFIX):
        return None, None
    rest = goal[len(GOAL_X_PREFIX) :]
    for display, slug in KINGDOM_GOAL_PREFIXES:
        prefix = f"{display} "
        if rest.startswith(prefix):
            return slug, rest[len(prefix) :]
    return None, None


def parse_kingdom_named_goal(goal: str) -> tuple[str | None, str | None]:
    """Reino en el nombre: {{X}} Metro … o Metro Shop Moon → (metro, resto)."""
    slug, suffix = parse_kingdom_prefixed_goal(goal)
    if slug:
        return slug, suffix
    for display, slug in KINGDOM_GOAL_PREFIXES:
        prefix = f"{display} "
        if goal.startswith(prefix):
            return slug, goal[len(prefix) :]
    return None, None


def kingdoms_in_categories(board_categories: list[str]) -> list[str]:
    known = set(STORY_ORDER)
    return [c for c in board_categories if c in known]


def classify_objective(
    goal: str,
    board_categories: list[str],
    line_categories: list[str] | None = None,
) -> tuple[str, str | None]:
    """Return (tipo, reino_slug)."""
    if goal in CATALOG_GOAL_SET:
        return "cross_reino", None
    # Antes de parse {{X}} <Reino> …: p. ej. {{X}} Moon Rocks ≠ reino Moon.
    if goal in GLOBAL_AGGREGATE_GOALS:
        return "global", None

    kingdoms = list(
        dict.fromkeys(
            kingdoms_in_categories(board_categories)
            + kingdoms_in_categories(line_categories or [])
        )
    )
    slug, suffix = parse_kingdom_prefixed_goal(goal)
    # Totales / regionales: confiar en el prefijo del nombre.
    if slug and suffix == "Moons":
        return "reino_total", slug
    if slug and suffix == "Regional Coins":
        return "reino_regional", slug
    # Un solo reino en board/line gana al nombre (Metro Night/Shop → lost).
    if len(kingdoms) == 1:
        return "reino_exclusivo", kingdoms[0]
    if slug and suffix:
        return "reino_exclusivo", slug

    return "cross_reino_pendiente", None


def tier_max_for_kingdom(kingdom: str, meta: dict) -> dict[str, int]:
    story_order = meta["story_order"]
    ceilings = meta["run_tier_ceiling"]
    total = meta["in_scope_moons"].get(kingdom, 0)
    idx = story_order.index(kingdom)
    return {
        zone: total if idx <= story_order.index(ceilings[zone]) else 0
        for zone in ZONE_ORDER
    }
