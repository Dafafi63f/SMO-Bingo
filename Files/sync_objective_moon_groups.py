"""Grupos tematicos derivados de objetivos Combined + lunas asociadas.

Fuente unica: OBJECTIVE_MOON_GROUP_SPECS.
sync_objective_moon_groups() crea/actualiza bingo_groups.json.

Existencia de grupo: >= MIN_MOONS lunas O >=1 objetivo Combined relacionado.
internal=True: solo tags/grupos de catalogo (no superficie bingo/linea).

Ids: preferir `reino_tema` si el grupo es de un solo reino
(p. ej. metro_rc_car). La tag de luna es el sufijo tras strip
(strip_kingdom_prefix_from_id). Si id y tag son el mismo nombre y se
renombra el concepto, actualizar ambos (grupo + tag).
"""
from __future__ import annotations

import re
from typing import Any

from catalog_lib import (
    BINGO_GROUPS_PATH,
    GROUP_MIN_MOONS,
    KINGDOM_COLUMNS,
    UMBRELLA_MOON_TAGS,
    assign_bingo_group_orden,
    build_matrix_moon_registry,
    clear_group_context_tags_cache,
    finalize_bingo_groups_doc,
    group_objectives,
    load_bingo_groups,
    load_catalog,
    load_combined_objectives_by_goal,
    load_wiki_moon_meta,
    normalize_bingo_group,
    objective_ref_from_combined,
    wiki_moon_in_scope,
    write_catalog_json,
)

MIN_MOONS = GROUP_MIN_MOONS

GOAL_MINI_ROCKET_MOONS = "{{X}} Mini Rocket Moons"
GOAL_BEANSTALK_MOONS = "{{X}} Beanstalk Moons"

# Ids retirados (fusionados / fuera de norma).
RETIRED_OBJECTIVE_GROUP_IDS: frozenset[str] = frozenset(
    {
        "luncheon_golden_turnip",  # → seeds (via golden_turnip)
        "golden_turnip",  # → seeds (goal Luncheon Golden Turnip se mantiene)
        "wooded_seed_moon",  # → seeds (Special Seed)
        "koopa_freerunning",  # carreras fuera del Combined (postgame cups)
        "picture_match",  # Cloud/Mushroom fuera de alcance
        "sand_bullet_bill",  # → bullet_bill (multireino)
        "wooded_sherm",  # → sherm (multireino)
        "uproot",  # → wooded_uproot (+ seaside_uproot)
        "luncheon_hammer_bro",  # → hammer_bro
        "fire_hammer_bro",  # → fire_bro + hammer_bro (goals separadas)
        "talkatoo_moons",  # Talkatoo Moons retirado; solo hablar (como Moon Rock)
        "wooded_coin_coffer",  # → seeds (Coin Coffer / Special Seed)
        "metro_sewer",  # → metro_manhole (4 lunas: ambos manholes)
        "special_capture_moons",  # Capture fijas → captures / goals
        "special_captures",  # vacío legado; Capture fijas en captures
        "bowser_statue",  # Bowser Statue Moon (sin grupo; evita strip bowser_)
        "sub_area_access",  # → transport
        "lake_cheep_cheep",  # → cheep_cheep (multireino)
        "seaside_cheep_cheep",  # → cheep_cheep (multireino)
        "style_sisters",  # post-Bowser (fuera de alcance)
        # musicos metro#2–#5: tag npc vía npc_moons.tag_only_moons
        "ndc_festival_band",
        "totals",  # → totales (Total Moons/Checkpoints/Regionals/Multi/Story)
        "shop",  # → shopping
        "checkpoint",  # → checkpoints (id bingo_lineas)
        "regionals",  # → regionalcoins
        "moon_rock",  # → moonrock
        "captain_toad",  # → captaintoad
        "story_moon",  # → storymoons
        "sub_area",  # → subarea
        "kingdommoons",  # totales de reino viven en grupos kingdom
        "moontype",  # tipos concretos viven en grupos tematicos
        "jump_rope",  # → metro_minigames
        "volleyball",  # goal en minigame; sin grupo propio
        "rc_car",  # → metro_rc_car
        "misc",  # levers/P-Switches → story_moon
        "snow_rocket_flower",  # Cold Water Dash → solo sub_area+cappy (sin goal)
        # snow_bitefrost: Hollow Crevasse reactivado (goal + tag)
        # Singulares 1 luna: goal Combined OK; sin grupo/tag propio
        "moon_bowser_statue",
        "festival",  # Metro Festival Moon (#36 8-bit)
        # banzai_bill: reactivado (#11+#13)
        "parabones",  # Moon Parabones Moon
        # sheep: grupo propio (Sand Sheep Moon → tag fauna)
        "sub_area_hybrid_2d",  # → hybrid_2d
        # fire_piranha_plant: reactivado (#32 + Magma Swamp #37+#38)
        "special_seeds",  # lunas Special Seed viven en seeds
        "miscellaneous",  # goals viven en 8bit/seeds/captures/sand_jaxi/…
    }
)

