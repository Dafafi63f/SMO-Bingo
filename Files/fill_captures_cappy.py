"""Asigna tags captures / cappy / mario desde guias Mario Wiki.

- captures: la luna exige capturar algo (enemigo/boss/objeto de la pelea)
- cappy: la accion de la luna es Cappy (throw/hold/palanca, etc.)
- mario: solo MARIO_MOONS (pool curado "en medio de la nada" / goal
  {{X}} Mario Moons). El resto a pie (ni captures ni cappy) no lleva tag
  de accion aunque tenga otras tags tematicas.
- scarecrow: Cappy solo activa; la carrera/subarea la hace Mario → sin
  cappy (TC, Spinning Athletics, Freezing Water…; no confundir con Mini
  Rocket: el cohete es transporte y la luna suele ser Mario a pie dentro)
- P-switch se pisa a pie → no cappy
- XOR por defecto; ALLOW_CAPTURES_AND_CAPPY = ambas (palanca/hold + captura)
- Broodals y peleas Cappy+stomp: sin captures

Usage:
  python fill_captures_cappy.py
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from collections import Counter
from html import unescape
from pathlib import Path

from catalog_lib import (
    ALLOW_CAPTURES_AND_CAPPY,
    FORCE_IN_SCOPE_MOONS,
    KINGDOM_COLUMNS,
    KINGDOM_DISPLAY,
    MARIO_MOONS,
    ROCKET_FLOWER_MOONS,
    TAG_ACTION,
    TAG_CAPTURES_AND_CAPPY,
    build_matrix_moon_registry,
    infer_availability,
    load_kingdom_availability,
    load_wiki_moon_meta,
    upsert_moon_tag_group,
    wiki_moon_in_scope,
)
from export_lunas_tags import export_lunas, export_tags

USER_AGENT = "BingoMoonTagger/1.1 (captures/cappy; +https://www.mariowiki.com)"

MARIOWIKI_URLS: dict[str, str] = {
    "cap": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Cap_Kingdom",
    "cascade": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Cascade_Kingdom",
    "sand": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Sand_Kingdom",
    "lake": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Lake_Kingdom",
    "wooded": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Wooded_Kingdom",
    "lost": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Lost_Kingdom",
    "metro": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Metro_Kingdom",
    "snow": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Snow_Kingdom",
    "seaside": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Seaside_Kingdom",
    "luncheon": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Luncheon_Kingdom",
    "bowser": "https://www.mariowiki.com/List_of_Power_Moons_in_Bowser%27s_Kingdom",
    "moon": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Moon_Kingdom",
}

# Captura tiene prioridad sobre cappy si ambos aparecen.
CAPTURE_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\bcapture[sd]?\b",
        r"\bcapturing\b",
        r"\bas a (?:captured )?",
        r"while captured",
        r"must capture",
        r"capture (?:the |a |an )?",
    )
]

# Espantapajaros: Cappy solo abre; la luna es mario (no van en CAPPY_PATTERNS).
SCARECROW_PATTERN = re.compile(r"\bscarecrow\b", re.I)

CAPPY_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"throw(?:s|ing)? cappy",
        r"toss(?:es|ing)? cappy",
        r"throw(?:s|ing)? (?:his |the )?cap\b",
        r"toss(?:es|ing)? (?:his |the )?cap\b",
        r"hold(?:s|ing)? cappy",
        r"leave(?:s|ing)? cappy",
        r"cappy (?:on|onto|at|into|against)",
        r"cap throw",
        r"spin(?:s|ning)? (?:the )?cap",
        r"cap jump",
        r"hat[- ]throw",
        r"\blever(?:\s+switch)?\b",
        r"activat(?:e|es|ing) the lever",
        # P-switch / purple switch: Mario (o captura) pisa; no requiere Cappy.
        # scarecrow → mario (ver SCARECROW_PATTERN / classify_action).
    )
]

# Capturas de criaturas / mecánicas por nombre (no bosses de historia genéricos).
NAME_CAPTURE = [
    re.compile(p, re.I)
    for p in (
        r"frog-jumping",
        r"poison tide",
        r"frog pond",
        r"chain chomp",
        r"bullet bill",
        r"\bgoomba\b",
        r"\bglydon\b",
        r"\bt-rex\b",
        r"\btrex\b",
        r"\bpokio\b",
        r"\blakitu\b",
        r"\buroko\b",
        r"\bsherm\b",
        r"\bburzzo\b",
        r"motor scooter",
        r"\btaxi\b",
        r"\bparrot\b",
        r"\bbinocular",
        r"\bfrog\b",
        r"\bcaptured\b",
        r"spark pylon",
        r"\buproot\b",
        r"moe[- ]eye",
        r"invisible maze",
        r"transparent maze",
        r"\bgushen\b",
        r"jetstream",
        r"narrow valley",
        r"\bzipper\b",
        r"\bvolbonan\b",
        r"fork flickin",
        r"bound bowl",
        r"snowline circuit",
        r"cheese rocks",
        r"golden turnip recipe",
        r"rewiring the neighborhood",
        r"beaten wire",
        r"sea gardening",
    )
]

# Bosses / objetivos donde la pelea SÍ exige captura para ganar la luna.
NAME_CAPTURE_REQUIRED = [
    re.compile(p, re.I)
    for p in (
        r"multi moon atop the falls",  # Madame Broode → Chain Chomp
        r"madame broode",
        r"moon shards in the sand",  # Moe-Eye Habitat
        r"the hole in the desert",  # Knucklotec → Fist
        r"knucklotec",
        r"defend the secret flower",  # Torkdrift → Uproot
        r"torkdrift",
        r"pest problem",  # Mechawiggler → Spark Pylon
        r"mechawiggler",
        r"glass is half full",  # Mollusque → Cheep Cheep
        r"mollusque",
        r"cookatiel showdown",  # Cookatiel → Lava Bubble
        r"\bcookatiel\b",
    )
]

# Broodals / peleas con Cappy+stomp (o sin captura): NUNCA tag captures.
NAME_NO_CAPTURE = [
    re.compile(p, re.I)
    for p in (
        r"\bbroodals?\b",
        r"big broodal",
        r"flower thieves",  # Spewart
        r"showdown on the inverted",  # Hariet
        r"traditional festival",  # RoboBrood
        r"showdown at bowser",  # Bowser
        r"\bdorrie\b",  # fauna, no captures
        r"\bjaxi\b",  # fauna, no captures (solo lista oficial → captures)
    )
]

NAME_CAPPY = [
    re.compile(p, re.I)
    for p in (
        r"hat-and-seek",
        r"spin the hat",
        r"hang your hat",
        r"on the statue'?s tail",
        r"statue'?s tail",
    )
]

# Overrides curados: ganan sobre la clasificacion wiki.
# None = mario (sin captures/cappy). "both" = captures+cappy.
# Scarecrow abre → mario (Cappy solo activa).
FORCE_ACTION: dict[tuple[str, int], str | None] = {
    ("sand", 60): None,  # Mini Rocket → plataformas sin Cappy (#61 arriba)
    ("sand", 61): None,  # (espantapájaro interior no abre el cohete)
    # Slots: minigame + cappy (grupo slots también pone extra_tags).
    ("sand", 44): "cappy",
    ("metro", 28): "cappy",
    ("luncheon", 26): "cappy",
    # Spinning Athletics: scarecrow abre; Mario corre → mario
    ("luncheon", 45): None,
    ("luncheon", 46): None,
    # Contenido real (forma = la luna), no transporte:
    ("lake", 16): "captures",  # Cheep Cheep Moons (+ npc)
    ("luncheon", 4): "captures",
    ("luncheon", 5): "captures",  # Cookatiel (también NAME_CAPTURE_REQUIRED)
    ("luncheon", 8): "captures",  # cañón LB + decapture
    ("luncheon", 14): "captures",
    ("luncheon", 31): "captures",  # Light the Two Flames: Fire Bro
    ("luncheon", 23): "captures",  # notes en magma (LB)
    ("luncheon", 27): "captures",
    ("luncheon", 28): "captures",
    ("luncheon", 36): "captures",  # Big Pot Swim notes (LB)
    ("luncheon", 39): "captures",  # Magma Narrow Path
    ("luncheon", 40): "captures",  # Crossing to the Magma
    ("wooded", 3): "captures",  # Path to Secret Flower Field: Sherm (tanque)
    ("wooded", 6): None,  # Back Way Up the Mountain: 8-bit (Uproot = acceso)
    ("lost", 6): None,  # Avoiding Fuzzies Inside the Wall: 8-bit
    ("lost", 19): "cappy",  # The Caged Gold: Cappy → Trapeetle (como #11)
    # Acceso / sin captura de lista / falsa positiva wiki:
    ("sand", 6): None,   # Alcove in the Ruins: exploracion, sin captura
    ("sand", 7): None,   # On the Leaning Pillar: BB opcional (como #13)
    ("sand", 11): None,  # On Top of the Stone Archway: BB opcional
    ("sand", 13): None,  # On the Lone Pillar: salto, sin captura
    ("metro", 43): None,  # Rotating Maze: Manhole = acceso
    ("metro", 44): None,
    ("metro", 45): None,  # High-Rise: cohete = acceso; contenido = poles
    ("metro", 46): None,
    ("metro", 18): None,  # How Do They Take Out the Trash?: dumpster (salto), no cappy
    ("metro", 34): None,  # City Hall Lost & Found: cofre → treasure_chest (no cappy)
    # Palanca / hold-Cappy (contenido = Cappy; captura solo acceso o grupo aparte):
    ("metro", 37): "cappy",  # Pushing Through the Crowd: palanca → TC corto
    # Palanca/hold + captura de contenido → ALLOW_CAPTURES_AND_CAPPY (ambas tags).
    ("luncheon", 2): "both",  # Lever + Hammer Bro
    ("sand", 55): "both",  # hold Cappy + Moe-Eye
    ("sand", 29): "captures",  # TC2: P-Switch abre; fuera de pool moe_eye
    ("metro", 20): None,  # TC2: scooter + P-Switch/llave; scooter ≠ captura de lista (como #25)
    ("wooded", 14): "captures",  # Uproot/nut; palanca cueva = solo Activate Levers (lista)
    ("wooded", 19): "both",  # Cappy + Fire Bro
    ("sand", 36): "captures",  # Five Cactuses: misma regla que #40/#34 (cactus_tree)
    ("sand", 40): "captures",  # Wandering Cactus
    ("wooded", 34): "captures",  # Beneath the Roots of the Moving Tree
    # Rocket Flower dash → grupo rocket_flower (sin tag cappy; ver ROCKET_FLOWER_MOONS).
    # Freezing Water Swim: scarecrow abre; Mario nada → mario (no Cheep Cheep)
    ("snow", 26): None,
    ("snow", 27): None,
    ("bowser", 2): "captures",  # Smart Bombing: Pokio + shards (story)
    ("bowser", 4): "captures",  # Showdown: Pokio en Inner Wall (multi)
    ("bowser", 9): "captures",  # Past the Moving Wall: Pokio
    ("bowser", 34): "captures",  # Down and Up the Spinning Tower (Pokio sub_area)
    # Lakitu = vuelo sobre veneno (no pesca); tag captures sin lakitu_fishing.
    ("bowser", 10): "captures",  # Above the Poison Swamp
    # Capturas especiales CSV con goal/zona propia → captures (no special_capture_moons):
    ("lake", 20): "captures",  # Puzzle Part → {{X}} Puzzle Moon[[s]]
    ("wooded", 33): "captures",  # Coin Coffer → Special Seed Moon
    ("snow", 28): "captures",  # Ty-foo → Ty-Foo Moons (+ puzzle)
    ("snow", 3): "captures",  # Gusty Barrier: Ty-foo (story; sí en Ty-Foo Moons)
    ("snow", 9): "captures",  # Atop a Blustery Arch: Ty-foo
    ("luncheon", 32): None,  # Far-Off Lanterns: Fire Piranha/LB opcional → mario
    ("luncheon", 37): None,  # Magma Swamp: Fire Piranha ambiente → mario
    ("luncheon", 38): None,  # Magma Swamp corner → mario
    ("moon", 9): "captures",  # Bowser Statue Moon
    ("moon", 10): "captures",  # Moon Parabones Moon
    ("moon", 11): "captures",  # Around the Barrier Wall: Banzai Bill
    ("moon", 13): "captures",  # Moon Banzai Bill Moon
    # Alinear capturas_lunas.json → grupo captures (faltaban tras sync wiki):
    ("lake", 23): "captures",  # Zipper: Super-Secret Zipper
    ("luncheon", 41): "captures",  # Volbonan: Fork Flickin' to the Summit
    ("luncheon", 42): "captures",  # Volbonan: Fork Flickin' Detour
    ("luncheon", 44): "captures",  # Hammer Bro: Climb the Cheese Rocks
    ("cap", 8): "captures",  # Spark pylon: Push-Block Peril
    ("cap", 9): "captures",  # Spark pylon: Hidden Among the Push-Blocks
    ("metro", 14): None,  # Who Piled Garbage: GP basura; pylon/pole = acceso
    ("metro", 39): "captures",  # Spark pylon: Rewiring
    ("metro", 40): "captures",  # Spark pylon: Off the Beaten Wire
    ("metro", 42): "captures",  # Sherm: Sharpshooting Under Siege
    ("metro", 50): "captures",  # T-Rex: Big Jump: Escape!
    ("seaside", 23): None,  # Sea Gardening: Gushen opcional (acelerar)
    ("seaside", 24): None,
    ("seaside", 25): None,
    ("seaside", 26): "captures",  # Ocean Trench Seed → Seaside Gushen Moons
    ("seaside", 46): "captures",  # Gushen: Treasure Chest in the Narrow Valley
    ("seaside", 48): "captures",  # Uproot: Stretch on the Side Path
    ("snow", 1): "captures",  # Goomba: The Icicle Barrier
    ("snow", 5): "captures",  # Shiverian Racer: Bound Bowl
    ("snow", 11): None,  # The Shiverian Treasure Chest (NPC/cofre, no captura)
    ("snow", 23): "captures",  # Shiverian Racer: Class S
    ("wooded", 11): "captures",  # Uproot: Tucked Away Inside the Tunnel
    ("wooded", 13): "captures",  # Uproot: The Nut 'Round the Corner
    ("wooded", 15): "captures",  # Uproot: The Nut in the Red Maze
    ("wooded", 16): "captures",  # Uproot: The Nut at the Dead End
    ("wooded", 24): "captures",  # Uproot: Nut Planted in the Tower (par #25)
    ("wooded", 42): "captures",  # Paragoomba: Nut Hidden in the Fog
    ("wooded", 45): "captures",  # Sherm: Elevator Escalation
    ("wooded", 47): "captures",  # Cloud Walking: Uproot (+ beanstalk acceso)
    ("wooded", 48): "captures",  # Above the Clouds: Uproot (+ beanstalk acceso)
    # Meat: captura sí, sin goal concreta (solo Unique Captures; no Capture Meat).
    ("luncheon", 3): "captures",  # Big Pot multiluna
    # Transporte (nadar/lava) o GP alt.:
    ("seaside", 10): "captures",  # Cheep Cheep: Underwater Highway Tunnel
    ("seaside", 11): "captures",  # Cheep Cheep: Shh! It's a Shortcut!
    ("seaside", 12): "captures",  # Cheep Cheep: Gap in the Ocean Trench
    ("seaside", 13): "captures",  # Cheep Cheep: Slip Through the Nesting Spot
    ("seaside", 39): "captures",  # Cheep Cheep: Looking Back in the Dark Waterway
    ("lake", 3): None,
    ("lake", 18): "captures",  # Captain Toad: Cheep Cheep (GP alt existe; captura = camino oficial)
    ("luncheon", 15): None,  # Golden Turnip Recipe 1: nabo plaza, sin captura
    ("luncheon", 16): None,  # Golden Turnip Recipe 2: nabo crag, sin captura
    ("luncheon", 29): None,  # Alcove Behind Pillars: sin captura
    ("luncheon", 37): None,  # Magma Swamp: plataformas
    ("luncheon", 38): None,
}

# Golpear pajaros / lunas de pajaros: objetivo bingo propio (no tag cappy).
NAME_NO_CAPPY = [
    re.compile(p, re.I)
    for p in (
        r"bird traveling",
        r"where the birds gather",
        r"traveling[- ]bird",
    )
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read().decode("utf-8", "replace")


def strip_tags(html: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def parse_mariowiki_table(html: str) -> dict[int, dict[str, str]]:
    tables = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
        html,
        flags=re.S | re.I,
    )
    if not tables:
        return {}
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], flags=re.S | re.I)
    result: dict[int, dict[str, str]] = {}
    for row in rows[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)
        if len(cells) < 3:
            continue
        num_match = re.match(r"(\d+)", strip_tags(cells[0]))
        if not num_match:
            continue
        moon = int(num_match.group(1))
        name = strip_tags(cells[2] if len(cells) >= 4 else cells[1])
        name = re.sub(r"[❸②①]+$", "", name).strip()
        desc_idx = 3 if len(cells) >= 5 else 2
        description = strip_tags(cells[desc_idx]) if len(cells) > desc_idx else ""
        result[moon] = {"name": name, "description": description}
    return result


def classify_action(name: str, description: str, existing_tags: set[str]) -> str | None:
    """Return 'captures', 'cappy', or None. Captures gana si hay duda.

    captures = el enemigo/boss/cosa que da la luna EXIGE captura.
    Broodals y peleas Cappy+stomp: sin captures.
    scarecrow = Cappy solo activa → None (mario), aunque el texto diga
    "throw Cappy onto the scarecrow".
    timer_challenge: palanca → cappy; scarecrow/P-switch → mario.
    Captura dentro del TC (p. ej. Moe-Eye) → captures.
    """
    blob = f"{name}. {description}"
    no_capture = any(p.search(name) for p in NAME_NO_CAPTURE)

    def capture_hit() -> bool:
        if no_capture:
            return False
        if any(p.search(name) for p in NAME_CAPTURE_REQUIRED):
            return True
        if any(p.search(name) for p in NAME_CAPTURE):
            return True
        # En descripcion: verbo capture*, no "cap" de Cappy.
        return any(p.search(blob) for p in CAPTURE_PATTERNS)

    def scarecrow_gate() -> bool:
        return bool(SCARECROW_PATTERN.search(blob))

    def cappy_activation() -> bool:
        if any(p.search(blob) for p in CAPPY_PATTERNS):
            return True
        return any(p.search(name) for p in NAME_CAPPY)

    if "timer_challenge" in existing_tags:
        if capture_hit():
            return "captures"
        # Scarecrow: Cappy abre el reloj; la carrera es Mario → mario.
        if scarecrow_gate():
            return None
        # Palanca / hold-Cappy como contenido de activacion → cappy.
        if cappy_activation():
            return "cappy"
        return None

    if capture_hit():
        return "captures"

    # Scarecrow abre puerta/subarea: la luna la hace Mario.
    if scarecrow_gate():
        return None

    # Pajaros: bingo group propio; no clasificar como cappy aunque se use el sombrero.
    if any(p.search(name) for p in NAME_NO_CAPPY):
        return None

    cappy_hit = cappy_activation()
    if cappy_hit and not no_capture:
        return "cappy"
    # Broodals pueden usar Cappy sin captura → sin tag de accion aqui.
    if cappy_hit and no_capture:
        return None
    return None


def main(*, export: bool = True) -> None:
    wiki = load_wiki_moon_meta()
    rules = load_kingdom_availability()
    registry = build_matrix_moon_registry()

    guides: dict[str, dict[int, dict[str, str]]] = {}
    for kingdom in KINGDOM_COLUMNS:
        print(f"  Mario Wiki: {KINGDOM_DISPLAY.get(kingdom, kingdom)}...")
        try:
            guides[kingdom] = parse_mariowiki_table(fetch(MARIOWIKI_URLS[kingdom]))
        except Exception as exc:  # noqa: BLE001
            print(f"    AVISO: {exc}")
            guides[kingdom] = {}
        time.sleep(0.35)

    items: list[dict] = []
    mario_items: list[dict] = []
    counts: Counter[str] = Counter()
    neither = 0

    def _kingdom_sort_key(kv: tuple) -> tuple:
        kingdom, moon = kv[0]
        try:
            idx = KINGDOM_COLUMNS.index(kingdom)
        except ValueError:
            idx = 99  # mushroom u otros fuera de columnas bingo
        return (idx, moon)

    for (kingdom, moon), entry in sorted(registry.items(), key=_kingdom_sort_key):
        # mushroom u otros fuera de columnas bingo solo si FORCE_IN_SCOPE
        if kingdom not in KINGDOM_COLUMNS and (kingdom, moon) not in FORCE_IN_SCOPE_MOONS:
            continue
        wiki_entry = wiki.get(kingdom, {}).get(moon)
        if not wiki_moon_in_scope(kingdom, moon, wiki_entry, rules):
            continue

        guide = guides.get(kingdom, {}).get(moon) or {}
        name = entry["name"]
        description = guide.get("description", "")
        if (kingdom, moon) in ROCKET_FLOWER_MOONS:
            neither += 1
            continue
        if (kingdom, moon) in ALLOW_CAPTURES_AND_CAPPY:
            action = "both"
        elif (kingdom, moon) in FORCE_ACTION:
            action = FORCE_ACTION[kingdom, moon]
        else:
            action = classify_action(name, description, set(entry["tags"]))

        if action is None:
            neither += 1
            # Tag mario solo en el pool curado (goal {{X}} Mario Moons).
            if (kingdom, moon) in MARIO_MOONS:
                mario_items.append(
                    {
                        "kingdom": kingdom,
                        "moon": moon,
                        "name": name,
                    }
                )
            continue

        if action == "both":
            tags = ["captures", "cappy"]
            counts["captures"] += 1
            counts["cappy"] += 1
        else:
            tags = [action]
            counts[action] += 1
        items.append(
            {
                "kingdom": kingdom,
                "moon": moon,
                "name": name,
                "availability": infer_availability(
                    kingdom, moon, name, wiki_entry, rules, tags
                ),
                "tags": tags,
            }
        )

    captures = [i for i in items if "captures" in i["tags"]]
    cappy = [i for i in items if "cappy" in i["tags"]]
    n_cap = upsert_moon_tag_group(
        "captures",
        captures,
        moon_tag="captures",
        note=(
            "Requiere captura. XOR cappy/mario salvo ALLOW_CAPTURES_AND_CAPPY "
            "(palanca/hold + captura)."
        ),
    )
    n_cappy = upsert_moon_tag_group(
        "cappy",
        cappy,
        moon_tag="cappy",
        note=(
            "Requiere Cappy. XOR captures/mario salvo ALLOW_CAPTURES_AND_CAPPY "
            "(palanca/hold + captura)."
        ),
        objectives=[
            {"goal": "{{X}} Cappy Moons"},
            {"goal": "Save Cappy From Klepto"},
        ],
    )
    n_mario = upsert_moon_tag_group(
        "mario",
        mario_items,
        moon_tag="mario",
        note=(
            "Mario a pie 'en medio de la nada' (MARIO_MOONS). "
            "Goal {{X}} Mario Moons. Resto a pie sin tag de accion."
        ),
        objectives=[
            {"goal": "{{X}} Mario Moons"},
        ],
    )

    print(f"\nActualizado bingo_groups: captures={n_cap}  cappy={n_cappy}  mario={n_mario}")
    print(
        f"  (wiki: captures={counts['captures']} cappy={counts['cappy']} "
        f"a_pie={neither} mario_tag={len(mario_items)})"
    )

    if not export:
        return

    print("\nExportando...")
    export_lunas()
    export_tags()

    reg2 = build_matrix_moon_registry()
    both = [
        (k, m, e["name"], sorted(e["tags"]))
        for (k, m), e in reg2.items()
        if TAG_CAPTURES_AND_CAPPY <= set(e["tags"])
    ]
    allowed_both = [row for row in both if (row[0], row[1]) in ALLOW_CAPTURES_AND_CAPPY]
    unexpected = [row for row in both if (row[0], row[1]) not in ALLOW_CAPTURES_AND_CAPPY]
    if allowed_both:
        print(f"OK excepciones captures+cappy ({len(allowed_both)}):")
        for row in allowed_both:
            print(" ", row)
    if unexpected:
        print(f"AVISO: {len(unexpected)} lunas con captures+cappy no permitidas:")
        for row in unexpected[:20]:
            print(" ", row)
    elif not allowed_both:
        print("OK: ninguna luna con captures+cappy a la vez.")

    with_action = sum(1 for e in reg2.values() if set(e["tags"]) & TAG_ACTION)
    no_extra = sum(1 for e in reg2.values() if not e["tags"])
    print(f"Con captures/cappy/mario: {with_action}")
    print(f"Sin tags extra (solo reino en CSV): {no_extra}")


if __name__ == "__main__":
    main()
