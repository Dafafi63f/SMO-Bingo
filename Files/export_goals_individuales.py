"""Genera Catalog/goals_individuales.json desde goals_referencia.json.

Agrupado por reino (id=cap/sand/…), blank_reino (reservado blank_progresion
si reino sin progression) e índices early/mid/late/endgame (e/m/l/n)
con las mismas goals (reino o blank) cuya progression toca esa zona.
Grupos en alfa 1..G.

Campos por goal:
- grupo blank_* o zona → goal + kingdom + progression + lockout
- grupo reino → goal + progression + lockout (kingdom = id del grupo)
- Con reino, overlap → una sola goal con progression en lista (p. ej. ["l","n"])
- Sin reino → blank_reino (con o sin progression; lockout puede llevar zonas).
- early/mid/late/endgame: copia índice (puede repetir goals de reino/blank).
- Multi-reino con max(range) < tamaño del pool → kingdom blank
  (el umbral no fija el reino; overrides curados siguen aplicando).
- Multi-reino con max(range) == pool → el último umbral se sella al reino
  del último item si seguía blank (p. ej. Special Seed 3 → seaside).
- Warp-Painting con varias entradas → blank_reino + progression de entrada
  (lista); Metro → lost; Mushroom → luncheon/l (entrada clara, luna base).
"""
from __future__ import annotations

from apply_progression_accessibility import (
    GOAL_TOURIST_MOONS,
    KINGDOM_BORDER_PROGRESSION,
    TOURIST_PROGRESSION_BORDER,
    progression_letter_for_threshold,
)
from catalog_lib import (
    CATALOG_DIR,
    GLOBAL_AGGREGATE_GOALS,
    KINGDOM_GOAL_PREFIXES,
    TAG_KINGDOM,
    ZONE_ORDER,
    catalog_kingdom,
    catalog_kingdom_for_moon,
    load_catalog,
    write_catalog_json,
)
from fix_bingo_group_ranges import METRO_NIGHT_CHECKPOINT_NAMES

SRC = CATALOG_DIR / "goals_referencia.json"
OUT = CATALOG_DIR / "goals_individuales.json"

# Sin reino + progression mono-zona → grupo por fase de run.
ZONE_GROUP_IDS: dict[str, str] = {
    "e": "early",
    "m": "mid",
    "l": "late",
    "n": "endgame",
}
ZONE_GROUP_ID_SET = frozenset(ZONE_GROUP_IDS.values())

# Pistas por nombre cuando pool/cats no aportan un reino unico.
NAME_HINTS = [
    ("Deep Woods", "wooded"),
    ("Metro Night", "lost"),
    ("Metro Girder", "lost"),
    ("Metro Shop", "lost"),
    ("Metro Moon Rock", "lost"),  # base al llegar; tramo noche → lost/m
    # Pintura inbound a Metro (#51 Secret Path): cuenta en Night → lost/m.
    ("Metro Warp-Painting", "lost"),
    # City Hall Lost & Found (#34): Night → lost/m.
    ("Metro City Hall", "lost"),
    # Pintura a Mushroom: entrada única Luncheon (luna base) → luncheon/l.
    ("Mushroom Warp-Painting", "luncheon"),
    ("Sand Ice", "sand"),
    ("Sand Jaxi", "sand"),
    ("Sand Ruins", "sand"),
    ("Sand Tostarena", "sand"),
    ("Snow Overworld", "snow"),
    ("Snow Shiveria", "snow"),
    ("Cloud Kingdom", "lost"),
    ("Moon Kingdom", "moon"),
]


def pool_items(g: dict) -> list[dict]:
    return list(g.get("moons") or g.get("lista") or [])


def item_catalog_kingdom(m: dict) -> str:
    """Reino de progresión de un item: metro noche (CP Night / luna base) → lost."""
    k = m.get("kingdom")
    if not k:
        return ""
    name = str(m.get("name") or "")
    if str(k) == "metro" and name in METRO_NIGHT_CHECKPOINT_NAMES:
        return "lost"
    # Solo lunas (campo moon): metro+base → lost. Listas/shops conservan metro.
    if m.get("moon") is not None:
        return catalog_kingdom_for_moon(
            str(k), m.get("disponibilidad") or m.get("availability")
        )
    return catalog_kingdom(str(k))


def pool_items_catalog(g: dict) -> list[dict]:
    """Pool con kingdom de progresión (no muta la referencia)."""
    out: list[dict] = []
    for m in pool_items(g):
        ck = item_catalog_kingdom(m)
        if ck and ck != m.get("kingdom"):
            out.append({**m, "kingdom": ck})
        else:
            out.append(m)
    return out


def name_hint_kingdom(template: str) -> str | None:
    """Pistas por nombre (Metro Night→lost, …); prioridad sobre el pool."""
    for hint, slug in NAME_HINTS:
        if hint in template:
            return slug
    return None