# id → spec.
# - goals / goal: texto(s) Combined
# - line_category: id de Catalog/bingo_lineas.json → objectives de esa cat
#   (fuente de verdad para alineacion board/line; se fusiona con goals/)
# - moons / name_patterns: lunas
# - capture: si hay captura, resolve_moons excluye story/multi salvo
#   include_story_moons (excepciones: sand#2, snow#1/#3/#5, …)
# - include_story_moons: [(kingdom, moon), ...] que sí cuentan pese a story/multi
# - internal: no bingo/linea; solo tags/grupos internos
# - moon_tag: tag en lunas si ≠ id (paraguas fauna/flora → umbrella)
# - aggregate_moon_tag: une lunas (+ goals) de grupos con ese moon_tag
# - preserve_moons: si no hay moons/patrones, conserva moons[] ya en bingo_groups
# - goals_only: solo objectives[] (moons/lista vacios). Para cats con pool
#   enorme ya cubierto en reinos/grupos concretos (evita duplicar JSON).
# - note: texto _note en el grupo
OBJECTIVE_MOON_GROUP_SPECS: dict[str, dict[str, Any]] = {
    # --- lost ---
    "lost_tropical_wiggler": {
        "goal": "{{X}} Lost Tropical Wiggler Moons",
        "kingdom": "lost",
        "capture": "Tropical Wiggler",
        "moons": [
            ("lost", 4),
            ("lost", 5),
            ("lost", 15),
            ("lost", 16),
            ("lost", 17),
            ("lost", 20),
        ],
    },
    "lost_butterfly": {
        "goal": "{{X}} Lost Butterfly Moons",
        "kingdom": "lost",
        "moons": [
            ("lost", 9),  # On the Mountain Road (enjambre → GP)
            ("lost", 10),  # A Propeller Pillar's Secret (enjambre → GP)
            ("lost", 12),  # A Butterfly's Treasure (Cappy)
        ],
        "moon_tag": "fauna",
        "note": (
            "Fauna ≥3 → solo butterfly. #9/#10: mariposas como pista, "
            "ground pound. #12: mariposa brillante + Cappy."
        ),
    },
    "lost_trapeetle": {
        "goal": "{{X}} Lost Trapeetle Moon[[s]]",
        "kingdom": "lost",
        "moons": [
            ("lost", 11),  # Wrecked Rock Block → trapeetle+blocks
            ("lost", 19),  # The Caged Gold → trapeetle+cages
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag trapeetle (solo cappy + blocks/cages). "
            "#11 bloque + #19 jaula. Sin lost#13 (Caught Hopping = rabbit)."
        ),
    },
    # --- sand ---
    "sand_jaxi": {
        "goals": [
            "{{X}} Sand Jaxi Moons",
            "{{X}} Sand Jaxi Regional Coins",
            "Call Jaxi from {{X}} Stand[[s]]",
        ],
        "kingdom": "sand",
        "name_patterns": [r"\bjaxi\b"],
        "moons": [
            ("sand", 14),  # On the Statue's Tail (estatua Jaxi en pirámide)
        ],
        "moon_tag": "jaxi",
        "note": (
            "Tag jaxi (6 lunas). #14 estatua en pirámide + name_patterns. "
            "Call Jaxi Stands lista ×9. purchase_site: Town (noche) + Jaxi Ruins (día). "
            "1ª compra (30 monedas, una vez) = ese stand solo (no doble compra+llamada); "
            "no hace falta comprar en el otro sitio. Rango moons [2, 4, 6]. "
            "Regional: 12 purple (veneno 4 + cueva Jaxi Ruins 8)."
        ),
    },
    "sand_moe_eye": {
        "goal": "{{X}} Sand Moe-Eye Moons",
        "kingdom": "sand",
        "capture": "Moe-Eye",
        "moons": [
            ("sand", 29),  # TC2: llave/P-Switch + Moe-Eye en el camino
            ("sand", 54),  # Invisible Maze
            ("sand", 55),  # Skull Sign in the Transparent Maze
        ],
        # n=3 + goal propia, pero sin tag moe_eye (basta captures): excepción
        # documentada en CAPTURE_NO_CONCRETE_TAGS / apply_moon_tag=False.
        "apply_moon_tag": False,
        "note": (
            "TC2 (#29) + Invisible Maze (#54+#55). Sin tag moe_eye "
            "(n=3 con goal; basta captures; presupuesto de tags en "
            "sub_area/key/switch/timer). "
            "Sin #2 Moon Shards (story; captura Moe-Eye en habitat pero "
            "fuera del pool Combined). "
            "Sin goal regional (habitat/Invisible Maze siguen en Sand Regional)."
        ),
    },
    "sand_birds": {
        "goal": "{{X}} Sand Bird Moons",
        "kingdom": "sand",
        "moons": [("sand", 16), ("sand", 21), ("sand", 22)],
        "moon_tag": "fauna",
        "note": "Fauna ≥3 → solo birds. Rango [2, 3] (n=3).",
    },
    "cactus_tree": {
        "goal": "{{X}} Cactus/Tree Moons",
        "moons": [
            ("sand", 36),   # Five Cactuses: captures+cactus_tree
            ("sand", 40),   # Wandering Cactus: captures+cactus_tree
            ("wooded", 34),  # Moving Tree: captures+cactus_tree
        ],
        "moon_tag": "flora",
        "note": (
            "n=3 → cactus_tree (sin flora; normalize también quita flora "
            "si hay captures/PLANT_CAPTURE_TAGS). Las 3 = captures+cactus_tree."
        ),
    },
    "seeds": {
        "goals": [
            "{{X}} Seed Moon (No Time Travel)",
            "{{X}} Seeds Planted",
            "{{X}} Special Seed Moon[[s]]",
            "{{X}} Luncheon Golden Turnip Moon[[s]]",
        ],
        "moons": [
            ("sand", 25),
            ("sand", 26),
            ("sand", 27),
            ("lake", 9),
            ("metro", 21),
            ("metro", 22),
            ("metro", 23),
            ("seaside", 23),
            ("seaside", 24),
            ("seaside", 25),
            ("seaside", 26),
            ("wooded", 33),
            ("luncheon", 15),
            ("luncheon", 16),
            ("luncheon", 17),
        ],
        "note": (
            "Orden: NTT (1) → Seeds Planted → Special Seed → Golden Turnip. "
            "Pool total 15. NTT y Seeds Planted = 9 macetas (3 sand + 3 metro "
            "+ 3 seaside #23–#25). Special Seed = lake#9 + wooded#33 + "
            "seaside#26 (sin grupo propio; basta tag seeds). "
            "Turnip = #15–#17. Tag seeds."
        ),
    },
    "sand_tostarena": {
        "goals": [
            "{{X}} Sand Tostarena Moons",
            "{{X}} Sand Tostarena Regional Coins",
        ],
        "kingdom": "sand",
        "moons": [
            ("sand", 5),   # Overlooking the Desert Town
            ("sand", 15),  # Hang Your Hat on the Fountain
            ("sand", 21),  # Bird Traveling the Desert (tostarena, no oasis)
            ("sand", 25),  # Desert Gardening: Plaza Seed
            ("sand", 26),  # Desert Gardening: Ruins Seed (macetas del pueblo)
            ("sand", 27),  # Desert Gardening: Seed on the Cliff (macetas del pueblo)
            ("sand", 31),  # Found in the Sand! Good Dog! (Crazy Cap)
            ("sand", 42),  # Shopping in Tostarena
            ("sand", 43),  # Employees Only (outfit / tras tienda)
            ("sand", 44),  # Sand Kingdom Slots
            ("sand", 52),  # A Rumble from the Sandy Floor (pipe del pueblo; lurker_rumble)
            ("sand", 53),  # Dancing with New Friends (outfit)
            ("sand", 60),  # Strange Neighborhood
            ("sand", 61),  # Above a Strange Neighborhood
        ],
        "moon_tag": "tostarena",
        "note": (
            "Lunas del pueblo Tostarena (sin oasis/ruinas/piramide). "
            "Incluye #21 Bird Traveling the Desert. Tag tostarena. "
            "Regional: 29 purple coins (pueblo 24 + Strange Neighborhood 5)."
        ),
    },
    "sand_oasis": {
        "goal": "{{X}} Sand Oasis Moons",
        "kingdom": "sand",
        "moons": [
            ("sand", 16),  # Where the Birds Gather
            ("sand", 32),  # Taking Notes: Jump on the Palm
            ("sand", 34),  # Fishing in the Oasis
            ("sand", 37),  # You're Quite a Catch, Captain Toad!
            ("sand", 38),  # Jaxi Reunion! (este del oasis; también jaxi)
            ("sand", 40),  # Wandering Cactus (norte del oasis)
        ],
        "moon_tag": "oasis",
        "note": (
            "Desert Oasis. 6 lunas (sin #21 pájaro → tostarena). "
            "Tag oasis. #38 también sand_jaxi. Rango [3, 6]. "
            "Sin regional; sin Moon Rock #70."
        ),
    },
    "sand_ruins": {
        "goals": [
            "{{X}} Sand Ruins Moons",
            "{{X}} Sand Ruins Regional Coins",
        ],
        "kingdom": "sand",
        "moons": [
            ("sand", 1),   # Atop the Highest Tower
            ("sand", 6),   # Alcove in the Ruins
            ("sand", 7),   # On the Leaning Pillar
            ("sand", 8),   # Hidden Room in the Flowing Sands
            ("sand", 9),   # Secret of the Mural
            ("sand", 11),  # On Top of the Stone Archway
            ("sand", 12),  # From a Crate in the Ruins
            ("sand", 19),  # Bullet Bill Breakthrough
            ("sand", 20),  # Inside a Block Is a Hard Place
            ("sand", 35),  # Love in the Heart of the Desert (Goombette)
        ],
        "moon_tag": "ruins",
        "note": (
            "Ruinas de Tostarena (estructura principal: entrada → torre). "
            "10 lunas: path de ruinas + Goombette. Tag ruins. "
            "Sand Ruins Moons range [4, 6, 8, 10]. "
            "Sin Ice Cave #50 ni sus 4 purple (solo sand_ice; no doble conteo). "
            "Sin semilla #26, Jaxi Ruins, pirámide/templo ni Moe-Eye Habitat. "
            "Regional: 16 purple coins (entrada/8-bits 10 + Sphynx 3 + "
            "plataformas Round Tower→Moe-Eye 3). "
            "Sin Jaxi Ruins / oasis / pirámide / Underground Temple / Moe-Eye."
        ),
    },
    "sand_pyramid": {
        "goal": "{{X}} Sand Pyramid Moons",
        "kingdom": "sand",
        "moons": [
            ("sand", 3),   # Showdown on the Inverted Pyramid (multi)
            ("sand", 10),  # Secret of the Inverted Mural
            ("sand", 14),  # On the Statue's Tail (también jaxi)
            ("sand", 23),  # The Lurker Under the Stone
            ("sand", 39),  # Welcome Back, Jaxi! (también jaxi)
            ("sand", 46),  # Hidden Room in the Inverted Pyramid
        ],
        "moon_tag": "pyramid",
        "note": (
            "Pirámide invertida (estructura + techo). 6 lunas; #3 multi "
            "cuenta 1 (physical). #14+#39 también sand_jaxi. "
            "Sin #18 Luggage / #33 Sheep (base/dunas) ni templo ice. "
            "Sin goal regional (8-bit/techo siguen en Sand Regional / 8-Bit Regional)."
        ),
    },
    # --- wooded ---
    "nut": {
        "goal": "{{X}} Wooded Nut Moons",
        "kingdom": "wooded",
        "name_patterns": [r"\bnut\b"],
        "moons": [
            ("wooded", 10),  # Atop the Tall Tree (nuez; nombre sin "nut")
            ("wooded", 11),  # Tucked Away Inside the Tunnel (idem)
            ("wooded", 12),  # Over the Cliff's Edge (idem)
            ("wooded", 26),  # Spinning-Platforms Treasure (idem)
        ],
        "note": (
            "Wooded nuts. Fuera del paraguas flora. Incluye #10/#11/#12/#26 "
            "(nombre sin 'nut') ademas de name_patterns. "
            "Uproot en #10/#11/#13/#14/#15/#16/#24; resto nut sin captura."
        ),
    },
    "wooded_flower_road": {
        "goal": "{{X}} Wooded Flower Road Moons",
        "kingdom": "wooded",
        "moons": [("wooded", 43), ("wooded", 44)],
        "moon_tag": "flora",
        "note": (
            "Flower Road (enredadera). n=2 <3 → solo flora (sin tag flower_road). "
            "Goal/grupo propio; sin transport."
        ),
    },
    "deep_woods": {
        "goals": [
            "{{X}} Deep Woods Moons",
            "{{X}} Deep Woods Regional Coins",
        ],
        "kingdom": "wooded",
        "moons": [
            ("wooded", 28),  # The Nut That Grew on the Tall Tree
            ("wooded", 29),  # Fire in the Deep Woods
            ("wooded", 30),  # Past the Peculiar Pipes
            ("wooded", 31),  # By the Babbling Brook in the Deep Woods
            ("wooded", 32),  # The Hard Rock in the Deep Woods
            ("wooded", 33),  # A Treasure Made of Coins
            ("wooded", 34),  # Beneath the Roots of the Moving Tree
            ("wooded", 35),  # Deep Woods Treasure Trap
            ("wooded", 36),  # Exploring for Treasure
        ],
        "moon_tag": "deep_woods",
        "note": (
            "Deep Woods + subzonas Treasure Trap (#35) y Treasure Vault (#36). "
            "smo.wiki: 7 lunas en el level + 2 en sub-worlds = 9. "
            "Tag deep_woods. Regional: 9 purple coins (3 clusters × 3)."
        ),
    },
    "sand_ice": {
        "goals": [
            "{{X}} Sand Ice Moon[[s]]",
            "{{X}} Sand Ice Regional Coins",
        ],
        "kingdom": "sand",
        "moons": [
            ("sand", 47),  # Underground Treasure Chest (templo / solo ice)
            ("sand", 48),  # Goomba Tower Assembly (templo / solo ice)
            ("sand", 49),  # Under the Mummy's Curse (bajo pirámide / solo ice)
            ("sand", 50),  # Ice Cave Treasure (solo ice; no sand_ruins)
        ],
        "moon_tag": "ice",
        "note": (
            "Hielo Sand: Ice Cave (ruinas) + Underground Temple / Deepest "
            "(bajo pirámide). Tag ice. Templo (#47–#49) antes del par Ice "
            "Cave → rango moons [1, 3]. "
            "#50 Ice Cave solo ice (no sand_ruins); #47–#49 solo ice. "
            "Regional: 11 purple (Ice Cave 4 + Underground Temple 7). "
            "Ice Cave coins solo sand_ice (no Sand Ruins Regional); "
            "templo solo ice. "
            "Sin sand#4 The Hole in the Desert (story/multi)."
        ),
    },
    "wooded_pipe": {
        "goal": "{{X}} Wooded Pipe Moons",
        "kingdom": "wooded",
        "moons": [
            ("wooded", 30),  # Past the Peculiar Pipes (Deep Woods)
            ("wooded", 39),  # Flooding Pipeway
            ("wooded", 40),  # Flooding Pipeway Ceiling Secret
        ],
        "note": (
            "Pipes Wooded: Deep Woods #30 + sub_area Flooding Pipeway (#39+#40). "
            "Tag pipe; sin transport (el pipe es contenido, no acceso)."
        ),
    },
    "bloom_flower": {
        "goal": "{{X}} Bloom Flower Moon[[s]]",
        "moons": [
            ("wooded", 27),  # Make the Secret Flower Field Bloom
            ("lost", 14),    # Cave Gardening
        ],
        "moon_tag": "flora",
        "note": (
            "Florecer brotes con Cappy (spin). "
            "No Path/Defend (historia/boss). <3 → solo flora. "
            "En paraguas Flora Moons / Nature."
        ),
    },
    # --- metro ---
    "metro_girder": {
        "goal": "{{X}} Metro Girder Moon[[s]]",
        "kingdom": "metro",
        "moons": [
            ("metro", 8),   # Inside an Iron Girder
            ("metro", 9),   # Swaying in the Breeze (girder oscilante)
            ("metro", 10),  # Girder Sandwich
            ("metro", 13),  # Secret Girder Tunnel!
        ],
        "note": (
            "Vigas Metro: #8/#10/#13 (nombre girder) + #9 Swaying (plataforma girder). "
            "Sin #18/#24/#42 (trash/toad/sherm en viga). "
            "Board/line Combined: lost (tramo Metro noche), no metro."
        ),
    },
    "metro_night": {
        "goals": [
            "{{X}} Metro Night Moons",
            "{{X}} Metro Girder Moon[[s]]",
            "Metro City Hall Moon",
            "Metro Shop Moon",
            "Metro Warp-Painting Moon",
        ],
        "kingdom": "metro",
        "moons": [
            # Noche pre-Mechawiggler + pintura inbound (Secret Path).
            ("metro", 8),   # Inside an Iron Girder
            ("metro", 9),   # Swaying in the Breeze
            ("metro", 10),  # Girder Sandwich
            ("metro", 27),  # Shopping in New Donk City
            ("metro", 34),  # City Hall Lost & Found
            ("metro", 51),  # Secret Path to New Donk City! (pintura; entrada Sand)
        ],
        "note": (
            "Noche pre-Mechawiggler (base #8/#9/#10/#27/#34) + #51 Secret Path. "
            "Sin #1 Pest Problem (multi). Tag night = Metro que cuenta en tramo lost "
            "(board/line lost; Cloud+Lost+Metro noche). "
            "Girder #13 mid_story también lost/m. Kingdom tag sigue metro."
        ),
    },
    "metro_trash": {
        "goal": "{{X}} Metro Trash Moon[[s]]",
        "kingdom": "metro",
        "name_patterns": [r"trash|garbage|scrap"],
    },
    "metro_manhole": {
        "goal": "{{X}} Metro Manhole Moons",
        "kingdom": "metro",
        "capture": "Manhole",
        "moons": [
            ("metro", 35),  # Sewer Treasure (Underground Power Plant; no en Sub-Area Moons)
            ("metro", 43),  # Inside the Rotating Maze
            ("metro", 44),  # Outside the Rotating Maze
        ],
        "moon_tag": "manhole",
        "note": (
            "Acceso manhole → tag manhole. Goal: #35+#43+#44. "
            "#43+#44 Rotating Maze llevan sub_area (grupo); "
            "#35 Sewer Treasure no (como bowser#26 spark_pylon). "
            "metro#6 Powering Up (story) fuera: no cuenta → story_moon (sin manhole). "
            "#35 no cuenta en {{X}} Sub-Area Moons (guía)."
        ),
    },
    "metro_taxi": {
        "goal": "{{X}} Metro Taxi Moons",
        "kingdom": "metro",
        "capture": "Taxi",
        "moons": [
            ("metro", 41),  # Moon Shards Under Siege
            ("metro", 42),  # Sharpshooting Under Siege
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag taxi; paraguas captures + sub_area (+ sherm). "
            "Acceso taxi → Under Siege. Contenido = sherm."
        ),
    },
    "mini_rocket": {
        "goal": GOAL_MINI_ROCKET_MOONS,
        "capture": "Mini Rocket",
        "moons": [
            ("sand", 60),    # Strange Neighborhood
            ("sand", 61),    # Above a Strange Neighborhood
            ("wooded", 41),  # Wandering in the Fog
            ("wooded", 42),  # Nut Hidden in the Fog
            ("metro", 45),   # Hanging from a High-Rise
            ("metro", 46),   # Vaulting Up a High-Rise
            ("seaside", 43),  # Wading in the Cloud Sea
            ("seaside", 44),  # Sunken Treasure in the Cloud Sea
        ],
        "moon_tag": "mini_rocket",
        "note": (
            "Acceso Mini Rocket → tag mini_rocket (sin sub_area encima). "
            "Sand Strange Neighborhood + Wooded Fog + Metro High-Rise + "
            "Seaside Cloud Sea (8)."
        ),
    },
    "beanstalk": {
        "goal": GOAL_BEANSTALK_MOONS,
        "moons": [
            # Wooded Cloud Walking
            ("wooded", 47),  # Walking on Clouds
            ("wooded", 48),  # Above the Clouds
            # Snow Cloud Spinning (semilla → enredadera)
            ("snow", 31),  # Spinning Above the Clouds
            ("snow", 32),  # High-Altitude Spinning
            # Bowser Cloud Dashing (semilla → enredadera)
            ("bowser", 37),  # Dashing Above the Clouds
            ("bowser", 38),  # Dashing Through the Clouds
        ],
        "moon_tag": "beanstalk",
        "note": (
            "Enredadera/nubes → tag beanstalk (sin sub_area encima). "
            "Wooded Cloud Walking (#47+#48 tambien uproot) + Snow Cloud "
            "Spinning + Bowser Cloud Dashing."
        ),
    },
    "rocket_flower": {
        "goal": "{{X}} Rocket Flower Moons",
        "moons": [
            ("seaside", 31),  # Taking Notes: Ocean Surface Dash
            ("snow", 24),     # Dashing Over Cold Water!
            ("snow", 25),     # Dashing Above and Beyond!
            ("bowser", 37),   # Dashing Above the Clouds (semilla + RF)
            ("bowser", 38),   # Dashing Through the Clouds
            ("moon", 6),      # Cliffside Treasure Chest (sella umbral 6)
        ],
        "moon_tag": "flora",
        "note": (
            "Rocket Flower (correr/dash). Seaside #31 + Snow #24+#25 + "
            "Bowser Cloud Dashing #37+#38 + Moon #6 (último: sella range 6). "
            "n=6 → tag rocket_flower (sin flora ni cappy en luna). "
            "Fuera del grupo/tag cappy (ROCKET_FLOWER_MOONS). "
            "En paraguas Flora/Nature. Rango propio [2, 4, 6]."
        ),
    },
    "metro_motor_scooter": {
        "goal": "{{X}} Metro Motor Scooter Moon[[s]]",
        "kingdom": "metro",
        "moons": [
            ("metro", 20),  # Timer Challenge 2 (scooter + llave)
            ("metro", 25),  # Free Parking: Rooftop Hop
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag motor_scooter. "
            "Scooter como contenido de goal: TC2 (#20) + Free Parking (#25); "
            "sin tag captures (scooter no es captura de lista). "
            "Escape (#49+#50): no cuentan → t_rex/captures. "
            "#60 Leap of Faith = Moon Rock (fuera)."
        ),
    },
    "metro_minigames": {
        "goal": "{{X}} Metro Minigame Moon[[s]]",
        "kingdom": "metro",
        "moon_tag": "minigame",
        "moons": [
            ("metro", 28),  # Slots
            ("metro", 29),  # Jump-Rope Hero
            ("metro", 30),  # Jump-Rope Genius
            ("metro", 32),  # RC Car Pro!
        ],
        "note": (
            "4 minijuegos Metro. Tag minigame (no 'minigames'). "
            "Sin #31 Remotely Captured Car (tutorial captura). "
            "Goal tambien en grupo minigame."
        ),
    },
    "metro_rc_car": {
        "goal": "{{X}} Metro RC Car Moons",
        "kingdom": "metro",
        "capture": "RC Car",
        "moons": [("metro", 31), ("metro", 32)],
        "note": "#31 Remotely Captured Car + #32 RC Car Pro!. Tambien captures.",
    },
    "pokio": {
        "goal": "{{X}} Bowser's Pokio Moons",
        "kingdom": "bowser",
        "capture": "Pokio",
        "moons": [
            ("bowser", 5),
            ("bowser", 6),
            ("bowser", 9),   # Past the Moving Wall
            ("bowser", 33),
            ("bowser", 34),
        ],
        "note": (
            "Pokio overworld (#5/#6/#9) + Spinning Tower (#33+#34). "
            "Holes (#21–#23) → grupo pokio_hole (misma captura Pokio; "
            "2 goals en capturas_lunas). "
            "#2/#4 story/multi: captures (Pokio en camino); no cuentan en este goal. "
            "#14 bloque = stairface_ogre. #26 Behind Bars → solo spark_pylon."
        ),
    },
    "stairface_ogre": {
        "goal": "{{X}} Bowser's Stairface Ogre Moon[[s]]",
        "kingdom": "bowser",
        "moons": [
            ("bowser", 1),   # Infiltrate Bowser's Castle! (story)
            ("bowser", 14),  # Inside a Block in the Castle (ogro rompe bloque)
            ("bowser", 16),  # Exterminate the Ogres!
        ],
        "apply_moon_tag": False,
        "note": (
            "Paraguas blocks (#14) / critter (#16) / story (#1 Infiltrate). "
            "Stairface Ogre: #1 story + #14 (rompe bloque) + #16 (derrotar 3). "
            "Rango [1, 2, 3]. #33 ogro solo abre puerta → Pokio."
        ),
    },
    "pokio_hole": {
        "goal": "{{X}} Pokio Hole Moons",
        "kingdom": "bowser",
        "capture": "Pokio",
        "moon_tag": "pokio_hole",
        "moons": [
            ("bowser", 21),  # Poking Your Nose in the Plaster Wall
            ("bowser", 22),  # Poking the Turret Wall
            ("bowser", 23),  # Poking Your Nose by the Great Gate
        ],
        "note": (
            "Lunas en muros agujereados (Pokio Hole). Misma captura wiki Pokio "
            "que Bowser's Pokio Moons (unica captura con 2 goals)."
        ),
    },
    "spark_pylon": {
        "goal": "{{X}} Spark Pylon Moons",
        "capture": "Spark Pylon",
        "moons": [
            ("cap", 8),    # Push-Block Peril
            ("cap", 9),    # Hidden Among the Push-Blocks
            ("metro", 39),  # Rewiring the Neighborhood
            ("metro", 40),  # Off the Beaten Wire
            ("bowser", 26),  # Found Behind Bars! (pylon → celda)
        ],
        "moon_tag": "spark_pylon",
        "note": (
            "Cap Push-Block (#8+#9) + Metro Wire (#39+#40) + bowser#26 "
            "Behind Bars (pylon a la celda; sin Pokio). Rango [2, 4]. "
            "Push-Block/Wire: sub_area; #26 no (overworld). "
            "metro#14 (basura) = pylon solo acceso → fuera."
        ),
    },
    "swinging_pole": {
        "goal": "{{X}} Swinging Pole Moon[[s]]",
        "capture": "Pole",
        "moons": [
            ("metro", 45),  # Hanging from a High-Rise
            ("metro", 46),  # Vaulting Up a High-Rise
            ("wooded", 37),  # Timer Challenge 1 (swing poles)
        ],
        "note": (
            "Captura Pole (transporte wiki). Poles: Metro High-Rise (#45+#46) + "
            "wooded#37 TC1 (antes del par → rango [1, 3]). Sin City Hall (#34); "
            "sin #38 Crowd; sin Bullet Billding."
        ),
    },
    # --- luncheon ---
    # golden_turnip → seeds (goal {{X}} Luncheon Golden Turnip Moon[[s]] se mantiene)
    "fire_bro": {
        "goal": "{{X}} Fire Bro Moon[[s]]",
        "capture": "Fire Bro",
        "moons": [
            ("wooded", 19),  # Fire in the Cave
            ("luncheon", 31),  # Light the Two Flames
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag fire_bro; paraguas captures (Unique Captures sí). "
            "Fire Bro: wooded#19 + luncheon#31. Rango [1, 2]. "
            "Sin #14 (lava_bubble). Sin #50/#64."
        ),
    },
    "hammer_bro": {
        "goal": "{{X}} Hammer Bro Moons",
        "capture": "Hammer Bro",
        "kingdom": "luncheon",
        "moons": [
            ("luncheon", 17),  # Golden Turnip Recipe 3 (queso)
            ("luncheon", 30),  # Treasure Beneath the Cheese Rocks
            ("luncheon", 43),  # Excavate 'n' Search the Cheese Rocks
            ("luncheon", 44),  # Climb the Cheese Rocks
        ],
        "moon_tag": "hammer_bro",
        "note": (
            "Hammer Bro Luncheon (queso). Rango [2, 3]: pool 4 lunas "
            "(#17, #30, #43+#44). Sin #2 Under the Cheese Rocks (story). "
            "Sin Recipe 1/2."
        ),
    },
    "bullet_bill": {
        "goal": "{{X}} Bullet Bill Moons",
        "capture": "Bullet Bill",
        "moons": [
            ("sand", 56),   # The Bullet Bill Maze: Break Through!
            ("sand", 57),   # The Bullet Bill Maze: Side Path
            ("metro", 47),  # Bullet Billding
            ("metro", 48),  # One Man's Trash...
        ],
        "tag_only_moons": [
            ("sand", 19),  # Bullet Bill Breakthrough
            ("sand", 20),  # Inside a Block Is a Hard Place
            ("sand", 47),  # Underground Treasure Chest
        ],
        "moon_tag": "bullet_bill",
        "note": (
            "Goal: solo subáreas BB Maze (sand#56+#57) + Bullet Billding "
            "(metro#47+#48). Rango [2, 4]. Sand#19/#20/#47: tag_only. "
            "sand#7/#11 quedan como Mario sin Bullet Bill."
        ),
    },
    "goomba": {
        "goal": "{{X}} Goomba Moon[[s]]",
        "capture": "Goomba",
        "moons": [
            ("sand", 35),      # Love in the Heart of the Desert
            ("sand", 48),      # Goomba Tower Assembly
            ("wooded", 21),    # Love in the Forest Ruins
            ("wooded", 44),    # Flower Road Reach
            ("snow", 18),      # Ice-Dodging Goomba Stack
            ("seaside", 32),   # Love by the Seaside
            ("luncheon", 24),  # Love Above the Lava
            ("bowser", 19),    # Stack Up Above the Wall
        ],
        "note": (
            "Captura Goomba multireino. Snow: solo #18 en este pool; "
            "#1 Icicle Barrier → {{X}} Snow Goomba Moons (junto a #18). "
            "Wooded: Love + Flower Road Reach (#43 carrera sin Goomba). "
            "#48 Stacked-Up Ice Climb = Moon Rock."
        ),
    },
    "snow_goomba": {
        "goal": "{{X}} Snow Goomba Moons",
        "kingdom": "snow",
        "capture": "Goomba",
        "moons": [
            ("snow", 1),   # The Icicle Barrier (historia; excepción)
            ("snow", 18),  # Ice-Dodging Goomba Stack (tambien Goomba Moon[[s]])
        ],
        "include_story_moons": [("snow", 1)],
        "note": (
            "Icicle Cavern: ambas captures+goomba. Rango fijo [2]. "
            "#1 story no cuenta en {{X}} Goomba Moon[[s]]; sí en este goal."
        ),
    },
    "sherm": {
        "goal": "{{X}} Sherm Moons",
        "capture": "Sherm",
        "moons": [
            ("wooded", 5),
            ("wooded", 22),
            ("wooded", 45),
            ("wooded", 46),
            ("metro", 41),
            ("metro", 42),
        ],
        "note": (
            "Captura multireino Sherm (Wooded+Metro). "
            "Sin wooded#3 / metro#1 (story). Rango [2, 4, 6] (n=6)."
        ),
    },
    "wooded_uproot": {
        "goal": "{{X}} Wooded Uproot Moons",
        "capture": "Uproot",
        "kingdom": "wooded",
        "moons": [
            ("wooded", 10),  # Atop the Tall Tree (nut)
            ("wooded", 11),  # Tucked Away Inside the Tunnel (nut)
            ("wooded", 13),  # The Nut 'Round the Corner
            ("wooded", 14),  # Climb the Cliff to Get the Nut
            ("wooded", 15),  # The Nut in the Red Maze
            ("wooded", 16),  # The Nut at the Dead End
            ("wooded", 24),  # Nut Planted in the Tower
            ("wooded", 25),  # Stretching Your Legs
            ("wooded", 47),  # Walking on Clouds (Cloud Walking + Uproot)
            ("wooded", 48),  # Above the Clouds (idem)
        ],
        "moon_tag": "uproot",
        "note": (
            "Uproot Wooded (10). Sin #4 multi. Nut∩uproot: "
            "#10/#11/#13/#14/#15/#16/#24. Torre #24+#25. Cloud Walking "
            "#47+#48 (+ beanstalk). Seaside Stretch → seaside_uproot."
        ),
    },
    "seaside_uproot": {
        "goal": "{{X}} Seaside Uproot Moons",
        "kingdom": "seaside",
        "capture": "Uproot",
        "moons": [
            ("seaside", 47),  # Hurry and Stretch
            ("seaside", 48),  # Stretch on the Side Path
        ],
        "moon_tag": "uproot",
        "note": (
            "Subárea Stretch Seaside (#47+#48). Goal propia; tag uproot. "
            "Rango fijo [2]. No cuenta en {{X}} Wooded Uproot Moons."
        ),
    },
    "luncheon_lantern": {
        "goal": "{{X}} Luncheon Lantern Moon[[s]]",
        "kingdom": "luncheon",
        "moons": [
            ("luncheon", 14),  # Light the Lantern on the Small Island
            ("luncheon", 31),  # Light the Two Flames
            ("luncheon", 32),  # Light the Far-Off Lanterns
        ],
        "name_patterns": [r"lantern|flame"],
        "note": (
            "Encender linternas en Luncheon: #14+#31+#32 → rango [1, 2, 3]. "
            "Sin #4 Cascading Magma (story; antorcha al final, sin tag lantern). "
            "#14 lava_bubble; #31 Fire Bro; #32 Fire Piranha (+ Magma Swamp "
            "en fire_piranha_plant). Sin #50 Rooftop."
        ),
    },
    "luncheon_volbonan": {
        "goal": "{{X}} Luncheon Volbonan Moons",
        "kingdom": "luncheon",
        "capture": "Volbonan",
        "moons": [("luncheon", 41), ("luncheon", 42)],
        "note": (
            "Fork Flickin' (sub_area): captura Volbonan. "
            "2 lunas → goal fija [2]; tag captura colapsa a captures (n<3)."
        ),
    },
    "fire_piranha_plant": {
        "goal": "{{X}} Luncheon Fire Piranha Plant Moons",
        "kingdom": "luncheon",
        "capture": "Fire Piranha Plant",
        "moons": [
            ("luncheon", 32),  # Light the Far-Off Lanterns
            ("luncheon", 37),  # Magma Swamp: Floating and Sinking
            ("luncheon", 38),  # Corner of the Magma Swamp
        ],
        "moon_tag": "fire_piranha_plant",
        "note": (
            "Fire Piranha: #32 linternas (mid) + Magma Swamp (#37+#38, base). "
            "Par sub_area antes que #32 → rango [2, 3]. "
            "Sin #50 Rooftop (postgame)."
        ),
    },
    "lava_bubble": {
        "goal": "{{X}} Luncheon Lava Bubble Moons",
        "kingdom": "luncheon",
        "capture": "Lava Bubble",
        "moons": [
            ("luncheon", 8),   # Atop the Jutting Crag
            ("luncheon", 39),  # Magma Narrow Path (sub_area LB)
            ("luncheon", 40),  # Crossing to the Magma (par #39)
        ],
        "tag_only_moons": [
            ("luncheon", 14),  # linterna isla
            ("luncheon", 23),  # Taking Notes: Swimming in Magma
            ("luncheon", 27),  # olla Strong Simmer
            ("luncheon", 28),  # olla Extreme Simmer
            ("luncheon", 36),  # Taking Notes: Big Pot Swim
        ],
        "moon_tag": "lava_bubble",
        "note": (
            "Goal: #8 Jutting Crag + Magma Narrow (#39+#40). Rango [2, 3] "
            "(par sub_area cerca de Meat Plateau, antes/junto a #8). "
            "Olla/notes/linterna (#14/#23/#27/#28/#36): tag_only (captura LB). "
            "Sin #4/#5 story ni Magma Swamp (fire_piranha)."
        ),
    },
    # --- lake ---
    "cheep_cheep": {
        "goal": "{{X}} Cheep Cheep Moons",
        "capture": "Cheep Cheep",
        "moons": [
            ("lake", 16),  # I Met a Lake Cheep Cheep!
            ("lake", 18),  # Let's Go Swimming, Captain Toad!
            ("seaside", 10),  # Underwater Highway Tunnel
            ("seaside", 11),  # Shh! It's a Shortcut!
            ("seaside", 12),  # Gap in the Ocean Trench
            ("seaside", 13),  # Slip Through the Nesting Spot (captura Cheep; obstáculo Maw-Ray)
            ("seaside", 39),  # Looking Back in the Dark Waterway (túnel faro)
        ],
        "tag_only_moons": [
            ("lake", 3),  # Cheep Cheep Crossing = transporte (tag cheep_cheep; no goal)
        ],
        "note": (
            "Cheep Cheep multireino Lake+Seaside (captura pez). lake#3 Crossing = "
            "transporte (tag_only; no Cheep Cheep ni Mario Moons). "
            "Seaside #2/#20/#21 usan Cheep Cheep de acceso (sello/Lurker/cofre). "
            "#13/#39 requieren Cheep Cheep pero el reto es esquivar Maw-Rays → tag maw_ray. "
            "Snow: 0 Moon Get in-scope → Capture Snow Cheep Cheep (special)."
        ),
    },
    "maw_ray": {
        "goal": "{{X}} Seaside Maw-Ray Moon[[s]]",
        "moons": [
            ("seaside", 2),   # The Lighthouse Seal (túnel del faro)
            ("seaside", 13),  # Slip Through the Nesting Spot
            ("seaside", 30),  # Moon Shards in the Sea
            ("seaside", 39),  # Looking Back in the Dark Waterway
        ],
        "moon_tag": "maw_ray",
        "note": (
            "Maw-Ray (anguila gigante / Unagi): enemigo, no captura. "
            "Distinto de Cheep Cheep (pez). Solo Seaside: sello faro, nido, shards, túnel."
        ),
    },
    "komboo": {
        "goal": "{{X}} Seaside Komboo Moons",
        "moons": [
            ("seaside", 16),  # Under a Dangerous Ceiling
            ("seaside", 17),  # What the Waves Left Behind
            ("seaside", 19),  # Bubblaine Northern Reaches
            ("seaside", 21),  # Glass Palace Treasure Chest (túnel de algas)
        ],
        "moon_tag": "komboo",
        "note": (
            "Komboo (algas enemigas): no captura; derrotar con Cappy/spin. "
            "Solo Seaside. Distinto de Gushen (captura burbuja). "
            "Lake no tiene Komboo. Rango [2, 4] (n=4)."
        ),
    },
    # --- seaside ---
    "gushen": {
        "goal": "{{X}} Seaside Gushen Moons",
        "kingdom": "seaside",
        "capture": "Gushen",
        "moons": [
            ("seaside", 6),   # On the Cliff Overlooking the Beach
            ("seaside", 7),   # Ride the Jetstream
            ("seaside", 26),  # Ocean Trench Seed (Gushen acelera; special seed)
            ("seaside", 34),  # Good Job, Captain Toad!
            ("seaside", 45),  # Fly Through the Narrow Valley
            ("seaside", 46),  # Treasure Chest in the Narrow Valley
        ],
        "note": (
            "Gushen (captura burbuja), no Komboo (algas enemigas → tag komboo). "
            "Sin sellos #1/#3/#5 (story/multi). "
            "Incluye #26 Ocean Trench Seed (special; Gushen acelera). "
            "Sin Sea Gardening #23–#25 (macetas normales). "
            "Sin #15 Dorrie/#31 Notes (alt opcional). Rango [2, 4, 6]."
        ),
    },
    # --- snow ---
    "shiverian_racer": {
        "goal": "{{X}} Snow Shiverian Racer Moon[[s]]",
        "kingdom": "snow",
        "capture": "Shiverian Racer",
        "moons": [
            ("snow", 5),   # The Bound Bowl Grand Prix (multi; excepción)
            ("snow", 23),  # Snowline Circuit Class S
        ],
        "include_story_moons": [("snow", 5)],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag shiverian_racer; paraguas captures + shiveria. "
            "#5 Bound Bowl (multi, sí cuenta) + #23 Class S. "
            "También Snow Multi-Moon y pool Minigame."
        ),
    },
    "snow_shiveria": {
        "goals": [
            "{{X}} Snow Shiveria Moons",
            "{{X}} Snow Shiveria Regional Coins",
            # Goals cuyo pool de lunas cae entero (o casi) en este perímetro.
            "{{X}} Snow Story Moons",
            "{{X}} Snow Bitefrost Moons",
            "{{X}} Snow Goomba Moons",
            "{{X}} Snow Outfit Door Moons",
            "{{X}} Snow Shiverian Racer Moon[[s]]",
            "Snow Boxer Shorts Moon",
            "Snow Hint Art Moon",
            "Snow Multi-Moon",
            "Snow Shop Moon",
        ],
        "kingdom": "snow",
        "moons": [
            # Agujero: 4 barreras story + Bound Bowl + extras cavernas + pueblo +
            # circuito + Cold Room (17).
            ("snow", 1),   # The Icicle Barrier
            ("snow", 2),   # The Ice Wall Barrier
            ("snow", 3),   # The Gusty Barrier
            ("snow", 4),   # The Snowy Mountain Barrier
            ("snow", 5),   # The Bound Bowl Grand Prix (multi)
            ("snow", 6),   # Entrance to Shiveria
            ("snow", 7),   # Behind Snowy Mountain
            ("snow", 8),   # Shining in the Snow in Town
            ("snow", 9),   # Atop a Blustery Arch
            ("snow", 11),  # The Shiverian Treasure Chest
            ("snow", 12),  # Treasure in the Ice Wall
            ("snow", 18),  # Ice-Dodging Goomba Stack
            ("snow", 20),  # I'm Not Cold!
            ("snow", 21),  # Shopping in Shiveria
            ("snow", 23),  # Snowline Circuit Class S
            ("snow", 29),  # Moon Shards in the Cold Room
            ("snow", 30),  # Slip Behind the Ice
            ("snow", 34),  # Found with Snow Kingdom Art (pintura en pueblo)
        ],
        "moon_tag": "shiveria",
        "note": (
            "Todo el agujero (18 lunas): 4 barreras + Bound Bowl + pueblo + "
            "extras cavernas + Class S + Cold Room + Hint Art (#34). "
            "Sin overworld ni Trace-Walking (#22 → snow_overworld). "
            "Tag shiveria. Regional: 37 purple coins (mismo perímetro). "
            "También goals Combined cuyo pool de lunas es solo Shiveria "
            "(Story, Bitefrost, Goomba, Outfit Door, Racer, Multi, Shop, "
            "Hint Art, Boxer Shorts)."
        ),
    },
    "snow_overworld": {
        "goals": [
            "{{X}} Snow Overworld Moons",
            "{{X}} Snow Overworld Regional Coins",
        ],
        "kingdom": "snow",
        "moons": [
            # Superficie + sub-áreas accesibles desde fuera (15).
            ("snow", 10),  # Caught Hopping in the Snow!
            ("snow", 13),  # Timer Challenge 1
            ("snow", 14),  # Timer Challenge 2
            ("snow", 15),  # Moon Shards in the Snow
            ("snow", 16),  # Taking Notes: Snow Path Dash
            ("snow", 17),  # Fishing in the Glacier!
            ("snow", 19),  # Captain Toad is Chilly!
            ("snow", 22),  # Walking on Ice! (Koopa Trace; superficie)
            ("snow", 24),  # Dashing Over Cold Water!
            ("snow", 25),  # Dashing Above and Beyond!
            ("snow", 26),  # Jump 'n' Swim in the Freezing Water
            ("snow", 27),  # Freezing Water Near the Ceiling
            ("snow", 28),  # Blowing and Sliding
            ("snow", 31),  # Spinning Above the Clouds
            ("snow", 32),  # High-Altitude Spinning
        ],
        "moon_tag": "overworld",
        "note": (
            "Fuera del agujero (15 lunas): overworld + Trace-Walking (#22) + "
            "Cold Water Dash / Freezing Water Swim / Ty-foo Puzzle / "
            "Cloud Spinning. Hint Art (#34) → shiveria (pintura en pueblo). "
            "Sin Secret Path (#33 fuera de alcance). "
            "Tag overworld. Regional: 13 purple coins (solo clusters de superficie)."
        ),
    },
    "snow_ty_foo": {
        "goal": "{{X}} Snow Ty-Foo Moons",
        "kingdom": "snow",
        "capture": "Ty-foo",
        "moons": [
            ("snow", 3),   # The Gusty Barrier (story; excepción)
            ("snow", 9),   # Atop a Blustery Arch (Wind-Chill)
            ("snow", 28),  # Blowing and Sliding (captura; también puzzle)
        ],
        "include_story_moons": [("snow", 3)],
        "moon_tag": "ty_foo",
        "note": (
            "Tag ty_foo (no sub_area). #3 Gusty Barrier (story, sí cuenta) + "
            "#9 Blustery Arch + #28 Blowing and Sliding. "
            "Fuera del pool Sub-Area Moons. Rango [2, 3]."
        ),
    },
    "snow_bitefrost": {
        "goal": "{{X}} Snow Bitefrost Moons",
        "kingdom": "snow",
        "moons": [
            ("snow", 2),   # The Ice Wall Barrier (Hollow Crevasse, historia)
            ("snow", 12),  # Treasure in the Ice Wall (shimmy + cofre)
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag bitefrost; paraguas shiveria (snow_shiveria). "
            "Hollow Crevasse: #2 Ice Wall Barrier + #12 Treasure. Rango fijo [2]."
        ),
    },
    "puzzle": {
        "goal": "{{X}} Puzzle Moon[[s]]",
        "moons": [
            ("lake", 20),  # A Successful Repair Job (Puzzle Part)
            ("snow", 28),  # Blowing and Sliding (Ty-foo puzzle)
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag puzzle; paraguas captures (+ ty_foo en #28). "
            "Lake Puzzle Part (#20) + Snow Blowing and Sliding (#28). "
            "Lake Puzzle Part (#20) + Snow Blowing and Sliding (#28). Rango [1,2]."
        ),
    },
    # --- moon ---
    "banzai_bill": {
        "goal": "{{X}} Moon Banzai Bill Moon[[s]]",
        "kingdom": "moon",
        "capture": "Banzai Bill",
        "moons": [
            ("moon", 11),  # Around the Barrier Wall
            ("moon", 13),  # Fly to the Treasure Chest and Back
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag banzai_bill; paraguas captures (+ cave). "
            "Banzai Bill en Underground Moon Caverns: #11 (detrás del muro) + "
            "#13 (cofre volando). #12 On Top of the Cannon = GP del cañón "
            "(Banzai = acceso) → fuera. Rango [1, 2]."
        ),
    },
    "moon_cave": {
        "goals": [
            "{{X}} Moon Cave Moons",
        ],
        "kingdom": "moon",
        "moons": [
            ("moon", 9),   # Under the Bowser Statue
            ("moon", 10),  # In a Hole in the Magma
            ("moon", 11),  # Around the Barrier Wall
            ("moon", 12),  # On Top of the Cannon
            ("moon", 13),  # Fly to the Treasure Chest and Back
        ],
        "note": (
            "Underground Moon Caverns (5 lunas). Sin #14 Up in the Rafters "
            "(Wedding Hall). Sin goal Regional Coins (clusters siguen en Moon Regional)."
        ),
    },
    # --- cross ---
    "transport": {
        "goals": [
            GOAL_BEANSTALK_MOONS,
            GOAL_MINI_ROCKET_MOONS,
        ],
        "moons": [
            # Beanstalk / enredadera → nubes
            ("wooded", 47),
            ("wooded", 48),
            ("snow", 31),
            ("snow", 32),
            ("bowser", 37),
            ("bowser", 38),
            # Mini Rocket (cohete; no Rocket Flower)
            ("sand", 60),
            ("sand", 61),
            ("wooded", 41),
            ("wooded", 42),
            ("metro", 45),
            ("metro", 46),
            ("seaside", 43),
            ("seaside", 44),
        ],
        "apply_moon_tag": False,
        "note": (
            "Paraguas acceso (grupo + goals; sin tag transport en lunas). "
            "Solo Beanstalk + Mini Rocket (cohete). Rocket Flower = planta "
            "(flora; fuera del paraguas). Manhole/Taxi = grupos propios. "
            "Sin Flower Road / Pipe / Spark Pylon / Warp-Painting."
        ),
    },
    # Paraguas catalogo: union de familias concretas (lunas + goals).
    "fauna": {
        "aggregate_moon_tag": "fauna",
        "moon_tag": "fauna",
        "apply_moon_tag": False,
        "goals": [
            "{{X}} Fauna Moons",
        ],
        "note": (
            "Paraguas fauna (pool/goals; sin retaguear lunas). "
            "birds, butterfly, dorrie, dog, jaxi, sheep. "
            "Sin Klepto (boss → story_moon/cappy). "
            "Tags: <3 solo fauna, ≥3 solo concreto. "
            "Goal {{X}} Fauna Moons. Nature = fauna+flora."
        ),
    },
    "flora": {
        "aggregate_moon_tag": "flora",
        "moon_tag": "flora",
        "apply_moon_tag": False,
        "goals": [
            "{{X}} Flora Moons",
        ],
        "note": (
            "Paraguas flora (pool/goals; sin retaguear lunas). "
            "Tags las ponen familias: bloom/flower_road <3 → flora; "
            "cactus/rocket_flower ≥3 → solo concreto. Sin golden_turnip "
            "(→ seeds). Goal {{X}} Flora Moons (11). Nature = fauna+flora."
        ),
    },
    "nature": {
        "aggregate_moon_tags": ["fauna", "flora"],
        "goals_only_spec": True,
        "apply_moon_tag": False,
        "goals": [
            "{{X}} Nature Moons",
        ],
        "note": (
            "Suma fauna+flora para {{X}} Nature Moons (sin tag nature). "
            "moons[] = union fauna+flora. Incluye rocket_flower/bloom via "
            "flora. Sin rabbit/glydon/seeds/nuts."
        ),
    },
    "dorrie": {
        "goal": "{{X}} Dorrie Moon[[s]]",
        "name_patterns": [r"\bdorrie\b"],
        "moon_tag": "fauna",
        "note": (
            "Fauna (no captures). ≥3 → solo dorrie."
        ),
    },
    "dog": {
        "goal": "{{X}} Dog Moon[[s]]",
        "moons": [("sand", 31), ("seaside", 29)],
        "moon_tag": "fauna",
        "note": (
            "Good Dog: sand#31 + seaside#29. Fauna <3 → solo fauna. "
            "Objetivo junta ambas (rango [1, 2]). "
            "sand#33 Sheep → grupo sheep (fauna); no cuenta en Dog."
        ),
    },
    "sheep": {
        "goal": "Sand Sheep Moon",
        "moons": [("sand", 33)],  # Herding Sheep in the Dunes
        "moon_tag": "fauna",
        "note": (
            "n=1 → sin tag sheep; paraguas fauna. "
            "Goal Sand Sheep Moon; también en pool fauna/nature."
        ),
    },
    "slots": {
        "goal": "{{X}} Slots Moon[[s]]",
        "name_patterns": [r"\bslots\b"],
        "extra_tags": ["cappy"],
        "note": (
            "Slots (sand/metro/luncheon): tag via name_pattern + cappy. "
            "Goal propia; también en minigame."
        ),
    },
    "rabbit": {
        "goal": "{{X}} Rabbit Chase Moon[[s]]",
        "name_patterns": [r"caught hopping"],
        "note": (
            "Caught Hopping / Rabbit Chase. Fuera del paraguas fauna. "
            "n=7 → rango [1, 3, 5] (progression m/l/n)."
        ),
    },
    "koopa_trace": {
        "goal": "{{X}} Koopa Trace-Walking Moon[[s]]",
        "moons": [
            ("sand", 45),   # Walking the Desert!
            ("snow", 22),   # Walking on Ice!
        ],
        "apply_moon_tag": False,
        "extra_tags": ["npc"],  # Koopa NPC; fuera del pool {{X}} NPC Moons
        "note": (
            "n=2 → sin tag koopa_trace; tag npc (Koopa) sin entrar en "
            "npc_moons / {{X}} NPC Moons. snow#22 también overworld. "
            "2 in-scope (sand/snow); también pool Minigame (trofeo mapa). "
            "moon#21 Walking on the Moon! = post-Bowser. "
            "wooded#47 Walking on Clouds = enredadera, no Trace."
        ),
    },
    "minigame": {
        "goals": [
            "{{X}} Minigame Moons",
            "{{X}} Metro Minigame Moon[[s]]",  # pool: 4 metro (filtro export)
            "{{X}} Slots Moon[[s]]",
            "{{X}} Koopa Trace-Walking Moon[[s]]",
            "{{X}} Snow Shiverian Racer Moon[[s]]",
        ],
        "moon_tag": "minigame",
        "include_story_moons": [("snow", 5)],  # Bound Bowl (multi)
        "moons": [
            # Trofeo / minijuegos in-scope: slots, jump-rope, RC Car Pro,
            # volleyball, Trace-Walking, carrera Snow (Bound Bowl + Class S).
            # Sin Freerunning (post-historia), Moon Trace,
            # #31 RC tutorial.
            ("sand", 44),   # Sand Kingdom Slots
            ("sand", 45),   # Walking the Desert! (Trace-Walking)
            ("metro", 28),  # Metro Kingdom Slots
            ("metro", 29),  # Jump-Rope Hero
            ("metro", 30),  # Jump-Rope Genius
            ("metro", 32),  # RC Car Pro!
            ("snow", 5),    # The Bound Bowl Grand Prix (multi)
            ("snow", 22),   # Walking on Ice! (Trace-Walking)
            ("snow", 23),   # Snowline Circuit Class S
            ("seaside", 37),  # Beach Volleyball: Champ
            ("seaside", 38),  # Beach Volleyball: Hero of the Beach!
            ("luncheon", 26),  # Luncheon Kingdom Slots
        ],
        "note": (
            "12 lunas: trofeos mapa (slots×3 + jump-rope×2 + volleyball×2 + "
            "RC Car Pro + Trace sand#45/snow#22) + carrera Snow (#5+#23). "
            "Goals: Minigame [2,4,6,8] e/m/l/n; Metro Minigame [1,2,3] m/l; "
            "Slots [1,2,3] e/l/n; Trace [1,2] e/l; Shiverian Racer [1,2] l. "
            "Sin Freerunning/Moon Trace (fuera de alcance). "
            "Sin Volleyball Moon (goal retirada). Sin #31 RC tutorial."
        ),
    },
    "key": {
        "goal": "{{X}} Key Moon[[s]]",
        "moons": [
            ("sand", 29),      # TC2: llave (P-Switch; también pool Moe-Eye)
            ("lake", 22),      # Unzip the Chasm (zipper sub_area → llave al final)
            ("lost", 17),      # Twist 'n' Turn-Up Treasure (Wiggler → llave)
            ("metro", 20),     # TC2: scooter → llave
            ("luncheon", 19),  # TC2: llave
            ("luncheon", 20),  # TC3: llave
            ("bowser", 34),    # Down and Up the Spinning Tower
            ("moon", 10),      # In a Hole in the Magma (Parabones → llave)
        ],
        "note": (
            "Llave → Keyhole Pedestal. 8 in-scope: sand#29, lake#22 "
            "(zipper; wiki omite la llave), lost#17, metro#20, "
            "luncheon#19+#20, bowser#34, moon#10. "
            "sand#29 también en pool Sand Moe-Eye Moons (sin tag moe_eye). "
            "Sin lake#23 Super-Secret Zipper (sin llave). "
            "Sin TCs de carrera pura. Cages rotas → cages."
        ),
    },
    "lever": {
        "goal": "Activate {{X}} Levers",
        "moons": [],
        "allow_empty_moons": True,
        "apply_moon_tag": False,
        "note": (
            "Solo lista (Activate Levers ×6; cuenta palanca, no Moon Get). "
            "Sin moons[]: metro#37 / luncheon#2 son Moon Get en sus grupos de "
            "reino/story/cappy, no aquí (evita el mismo POI en moons y lista). "
            "Lista: Cap Sometimes Bridge, Sand 8-bit shortcut, Sand Moe-Eye bridge, "
            "Wooded Climb the Cliff, Metro Pushing Through the Crowd, "
            "Luncheon Under the Cheese Rocks. "
            "Combined range [2,3,4,5] (min 1 gratis). "
            "Fuera: Gusty Bridges (Cascade Moon Rock), seed-bots Wooded."
        ),
    },
    "switch": {
        "goals": [
            "{{X}} Switch Moon[[s]]",
            "Activate {{X}} P-Switches",
            "Activate {{X}} Ground-Pound Switches",
        ],
        "moons": [
            # P-Switch (Moon Get)
            ("sand", 29),      # TC2 (también pool Moe-Eye sin tag)
            ("metro", 20),     # TC2 scooter
            # Ground-Pound Switch (Moon Get)
            ("seaside", 27),   # Timer Challenge 1
        ],
        "moon_tag": "switch",
        "note": (
            "Tag switch solo si P/GP Switch es requisito del Moon Get. "
            "kind=both: Switch Moon[[s]] = moons[]; Activate P/GP = lista[]. "
            "Nombres distintos (no como lever, que duplicaba el mismo name). "
            "Moon Get [1,2,3]: sand#29, metro#20, seaside#27. "
            "Activate P/GP listas ×4, range [2,3,4] "
            "(min 1 gratis: Lake acceso / Lost peaje). "
            "P: 2 TC + 2 Lake acceso (sin tag). "
            "GP: seaside#27 + Lost/Metro/Moon acceso. "
            "Sin corks Seaside. Wooded/Bowser P fuera por ahora."
        ),
    },
    "blocks": {
        "goal": "{{X}} Destructible Block Moons",
        "moons": [
            ("sand", 20),    # Inside a Block Is a Hard Place
            ("wooded", 5),   # Behind the Rock Wall
            ("wooded", 22),  # Inside a Rock in the Forest
            ("wooded", 46),  # Elevator Blind Spot (roca en Elevator Shaft)
            ("lost", 11),    # Wrecked Rock Block
            ("bowser", 14),  # Inside a Block in the Castle
        ],
        "note": (
            "Bloque/roca destruible que spawnea la luna. "
            "Incluye wooded#46 (Blind Spot). No wooded#32 (Hard Rock = GP). "
            "Fuera Moon Rock: bowser#49, lost#28."
        ),
    },
    "cages": {
        "goal": "{{X}} Cage Moon[[s]]",
        "moons": [
            ("sand", 19),    # Bullet Bill Breakthrough
            ("wooded", 45),  # Elevator Escalation (jaula en Elevator Shaft)
            ("lost", 19),    # The Caged Gold
        ],
        "note": (
            "Jaulas que se rompen: sand#19, lost#19, wooded#45 Elevator. "
            "Sin lost#3 (Stone Cage = barras de piedra, no jaula)."
        ),
    },
    "wooden_crates": {
        "goal": "{{X}} Wooden Crate Moon[[s]]",
        "moons": [
            ("sand", 12),      # From a Crate in the Ruins
            ("lake", 5),       # What's in the Box?
            ("metro", 40),     # Off the Beaten Wire (caja en Wire Neighborhood)
            ("luncheon", 9),   # Is This an Ingredient Too?! (chef + cajas)
        ],
        "note": (
            "Cajas de madera: sand#12, lake#5, metro#40, luncheon#9. "
            "luncheon#9 = chef + cajas (antes solo luncheon+mario)."
        ),
    },
    "ledge_grab": {
        "goal": "{{X}} Ledge Grab Moons",
        "moons": [
            ("lake", 24),  # Jump, Grab, Cling, and Climb
            ("lake", 25),  # Jump, Grab, and Climb Some More
            ("snow", 12),  # Treasure in the Ice Wall (Hollow Crevasse)
        ],
        "note": (
            "Climbing Course Lake (#24+#25) + snow#12 (shimmy en Ice Wall). "
            "metro#45 es solo swinging_pole."
        ),
    },
    "8bit": {
        "goals": [
            "{{X}} 8-Bit Moons",
            "{{X}} 8-Bit Regional Coins",
            "{{X}} Pixel Cat Marios/Peaches",
            "{{X}} Pixel Luigis",
        ],
        "moon_tag": "8bit",
        "preserve_moons": True,
        "note": (
            "Secciones 8-bit (lunas) + pixels Mario/Peach/Luigi (no Power Moons). "
            "Cat Mario/Peach: 2/reino (sin Cloud/Ruined); listas pixel_cat_marios + "
            "pixel_cat_peaches (12+12, ids 1..12 independientes por lista). "
            "Pixel Luigis: coin Hint Art (sin Cloud/Snow/Ruined Toad, sin Mushroom); "
            "Cat Mario/Peach rango [5,10,15,20]; Pixel Luigis [3,6,9,12] lim2. "
            "Lunas via preserve_moons (tag 8bit). "
            "Regional: 29 purple DENTRO del mural 8-bit (sin 3D cerca del "
            "pipe Cascade ni techo Chasm Lifts). "
            "Subáreas híbridas 2D/3D: goal Hybrid 2D Sub-Area; "
            "8bit solo en la luna 2D de cada par (#17, #30, ruined#4)."
        ),
    },
    "timer_challenge": {
        "goal": "{{X}} Timer Challenge Moons",
        "name_patterns": [r"timer challenge"],
        # Extras smo.wiki Timer Challenge (Toadette): spawn temporal sin nombre «Timer Challenge».
        "moons": [
            ("wooded", 29),  # Glowing in the Deep Woods
            ("metro", 37),  # Pushing Through the Crowd
        ],
        "moon_tag": "timer_challenge",
        "note": (
            "Lista Toadette smo.wiki/Timer_Challenge: nombradas + Glowing "
            "(wooded#29) + Crowd (metro#37). 23 in-scope; resto Moon Rock/"
            "postgame (cap#28, lost#31, metro#71+#81, etc.). "
            "Rango [4,8,12,16]. Music Note no cuentan (tooltip). "
            "Subset tematico: ver hidden_timer (+ metro#38)."
        ),
    },
    "music_note": {
        "goal": "{{X}} Music Note Moons",
        "name_patterns": [r"taking notes"],
        "moons": [
            ("sand", 59),  # Jaxi Stunt Driving (notas sin «Taking Notes»)
        ],
        "moon_tag": "music_note",
        "note": (
            "Taking Notes + Jaxi Stunt Driving (sand#59). "
            "13 in-scope. Timer Challenge no cuentan (tooltip inverso)."
        ),
    },
    "moon_shard": {
        "goal": "{{X}} Moon Shard Moons",
        "moons": [
            ("cap", 6),       # Skimming the Poison Tide
            ("cap", 10),      # Searching the Frog Pond
            ("sand", 2),      # Moon Shards in the Sand
            ("lake", 12),     # Moon Shards in the Lake
            ("wooded", 41),   # Wandering in the Fog
            ("lost", 15),     # Moon Shards in the Jungle
            ("metro", 39),    # Rewiring the Neighborhood
            ("metro", 41),    # Moon Shards Under Siege
            ("metro", 43),    # Inside the Rotating Maze
            ("snow", 2),      # The Ice Wall Barrier
            ("snow", 15),     # Moon Shards in the Snow
            ("snow", 29),     # Moon Shards in the Cold Room
            ("seaside", 30),  # Moon Shards in the Sea
            ("luncheon", 37), # Magma Swamp: Floating and Sinking
            ("luncheon", 43), # Excavate 'n' Search the Cheese Rocks
            ("bowser", 2),    # Smart Bombing
        ],
        "moon_tag": "moon_shard",
        "note": (
            "16 moon-shard in-scope (curado; no todas tienen «Moon Shard» "
            "en el nombre). Incluye story sand#2 / snow#2 / bowser#2."
        ),
    },
    "shiny_rocks": {
        "goal": "{{X}} Shiny Rock Moon[[s]]",
        "moons": [
            ("cascade", 20),  # Rolling Rock by the Falls
            ("wooded", 7),  # Rolling Rock in the Woods
            ("wooded", 28),  # Rolling Rock in the Deep Woods
            ("moon", 4),  # Rolling Rock on the Moon
        ],
        "moon_tag": "shiny_rocks",
        "note": (
            "4 Rolling Rock in-scope: Cascade revisit, Wooded×2, Moon#4. "
            "Resto postgame/Moon Rock."
        ),
    },
    "captaintoad": {
        "line_category": "captaintoad",
        "name_patterns": [r"captain toad"],
        "moon_tag": "captain_toad",
        "note": (
            "11 Captain Toad in-scope (1/reino salvo Cloud/Ruined/Moon). "
            "Total + fijas por reino."
        ),
    },
    "hidden_timer": {
        "goal": "{{X}} Hidden Timer Moon[[s]]",
        "moons": [
            ("wooded", 29),  # Glowing in the Deep Woods
            ("metro", 37),  # Pushing Through the Crowd
            ("metro", 38),  # High Over the Crowd (par Crowded Room)
        ],
        "note": (
            "TC sin nombre Toadette (Glowing + Crowd) + la otra luna del "
            "Crowded Room (#38). wooded antes del par metro → rango [1, 3]. "
            "Siguen en timer_challenge (#29+#37)."
        ),
    },
    "hybrid_2d": {
        "goal": "{{X}} Hybrid 2D Sub-Area Moons",
        "moons": [
            # Chasm Lifts: #16 3D / #17 2D (8bit)
            ("cascade", 16),
            ("cascade", 17),
            # Cold Room: #29 shards 3D / #30 2D (8bit)
            ("snow", 29),
            ("snow", 30),
            # Roulette Tower: #3 3D / #4 2D oculta (8bit)
            ("ruined", 3),
            ("ruined", 4),
        ],
        "note": (
            "Subáreas Level con una luna 2D y otra 3D (3 pares = 6 lunas). "
            "Chasm Lifts (#16 3D / #17 2D), Cold Room (#29 3D / #30 2D), "
            "Roulette Tower (#3 3D / #4 2D oculta). Folding Screen no cuenta "
            "(ambas 2D). Tag 8bit solo en la luna 2D de cada par "
            "(#17, #30, ruined#4)."
        ),
    },
    "cappy": {
        "goals": [
            "{{X}} Cappy Moons",
            "Save Cappy From Klepto",
            # Pools enteros dentro de moons[] cappy (acción Cappy).
            "{{X}} Slots Moon[[s]]",
            "{{X}} Bloom Flower Moon[[s]]",
            "{{X}} Lost Trapeetle Moon[[s]]",
            "Lake Outfit Door Moon",
        ],
        "moon_tag": "cappy",
        "preserve_moons": True,
        "note": (
            "Lunas que requieren Cappy + Save Cappy From Klepto (boss; no fauna). "
            "Lunas via preserve_moons / fill_captures_cappy. "
            "Goal {{X}} Cappy Moons rango [3, 6, 9, 12] (como Mario Moons; pool 18). "
            "También goals cuyo pool es subconjunto: Slots (3), Bloom Flower (2), "
            "Lost Trapeetle (2), Lake Outfit Door (#21)."
        ),
    },
    "mario": {
        "goal": "{{X}} Mario Moons",
        "moon_tag": "mario",
        "moons": [
            ("cascade", 5),
            ("cascade", 8),
            ("sand", 6),
            ("sand", 7),
            ("sand", 11),
            ("sand", 13),
            ("lost", 1),
            ("lost", 2),
            ("lost", 8),
            ("metro", 11),
            ("metro", 12),
            ("luncheon", 6),
            ("luncheon", 7),
            ("bowser", 7),
            ("moon", 1),
            ("moon", 14),
        ],
        "tag_only_moons": [
            ("lost", 3),
            ("lost", 7),
            ("metro", 25),
            ("luncheon", 29),
            ("bowser", 8),
            ("bowser", 16),
            ("bowser", 20),
        ],
        "note": (
            "Mario a pie 'en medio de la nada': solo reino+mario (sin tag "
            "tematica). Goal {{X}} Mario Moons rango [3, 6, 9, 12], progression "
            "e/m/l/n (puente multireino; zonas vacias OK). "
            "Tag-only fuera de la goal para evitar lunas con solo reino: "
            "lost#3/#7, metro#25, luncheon#29, bowser#8/#16/#20. "
            "Sand: pilares/alcobas de ruinas (#6, #7, #11, #13; "
            "Bullet Bill opcional en #7/#11/#13). lake#3 Crossing = tag "
            "cheep_cheep (transporte; no Mario). Bowser: solo #7 (azotea; "
            "sin #8 foso/agua, #16 ogres, #20 pasillo). Sin lunas bajo el "
            "agua. Resto a pie sin captures/cappy: sin tag de accion."
        ),
    },
    "storymoons": {
        "line_category": "storymoons",
        "moon_tag": "story_moon",
        "preserve_moons": True,
        "allow_empty_moons": True,
        "note": (
            "Cat bingo_lineas storymoons (id alineado). "
            "Lunas story (wiki, XOR multi) via preserve_moons / sync_lunas. "
            "Incluye Multi + Boss/Broodal + Levers/P/GP + Sphynx/Klepto/Life-Up "
            "(board Combined storymoons). multi_moon / boss / lever siguen aparte."
        ),
    },
    "subarea": {
        "line_category": "subarea",
        # Guía bingo subáreas (pares Level + extras). Ruined Roulette Tower incluido.
        # Fuera (ya en otros goals): Sky Garden Tower, Power Plant, barreras Snow
        # (Icicle/Hollow/Wind-Chill/Snowy Mountain), Volcano Cave Luncheon.
        # Sin Ty-Foo (barrera/captura; no par Level).
        # Levels sin goal tematica propia: Freezing Water Swim, Magma Swamp,
        # Spinning Athletics, Folding Screen, Sinking Island → solo reino.
        # Híbridas 2D/3D (Chasm Lifts, Cold Room, Roulette) → Hybrid 2D goal.
        "moons": [
            # Cap
            ("cap", 6),
            ("cap", 7),
            ("cap", 8),
            ("cap", 9),
            ("cap", 10),
            ("cap", 11),
            # Cascade
            ("cascade", 12),
            ("cascade", 13),
            ("cascade", 14),
            ("cascade", 15),
            ("cascade", 16),
            ("cascade", 17),
            # Sand (mazes + Jaxi + Strange Neighborhood; sin Ice Cave #49+#50 → sand_ice)
            ("sand", 54),
            ("sand", 55),
            ("sand", 56),
            ("sand", 57),
            ("sand", 58),
            ("sand", 59),
            ("sand", 60),
            ("sand", 61),
            # Lake
            ("lake", 22),
            ("lake", 23),
            ("lake", 24),
            ("lake", 25),
            # Wooded (sin Sky Garden Tower #24+#25)
            ("wooded", 39),
            ("wooded", 40),
            ("wooded", 41),
            ("wooded", 42),
            ("wooded", 43),
            ("wooded", 44),
            ("wooded", 45),
            ("wooded", 46),
            ("wooded", 47),
            ("wooded", 48),
            # Metro (sin Underground Power Plant #6+#35)
            ("metro", 37),
            ("metro", 38),
            ("metro", 39),
            ("metro", 40),
            ("metro", 41),
            ("metro", 42),
            ("metro", 43),
            ("metro", 44),
            ("metro", 45),
            ("metro", 46),
            ("metro", 47),
            ("metro", 48),
            ("metro", 49),
            ("metro", 50),
            # Snow guía (sin barreras historia #1+#18/#2+#12/#3+#9/#4+#7)
            ("snow", 24),
            ("snow", 25),
            ("snow", 26),
            ("snow", 27),
            ("snow", 29),
            ("snow", 30),
            ("snow", 31),
            ("snow", 32),
            # Seaside
            ("seaside", 43),
            ("seaside", 44),
            ("seaside", 45),
            ("seaside", 46),
            ("seaside", 47),
            ("seaside", 48),
            # Luncheon (sin Volcano Cave #4+#29)
            ("luncheon", 27),
            ("luncheon", 28),
            ("luncheon", 37),
            ("luncheon", 38),
            ("luncheon", 39),
            ("luncheon", 40),
            ("luncheon", 41),
            ("luncheon", 42),
            ("luncheon", 43),
            ("luncheon", 44),
            ("luncheon", 45),
            ("luncheon", 46),
            # Bowser
            ("bowser", 31),
            ("bowser", 32),
            ("bowser", 33),
            ("bowser", 34),
            ("bowser", 35),
            ("bowser", 36),
            ("bowser", 37),
            ("bowser", 38),
            # Ruined (Roulette Tower; acceso Mini Rocket, no pool mini_rocket)
            ("ruined", 3),
            ("ruined", 4),
        ],
        "moon_tag": "sub_area",
        "note": (
            "Subáreas guía bingo (pares Level). 84 lunas = 42 pares. "
            "Goals: total + por reino (10) + tema/acceso de cada Level "
            "(Frog, Zipper, Moe-Eye, Jaxi, Ice, Pipe, Flower Road, Sherm, "
            "Manhole, Taxi, Mini Rocket, Beanstalk, Rocket Flower, Gushen, "
            "Pokio, Jizo, Bullet Bill, Lava Bubble, Ledge Grab, Hidden Timer, "
            "Chasm Lifts, Roulette Tower, …). "
            "Reinos >4 pares: rango min 4 lunas, nunca el total "
            "(wooded/metro/luncheon). Sand: 4 pares (sin Ice Cave). "
            "Sin Sky Garden / Power Plant / barreras Snow / Volcano Cave / "
            "Ty-Foo (otros goals). Sin snow#28 Blowing (Ty-Foo; no es par Level). "
            "Ice Cave Level (#49+#50): solo sand_ice (no Sub-Area ni "
            "sand_ruins). "
            "Pares Level → Files/sub_area_levels_data.py."
        ),
    },
    "hint_art": {
        "goals": [
            "Look at {{X}} Hint-Arts",
            "Lake Hint Art Moon",
            "Wooded Hint Art Moon",
            "Metro Hint Art Moon",
            "Snow Hint Art Moon",
            "Seaside Hint Art Moon",
            "Luncheon Hint Art Moon",
        ],
        "preserve_moons": True,
        "note": (
            "Hint Arts: lunas Found with … Art por reino + mirar pinturas "
            "(Look at {{X}} Hint-Arts; no contador Moon Get global). "
            "Lunas via preserve_moons."
        ),
    },
    "ground_pound": {
        "goals": [
            "{{X}} Ground Pound Moons",
            "{{X}} Sand Ground Pound Moons",
            "{{X}} Wooded Ground Pound Moons",
            "{{X}} Seaside Ground Pound Moons",
            "{{X}} Luncheon Ground Pound Moons",
        ],
        "moons": [
            ("sand", 16),
            ("sand", 17),
            ("sand", 18),
            ("sand", 23),  # The Lurker Under the Stone (también lurker_rumble)
            ("sand", 31),
            ("sand", 40),
            ("sand", 52),  # A Rumble from the Sandy Floor (también lurker_rumble)
            ("lake", 6),
            ("lake", 7),
            ("lake", 27),
            ("wooded", 9),
            ("wooded", 31),
            ("wooded", 32),
            ("wooded", 34),  # Beneath the Roots (árbol → glowing spot)
            ("wooded", 50),
            ("lost", 9),
            ("lost", 10),
            ("metro", 14),  # Who Piled Garbage… (spot bajo bolsas; Cappy solo limpia)
            ("metro", 15),  # Hidden in the Scrap (GP en resto Mechawiggler)
            ("metro", 16),  # Left at the Café? (pájaros → GP)
            ("metro", 53),
            # NO metro#18/#48: dumpster + Cappy (contenedor = trash solo)
            ("snow", 8),   # Shining in the Snow in Town
            ("snow", 9),   # Atop a Blustery Arch
            ("snow", 34),
            # seaside#10 → cheep_cheep (ladrillos con Cheep Cheep)
            ("seaside", 16),
            ("seaside", 17),
            ("seaside", 18),
            ("seaside", 19),
            ("seaside", 20),  # Wriggling on the Sandy Bottom (también lurker_rumble)
            ("seaside", 29),  # Good Dog!
            ("seaside", 41),  # A Rumble on the Seaside Floor (también lurker_rumble)
            ("seaside", 50),
            ("luncheon", 10),
            ("luncheon", 11),
            ("luncheon", 12),
            ("luncheon", 13),
            ("luncheon", 22),
            ("luncheon", 30),  # queso → glowing spot
            ("luncheon", 49),
            ("bowser", 13),  # On the Giant Bowser Statue's Nose
            ("moon", 12),
        ],
        "moon_tag": "ground_pound",
        "note": (
            "Spots/bumps, hint art, Good Dog, scrap/#14. "
            "Incluye las 4 Lurker/Rumble (también grupo lurker_rumble). "
            "Snow: #8+#9 (spots) + #34 hint art. "
            "Bowser: #13 statue nose. Moon: #12 cannon. "
            "Goal por reino si >3 (Sand/Wooded/Seaside/Luncheon). "
            "NO dumpsters (#18/#48), Rolling Rock/bloques/cajas/Moon Rock; "
            "NO luncheon#7 (alcove)."
        ),
    },
    "outfit_door": {
        "goals": [
            "{{X}} Outfit Door Moons",
            "Sand Outfit Door Moon",
            "Lake Outfit Door Moon",
            "Wooded Outfit Door Moon",
            "{{X}} Metro Outfit Door Moons",
            "{{X}} Snow Outfit Door Moons",
            "Seaside Outfit Door Moon",
            "{{X}} Luncheon Outfit Door Moons",
            "{{X}} Bowser's Outfit Door Moons",
        ],
        "moons": [
            # Puerta/outfit requerido. Si abre sub_area de 2 lunas, ambas cuentan.
            ("sand", 53),       # Dancing with New Friends (unico Sand)
            ("lake", 21),       # I Feel Underdressed (bañador)
            ("wooded", 36),     # Exploring for Treasure (Explorer)
            ("metro", 39),      # Rewiring the Neighborhood (Builder / Wire Neighborhood)
            ("metro", 40),      # Off the Beaten Wire
            ("snow", 29),       # Moon Shards in the Cold Room (Snow Suit)
            ("snow", 30),       # Slip Behind the Ice
            ("seaside", 42),    # A Relaxing Dance (resort)
            ("luncheon", 27),   # A Strong Simmer (Chef)
            ("luncheon", 28),   # An Extreme Simmer
            ("bowser", 31),     # Scene of Crossing the Poison Swamp (Samurai)
            ("bowser", 32),     # Taking Notes: In the Folding Screen
        ],
        "moon_tag": "outfit_door",
        "note": (
            "Outfit requerido para puerta. Tag outfit_door SIN npc "
            "(sin sub_area encima: basta el acceso). "
            "Board/line Combined: subarea (ya no hay cat outfitdoor). "
            "Sand: solo #53 baile (#43 Employees Only = normal). "
            "No Private Room / I'm Not Cold (esas = npc). "
            "Luncheon Spinning Athletics = scarecrow → mario (no outfit_door). "
            "Goals por reino: 1 luna → rango [1×4]; sub_area de 2 → [2×4]. "
            "Global: 12 in-scope → rango [2,4,6,8]."
        ),
    },
    "sphynx": {
        "goals": [
            "{{X}} Sphynx Moons",
            "Correct Wooded Sphynx Question",
            "Correct Moon Sphynx Question",
        ],
        "moons": [
            ("sand", 41),      # Sand Quiz: Wonderful!
            ("sand", 51),      # Sphynx's Treasure Vault
            ("seaside", 35),   # Ocean Quiz: Good!
            ("seaside", 40),   # The Sphynx's Underwater Vault
        ],
        "note": (
            "4 lunas Sand+Seaside (quiz+vault). Goals: {{X}} Sphynx Moons "
            "[2,4] + Correct Wooded/Moon Sphynx Question. "
            "lista sphynxes ×4 (Sand/Wooded/Seaside/Moon)."
        ),
    },
    "lurker_rumble": {
        "goal": "{{X}} Lurker/Rumble Moon[[s]]",
        "moons": [
            ("sand", 52),     # A Rumble from the Sandy Floor (base / pueblo)
            ("sand", 23),     # The Lurker Under the Stone (world_peace)
            ("seaside", 20),  # Wriggling on the Sandy Bottom (Lurker)
            ("seaside", 41),  # A Rumble on the Seaside Floor
        ],
        "moon_tag": "lurker_rumble",
        "note": (
            "Lurkers enterrados + lunas HD Rumble (Toadette Instructor). "
            "GP para revelar; tambien en pool ground_pound. "
            "Orden: sand#52 base → sand#23 wp → seaside. "
            "sand#52 sigue en sand_tostarena (ubicacion pueblo)."
        ),
    },
    "critter": {
        "goal": "{{X}} Critter Moon[[s]]",
        "moons": [
            ("cascade", 12),  # Dinosaur Nest: Big Cleanup! (Burrbo)
            ("sand", 49),     # Under the Mummy's Curse (Chincho)
            ("lost", 5),      # Over the Fuzzies, Above the Swamp
            ("lost", 6),      # Avoiding Fuzzies Inside the Wall
        ],
        "apply_moon_tag": False,
        "note": (
            "Cajon lunas sueltas criatura/enemigo: Burrbo, Chincho, Fuzzy×2. "
            "Stairface → stairface_ogre (#1+#14+#16). Sin Sheep (Sand Sheep Moon). "
            "Sin cascade#13 Running Wild (no Burrbo). Sin retaguear lunas. "
            "n=4 → rango [1, 2, 3] (progression e/l)."
        ),
    },
    "trapped_chest": {
        "goal": "{{X}} Traped Chest Moon[[s]]",
        "moons": [
            ("seaside", 22),   # Treasure Trap Hidden in the Inlet
            ("wooded", 35),    # Deep Woods Treasure Trap
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag trapped_chest; paraguas treasure_chest. "
            "Typo Combined: Traped. lost#19 = cages, no trapped_chest."
        ),
    },
    "poochy": {
        "goal": "{{X}} Poochy Moon[[s]]",
        "moons": [
            ("bowser", 27),    # Fishing(?) — aparece Poochy
            ("metro", 53),     # Hint Art Metro (Poochy en Lake)
            ("snow", 34),      # Hint Art Snow (Poochy en Lost)
            ("luncheon", 49),  # Hint Art Luncheon (Poochy en Seaside)
        ],
        "moon_tag": "poochy",
        "note": (
            "Pesca Bowser + Hint Art in-scope donde sale Poochy. "
            "Fuera: bowser#45 / moon#27 / Dark Side (postgame)."
        ),
    },
    "npc_moons": {
        "goals": [
            "{{X}} NPC Moons",
            "Snow Boxer Shorts Moon",
        ],
        "moons": [
            # Hablar / pedir captura o traje (NO outfit_door, NO Goombette).
            ("lake", 16),      # I Met a Lake Cheep Cheep!
            ("lake", 17),      # Our Secret Little Room
            ("metro", 26),     # Bench Friends
            ("snow", 20),      # I'm Not Cold! (traje a NPC; = Snow Boxer Shorts Moon)
        ],
        # Tag npc sin entrar en pool {{X}} NPC Moons (moons[]).
        "tag_only_moons": [
            ("metro", 2),  # Drummer on Board!
            ("metro", 3),  # Guitarist on Board!
            ("metro", 4),  # Bassist on Board!
            ("metro", 5),  # Trumpeter on Board!
        ],
        "moon_tag": "npc",
        "note": (
            "NPC pide captura/traje o hablar. "
            "Goombette → goomba (no npc). "
            "outfit_door usa outfit_door sin npc. "
            "lake#16 tambien en Cheep Cheep Moons. "
            "Snow Boxer Shorts Moon = Moon Get snow#20 I'm Not Cold!. "
            "Musicos Metro#2–#5: tag npc vía tag_only_moons (fuera del pool). "
            "Koopa Trace + turista: tag npc vía extra_tags "
            "(fuera de este pool / {{X}} NPC Moons)."
        ),
    },
    "tourist": {
        "goal": "{{X}} Tourist Moon[[s]]",
        "moons": [
            ("metro", 52),     # A Tourist in the Metro Kingdom!
            ("cascade", 19),   # A Tourist in the Cascade Kingdom
            ("luncheon", 48),  # A Tourist in the Luncheon Kingdom!
            ("moon", 25),      # A Tourist in the Moon Kingdom!
        ],
        "apply_moon_tag": False,
        "extra_tags": ["npc"],
        "note": (
            "Cadena Desert Wanderer in-scope (4). "
            "Sin mushroom#40 ni sand#68 Round-the-World. "
            "Solo tag npc (como otras lunas de hablar); el goal "
            "{{X}} Tourist Moon[[s]] diferencia el subconjunto."
        ),
    },
    "shopping": {
        "line_category": "shopping",
        "name_patterns": [r"\bshopping\b"],
        "moon_tag": "shop",
        "note": (
            "Crazy Cap (ex-id shop): lunas Shopping (tag shop) + goals por reino + "
            "compras (costume_sets/hats/souvenirs/stickers/boxer_shorts) + "
            "lists.shops (Crazy Cap ×11). "
            "Snow Boxer Shorts Moon = moon Get en npc/snow; aquí por la compra "
            "del traje (lista boxer_shorts). Sin Moon postgame."
        ),
    },
    # Objetivos sin moons[]: pool lista (kind=lista).
    "boss": {
        "goals": [
            "{{X}} Boss Fights",
            "{{X}} Broodal Fights",
            "{{X}} Kingdom Boss Fight[[s]]",
            "Defeat Bowser in Cloud Kingdom",
            "Defeat Madame Broode in Moon Kingdom",
            "Defeat Ruined Dragon",
        ],
        "moons": [],
        "allow_empty_moons": True,
        "note": (
            "Peleas de jefe (Death Cutscene), no Moon Get. "
            "lista[] = bosses (sin moons[]). "
            "Especificos: Cloud Bowser + Moon Madame Broode + Ruined Dragon. "
            "Board/line Combined: storymoons (ya no hay cat boss)."
        ),
    },
    "checkpoints": {
        "line_category": "checkpoints",
        "moons": [],
        "allow_empty_moons": True,
        "goals_only": True,
        "note": (
            "Cat checkpoints: solo goals (Total + All + por reino). "
            "lista checkpoints vive en grupos kingdom (sin duplicar ×78)."
        ),
    },
    "regionalcoins": {
        "line_category": "regionalcoins",
        "moons": [],
        "allow_empty_moons": True,
        "goals_only": True,
        "note": (
            "Cat regionalcoins: solo goals (Total + All Large/Small + "
            "por reino + subsets). lista regionals vive en kingdom / "
            "8bit / subarea / etc. (sin duplicar ×287)."
        ),
    },
    "life_up": {
        "goal": "{{X}} Unique Life Up Hearts",
        "moons": [],
        "allow_empty_moons": True,
        "note": (
            "Corazones 1-Up únicos (lists.life_up_hearts ×17). Sin moons[]. "
            "También en story_moon (misc de ruta)."
        ),
    },
    "talkatoo": {
        "line_category": "talkatoo",
        "moons": [],
        "allow_empty_moons": True,
        "internal": True,
        "note": (
            "Hablar con Talkatoo por reino (12; como Moon Rock) "
            "+ total soft {{X}} Talkatoos. lista[] = talkatoos (sin moons[])."
        ),
    },
    "painting": {
        "goals": [
            "{{X}} Warp-Painting Moons",
            "Cascade Warp-Painting Moon",
            "Sand Warp-Painting Moon",
            "Lake Warp-Painting Moon",
            "Wooded Warp-Painting Moon",
            "Metro Warp-Painting Moon",
            "Luncheon Warp-Painting Moon",
            "Mushroom Warp-Painting Moon",
        ],
        "moons": [
            ("cascade", 18),
            ("sand", 62),
            ("lake", 26),
            ("wooded", 49),
            ("metro", 51),
            ("luncheon", 47),
            ("mushroom", 39),  # via Luncheon painting (Yoshi's House)
        ],
        "moon_tag": "painting",
        "note": (
            "7 Secret Path: 6 run + mushroom#39 (portal Luncheon). "
            "mushroom#39 en pool de goals; en lunas-objetivos como "
            "luncheon#50 (LUNAS_CATALOG_SYNTHETIC). "
            "FUERA: snow/seaside outbound, bowser tras creditos."
        ),
    },
    "moonrock": {
        "line_category": "moonrock",
        "moons": [],
        "allow_empty_moons": True,
        "internal": True,
        "note": (
            "Llegar a la ubicacion del Moon Rock por reino (13; sin Cloud) "
            "+ total soft {{X}} Moon Rocks (solo aqui; no grupo moon). "
            "No hace falta activarlo. lista[] = moon_rocks (sin moons[])."
        ),
    },

    # --- categorias bingo_lineas sin grupo previo (ids = lineas) ---
    "artistic": {
        "line_category": "artistic",
        "moons": [
            # Warp-Painting / Secret Path (painting)
            ("cascade", 18),
            ("sand", 62),
            ("lake", 26),
            ("wooded", 49),
            ("metro", 51),
            ("luncheon", 47),
            ("mushroom", 39),  # via Luncheon painting
            # Hint Art Moon Get (hint_art)
            ("lake", 27),
            ("wooded", 50),
            ("metro", 53),
            ("snow", 34),
            ("seaside", 50),
            ("luncheon", 49),
        ],
        "note": (
            "Cat bingo_lineas artistic: Hint Art + Warp-Painting. "
            "moons[] = 7 Secret Path + 6 Found with … Art "
            "(mismos pools que painting + hint_art)."
        ),
    },
    "totales": {
        "goals": [
            "{{X}} Total Moons",
            "{{X}} Total Checkpoints",
            "{{X}} Total Regional Coins",
            "{{X}} Total Multi-Moons",
            "{{X}} Total Story Moons",
        ],
        "moons": [],
        "allow_empty_moons": True,
        "goals_only": True,
        "note": (
            "Totales globales soft ({{X}} Total …). Solo goals. "
            "Cubre Total Moons (huerfana de kingdommoons retirado) y "
            "los otros Total* que tambien viven en checkpoints / "
            "regionalcoins / multi_moon / storymoons."
        ),
    },
    "multi_moon": {
        "goals": [
            "{{X}} Total Multi-Moons",
            "All Multi-Moons in {{X}} Kingdoms",
            "{{X}} Sand Multi-Moon[[s]]",
            "{{X}} Wooded Multi-Moon[[s]]",
            "{{X}} Metro Multi-Moon[[s]]",
            "{{X}} Luncheon Multi-Moon[[s]]",
            "Seaside Multi-Moon",
            "Snow Multi-Moon",
        ],
        "moons": [
            ("cascade", 2),    # Multi Moon Atop the Falls
            ("sand", 3),       # Showdown on the Inverted Pyramid
            ("sand", 4),       # The Hole in the Desert
            ("lake", 1),       # Broodals Over the Lake
            ("wooded", 2),     # Flower Thieves of Sky Garden
            ("wooded", 4),     # Defend the Secret Flower Field!
            ("metro", 1),      # New Donk City's Pest Problem
            ("metro", 7),      # A Traditional Festival!
            ("snow", 5),       # The Bound Bowl Grand Prix
            ("seaside", 5),    # The Glass Is Half Full!
            ("luncheon", 3),   # Big Pot on the Volcano: Dive In!
            ("luncheon", 5),   # Cookatiel Showdown!
            ("bowser", 4),     # Showdown at Bowser's Castle
            ("ruined", 1),     # Battle with the Lord of Lightning!
        ],
        "moon_tag": "multi_moon",
        "note": (
            "14 multilunas in-scope (XOR story_moon; tipo wiki). "
            "Goals: Total + All Kingdoms + por reino con goal Combined "
            "(Sand/Wooded/Metro/Luncheon/Seaside/Snow). "
            "Sin Cascade/Lake/Bowser/Ruined (1 multi; Ruined = Defeat Dragon). "
            "Board/line Combined: storymoons (ya no hay cat multimoons)."
        ),
    },
    "treasure_chest": {
        "goals": [
            "{{X}} Treasure Chest Moons",
            "{{X}} Traped Chest Moon[[s]]",
            "Metro City Hall Moon",
        ],
        "moons": [
            ("cascade", 6),   # Treasure of the Waterfall Basin
            ("sand", 24),     # The Treasure of Jaxi Ruins
            ("sand", 46),     # Hidden Room in the Inverted Pyramid
            ("sand", 47),     # Underground Treasure Chest
            ("sand", 51),     # Sphynx's Treasure Vault
            ("lake", 8),      # Treasure in the Spiky Waterway
            ("lake", 25),     # Jump, Grab, and Climb Some More
            ("lake", 26),     # Secret Path to Lake Lamode!
            ("wooded", 35),   # Deep Woods Treasure Trap
            ("wooded", 36),   # Exploring for Treasure
            ("metro", 34),    # City Hall Lost & Found
            ("snow", 11),     # The Shiverian Treasure Chest
            ("snow", 12),     # Treasure in the Ice Wall
            ("seaside", 21),  # Glass Palace Treasure Chest
            ("seaside", 22),  # Treasure Trap Hidden in the Inlet
            ("seaside", 40),  # The Sphynx's Underwater Vault
            ("seaside", 44),  # Sunken Treasure in the Cloud Sea
            ("seaside", 46),  # Treasure Chest in the Narrow Valley
            ("luncheon", 34), # The Treasure Chest in the Veggies
            ("bowser", 30),   # Bowser's Castle Treasure Vault
            ("ruined", 2),    # In the Ancient Treasure Chest
            ("moon", 6),      # Cliffside Treasure Chest
            ("moon", 13),     # Fly to the Treasure Chest and Back
        ],
        "moon_tag": "treasure_chest",
        "note": (
            "Solo lunas que cuentan para Treasure Chest Hunter (cofre o "
            "Treasure Trap). El nombre puede decir 'tesoro' sin ser cofre. "
            "Metro City Hall Moon = #34 fija. "
            "Incluye {{X}} Traped Chest (seaside#22 + wooded#35; typo Combined)."
        ),
    },
    # --- cascade ---
    "cascade_chain_chomp": {
        "goal": "{{X}} Cascade Chain Chomp Moons",
        "kingdom": "cascade",
        "capture": "Chain Chomp",
        "moons": [
            ("cascade", 14),  # Nice Shot with the Chain Chomp!
            ("cascade", 15),  # Very Nice Shot with the Chain Chomp!
        ],
        "tag_only_moons": [
            ("cascade", 3),  # Chomp Through the Rocks
            ("cascade", 7),  # Above a High Cliff
        ],
        "moon_tag": "chain_chomp",
        "note": (
            "Goal: solo subárea Chain Chomp Cave (#14+#15), rango [2]. "
            "#3/#7 tag chain_chomp (tag_only; no cuentan en la goal)."
        ),
    },
    "cascade_chasm_lifts": {
        "goal": "{{X}} Cascade Chasm Lifts Moons",
        "kingdom": "cascade",
        "moons": [
            ("cascade", 16),  # Past the Chasm Lifts (3D)
            ("cascade", 17),  # Hidden Chasm Passage (2D / 8bit)
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag chasm_lifts; paraguas sub_area (+ hybrid_2d). "
            "Par Chasm Lifts (puerta Cappy tras Stone Bridge). "
            "#16 3D / #17 2D oculta. También Hybrid 2D Sub-Area + Cascade Sub-Area."
        ),
    },
    # --- ruined ---
    "ruined_roulette": {
        "goal": "{{X}} Roulette Tower Moons",
        "kingdom": "ruined",
        "moons": [
            ("ruined", 3),  # Roulette Tower: Climbed
            ("ruined", 4),  # Roulette Tower: Stopped
        ],
        "apply_moon_tag": False,
        "note": (
            "n=2 → sin tag roulette; paraguas sub_area (+ hybrid_2d). "
            "Par Roulette Tower (Mini Rocket). Pool reino: #1 multi, #2 cofre, "
            "#3+#4 torre (6 unidades con multi×3)."
        ),
    },

}


