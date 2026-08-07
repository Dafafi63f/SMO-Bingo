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
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent
ROOT = FILES_DIR.parent
BINGOS_DIR = ROOT / "Bingos"
CATALOG_DIR = ROOT / "Catalog"
CAPTURES_LUNAS_JSON = CATALOG_DIR / "capturas_lunas.json"
# Captura normal con ≥N lunas → tag concreta junto a `captures`.
# Especial o minoritaria (<N) → basta `captures`.
CAPTURE_TAG_MIN = 3
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
    # Alias Unique Captures display (no unifica tags en lunas).
    "Fire/Hammer Bro": "hammer_bro",
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
# Fuente de verdad de objetivos (editar solo este).
JSON_PATH = BINGOS_DIR / "Super Mario Odyssey-Combined-2026-08-07.json"
# Referencias lockout.live (no modificar). AK = mas completo / umbrales altos;
# Short/Default/Long = cobertura menor, rangos mas blandos (mejor guia Combined).
ALL_KINGDOMS_REFERENCE_PATH = BINGOS_DIR / "Super Mario Odyssey-All Kingdoms-2026-07-24.json"
SHORT_GOALS_REFERENCE_PATH = BINGOS_DIR / "Super Mario Odyssey-Short Goals-2026-07-27.json"
DEFAULT_GOALS_REFERENCE_PATH = BINGOS_DIR / "Super Mario Odyssey-Default-2026-07-27.json"
LONG_GOALS_REFERENCE_PATH = BINGOS_DIR / "Super Mario Odyssey-Long Goals-2026-07-27.json"
# Norma Combined: totales de lunas por reino salto +2; regionales salto +5.
MOON_TOTAL_STEP = 2
REGIONAL_COIN_STEP = 5

ZONE_ORDER = ["e", "m", "l", "n"]

# Orden narrativo (incluye reinos solo-boss).
STORY_ORDER = [
    "cap",
    "cascade",
    "sand",
    "lake",
    "wooded",
    "cloud",
    "lost",
    "metro",
    "snow",
    "seaside",
    "luncheon",
    "ruined",
    "bowser",
    "moon",
]

# Cloud: sin lunas en alcance (boss-only). Ruined: scope_moons curado en project.json.
BOSS_ONLY_KINGDOMS = frozenset({"cloud"})
# Reinos solo postgame (fuera de alcance salvo FORCE_IN_SCOPE, p. ej. mushroom#39).
POSTGAME_KINGDOMS = frozenset({"mushroom"})

# Reinos con Power Moons en catálogos / CSV.
KINGDOM_COLUMNS = [k for k in STORY_ORDER if k not in BOSS_ONLY_KINGDOMS]

# Umbral "muy lejano" al rellenar 3 rangos → 4 progresiones.
FAR_RANGE_KINGDOMS = frozenset({"bowser", "moon"})


def pad_range_three_to_four(
    ranges: list[int],
    moons: list[dict] | None = None,
    *,
    far_kingdoms: frozenset[str] = FAR_RANGE_KINGDOMS,
) -> list[int]:
    """Rellena rangos de bingo cuando hay 3 valores y 4 progresiones (e/m/l/n).

    Convenio del proyecto:
      - Por defecto repetir el ultimo: [a, b, c] → [a, b, c, c]
      - Si la luna #c (orden de reinos) esta en un reino muy lejano
        (Bowser/Moon), repetir el del medio: [a, b, b, c]
      - Nunca repetir el primero.

    No altera listas que no tengan exactamente 3 enteros.
    """
    if len(ranges) != 3:
        return list(ranges)
    a, b, c = (int(x) for x in ranges)
    if moons and len(moons) >= c:
        ordered = sorted(
            moons,
            key=lambda m: (
                KINGDOM_COLUMNS.index(m["kingdom"])
                if m.get("kingdom") in KINGDOM_COLUMNS
                else 99,
                int(m.get("moon") or 0),
            ),
        )
        kingdom = ordered[c - 1].get("kingdom")
        if kingdom in far_kingdoms:
            return [a, b, b, c]
    return [a, b, c, c]


def ensure_unique_ascending_range(ranges: list[int]) -> list[int]:
    """Valores de range unicos y ascendentes (sin duplicados para bingo)."""
    return sorted({int(x) for x in ranges})


def ensure_four_range_values(ranges: list[int]) -> list[int]:
    """LEGACY: ya no se fuerza a 4 valores.

    Delega en ensure_unique_ascending_range. Mantener el nombre por imports.
    """
    return ensure_unique_ascending_range(ranges)


def align_numeric_range_to_progression(
    ranges: list[int],
    progression: list[str] | None = None,
) -> list[int]:
    """Goals numericas: range sin duplicados; progression define zonas Lockout.

    No se rellenan valores repetidos para igualar len(progression).
    Varios valores unicos escalan dificultad dentro de las zonas permitidas
    (progressive_ranges en el JSON).
    """
    del progression  # la longitud del range no se ata a len(progression)
    if not ranges:
        return list(ranges)
    return ensure_unique_ascending_range(ranges)