def kingdoms_from_cats(g: dict) -> set[str]:
    return {c for c in (g.get("board_categories") or []) if c in TAG_KINGDOM}


def kingdom_from_name(template: str) -> str | None:
    if template in GLOBAL_AGGREGATE_GOALS:
        return None
    if template.startswith("{{X}} Moon Rock"):
        return None
    hinted = name_hint_kingdom(template)
    if hinted:
        return hinted
    cleaned = (
        template.replace("{{X}} ", "")
        .replace("{{X}}", "")
        .replace("[[s]]", "")
    )
    for display, slug in KINGDOM_GOAL_PREFIXES:
        if (
            cleaned == display
            or cleaned.startswith(display + " ")
            or cleaned.startswith(display + "'")
        ):
            return slug
    return None


def fallback_single_kingdom(g: dict) -> str:
    cats = kingdoms_from_cats(g)
    if len(cats) == 1:
        return next(iter(cats))
    if len(cats) > 1:
        return ""
    return kingdom_from_name(g["goal"]) or ""


def item_weight(m: dict) -> int:
    if m.get("total") is not None:
        return int(m["total"])
    return 1


def pool_total_count(items: list[dict]) -> int:
    """Tamaño del pool (suma de pesos si weighted; si no, nº de items)."""
    if pool_is_weighted(items):
        return sum(item_weight(m) for m in items)
    return len(items)


def pool_is_weighted(items: list[dict]) -> bool:
    return any(m.get("total") is not None for m in items)


def kingdom_at_index(items: list[dict], count: int) -> str:
    """Reino del item nº count (1-indexed) en el pool; cada fila cuenta como 1."""
    if count < 1 or count > len(items):
        return ""
    k = items[count - 1].get("kingdom")
    return str(k) if k else ""


def kingdom_at_weight(items: list[dict], count: int) -> str:
    """Reino de la unidad nº count sumando total (p. ej. monedas regionales)."""
    if count < 1:
        return ""
    seen = 0
    for m in items:
        k = m.get("kingdom")
        if not k:
            return ""
        seen += item_weight(m)
        if seen >= count:
            return str(k)
    return ""


def prefix_unique_count(items: list[dict], count: int) -> int:
    """Reinos distintos en items[0:count] (count 1-indexed inclusive)."""
    if count < 1:
        return 0
    return len({m["kingdom"] for m in items[:count] if m.get("kingdom")})


def prefix_unique_weighted(items: list[dict], count: int) -> int:
    """Reinos distintos al acumular total hasta cubrir count unidades."""
    if count < 1:
        return 0
    seen = 0
    ks: set[str] = set()
    for m in items:
        k = m.get("kingdom")
        if not k:
            break
        ks.add(str(k))
        seen += item_weight(m)
        if seen >= count:
            break
    return len(ks)


def kingdom_run_boundaries(items: list[dict]) -> set[int]:
    """Cumulativos al cerrar cada bloque contiguo de reino (1-indexed)."""
    bounds: set[int] = set()
    i = 0
    seen = 0
    while i < len(items):
        k = items[i].get("kingdom")
        if not k:
            break
        j = i + 1
        while j < len(items) and items[j].get("kingdom") == k:
            j += 1
        seen += j - i
        bounds.add(seen)
        i = j
    return bounds


# Excepciones curadas: template → {range_value: kingdom}.
# Solo asignaciones completas (todos los umbrales con reino). Si falta alguno,
# homogenize_kingdoms deja la goal entera en blank.
# Cheep Cheep: lake + seaside + seaside (pool 2+5); Combined m,l → m / m,l / l.
# Critter: cascade + sand + lost.
# Destructible: sand/wooded/lost (Bowser fuera del range).
# Dorrie: lake + seaside + seaside (familia fauna con kingdom).
# Ground Pound (global): blank_reino — pool 41, range max 28 (< pool).
# Lurker/Rumble: sand + sand + seaside + seaside.
# Shiny Rock: cascade + wooded + wooded + moon.
# Tourist: orden de visita (no historia) metro → cascade → luncheon → moon.
# Levers: sand + sand + wooded + metro (umbrales 2/3/4/5; cap queda en 1).
# Spark Pylon: cap + metro (Bowser fuera del range; no hace falta la 5ª).
# Seed Moon NTT: siempre sand (pool multi tiene metro/seaside; no hace falta).
# Metro Checkpoints: 5 night (base→lost) cubren 3/5; 7/9 necesitan día → metro.
KINGDOM_OVERRIDES: dict[str, dict[int, str]] = {
    "{{X}} Cheep Cheep Moons": {2: "lake", 4: "seaside", 6: "seaside"},
    "{{X}} Critter Moon[[s]]": {1: "cascade", 2: "sand", 3: "lost"},
    "{{X}} Destructible Block Moons": {1: "sand", 3: "wooded", 5: "lost"},
    "{{X}} Dorrie Moon[[s]]": {1: "lake", 2: "seaside", 3: "seaside"},
# Lurker/Rumble: sand#52 base + sand#23 wp + seaside×2.
    "{{X}} Lurker/Rumble Moon[[s]]": {1: "sand", 2: "sand", 3: "seaside", 4: "seaside"},
    "{{X}} Metro Checkpoints": {3: "lost", 5: "lost", 7: "metro", 9: "metro"},
    "{{X}} Seed Moon (No Time Travel)": {1: "sand"},
    "{{X}} Shiny Rock Moon[[s]]": {1: "cascade", 2: "wooded", 3: "wooded", 4: "moon"},
    "{{X}} Spark Pylon Moons": {2: "cap", 4: "metro"},
    "{{X}} Tourist Moon[[s]]": {1: "metro", 2: "cascade", 3: "luncheon", 4: "moon"},
    "Activate {{X}} Levers": {2: "sand", 3: "sand", 4: "wooded", 5: "metro"},
}