def _goals_from_bingo_lineas(category_id: str) -> list[str]:
    """Objectives de una categoria de Catalog/bingo_lineas.json."""
    from catalog_lib import BINGO_LINEAS_PATH, load_catalog

    if not category_id or not BINGO_LINEAS_PATH.exists():
        return []
    data = load_catalog(BINGO_LINEAS_PATH)
    for group in data.get("groups") or []:
        if str(group.get("id") or "") != category_id:
            continue
        return [
            str(o["goal"])
            for o in (group.get("objectives") or [])
            if isinstance(o, dict) and o.get("goal")
        ]
    return []


def _spec_goals(spec: dict[str, Any]) -> list[str]:
    """Goals del SPEC: line_category (bingo_lineas) + goals/goal explicitos."""
    from catalog_lib import objective_goal_sort_key

    explicit: list[str] = []
    if "goals" in spec:
        explicit = [str(g) for g in spec["goals"]]
    elif "goal" in spec:
        explicit = [str(spec["goal"])]

    line_cat = str(spec.get("line_category") or "")
    from_line = _goals_from_bingo_lineas(line_cat) if line_cat else []

    seen: set[str] = set()
    out: list[str] = []
    for goal in explicit + sorted(from_line, key=objective_goal_sort_key):
        if goal and goal not in seen:
            seen.add(goal)
            out.append(goal)
    return out


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.I) for p in patterns]