KINGDOM_DISPLAY = {
    "cap": "Cap",
    "cascade": "Cascade",
    "sand": "Sand",
    "lake": "Lake",
    "wooded": "Wooded",
    "cloud": "Cloud",
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
# Capturas de planta: NO añaden flora (basta captures + tag concreta).
# flora queda para nut/bloom/cactus no-captura, etc. (turnips → seeds)
CAPTURE_UMBRELLA: dict[str, str] = {}
# Si hay captura de planta concreta, no apilar flora.
PLANT_CAPTURE_TAGS = frozenset({"uproot", "cactus_tree"})
TAG_STORY = frozenset({"story_moon", "multi_moon"})
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
# boss/bosses y checkpoint/checkpoints: solo board↔line Combined (NO tags de luna).
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
    "bosses": "boss",  # board/line, no moon tag
    "checkpoints": "checkpoint",  # board/line, no moon tag
    "destructible_blocks_capture": "blocks",
    "npc_moons": "npc",
    "koopa": "npc",
    "seed_moon": "seeds",
    "golden_turnip": "seeds",  # grupo retirado → seeds
    "minigames": "minigame",
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


def _slugify_capture_name(name: str) -> str:
    if name in CAPTURE_NAME_TO_TAG:
        return CAPTURE_NAME_TO_TAG[name]
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s


_CAPTURE_TAG_BY_MOON: dict[tuple[str, int], str | None] | None = None


def clear_capture_tag_cache() -> None:
    global _CAPTURE_TAG_BY_MOON
    _CAPTURE_TAG_BY_MOON = None


def load_capture_tag_by_moon() -> dict[tuple[str, int], str | None]:
    """(reino, luna) → tag concreta de captura, o None si especial/minoritaria.

    Fuente: catalog/capturas_lunas.json. El umbral ≥CAPTURE_TAG_MIN se aplica por
    tag unificada (p. ej. los 3 Chomps → `chomp`), no por fila suelta:
    variantes especial/minoritaria del mismo slug reciben la tag si la
    familia llega al mínimo. Si no, basta `captures`.

    Lunas con `goal: false` (p. ej. story/multi que usan la captura pero no
    cuentan en la goal Combined) no reciben tag concreta: basta `captures`
    u otra tag global del grupo donde sí cuenten.
    """
    global _CAPTURE_TAG_BY_MOON
    if _CAPTURE_TAG_BY_MOON is not None:
        return _CAPTURE_TAG_BY_MOON

    moons_by_tag: dict[str, set[tuple[str, int]]] = {}
    moon_to_tag: dict[tuple[str, int], str] = {}
    if CAPTURES_LUNAS_JSON.exists():
        data = json.loads(CAPTURES_LUNAS_JSON.read_text(encoding="utf-8"))
        for row in data.get("captures") or []:
            name = (
                row.get("capture")
                or row.get("name")
                or row.get("captura")
                or ""
            ).strip()
            if not name:
                continue
            tag = _slugify_capture_name(name)
            for moon in row.get("moons") or []:
                if not isinstance(moon, dict):
                    continue
                if "kingdom" not in moon or "moon" not in moon:
                    continue
                key = (str(moon["kingdom"]), int(moon["moon"]))
                # Cuenta para el umbral de familia aunque no etiquete la luna.
                moons_by_tag.setdefault(tag, set()).add(key)
                if moon.get("goal") is False:
                    continue
                moon_to_tag[key] = tag

    majority = {tag for tag, moons in moons_by_tag.items() if len(moons) >= CAPTURE_TAG_MIN}
    mapping: dict[tuple[str, int], str | None] = {
        key: (tag if tag in majority else None) for key, tag in moon_to_tag.items()
    }
    _apply_capture_subgroup_tag_overrides(mapping)
    _CAPTURE_TAG_BY_MOON = mapping
    return mapping


def _apply_capture_subgroup_tag_overrides(
    mapping: dict[tuple[str, int], str | None],
) -> None:
    """Subgrupos de captura con moon_tag propio (p. ej. pokio vs pokio_hole)."""
    if not BINGO_GROUPS_PATH.exists():
        return
    for group in load_catalog(BINGO_GROUPS_PATH).get("groups", []):
        if not group.get("capture"):
            continue
        moon_tag = group.get("moon_tag")
        if not moon_tag:
            continue
        tag = str(moon_tag)
        for raw in group_moons(group):
            key = (str(raw["kingdom"]), int(raw["moon"]))
            if key in mapping:
                mapping[key] = tag


def majority_capture_tags() -> frozenset[str]:
    """Slugs de captura concreta (normal mayoritaria)."""
    return frozenset(t for t in load_capture_tag_by_moon().values() if t)


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
    if "captures" in out and kingdom and moon is not None:
        specific = load_capture_tag_by_moon().get((kingdom, moon))
        if specific:
            out.add(specific)
            if specific == "pokio_hole":
                out.discard("pokio")
            umbrella = CAPTURE_UMBRELLA.get(specific)
            if umbrella:
                out.add(umbrella)
    # Captura de planta (uproot/cactus_tree): sin flora encima.
    if "captures" in out and out & PLANT_CAPTURE_TAGS:
        out.discard("flora")
    # Acceso concreto (mini_rocket / beanstalk / outfit_door): sin sub_area.
    if out & ACCESS_DROPS_SUB_AREA:
        out.discard("sub_area")
    # nature: solo grupo/goal agregado; en lunas usamos fauna o flora.
    out.discard("nature")
    # transport: solo grupo/goals (Beanstalk + Mini Rocket); en lunas
    # usamos beanstalk / mini_rocket (Rocket Flower = flora, fuera del paraguas).
    out.discard("transport")
    # 8-bit: la luna es el segmento 2D; captura solo de acceso no cuenta.
    if "8bit" in out:
        out.discard("captures")
        out -= majority_capture_tags() | PLANT_CAPTURE_TAGS
    # Captura especial (Coin Coffer, Ty-foo, …): special_capture_moons XOR captures.
    if "special_capture_moons" in out:
        out.discard("captures")
    # Puerta con outfit: outfit_door, nunca npc.
    if "outfit_door" in out:
        out.discard("npc")
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
        allowed |= normalize_moon_tags(
            entry.get("tags") or [], kingdom=kingdom, moon=moon
        )
    return frozenset(allowed)


# Cache de tags de contexto = ids de grupos pequenos (+ legacy group/sub_area).
_GROUP_CONTEXT_TAGS_CACHE: frozenset[str] | None = None


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
    global _GROUP_CONTEXT_TAGS_CACHE
    _GROUP_CONTEXT_TAGS_CACHE = None
    clear_capture_tag_cache()


_EXTRA_CACHE_CLEARS: list = []


def register_cache_clear(fn) -> None:
    """Otros módulos (p. ej. goal_list_lib) registran su clear aquí."""
    if fn not in _EXTRA_CACHE_CLEARS:
        _EXTRA_CACHE_CLEARS.append(fn)


def clear_runtime_caches() -> None:
    """Limpia caches en memoria, __pycache__ del repo y agent-tools temporal.

    Cuándo: tras cualquier script Python del repo (exports, sync, one-shots,
    -c). Casi todos importan catalog_lib → se registra en atexit, así que al
    salir del proceso se limpia solo. Si un comando NO importa catalog_lib,
    ejecutar a mano:
      python -c "from catalog_lib import clear_runtime_caches; clear_runtime_caches()"
    regenerate_all.py ya limpia como último paso.
    """
    clear_group_context_tags_cache()
    for fn in list(_EXTRA_CACHE_CLEARS):
        try:
            fn()
        except Exception:
            pass
    for path in ROOT.rglob("__pycache__"):
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


def load_group_context_tags() -> frozenset[str]:
    """Tags de contexto de grupo: no cuentan como metodo de obtencion.

    Incluye TAG_CONTEXT, ids de grupos pequenos y capturas concretas
    mayoritarias (van junto a `captures`, no como obtain aparte).
    """
    global _GROUP_CONTEXT_TAGS_CACHE
    if _GROUP_CONTEXT_TAGS_CACHE is not None:
        return _GROUP_CONTEXT_TAGS_CACHE
    tags: set[str] = set(TAG_CONTEXT)
    if BINGO_GROUPS_PATH.exists():
        for group in load_catalog(BINGO_GROUPS_PATH).get("groups", []):
            gid = group.get("id")
            if not gid:
                continue
            if group.get("apply_moon_tag") is False:
                continue
            particular = group.get("moon_tag") or group.get("tag")
            n = len(group.get("moons") or [])
            is_large_particular = bool(
                particular
                and particular != GROUP_MOON_TAG
                and (
                    n >= GROUP_LARGE_MIN
                    or group.get("large") is True
                    or group.get("umbrella") is True
                    or particular in UMBRELLA_MOON_TAGS
                )
            )
            if is_large_particular:
                continue
            # Misma tag que en lunas: sin prefijo de reino (cap_frog → frog).
            tags.add(strip_kingdom_prefix_from_id(str(gid)))
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


def tag_combination_violations(
    tags: set[str] | list[str],
    *,
    kingdom: str | None = None,
    moon: int | None = None,
) -> list[str]:
    """Return human-readable issues for an invalid tag set."""
    tag_set = set(tags)
    issues: list[str] = []

    for pair in INCOMPATIBLE_TAG_PAIRS:
        if pair.issubset(tag_set):
            if (
                pair == TAG_CAPTURES_AND_CAPPY
                and kingdom is not None
                and moon is not None
                and (kingdom, moon) in ALLOW_CAPTURES_AND_CAPPY
            ):
                continue
            a, b = sorted(pair)
            issues.append(f"incompatible: {a} + {b}")

    for tag, required in IMPLIED_TAGS.items():
        if tag in tag_set and not required.issubset(tag_set):
            missing = ", ".join(sorted(required - tag_set))
            issues.append(f"{tag} requiere tambien: {missing}")

    if "captures" in tag_set and kingdom and moon is not None:
        specific = load_capture_tag_by_moon().get((kingdom, moon))
        if specific and specific not in tag_set:
            issues.append(f"captures requiere tambien: {specific}")

    obtain = _obtain_tags(tag_set)
    if len(obtain) <= 1:
        return issues

    if any(combo.issubset(obtain) and obtain.issubset(combo) for combo in ALLOWED_MULTI_OBTAIN):
        return issues

    issues.append(
        "multiples metodos de obtencion: " + ", ".join(sorted(obtain))
    )

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
    "moon_names_wiki.json",
    "bingo_groups.json",  # grupos de objetivo; tags via apply_bingo_group_tags
    "bingo_lineas.json",  # categorias board/line Combined (no tags de luna)
    "goal_icons.json",  # iconos de goals Combined
    "goals_referencia.json",  # referencia goals + lunas/lista
    "goal_lists.json",  # listas contables + sub_area_levels (fuente manual/rebuild)
    "goal_tooltips.json",  # tooltips unicos Combined
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
    "{{X}} Unique Captures",
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


def load_wiki_moon_meta() -> dict[str, dict[int, dict[str, str]]]:
    path = CATALOG_DIR / "moon_names_wiki.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    result: dict[str, dict[int, dict[str, str]]] = {}
    for kingdom, moons in raw.items():
        # Meta (_definition, n_*) u otros no-mapa: no son reinos.
        if str(kingdom).startswith("_") or not isinstance(moons, dict):
            continue
        parsed: dict[int, dict[str, str]] = {}
        for num, value in moons.items():
            try:
                moon_num = int(num)
            except (TypeError, ValueError):
                continue
            if isinstance(value, str):
                parsed[moon_num] = {"name": value, "type": "", "prerequisite": ""}
            else:
                parsed[moon_num] = {
                    "name": value.get("name", ""),
                    "type": value.get("type", ""),
                    "prerequisite": value.get("prerequisite", ""),
                }
        result[kingdom] = parsed
    return result


def stamp_moon_names_wiki_counts(path: Path | None = None) -> dict[str, int]:
    """Añade n_kingdoms / n_moons al cache wiki (sin tocar entradas)."""
    path = path or (CATALOG_DIR / "moon_names_wiki.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    kingdoms = {
        k: v
        for k, v in raw.items()
        if not str(k).startswith("_") and isinstance(v, dict)
    }
    n_moons = sum(len(v) for v in kingdoms.values())
    ordered: dict = {
        "_definition": raw.get(
            "_definition",
            "Cache de nombres/tipos/prerequisites de Power Moons (Mario Wiki).",
        ),
        "_note": raw.get(
            "_note",
            "No editar a mano salvo refresh wiki. Contadores: n_kingdoms / n_moons.",
        ),
        "n_kingdoms": len(kingdoms),
        "n_moons": n_moons,
    }
    for k in KINGDOM_COLUMNS:
        if k in kingdoms:
            ordered[k] = kingdoms[k]
    for k, v in kingdoms.items():
        if k not in ordered:
            ordered[k] = v
    write_catalog_json(path, ordered)
    return {"n_kingdoms": len(kingdoms), "n_moons": n_moons}


# Lunas postgame / fuera de cutoff que entran por excepcion.
FORCE_IN_SCOPE_MOONS: frozenset[tuple[str, int]] = frozenset(
    {
        ("mushroom", 39),  # Secret Path via pintura Luncheon
        ("moon", 25),  # Tourist Moon (cadena; #15+ suelen ser postgame por nombre)
    }
)

# En lunas-objetivos / tags_inventario: no listar (siguen en bingo_groups/goals).
# mushroom#39 cuenta en painting / Warp-Painting; sin fila de catalogo por ahora.
LUNAS_CATALOG_EXCLUDE: frozenset[tuple[str, int]] = frozenset(
    {
        ("mushroom", 39),
    }
)

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
# Origen → unlock outbound (bingo):
#   Lake: Broodals (patio) → world_peace
#   Wooded: Flower Thieves → mid_story
#   Sand: Showdown → mid_story origen (destino Metro ≈ base)
#   Metro: Pest Problem → mid_story
#   Snow / Seaside: Bound Bowl / Glass → world_peace
#   Luncheon / Mushroom: None → base
#   Cascade / Bowser: complete the game → postgame
#
# Destinos desde Metro/Snow/Seaside (tabla de rutas):
#   wooded#49 / lake#26: Metro mid | Snow WP | Seaside WP → earliest mid_story
#   cascade#18: solo Snow/Seaside WP → world_peace
SECRET_PATH_AVAILABILITY: dict[tuple[str, int], str] = {
    ("cascade", 18): "world_peace",  # Snow WP o Seaside WP
    ("sand", 62): "mid_story",  # Lake WP o Wooded mid
    ("luncheon", 47): "mid_story",  # Lake WP o Wooded mid
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
    - physical_moons: pool temático o Multi-Moon[[s]] (1 por entrada en lista).
    """
    tip = obj.get("tooltip") or ""
    if KINGDOM_MOONS_ODYSSEY_TOOLTIP in tip:
        return "odyssey_units"
    if moonish or "moon" in goal.lower():
        if goal.startswith("All Multi-Moons") or "multi-moon[[" in goal.lower():
            return "physical_moons"
        if "{{X}}" in goal and "moon" in goal.lower():
            return "physical_moons"
    return None


def enrich_moon_ref_odyssey(
    ref: dict,
    registry: dict[tuple[str, int], dict],
) -> dict:
    """Añade odyssey_units en refs JSON cuando la luna es multi (×3)."""
    out = dict(ref)
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
    return low.startswith("peach in the ") or low.startswith("peach in bowser")


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
        or "picture match" in low
    )


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
    prerequisite = _normalize_prerequisite(
        (wiki_entry or {}).get("prerequisite", "")
    )
    # Quitar restos de refs wiki que a veces quedan en el texto.
    prerequisite = re.sub(r"<ref[^>]*>.*?</ref>", " ", prerequisite, flags=re.I | re.S)
    prerequisite = re.sub(r"\s+", " ", prerequisite).strip()

    if kingdom in BOSS_ONLY_KINGDOMS:
        return "base"

    key = (kingdom, int(moon))
    if key in AVAILABILITY_OVERRIDES:
        return AVAILABILITY_OVERRIDES[key]

    # Pinturas Secret Path: override curado (cache wiki suele ser «None»).
    if name.lower().startswith("secret path to"):
        return SECRET_PATH_AVAILABILITY.get(key, "base")

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

    if prerequisite == "second visit":
        return "revisit"

    final_markers = list(kingdom_rules.get("final_story_markers", []))
    final_markers.extend(FINAL_STORY_MARKERS.get(kingdom, ()))
    final_markers = [m.lower() for m in final_markers]
    if final_markers and _prereq_requires_any_marker(prerequisite, final_markers):
        return "world_peace"

    if "or second visit" in prerequisite:
        return "world_peace"

    mid_markers = list(kingdom_rules.get("mid_story_markers", []))
    mid_markers.extend(MID_STORY_MARKERS.get(kingdom, ()))
    mid_markers = [m.lower() for m in mid_markers]
    if mid_markers and _prereq_requires_any_marker(prerequisite, mid_markers):
        return "mid_story"

    # Wiki «None» / prereq temprano = al llegar o antes de la 1ª multi.
    return "base"


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
        # goals_referencia / bingo_*: orden+goal en objectives[] → expandir
        if "orden" in value and "goal" in value:
            return False
        return all(_is_flat_json_value(v) for v in value.values())
    return False


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

    def fmt_scalar_list(value: list, level: int, *, multiline: bool) -> str:
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

    def fmt(value: object, level: int, *, key: str | None = None) -> str:
        pad = " " * (indent * level)
        pad_in = " " * (indent * (level + 1))

        if isinstance(value, dict):
            if not value:
                return "{}"
            if _is_flat_json_value(value):
                inner = ", ".join(
                    f"{json.dumps(k, ensure_ascii=False)}: "
                    f"{json.dumps(v, ensure_ascii=False)}"
                    for k, v in value.items()
                )
                return "{" + inner + "}"
            lines = [
                f"{pad_in}{json.dumps(k, ensure_ascii=False)}: "
                f"{fmt(v, level + 1, key=str(k))}"
                for k, v in value.items()
            ]
            return "{\n" + ",\n".join(lines) + "\n" + pad + "}"

        if isinstance(value, list):
            if not value:
                return "[]"
            if all(isinstance(x, (str, int, float, bool)) or x is None for x in value):
                return fmt_scalar_list(
                    value,
                    level,
                    multiline=bool(key and key in multi_keys),
                )
            lines = [f"{pad_in}{fmt(x, level + 1)}" for x in value]
            return "[\n" + ",\n".join(lines) + "\n" + pad + "]"

        return json.dumps(value, ensure_ascii=False)

    return fmt(data, 0) + "\n"


def _ensure_path_under_root(path: Path) -> Path:
    """Resuelve path y exige que quede dentro del repo (anti path-traversal)."""
    resolved = path.resolve()
    root = ROOT.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path fuera del repo: {path}") from exc
    return resolved


def write_catalog_json(
    path: Path,
    data: object,
    *,
    multiline_string_list_keys: frozenset[str] | None = None,
) -> None:
    """Escribe catalogo JSON con objetos internos compactos."""
    safe_path = _ensure_path_under_root(path)
    safe_path.write_text(
        dumps_catalog_json(
            data, multiline_string_list_keys=multiline_string_list_keys
        ),
        encoding="utf-8",
    )


def finalize_bingo_groups_doc(bingo: dict) -> dict:
    """Asegura n_groups al inicio util (tras notas) antes de escribir."""
    groups = list(bingo.get("groups") or [])
    bingo["n_groups"] = len(groups)
    return bingo


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
)


def objective_goal_sort_key(goal: str) -> tuple:
    """{{X}}… primero, luego alfabetico (como Combined / sort_combined_json)."""
    return (0 if goal.startswith("{{X}}") else 1, goal.lower())


def kingdom_story_index(kingdom: str) -> int:
    """Índice de reino en orden de historia (incluye cloud/ruined/mushroom)."""
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


def entity_sort_key(item: dict) -> tuple:
    """Orden proyecto: reino (historia) → id numerico → precio → nombre.

    Ids prioritarios: moon, checkpoint / near_checkpoint, id.
    near_odyssey / near=\"Odyssey\" → checkpoint 0.
    near=\"#N …\" (post-enrich) → N.
    Tienda: regional antes que coins, luego importe, luego nombre.
    """
    k_ord = kingdom_story_index(str(item.get("kingdom") or ""))
    if item.get("near_odyssey") or item.get("near") == "Odyssey":
        return (k_ord, 0, 0)
    near = item.get("near")
    if isinstance(near, str) and near.startswith("#"):
        head = near[1:].split(None, 1)[0]
        try:
            return (k_ord, 0, int(head))
        except ValueError:
            pass
    for key in ("moon", "checkpoint", "near_checkpoint", "id"):
        val = item.get(key)
        if val is not None:
            try:
                return (k_ord, 0, int(val))
            except (TypeError, ValueError):
                pass
    moons = item.get("moons")
    if isinstance(moons, list) and moons:
        try:
            return (k_ord, 0, int(min(int(m) for m in moons)))
        except (TypeError, ValueError):
            pass
    name = str(item.get("name") or item.get("capture") or item.get("level") or "")
    if "regional" in item or "coins" in item:
        if "regional" in item:
            try:
                return (k_ord, 1, 0, int(item["regional"]), natural_name_key(name))
            except (TypeError, ValueError):
                pass
        if "coins" in item:
            try:
                return (k_ord, 1, 1, int(item["coins"]), natural_name_key(name))
            except (TypeError, ValueError):
                pass
    return (k_ord, 2, natural_name_key(name))


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
    """Objetivo ligero: goal + range/progression (+ limits). Sin tooltip/icons/cats."""
    if combined is None:
        combined = load_combined_objectives_by_goal().get(goal)
    ref: dict = {"goal": goal}
    if not combined:
        return ref
    for key in OBJECTIVE_REF_FIELDS:
        if key == "goal":
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
        names = {g for g in capture_goals.values() if g in active}
        # Subgoals de grupos con capture (p. ej. pokio_hole) no listados en CAPTURE_OBJECTIVE.
        if BINGO_GROUPS_PATH.exists():
            for g in load_catalog(BINGO_GROUPS_PATH).get("groups", []):
                if not g.get("capture"):
                    continue
                for goal in group_objectives(g):
                    if goal in active:
                        names.add(goal)
        # Goal global de capturar X cosas distintas (no está en CAPTURE_OBJECTIVE).
        if "{{X}} Unique Captures" in active:
            names.add("{{X}} Unique Captures")
        return sorted(names, key=objective_goal_sort_key)

    capture = group.get("capture")
    existing = group_objectives(group)
    listed = [g for g in existing if g in active]
    if capture:
        key = str(capture)
        mapped = capture_goals.get(key) or capture_goals.get(key.casefold())
        # Spec/listado del grupo gana (p. ej. Seaside vs Lake Cheep Cheep).
        if listed:
            return listed
        if mapped and mapped in active:
            return [mapped]
        return []

    return listed


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
    """Lunas del grupo (lista; independiente de objectives)."""
    raw = group.get("moons")
    if not isinstance(raw, list):
        return []
    return [m for m in raw if isinstance(m, dict) and "kingdom" in m and "moon" in m]


def group_kind(group: dict) -> str:
    """Tipo de grupo: both | objectives | moons | empty."""
    has_obj = bool(group_objectives(group))
    has_moons = bool(group_moons(group))
    if has_obj and has_moons:
        return "both"
    if has_obj:
        return "objectives"
    if has_moons:
        return "moons"
    return "empty"


def normalize_bingo_group(
    group: dict,
    combined_by_goal: dict[str, dict] | None = None,
) -> dict:
    """Normaliza un grupo: objectives y moons siempre presentes y separados."""
    if combined_by_goal is None:
        combined_by_goal = load_combined_objectives_by_goal()
    objectives = group_objective_refs(group, combined_by_goal)
    # Reinos: orden curado (Moons → Regional → Checkpoints → …).
    # Resto: {{X}} primero + alfabetico (como Combined).
    if group.get("id") not in KINGDOM_COLUMNS:
        objectives.sort(key=lambda o: objective_goal_sort_key(str(o.get("goal") or "")))
    # Lunas: se conserva el orden existente (reino/historia ya correcto).
    moons_raw = group_moons(group)
    registry = build_matrix_moon_registry()
    moons = [enrich_moon_ref_odyssey(m, registry) for m in moons_raw]
    odyssey_units = sum_moon_odyssey_units(moons_raw, registry)
    kind = group_kind({"objectives": [o["goal"] for o in objectives], "moons": moons})

    # Orden: id, orden (1..N alfa), kind, contadores, listas, meta.
    out: dict = {
        "id": group["id"],
    }
    if group.get("orden") is not None:
        out["orden"] = int(group["orden"])
    out.update(
        {
            "kind": kind,
            "n_objectives": len(objectives),
            "n_moons": len(moons),
            "objectives": objectives,
            "moons": moons,
        }
    )
    if odyssey_units != len(moons):
        out["n_odyssey_units"] = odyssey_units
    for key in (
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
    ):
        if key in group and group[key] not in (None, "", [], False):
            value = group[key]
            if key == "extra_tags" and isinstance(value, list):
                value = sort_category_list(value)
            out[key] = value
        # apply_moon_tag=False sí se persiste (omite etiquetar lunas).
        elif key == "apply_moon_tag" and group.get(key) is False:
            out[key] = False
    # internal=False no se escribe; True si.
    # Resto de claves desconocidas (sin goal legado ni vacios ni contadores viejos).
    skip = set(out) | {
        "goal",
        "objectives",
        "moons",
        "tag_only_moons",
        "kind",
        "id",
        "orden",
        "n_objectives",
        "n_moons",
        "n_objetivos",
        "n_lunas",
    }
    for key, value in group.items():
        if key in skip or value in (None, "", []):
            continue
        out[key] = value
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
    groups = [normalize_bingo_group(g, combined_by_goal) for g in groups]
    counts = {
        "both": sum(1 for g in groups if g["kind"] == "both"),
        "objectives": sum(1 for g in groups if g["kind"] == "objectives"),
        "moons": sum(1 for g in groups if g["kind"] == "moons"),
        "empty": sum(1 for g in groups if g["kind"] == "empty"),
    }
    ordered: dict = {
        "_definition": (
            "Grupos de bingo: 'objectives' y 'moons' son listas de objetos "
            "independientes. objectives[] = {goal, range, progression, …} "
            "desde Combined (tooltip/icons/cats → goals_referencia / "
            "goal_icons / bingo_lineas). "
            "moons[] = {kingdom, moon, name}; multi_moon añade odyssey_units:3. "
            "kind=both|objectives|moons. n_objectives / n_moons = tamanos; "
            "n_odyssey_units si difiere de n_moons (multi×3 al depositar). "
            "orden = id numerico 1..N tras ordenar por id (slug). "
            "Meta: moon_tag/large/umbrella/internal, kingdom, capture. "
            "internal=True: solo tags/grupos (no bingo/linea). "
            "story_moon/multi_moon/captures/cappy/mario: grupos de tag (moons) sin JSON aparte. "
            "Cobertura incompleta OK por ahora."
        ),
        "_note": (
            "Campos: id (slug), orden (1..N alfa), kind, n_objectives, n_moons, "
            "objectives[{goal,range,progression,…}], moons[{kingdom,moon,name}], "
            "moon_tag/large/umbrella/internal, kingdom/capture/_note. "
            "Existencia tematica: >=3 lunas o >=1 objetivo relacionado. "
            "Al normalizar, objectives se regeneran desde Combined (activos). "
            "Orden: groups por id; goals {{X}}+alpha (reinos: orden curado); "
            "moons sin reordenar; board/line cats alpha."
        ),
        "n_groups": len(groups),
        "groups": groups,
    }
    write_catalog_json(BINGO_GROUPS_PATH, ordered)
    clear_group_context_tags_cache()
    return counts


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
    moon_refs: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for raw in moons:
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
    tag_only_refs: list[dict] = []
    seen_tag_only: set[tuple[str, int]] = set()
    for raw in tag_only_raw:
        if not isinstance(raw, dict) or "kingdom" not in raw or "moon" not in raw:
            continue
        kingdom = str(raw["kingdom"])
        moon = int(raw["moon"])
        key = (kingdom, moon)
        if key in seen_tag_only:
            continue
        seen_tag_only.add(key)
        tag_only_refs.append(
            {
                "kingdom": kingdom,
                "moon": moon,
                "name": raw.get("name") or f"Moon {moon}",
            }
        )
    tag_only_refs.sort(key=entity_sort_key)
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
    groups = assign_bingo_group_orden(groups)
    bingo["groups"] = [normalize_bingo_group(g, combined) for g in groups]
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
    n = len(group.get("moons") or [])
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


def apply_bingo_group_tags(merged: dict[tuple[str, int], dict]) -> None:
    """Aplica tags de cada bingo group (concreto y/o paraguas)."""
    clear_group_context_tags_cache()
    if not BINGO_GROUPS_PATH.exists():
        return
    catalog = load_catalog(BINGO_GROUPS_PATH)
    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()

    for group in catalog.get("groups", []):
        tags_to_add = set(group_moon_tags(group))
        tags_to_add |= {
            canonicalize_tag(str(t))
            for t in (group.get("extra_tags") or [])
            if t
        }
        # No re-aplicar rare fallback sobre tags ya decididas por el grupo
        tag_targets = list(group_moons(group))
        for raw in group.get("tag_only_moons") or []:
            if isinstance(raw, dict) and "kingdom" in raw and "moon" in raw:
                tag_targets.append(raw)
        for raw in tag_targets:
            key = (raw["kingdom"], int(raw["moon"]))
            kingdom, moon = key
            entry = merged.get(key)
            if entry is None:
                wiki_entry = wiki.get(kingdom, {}).get(moon)
                name = raw.get("name") or (wiki_entry or {}).get("name") or f"Moon {moon}"
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
            else:
                entry["tags"] |= tags_to_add
                entry.setdefault("catalogs", set()).add("bingo_groups")


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


def load_active_combined_objectives() -> list[dict]:
    """Objetivos Combined activos (no disabled) del JSON de pagina."""
    if not JSON_PATH.exists():
        return []
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return [o for o in data.get("objectives", []) if not o.get("disabled") and o.get("goal")]


def kingdom_objectives_from_combined() -> dict[str, list[dict]]:
    """Objetivos Combined por reino (objetos {goal, ...info})."""
    by_kingdom: dict[str, list[tuple[int, int, dict]]] = {k: [] for k in KINGDOM_COLUMNS}
    tipo_rank = {"reino_total": 0, "reino_regional": 1, "reino_exclusivo": 2}

    def exclusivo_priority(goal: str) -> int:
        """Orden curado dentro de reino_exclusivo.

        Checkpoints → Story → Multi con {{X}} → resto {{X}} → Multi fijo → resto fijo.
        Asi Multi fijo (Seaside/Snow) no parte el bloque {{X}}.
        """
        low = goal.lower()
        has_x = goal.startswith("{{X}}")
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

    for obj in load_active_combined_objectives():
        goal = str(obj["goal"])
        if goal in KINGDOM_OBJECTIVE_EXCLUDE:
            continue
        tipo, reino = classify_objective(
            goal,
            obj.get("board_categories") or [],
            obj.get("line_categories") or [],
        )
        if not reino or reino not in by_kingdom:
            continue
        if tipo not in tipo_rank:
            continue
        sub = exclusivo_priority(goal) if tipo == "reino_exclusivo" else 0
        # Dentro del mismo bucket: alfabetico ({{X}} ya va en sub 2/3).
        by_kingdom[reino].append(
            (
                tipo_rank[tipo],
                sub,
                goal.lower(),
                objective_ref_from_combined(goal, obj),
            )
        )

    out: dict[str, list[dict]] = {}
    for slug, items in by_kingdom.items():
        items.sort(key=lambda pair: (pair[0], pair[1], pair[2]))
        seen: set[str] = set()
        refs: list[dict] = []
        for *_, ref in items:
            goal = ref["goal"]
            if goal not in seen:
                seen.add(goal)
                refs.append(ref)
        out[slug] = refs
    return out


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
            "kind": "both",
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


def load_bingo_groups() -> list[dict]:
    if not BINGO_GROUPS_PATH.exists():
        return []
    return list(load_catalog(BINGO_GROUPS_PATH).get("groups", []))


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

    Fuente: catalog/goal_lists.json → lists.sub_area_levels (rebuild_sub_area_bingo).
    """
    path = CATALOG_DIR / "goal_lists.json"
    if path.exists():
        data = load_catalog(path)
        lists = data.get("lists") or {}
        levels = lists.get("sub_area_levels")
        if isinstance(levels, list):
            return list(levels)
        # Compat: clave top-level antigua.
        legacy_top = data.get("sub_area_levels")
        if isinstance(legacy_top, list):
            return list(legacy_top)
    legacy = CATALOG_DIR / "sub_area_levels.json"
    if legacy.exists():
        data = load_catalog(legacy)
        return list(data.get("levels") or [])
    return []



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


def merge_catalog_moons() -> dict[tuple[str, int], dict]:
    """Return {(kingdom, moon): merged item} with union of tags."""
    merged: dict[tuple[str, int], dict] = {}

    for path in sorted(CATALOG_DIR.glob("*.json")):
        if path.name in SKIP_CATALOGS:
            continue
        catalog = load_catalog(path)
        stem = path.stem
        primary_tag = PRIMARY_TAGS.get(stem)
        for item in catalog.get("items", []):
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
                continue

            entry = merged[key]
            if len(item["name"]) > len(entry["name"]):
                entry["name"] = item["name"]
            entry["tags"].update(tags)
            entry["catalogs"].add(stem)
            priority = {"base": 0, "mid_story": 1, "world_peace": 2, "revisit": 3}
            cur = priority.get(entry["availability"], 0)
            new = priority.get(item.get("availability", "base"), 0)
            if new > cur:
                entry["availability"] = item.get("availability", "base")

    apply_bingo_group_tags(merged)
    return merged


def build_matrix_moon_registry() -> dict[tuple[str, int], dict]:
    """Lunas catalogadas en alcance (base/mid_story/revisit/world_peace)."""
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
    counts = {k: 0 for k in KINGDOM_COLUMNS}
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


def goal_to_matrix_column(goal: str, tipo: str, reino: str | None) -> str:
    if goal in GOAL_TO_TAG:
        return GOAL_TO_TAG[goal]
    slug, suffix = parse_kingdom_prefixed_goal(goal)
    if slug and suffix and tipo == "reino_exclusivo":
        mechanic = slugify_matrix_token(suffix)
        return f"{slug}_{mechanic}" if mechanic else slug
    rest = goal.removeprefix("{{X}} ").strip()
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
        if not goal.startswith("{{X}}"):
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
    if not goal.startswith("{{X}} "):
        return None, None
    rest = goal[len("{{X}} ") :]
    for display, slug in KINGDOM_GOAL_PREFIXES:
        prefix = f"{display} "
        if rest.startswith(prefix):
            return slug, rest[len(prefix) :]
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

    slug, suffix = parse_kingdom_prefixed_goal(goal)
    if slug and suffix == "Moons":
        return "reino_total", slug
    if slug and suffix == "Regional Coins":
        return "reino_regional", slug
    if slug and suffix:
        return "reino_exclusivo", slug

    kingdoms = list(
        dict.fromkeys(
            kingdoms_in_categories(board_categories)
            + kingdoms_in_categories(line_categories or [])
        )
    )
    if len(kingdoms) == 1:
        return "reino_exclusivo", kingdoms[0]

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


def objective_columns() -> list[tuple[str, str]]:
    """(column_id, tag) pairs for catalog cross-reino goals (legacy helper)."""
    return [(obj.column_id, obj.tag) for obj in load_matrix_objectives()]