# Solo overrides curados (ignora auto multi-reino del pool).
CURATED_ONLY_TEMPLATES = frozenset(KINGDOM_OVERRIDES)

# Progression curada por umbral (str | lista); si falta, regla avail→borde
# (o emparejado Lockout si no hay reino/items).
# Lista = overlap explícito (no filtrar al puente del reino).
# Solo blank-reino / narrativo que la regla no puede inferir:
# Special Seed / Rocket Flower (umbrales sin reino); Ledge Grab snow.
# Tourist: solo l/n (nunca e/m del reino, p.ej. cascade); orden visita.
PROGRESSION_OVERRIDES: dict[str, dict[int, str | list[str]]] = {
    # Cap gratis; sand 8-bit/e; sand Moe-Eye wp→m; wooded base→e; metro→l.
    "Activate {{X}} Levers": {2: "e", 3: "m", 4: "e", 5: "l"},
    # Lost gratis; metro/seaside Late (TC1 base→l, no Night); moon→n.
    "Activate {{X}} Ground-Pound Switches": {2: "l", 3: "l", 4: "n"},
    "{{X}} Glydon Moon[[s]]": {1: "m", 2: "l", 3: "n"},
    "{{X}} Ledge Grab Moons": {3: "l"},
    "{{X}} Rocket Flower Moons": {2: "l", 4: "n", 6: "n"},
    # Ice Cave 4 → e; 8/11 necesitan templo → m.
    "{{X}} Sand Ice Regional Coins": {4: "e", 8: "m", 11: "m"},
    "{{X}} Special Seed Moon[[s]]": {1: "m", 2: "m", 3: "l"},
    "{{X}} Tourist Moon[[s]]": {1: "l", 2: "l", 3: "n", 4: "n"},
}

# Fijas / 1-umbral: si hay varias zonas candidatas, usar la tardia.
# Moon Rock / Sphynx NO: basta llegar / responder (zona temprana del puente).
DELAYED_GOAL_FRAGMENTS = (
    "Warp-Painting",
    "Hint Art",
)

# Multi-reino / bosses / tours 1-por-reino: forzar kingdom vacio.
# Paraguas Flora/Fauna/Nature (agregados): sin kingdom; familias (Dorrie, …) si.
# Special Seed: lake/wooded/seaside intercambiables en 1–2; umbral 3 (=pool)
# se sella a seaside en seal_full_pool_last_kingdom.
# Warp-Painting fijas con varias entradas posibles → blank_reino + progression
# de entrada (lista); Metro (Sand→Night) y Mushroom (Luncheon) sí tienen reino.
FORCE_BLANK_TEMPLATES = frozenset(
    {
        "{{X}} Boss Fights",
        "{{X}} Kingdom Boss Fight[[s]]",
        "{{X}} Key Moon[[s]]",
        "{{X}} Lakitu-Fishing Moon[[s]]",
        "{{X}} Moon Shard Moons",
        "{{X}} Music Note Moons",
        "{{X}} Treasure Chest Moons",
        "{{X}} 8-Bit Regional Coins",
        "{{X}} Captain Toad Moons",
        "{{X}} Shop Moons",
        "{{X}} Talkatoos",
        "{{X}} Warp-Painting Moons",
        "Cascade Warp-Painting Moon",
        "Lake Warp-Painting Moon",
        "Luncheon Warp-Painting Moon",
        "Sand Warp-Painting Moon",
        "Wooded Warp-Painting Moon",
        "Look at {{X}} Hint-Arts",
        "All Checkpoints in {{X}} Kingdoms",
        "All Multi-Moons in {{X}} Kingdoms",
        "All Regional Coins in {{X}} Large Kingdom",
        "All Regional Coins in {{X}} Small Kingdom[[s]]",
        "{{X}} Fauna Moons",
        "{{X}} Flora Moons",
        "{{X}} Ground Pound Moons",
        "{{X}} Nature Moons",
        "{{X}} Special Seed Moon[[s]]",
    }
)