def _moon_registry_sort_key(km: tuple[str, int]) -> tuple[int, int]:
    return (
        KINGDOM_COLUMNS.index(km[0]) if km[0] in KINGDOM_COLUMNS else 99,
        km[1],
    )


def _keys_from_spec_patterns(
    spec: dict[str, Any],
    registry: dict[tuple[str, int], dict],
) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for pair in spec.get("moons") or []:
        keys.add((pair[0], int(pair[1])))
    patterns = _compile_patterns(list(spec.get("name_patterns") or []))
    if not patterns:
        return keys
    kingdom_filter = spec.get("kingdom")
    for (kingdom, moon), entry in registry.items():
        if kingdom_filter and kingdom != kingdom_filter:
            continue
        name = entry.get("name") or ""
        if any(p.search(name) for p in patterns):
            keys.add((kingdom, moon))
    return keys


def _resolve_moon_entry(
    kingdom: str,
    moon: int,
    registry: dict[tuple[str, int], dict],
    wiki: dict,
) -> dict | None:
    entry = registry.get((kingdom, moon))
    we = wiki.get(kingdom, {}).get(moon)
    wiki_name = (we or {}).get("name")
    if entry:
        name = entry.get("name") or ""
        if wiki_name and (
            not name or (name.startswith("Moon ") and name[5:].isdigit())
        ):
            return {**entry, "name": wiki_name}
        return entry
    # Lunas in-scope aun no en matrix (p. ej. ruined#3+#4, mushroom#39).
    if not we or not wiki_moon_in_scope(kingdom, moon, we):
        return None
    return {"name": wiki_name or f"Moon {moon}"}


def _should_drop_story_moon(
    key: tuple[str, int],
    entry: dict,
    *,
    drop_story: bool,
    allow_story: set[tuple[str, int]],
) -> bool:
    if not drop_story or key in allow_story:
        return False
    tags = set(entry.get("tags") or [])
    return bool(tags & {"story_moon", "multi_moon"})


def resolve_moons(
    spec: dict[str, Any],
    registry: dict[tuple[str, int], dict],
) -> list[dict]:
    """Resuelve moons explicitas + name_patterns → refs {kingdom, moon, name}.

    Si el SPEC tiene `capture`, excluye story_moon/multi_moon salvo las de
    `include_story_moons` (p. ej. sand#2, snow#1, snow#5).

    Las moons[] explícitas conservan el orden del SPEC; las de name_patterns
    se añaden al final ordenadas por reino/número.
    """
    allow_story = {
        (str(k), int(m)) for k, m in (spec.get("include_story_moons") or [])
    }
    drop_story = bool(spec.get("capture")) and not spec.get("include_all_story_moons")
    wiki = load_wiki_moon_meta()

    def _ref(kingdom: str, moon: int) -> dict | None:
        key = (kingdom, moon)
        entry = _resolve_moon_entry(kingdom, moon, registry, wiki)
        if not entry:
            return None
        if _should_drop_story_moon(
            key, entry, drop_story=drop_story, allow_story=allow_story
        ):
            return None
        return {
            "kingdom": kingdom,
            "moon": moon,
            "name": entry["name"],
        }

    refs: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for pair in spec.get("moons") or []:
        kingdom, moon = str(pair[0]), int(pair[1])
        key = (kingdom, moon)
        if key in seen:
            continue
        ref = _ref(kingdom, moon)
        if not ref:
            continue
        seen.add(key)
        refs.append(ref)

    patterns = _compile_patterns(list(spec.get("name_patterns") or []))
    if patterns:
        kingdom_filter = spec.get("kingdom")
        extra: list[tuple[str, int]] = []
        for (kingdom, moon), entry in registry.items():
            if kingdom_filter and kingdom != kingdom_filter:
                continue
            if (kingdom, moon) in seen:
                continue
            name = entry.get("name") or ""
            if any(p.search(name) for p in patterns):
                extra.append((kingdom, moon))
        for kingdom, moon in sorted(extra, key=_moon_registry_sort_key):
            ref = _ref(kingdom, moon)
            if not ref:
                continue
            seen.add((kingdom, moon))
            refs.append(ref)
    return refs