# Pinturas con progression de entrada multi-zona: blank_reino conserva la lista.
WARP_PAINTING_KEEP_ENTRANCE_PROG = frozenset(
    {
        "Cascade Warp-Painting Moon",
        "Lake Warp-Painting Moon",
        "Luncheon Warp-Painting Moon",
        "Sand Warp-Painting Moon",
        "Wooded Warp-Painting Moon",
    }
)


def apply_overrides(
    template: str, ranges: list[int] | None, kingdoms: list[str]
) -> list[str]:
    if template in FORCE_BLANK_TEMPLATES or template in GLOBAL_AGGREGATE_GOALS:
        return [""] * len(kingdoms)
    ov = KINGDOM_OVERRIDES.get(template)
    if template in CURATED_ONLY_TEMPLATES:
        if not ranges:
            return [""]
        return [ov.get(int(x), "") if ov else "" for x in ranges]
    if not ov or not ranges:
        return kingdoms
    out = list(kingdoms)
    for i, value in enumerate(ranges):
        if value in ov:
            out[i] = ov[value]
    return out


def apply_progression_overrides(
    template: str, ranges: list[int] | None, progressions: list[list[str]]
) -> list[list[str]]:
    ov = PROGRESSION_OVERRIDES.get(template)
    if not ov or not ranges:
        return progressions
    out = [list(zs) for zs in progressions]
    for i, value in enumerate(ranges):
        if int(value) in ov:
            z = ov[int(value)]
            if isinstance(z, list):
                out[i] = list(z)
            else:
                out[i] = [z] if z else []
    return out


def lock_blank_tail(kingdoms: list[str]) -> list[str]:
    """Si un umbral es blank, los siguientes tambien (no se reconstruye la run)."""
    out: list[str] = []
    locked = False
    for k in kingdoms:
        if locked or not k:
            locked = True
            out.append("")
        else:
            out.append(k)
    return out


def homogenize_kingdoms(kingdoms: list[str]) -> list[str]:
    """Por goal: o todos con kingdom o todos blank (sin umbrales mixtos).

    El sello full-pool (``seal_full_pool_last_kingdom``) puede dejar blank* +
    último reino después de esto.
    """
    has_k = any(kingdoms)
    has_blank = any(not k for k in kingdoms)
    if has_k and has_blank:
        return [""] * len(kingdoms)
    return kingdoms


def seal_full_pool_last_kingdom(
    kingdoms: list[str],
    ranges: list[int] | None,
    items: list[dict],
) -> list[str]:
    """Si max(range)==pool multi-reino, el último umbral exige todo el pool.

    Rellena kingdom vacío en ese umbral con el reino del último item (o peso).
    Umbrales previos pueden seguir blank (p. ej. Special Seed 1/2 blank, 3=seaside).
    """
    if not ranges or not kingdoms or not items:
        return kingdoms
    if len(pool_kingdoms(items)) <= 1:
        return kingdoms
    size = pool_total_count(items)
    if not size:
        return kingdoms
    mx = max(int(x) for x in ranges)
    if mx != size:
        return kingdoms
    if pool_is_weighted(items):
        last_k = kingdom_at_weight(items, mx)
    else:
        last_k = kingdom_at_index(items, mx)
    if not last_k:
        return kingdoms
    out = list(kingdoms)
    for i, x in enumerate(ranges):
        if int(x) == mx and not out[i]:
            out[i] = last_k
    return out


def progressions_for_entries(
    ranges: list[int] | None, template_prog: list[str]
) -> list[list[str]]:
    """Zonas (0+) por entrada; overlap → varias (la goal se emite en cada una).

    Emparejado con lockout.live ``progressive_ranges`` (preview del GameEditor):
    cada zona e en 0..m-1 y cada umbral r en 0..n-1 se solapan en [0,1) si
    ``(r/n) < ((e+1)/m)`` y ``((r+1)/n) > (e/m)``.

    - 1 zona → esa zona en todas las entradas
    - umbral en exactamente una zona → [zona]
    - umbral en varias zonas (overlap) → [zona, …] (p. ej. 3×2 medio → ambas)
    """
    values = ranges if ranges else [None]
    n = len(values)
    prog = list(template_prog or [])
    if not prog:
        return [[] for _ in range(n)]
    if len(prog) == 1:
        return [[prog[0]] for _ in range(n)]
    m = len(prog)
    owners: list[list[str]] = [[] for _ in range(n)]
    for e, zone in enumerate(prog):
        t, a = e / m, (e + 1) / m
        for r in range(n):
            o, s = r / n, (r + 1) / n
            if o < a and s > t:
                owners[r].append(zone)
    return owners