def resolve_tag_only_moons(
    spec: dict[str, Any],
    registry: dict[tuple[str, int], dict],
) -> list[dict]:
    """Legacy: lunas con tags del grupo fuera de moons[]/goals.

    Preferir no usarlo: si no cuenta para la goal, no va en el grupo;
    usar tag global (paraguas/captures/story_moon) vía su grupo real.
    """
    pairs = spec.get("tag_only_moons") or []
    if not pairs:
        return []
    # Sin filtro story: tag_only no cuenta para goals de captura.
    return resolve_moons(
        {**spec, "moons": pairs, "name_patterns": [], "capture": None},
        registry,
    )


def _aggregate_moons_by_moon_tag(
    by_id: dict[str, dict],
    *,
    tag: str,
    skip_ids: frozenset[str],
) -> list[dict]:
    """Une moons[] de grupos con moon_tag=tag (excl. skip_ids)."""
    return _aggregate_moons_by_moon_tags(by_id, tags=[tag], skip_ids=skip_ids)


def _moon_ref_from_raw(raw: dict) -> tuple[tuple[str, int], dict] | None:
    if not isinstance(raw, dict) or "kingdom" not in raw or "moon" not in raw:
        return None
    key = (str(raw["kingdom"]), int(raw["moon"]))
    return key, {
        "kingdom": key[0],
        "moon": key[1],
        "name": raw.get("name") or f"Moon {key[1]}",
    }


def _iter_group_moon_raws(group: dict):
    yield from list(group.get("moons") or [])
    yield from list(group.get("tag_only_moons") or [])


def _aggregate_moons_by_moon_tags(
    by_id: dict[str, dict],
    *,
    tags: list[str],
    skip_ids: frozenset[str],
) -> list[dict]:
    """Une moons[] de grupos con moon_tag en tags (excl. skip_ids)."""
    tag_set = set(tags)
    keys: set[tuple[str, int]] = set()
    by_key: dict[tuple[str, int], dict] = {}
    for gid, group in by_id.items():
        if gid in skip_ids or group.get("moon_tag") not in tag_set:
            continue
        for raw in _iter_group_moon_raws(group):
            parsed = _moon_ref_from_raw(raw)
            if parsed is None:
                continue
            key, ref = parsed
            if key in keys:
                continue
            keys.add(key)
            by_key[key] = ref
    return [by_key[km] for km in sorted(keys, key=_moon_registry_sort_key)]


def _append_unique_goal(seen: set[str], out: list[str], goal: str) -> None:
    if goal and goal not in seen:
        seen.add(goal)
        out.append(goal)


def _aggregate_goals_by_moon_tag(
    by_id: dict[str, dict],
    *,
    tag: str,
    skip_ids: frozenset[str],
    extra_goals: list[str] | None = None,
) -> list[str]:
    """Une goals de grupos con moon_tag=tag (+ extra_goals del spec)."""
    seen: set[str] = set()
    out: list[str] = []
    for goal in extra_goals or []:
        _append_unique_goal(seen, out, goal)
    for gid, group in by_id.items():
        if gid in skip_ids or group.get("moon_tag") != tag:
            continue
        for goal in group_objectives(group):
            _append_unique_goal(seen, out, goal)
    return out