def expand_zones_for_kingdom(
    kingdom: str, zones: list[str], *, template_prog: list[str]
) -> list[str]:
    """Filtra zonas al borde del reino; overlap vacío → todo el puente.

    Así una goal puede repetirse con cada progression que cumple (p. ej. Deep
    Woods 6 → wooded/e y wooded/m).
    """
    if not kingdom:
        return list(zones)
    border = progression_for_kingdom(kingdom)
    if not border:
        return list(zones)
    if len(border) == 1:
        return [border[0]]
    if not zones:
        return list(border)
    hit = [z for z in zones if z in border]
    return hit if hit else list(border)


def kingdoms_for_ranges(g: dict, ranges: list[int] | None) -> list[str]:
    """Un reino por umbral de range (o uno si no hay range).

    Multi-reino: reino del umbral si (a) cabe en el primer reino del pool, o
    (b) el umbral cierra un bloque contiguo de reino (p. ej. Beanstalk 2/4/6).
    Si max(range) < tamaño del pool, reino blank (umbral no fija el reino).
    Tras el primer blank de la run, el resto queda blank.

    NAME_HINTS ganan sobre el pool. Prefijo Metro + pool solo metro/lost
    (remap noche) → metro en totales/día; Multi-Moon sigue el pool (Pest→lost).
    """
    values = ranges if ranges else [None]
    n = len(values)
    forced = name_hint_kingdom(g["goal"])
    if forced:
        return [forced] * n

    items = pool_items_catalog(g)
    keyed = [m for m in items if m.get("kingdom")]
    unique = {m["kingdom"] for m in keyed}

    if len(unique) == 1:
        k = next(iter(unique))
        return [k] * n

    if len(unique) == 0:
        k = fallback_single_kingdom(g)
        return [k] * n

    named = kingdom_from_name(g["goal"])
    if (
        named == "metro"
        and unique <= {"metro", "lost"}
        and "Multi-Moon" not in g["goal"]
    ):
        return ["metro"] * n

    if not ranges:
        return [""]

    if len(keyed) != len(items):
        return [""] * n

    # Multi-reino: si el umbral más alto no cubre el pool, no hay reino claro.
    size = pool_total_count(items)
    if size and max(int(x) for x in ranges) < size:
        return [""] * n

    if pool_is_weighted(items):
        return [
            kingdom_at_weight(items, int(x))
            if prefix_unique_weighted(items, int(x)) == 1
            else ""
            for x in ranges
        ]

    bounds = kingdom_run_boundaries(items)
    out = []
    for x in ranges:
        xi = int(x)
        if prefix_unique_count(items, xi) == 1 or xi in bounds:
            out.append(kingdom_at_index(items, xi))
        else:
            out.append("")
    return out


def expand_goal(template: str, value: int) -> str:
    text = template.replace("{{X}}", str(value))
    if "[[s]]" in text:
        text = text.replace("[[s]]", "" if value == 1 else "s")
    return text


def progression_for_kingdom(kingdom: str) -> list[str]:
    return list(KINGDOM_BORDER_PROGRESSION.get(kingdom, []))


def is_delayed_goal(goal_text: str) -> bool:
    return any(frag in goal_text for frag in DELAYED_GOAL_FRAGMENTS)


def resolve_blank_progression(
    kingdom: str,
    prog: str,
    *,
    goal_text: str,
    template_prog: list[str],
    n_range: int,
    template_has_mapped_prog: bool,
) -> tuple[str, str]:
    """Rellena kingdom+prog vacíos tras el mapeo (fijas / sin overlap expandible).

    Sin reino y sin prog → blank_reino con progression vacía. Con reino el
    overlap ya se expandió a todas las zonas del puente antes de llegar aquí.
    """
    if not kingdom or prog:
        return kingdom, prog

    border = set(progression_for_kingdom(kingdom))
    candidates = [z for z in template_prog if z in border]
    if not candidates:
        return "", ""
    chosen = candidates[-1] if is_delayed_goal(goal_text) else candidates[0]
    return kingdom, chosen


def clamp_prog_to_kingdom_border(
    kingdom: str, prog: str, *, curated: bool
) -> str:
    """Mono-reino: forzar/validar prog contra el puente del reino."""
    if not kingdom or curated:
        return prog
    border = progression_for_kingdom(kingdom)
    if len(border) == 1:
        return border[0]
    if len(border) >= 2 and prog and prog not in border:
        return ""
    return prog


def pool_kingdoms(items: list[dict]) -> set[str]:
    return {str(m["kingdom"]) for m in items if m.get("kingdom")}


def item_availability(m: dict) -> str:
    from apply_progression_accessibility import earliest_disponibilidad

    raw = m.get("disponibilidad") or m.get("availability") or "base"
    return earliest_disponibilidad(raw)


def pool_has_moon_availability(items: list[dict]) -> bool:
    """True si el pool trae lunas u otros ítems con disponibilidad refinable.

    Clusters regionales (``total`` de monedas) llevan disponibilidad informativa
    en lista[], pero no refinan progression: Combined ya define e/m/l/n.
    """
    for m in items:
        if m.get("moon") is not None:
            return True
        if m.get("total") is not None:
            continue
        if m.get("disponibilidad") or m.get("availability"):
            return True
    return False


def refine_progression_from_availability(
    *,
    kingdom: str,
    template: str,
    goal_text: str,
    threshold: int | None,
    items: list[dict],
    multi_kingdom: bool = False,
) -> str:
    """Zona del umbral: avail limitante → 1ª/2ª del puente del reino.

    Tourist: puente fijo l,n (sin e/m del reino). Warp-Painting / Hint Art:
    no (entrada / overrides). Sin reino o sin pool → "".
    """
    if not kingdom or not items:
        return ""
    if is_delayed_goal(goal_text) or is_delayed_goal(template):
        return ""
    border = (
        TOURIST_PROGRESSION_BORDER if template == GOAL_TOURIST_MOONS else None
    )
    return progression_letter_for_threshold(
        kingdom,
        items,
        threshold,
        multi_kingdom=multi_kingdom,
        border=border,
    )


def refine_multi_kingdom_progression(
    *,
    kingdom: str,
    prog: str,
    template: str,
    goal_text: str,
    threshold: int | None,
    items: list[dict],
    multi_kingdom: bool,
    weighted: bool,
) -> str:
    """Compat: aplica avail→borde si hay reino (mono o multi)."""
    del weighted
    if not kingdom:
        return prog
    letter = refine_progression_from_availability(
        kingdom=kingdom,
        template=template,
        goal_text=goal_text,
        threshold=threshold,
        items=items,
        multi_kingdom=multi_kingdom,
    )
    return letter or prog


def _single_zone_letter(progression: str | list[str]) -> str | None:
    """e/m/l/n si progression es exactamente una zona; si no None."""
    if isinstance(progression, list):
        if len(progression) == 1 and progression[0] in ZONE_GROUP_IDS:
            return str(progression[0])
        return None
    s = str(progression or "")
    return s if s in ZONE_GROUP_IDS else None


def progression_zone_letters(progression: str | list[str]) -> list[str]:
    """Letras e/m/l/n presentes en progression (orden ZONE_ORDER)."""
    if isinstance(progression, list):
        return [z for z in ZONE_ORDER if z in progression]
    s = str(progression or "")
    return [s] if s in ZONE_GROUP_IDS else []


def group_id_for(kingdom: str, progression: str | list[str]) -> str:
    """Reino, blank_reino (sin reino) o blank_progresion (reino sin prog).

    early/mid/late/endgame no son destino primario: se añaden luego como
    índices sobre las goals ya emitidas.
    """
    has_k = bool(kingdom)
    has_p = (
        bool(progression)
        if not isinstance(progression, list)
        else bool(progression)
    )
    if has_k and has_p:
        return kingdom
    if not has_k:
        return "blank_reino"
    return "blank_progresion"


def is_zone_group(group_id: str) -> bool:
    return group_id in ZONE_GROUP_ID_SET


def is_kingdomless_group(group_id: str) -> bool:
    """blank_* o early/mid/late/endgame: llevan kingdom explícito en la row."""
    return group_id.startswith("blank_") or is_zone_group(group_id)


def compact_progression_value(zones: list[str]) -> str | list[str]:
    """str si 1 zona; lista ordenada e/m/l/n si overlap; "" si vacío."""
    ordered = [z for z in ZONE_ORDER if z in zones]
    if not ordered:
        return ""
    if len(ordered) == 1:
        return ordered[0]
    return ordered


def _zone_rank(z: str) -> int:
    try:
        return ZONE_ORDER.index(z)
    except ValueError:
        return 99


def lockout_inverted_vs_progression(
    progression: str | list[str], lockout: str | list[str]
) -> bool:
    """True si progression es estrictamente más tarde que todo lockout."""
    pr = (
        list(progression)
        if isinstance(progression, list)
        else ([progression] if progression else [])
    )
    lo = (
        list(lockout)
        if isinstance(lockout, list)
        else ([lockout] if lockout else [])
    )
    pr = [z for z in pr if z]
    lo = [z for z in lo if z]
    if not pr or not lo:
        return False
    if set(pr) <= set(lo):
        return False
    return min(_zone_rank(z) for z in pr) > max(_zone_rank(z) for z in lo)