def _preserve_moons_from_group(by_id: dict[str, dict], gid: str) -> list[dict]:
    return [
        {
            "kingdom": str(raw["kingdom"]),
            "moon": int(raw["moon"]),
            "name": raw.get("name") or f"Moon {raw['moon']}",
        }
        for raw in ((by_id.get(gid) or {}).get("moons") or [])
        if isinstance(raw, dict) and "kingdom" in raw and "moon" in raw
    ]


def _omit_reason_for_spec(
    gid: str,
    moons: list[dict],
    *,
    allow_empty: bool,
    has_related_objective: bool,
) -> str | None:
    if not moons and not allow_empty:
        return f"  AVISO: {gid} sin lunas resueltas; se omite."
    if (
        moons
        and len(moons) < MIN_MOONS
        and not has_related_objective
        and not allow_empty
    ):
        return (
            f"  AVISO: {gid} tiene {len(moons)} lunas y sin objetivo "
            f"relacionado (norma: >={MIN_MOONS} lunas o 1 objetivo); se omite."
        )
    if not moons and allow_empty and not has_related_objective:
        return f"  AVISO: {gid} sin lunas ni objetivo relacionado; se omite."
    return None


def _copy_prev_meta(group: dict[str, Any], prev: dict) -> None:
    for keep in ("_definition", "_source"):
        if prev.get(keep) not in (None, "", [], False):
            group[keep] = prev[keep]


def _apply_spec_flags(group: dict[str, Any], spec: dict[str, Any]) -> None:
    if spec.get("kingdom"):
        group["kingdom"] = spec["kingdom"]
    if spec.get("capture"):
        group["capture"] = spec["capture"]
    if spec.get("internal"):
        group["internal"] = True
    if spec.get("extra_tags"):
        group["extra_tags"] = [str(t) for t in spec["extra_tags"]]
    if spec.get("moon_tag"):
        group["moon_tag"] = spec["moon_tag"]
        if spec.get("umbrella") or spec["moon_tag"] in UMBRELLA_MOON_TAGS:
            group["umbrella"] = True
        else:
            group["large"] = True
    if spec.get("apply_moon_tag") is False:
        group["apply_moon_tag"] = False
    if spec.get("goals_only"):
        group["goals_only"] = True


def _build_spec_group(
    gid: str,
    spec: dict[str, Any],
    *,
    goals: list[str],
    moons: list[dict],
    combined: dict,
    registry: dict[tuple[str, int], dict],
    prev: dict,
) -> dict[str, Any]:
    obj_refs = [
        objective_ref_from_combined(goal, combined.get(goal)) for goal in goals
    ]
    note = spec.get("note") or (
        "Grupo tematico derivado del objetivo Combined; "
        "lunas curadas/patrones en OBJECTIVE_MOON_GROUP_SPECS."
    )
    group: dict[str, Any] = {
        "id": gid,
        "objectives": obj_refs,
        "moons": moons,
        "_note": note,
    }
    _copy_prev_meta(group, prev)
    _apply_spec_flags(group, spec)
    tag_only = resolve_tag_only_moons(spec, registry)
    if tag_only:
        group["tag_only_moons"] = tag_only
    return group


def _merge_extra_moons(moons: list[dict], extras: list[dict]) -> list[dict]:
    for raw in extras:
        key = (str(raw["kingdom"]), int(raw["moon"]))
        if any((m["kingdom"], int(m["moon"])) == key for m in moons):
            continue
        moons.append(
            {
                "kingdom": key[0],
                "moon": key[1],
                "name": raw.get("name") or f"Moon {key[1]}",
            }
        )
    moons.sort(
        key=lambda m: (
            KINGDOM_COLUMNS.index(m["kingdom"])
            if m["kingdom"] in KINGDOM_COLUMNS
            else 99,
            int(m["moon"]),
        )
    )
    return moons


def _resolve_aggregate_payload(
    gid: str,
    spec: dict[str, Any],
    *,
    by_id: dict[str, dict],
    aggregate_ids: frozenset[str],
    registry: dict[tuple[str, int], dict],
) -> tuple[list[dict], list[str], str, list[str], str | None] | None:
    multi_tags = spec.get("aggregate_moon_tags")
    if multi_tags:
        tags = [str(t) for t in multi_tags]
        moons = _aggregate_moons_by_moon_tags(
            by_id, tags=tags, skip_ids=aggregate_ids
        )
        goals = _spec_goals(spec)
        tag_label = "+".join(tags)
        moon_tag = spec.get("moon_tag")
    else:
        tag = str(spec["aggregate_moon_tag"])
        tags = [tag]
        moons = _aggregate_moons_by_moon_tag(
            by_id, tag=tag, skip_ids=aggregate_ids
        )
        moons = _merge_extra_moons(moons, resolve_moons(spec, registry))
        goals = (
            _spec_goals(spec)
            if spec.get("goals_only_spec")
            else _aggregate_goals_by_moon_tag(
                by_id,
                tag=tag,
                skip_ids=aggregate_ids,
                extra_goals=_spec_goals(spec),
            )
        )
        tag_label = tag
        moon_tag = spec.get("moon_tag") or tag

    if len(moons) < MIN_MOONS:
        print(
            f"  AVISO: {gid} aggregate {tag_label} tiene {len(moons)} lunas "
            f"(norma: >={MIN_MOONS}); se omite."
        )
        return None
    return moons, goals, tag_label, tags, moon_tag


def _sync_one_spec_group(
    gid: str,
    spec: dict[str, Any],
    *,
    by_id: dict[str, dict],
    combined: dict,
    registry: dict[tuple[str, int], dict],
    counts: dict[str, int],
) -> None:
    goals = _spec_goals(spec)
    moons = resolve_moons(spec, registry)
    if not moons and spec.get("preserve_moons"):
        moons = _preserve_moons_from_group(by_id, gid)
    goals_only = bool(spec.get("goals_only"))
    allow_empty = bool(spec.get("allow_empty_moons")) or goals_only
    related_goals = [g for g in goals if g in combined]
    has_related_objective = bool(related_goals)

    omit = _omit_reason_for_spec(
        gid,
        moons,
        allow_empty=allow_empty,
        has_related_objective=has_related_objective,
    )
    if omit:
        print(omit)
        by_id.pop(gid, None)
        return

    if goals_only:
        moons = []

    by_id[gid] = _build_spec_group(
        gid,
        spec,
        goals=goals,
        moons=moons,
        combined=combined,
        registry=registry,
        prev=by_id.get(gid) or {},
    )
    counts[gid] = len(moons)


def _sync_aggregate_group(
    gid: str,
    spec: dict[str, Any],
    *,
    by_id: dict[str, dict],
    aggregate_ids: frozenset[str],
    combined: dict,
    registry: dict[tuple[str, int], dict],
    counts: dict[str, int],
) -> None:
    payload = _resolve_aggregate_payload(
        gid,
        spec,
        by_id=by_id,
        aggregate_ids=aggregate_ids,
        registry=registry,
    )
    if payload is None:
        by_id.pop(gid, None)
        return
    moons, goals, tag_label, tags, moon_tag = payload
    if spec.get("goals_only"):
        moons = []
    obj_refs = [
        objective_ref_from_combined(goal, combined.get(goal)) for goal in goals
    ]
    note = spec.get("note") or (
        f"Paraguas {tag_label}: union de grupos con moon_tag={tags}."
    )
    group: dict[str, Any] = {
        "id": gid,
        "objectives": obj_refs,
        "moons": moons,
        "umbrella": True,
        "_note": note,
    }
    if moon_tag:
        group["moon_tag"] = moon_tag
    if spec.get("apply_moon_tag") is False:
        group["apply_moon_tag"] = False
    if spec.get("goals_only"):
        group["goals_only"] = True
    by_id[gid] = group
    counts[gid] = len(moons)


def sync_objective_moon_groups() -> dict[str, int]:
    """Crea/actualiza grupos tematicos objetivo↔lunas en bingo_groups.json."""
    registry = build_matrix_moon_registry()
    combined = load_combined_objectives_by_goal()
    bingo = load_catalog(BINGO_GROUPS_PATH) if BINGO_GROUPS_PATH.exists() else {"groups": []}
    by_id = {g["id"]: g for g in bingo.get("groups", [])}
    counts: dict[str, int] = {}

    for gid in RETIRED_OBJECTIVE_GROUP_IDS:
        by_id.pop(gid, None)

    deferred_aggregates: list[tuple[str, dict[str, Any]]] = []

    for gid, spec in OBJECTIVE_MOON_GROUP_SPECS.items():
        if spec.get("aggregate_moon_tag") or spec.get("aggregate_moon_tags"):
            deferred_aggregates.append((gid, spec))
            continue
        _sync_one_spec_group(
            gid,
            spec,
            by_id=by_id,
            combined=combined,
            registry=registry,
            counts=counts,
        )

    # Paraguas fauna/flora/nature: tras familias concretas.
    aggregate_ids = frozenset(gid for gid, _ in deferred_aggregates)
    for gid, spec in deferred_aggregates:
        _sync_aggregate_group(
            gid,
            spec,
            by_id=by_id,
            aggregate_ids=aggregate_ids,
            combined=combined,
            registry=registry,
            counts=counts,
        )

    bingo["groups"] = [
        normalize_bingo_group(g, combined)
        for g in assign_bingo_group_orden(
            [normalize_bingo_group(by_id[gid], combined) for gid in sorted(by_id)]
        )
    ]
    write_catalog_json(BINGO_GROUPS_PATH, finalize_bingo_groups_doc(bingo))
    clear_group_context_tags_cache()
    return counts


def main() -> None:
    print("Sincronizando grupos objetivo<->lunas...")
    counts = sync_objective_moon_groups()
    print(f"Grupos actualizados: {len(counts)}")
    for gid, n in sorted(counts.items()):
        print(f"  {gid}: {n} lunas")
    goals_covered: set[str] = set()
    for spec in OBJECTIVE_MOON_GROUP_SPECS.values():
        goals_covered.update(_spec_goals(spec))
    existing: set[str] = set()
    for g in load_bingo_groups():
        existing.update(group_objectives(g))
    missing = sorted(goals_covered - existing)
    if missing:
        print("AVISO: goals en specs no presentes tras sync:")
        for g in missing:
            print(f"  {g}")


if __name__ == "__main__":
    main()