def emit_goal_row(group_id: str, row: dict) -> dict:
    """Campos compactos + lockout (emparejado Lockout.live).

    blank_*/zona → kingdom+progression+lockout;
    reino → progression+lockout.
    """
    out: dict = {
        "goal": row["goal"],
        "progression": row["progression"],
        "lockout": row.get("lockout", row["progression"]),
    }
    if is_kingdomless_group(group_id):
        out["kingdom"] = row["kingdom"]
    return out


def resolve_goal_row(group_id: str, row: dict, *, orden: int) -> dict:
    """Rellena kingdom/progression implícitos (lectura / tests)."""
    raw = row.get("progression", "")
    raw_lockout = row.get("lockout", raw)
    if is_kingdomless_group(group_id):
        kingdom = str(row.get("kingdom") or "")
        prog: str | list[str] = (
            list(raw) if isinstance(raw, list) else str(raw or "")
        )
    else:
        kingdom = group_id
        prog = list(raw) if isinstance(raw, list) else str(raw or "")
    lockout: str | list[str] = (
        list(raw_lockout) if isinstance(raw_lockout, list) else str(raw_lockout or "")
    )
    return {
        "orden": orden,
        "goal": row["goal"],
        "kingdom": kingdom,
        "progression": prog,
        "lockout": lockout,
    }


def flatten_goals(
    groups: list[dict], *, include_zone_groups: bool = False
) -> list[dict]:
    """Lista plana con kingdom/progression resueltos y orden global 1..N.

    Por defecto omite early/mid/late/endgame (índices; no duplicar n_goals).
    """
    flat: list[dict] = []
    orden = 1
    for gr in groups:
        if not include_zone_groups and is_zone_group(gr["id"]):
            continue
        for row in gr["goals"]:
            flat.append(resolve_goal_row(gr["id"], row, orden=orden))
            orden += 1
    return flat


def build_groups(goals: list[dict]) -> list[dict]:
    """Agrupa por reino o blank_*; añade índices early/mid/late/endgame."""
    buckets: dict[str, list[dict]] = {}
    for row in goals:
        gid = group_id_for(row["kingdom"], row["progression"])
        buckets.setdefault(gid, []).append(row)

    zone_buckets: dict[str, list[dict]] = {z: [] for z in ZONE_GROUP_ID_SET}
    for row in goals:
        for letter in progression_zone_letters(row["progression"]):
            zone_buckets[ZONE_GROUP_IDS[letter]].append(row)

    all_ids = sorted(
        set(buckets)
        | {zid for zid, rows in zone_buckets.items() if rows}
    )
    groups: list[dict] = []
    for gid in all_ids:
        rows = zone_buckets[gid] if is_zone_group(gid) else buckets[gid]
        out_goals = [emit_goal_row(gid, row) for row in rows]
        groups.append(
            {
                "id": gid,
                "orden": len(groups) + 1,
                "n_goals": len(out_goals),
                "goals": out_goals,
            }
        )
    return groups


def build_template_individual_rows(g: dict) -> list[dict]:
    """Filas compactas (goal, kingdom, progression, lockout) para un template."""
    template = g["goal"]
    ranges = g.get("range")
    if ranges:
        ranges = sorted(int(x) for x in ranges)
    template_prog = list(g.get("progression") or [])
    items = pool_items_catalog(g)
    multi_kingdom = len(pool_kingdoms(items)) > 1
    weighted = pool_is_weighted(items)
    kingdoms = seal_full_pool_last_kingdom(
        homogenize_kingdoms(
            lock_blank_tail(
                apply_overrides(
                    template, ranges, kingdoms_for_ranges(g, ranges)
                )
            )
        ),
        ranges,
        items,
    )
    lockout_progressions = progressions_for_entries(ranges, template_prog)
    progressions = apply_progression_overrides(
        template, ranges, [list(zs) for zs in lockout_progressions]
    )
    values = ranges if ranges else [None]
    assert len(kingdoms) == len(values) == len(progressions) == len(
        lockout_progressions
    )
    curated = template in CURATED_ONLY_TEMPLATES
    ov_prog = PROGRESSION_OVERRIDES.get(template) or {}
    n_range = len(ranges) if ranges else 0
    mapped_any = any(any(zs) for zs in progressions)
    rows: list[dict] = []

    for value, kingdom, zones, lockout_zs in zip(
        values, kingdoms, progressions, lockout_progressions
    ):
        goal_text = template if value is None else expand_goal(template, value)
        lockout_prog = compact_progression_value(list(lockout_zs))
        curated_prog = value is not None and int(value) in ov_prog
        zones = list(zones)
        if (
            kingdom
            and items
            and not curated_prog
            and pool_has_moon_availability(items)
        ):
            letter = refine_progression_from_availability(
                kingdom=kingdom,
                template=template,
                goal_text=goal_text,
                threshold=value,
                items=items,
                multi_kingdom=multi_kingdom,
            )
            if letter:
                zones = [letter]
        elif len(zones) == 1 and not curated_prog and pool_has_moon_availability(
            items
        ):
            zones = [
                refine_multi_kingdom_progression(
                    kingdom=kingdom,
                    prog=zones[0],
                    template=template,
                    goal_text=goal_text,
                    threshold=value,
                    items=items,
                    multi_kingdom=multi_kingdom,
                    weighted=weighted,
                )
            ]

        def _emit(kingdom_v: str, prog_v: str | list[str]) -> None:
            lo = lockout_prog
            if lockout_inverted_vs_progression(prog_v, lo):
                lo = prog_v
            rows.append(
                {
                    "goal": goal_text,
                    "kingdom": kingdom_v,
                    "progression": prog_v,
                    "lockout": lo,
                }
            )

        if not kingdom:
            if len(zones) == 1:
                _emit("", zones[0])
            elif goal_text in WARP_PAINTING_KEEP_ENTRANCE_PROG and zones:
                _emit("", compact_progression_value(zones))
            else:
                _emit("", "")
            continue

        if not curated_prog:
            zones = expand_zones_for_kingdom(
                kingdom, zones, template_prog=template_prog
            )
        if not zones:
            k2, prog = kingdom, ""
            if not curated:
                k2, prog = resolve_blank_progression(
                    kingdom,
                    "",
                    goal_text=goal_text,
                    template_prog=template_prog,
                    n_range=n_range,
                    template_has_mapped_prog=mapped_any,
                )
            _emit(k2, prog)
            continue

        final: list[str] = []
        k2 = kingdom
        for prog in zones:
            prog = clamp_prog_to_kingdom_border(
                kingdom, prog, curated=curated or curated_prog
            )
            if not curated and not prog:
                k2, prog = resolve_blank_progression(
                    kingdom,
                    "",
                    goal_text=goal_text,
                    template_prog=template_prog,
                    n_range=n_range,
                    template_has_mapped_prog=mapped_any,
                )
            if prog and prog not in final:
                final.append(prog)
        if not final:
            _emit(k2, "")
        else:
            _emit(k2, compact_progression_value(final))
    return rows


def individuales_by_template(templates: list[dict]) -> dict[str, list[dict]]:
    """Mapa template Combined → filas individuales compactas."""
    out: dict[str, list[dict]] = {}
    for g in sorted(templates, key=lambda x: int(x.get("orden") or 0)):
        rows = build_template_individual_rows(g)
        if rows:
            out[str(g["goal"])] = rows
    return out


def main() -> None:
    data = load_catalog(SRC)
    templates = sorted(data["goals"], key=lambda g: int(g.get("orden") or 0))
    goals: list[dict] = []
    for g in templates:
        goals.extend(build_template_individual_rows(g))

    groups = build_groups(goals)
    flat = flatten_goals(groups)

    out = {
        "_definition": (
            "Goals individuales por reino (id=cap/sand/…) o blank_reino "
            "(blank_progresion reservado si reino sin progression), más índices "
            "early/mid/late/endgame (e/m/l/n) "
            "con las goals (reino o blank) cuya progression toca esa zona. "
            "Grupos en alfa con orden 1..G. n_goals = goals únicas "
            "(sin contar duplicados de zona). "
            "blank_*/zona → goal+kingdom+progression+lockout; "
            "reino → goal+progression+lockout. "
            "progression = avail→borde (catálogo); lockout = "
            "emparejado Lockout progressive_ranges del Combined (str o lista "
            "si overlap; p. ej. Cheep m/l/l vs m/[m,l]/l). "
            "Con reino, overlap en progression → lista. "
            "Sin reino → blank_reino (totales/globales y multi-zona). "
            "blank_reino no se duplica en grupos de reino. "
            "Multi-reino con max(range) < pool → kingdom blank; "
            "max(range)==pool sella el último umbral blank al reino final. "
            "Warp-Painting entrada ambigua → blank_reino + progression lista."
        ),
        "_source": "Catalog/goals_referencia.json",
        "n_templates": len(data["goals"]),
        "n_groups": len(groups),
        "n_goals": len(flat),
        "groups": groups,
    }
    write_catalog_json(OUT, out)
    print(f"wrote {OUT}")
    print(f"groups={len(groups)} goals={len(flat)}")
    from enrich_goals_referencia import enrich_referencia_with_individuales

    n = enrich_referencia_with_individuales()
    print(f"referencia hub: individuales[] en {n} templates")


if __name__ == "__main__":
    main()
