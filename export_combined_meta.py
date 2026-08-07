"""Exports de metadata "plana" de Combined + remapeo de iconos unicos.

Subcomandos (todos leen Combined y escriben en catalog/):
  lineas       -> bingo_lineas.json (categorias board/line)
  icons        -> goal_icons.json (inventario iconos SMO)
  tooltips     -> goal_tooltips.json (tooltips unicos)
  all (default)-> lineas + icons + tooltips

Remap de iconos (1 goal -> 1 icono oficial cuando el nombre/tema encaja).
No toca familias sin variante por reino/tema (Moon Rocks, Talkatoos, Shop
Moons, Hint Arts, etc.). Souvenirs/Stickers y Fire Bro / Hammer Bro / Pixel Cat
Marios-Peaches mantienen rotacion multi-icono (no estan en el mapa):

  python export_combined_meta.py --remap          # dry-run
  python export_combined_meta.py --remap --apply  # escribe Combined + regenera icons

Usage:
  python export_combined_meta.py [lineas|icons|tooltips|all]
  python export_combined_meta.py --remap [--apply]
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from catalog_lib import (
    CATALOG_DIR,
    JSON_PATH,
    load_combined_objectives_by_goal,
    objective_ref_from_combined,
    write_catalog_json,
)

ROOT = Path(__file__).parent


def _uniq(goals: list[str]) -> list[str]:
    return list(dict.fromkeys(goals))


# ---------------------------------------------------------------------------
# lineas: inventario de categorias bingo (board) y linea (line) de Combined.
# ---------------------------------------------------------------------------

LINEAS_OUT_JSON = CATALOG_DIR / "bingo_lineas.json"

# Concepto unico -> (clave_board, clave_line) cuando el nombre difiere.
# Combined unifica singular/plural (checkpoints, storymoons, subarea,
# regionalcoins) en el mismo slug en ambos lados; lista vacia.
# boss/multimoons → storymoons; outfitdoor → subarea.
BOARD_LINE_PAIRS: list[tuple[str, str, str]] = []



def _pair_lookup() -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, str]]]:
    board_to: dict[str, str] = {}
    line_to: dict[str, str] = {}
    pairs: dict[str, dict[str, str]] = {}
    for concepto, b, l in BOARD_LINE_PAIRS:
        board_to[b] = concepto
        line_to[l] = concepto
        pairs[concepto] = {"board": b, "line": l}
    return board_to, line_to, pairs


def export_lineas() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    limits = data.get("limits") or {}
    board_limits: dict[str, int] = dict(limits.get("board") or {})
    line_limits: dict[str, int] = dict(limits.get("line") or {})
    combined = load_combined_objectives_by_goal(include_disabled=True)

    board_goals: dict[str, list[str]] = defaultdict(list)
    line_goals: dict[str, list[str]] = defaultdict(list)
    board_disabled: dict[str, list[str]] = defaultdict(list)
    line_disabled: dict[str, list[str]] = defaultdict(list)

    for obj in data.get("objectives") or []:
        goal = str(obj.get("goal") or "")
        disabled = bool(obj.get("disabled"))
        for cat in obj.get("board_categories") or []:
            key = str(cat)
            (board_disabled if disabled else board_goals)[key].append(goal)
        for cat in obj.get("line_categories") or []:
            key = str(cat)
            (line_disabled if disabled else line_goals)[key].append(goal)

    board_to, line_to, pairs = _pair_lookup()
    all_board = set(board_limits) | set(board_goals) | set(board_disabled)
    all_line = set(line_limits) | set(line_goals) | set(line_disabled)

    group_sides: dict[str, dict[str, str | None]] = {}
    for key in all_board:
        gid = board_to.get(key, key)
        side = group_sides.setdefault(gid, {"board": None, "line": None})
        side["board"] = key
    for key in all_line:
        gid = line_to.get(key, key)
        side = group_sides.setdefault(gid, {"board": None, "line": None})
        side["line"] = key

    groups: list[dict] = []
    for orden, gid in enumerate(sorted(group_sides), start=1):
        side = group_sides[gid]
        board_key = side.get("board")
        line_key = side.get("line")

        active: list[str] = []
        disabled: list[str] = []
        if board_key:
            active.extend(board_goals.get(str(board_key), []))
            disabled.extend(board_disabled.get(str(board_key), []))
        if line_key:
            active.extend(line_goals.get(str(line_key), []))
            disabled.extend(line_disabled.get(str(line_key), []))
        active = _uniq(active)
        disabled = _uniq([g for g in disabled if g not in set(active)])

        objectives = [
            objective_ref_from_combined(goal, combined.get(goal)) for goal in active
        ]
        for goal in disabled:
            ref = objective_ref_from_combined(goal, combined.get(goal))
            ref["disabled"] = True
            objectives.append(ref)

        group: dict = {
            "id": gid,
            "orden": orden,
            "n_goals": len(active),
            "objectives": objectives,
        }
        if board_key:
            group["board"] = board_key
            if board_key in board_limits:
                group["limit_board"] = board_limits[str(board_key)]
        if line_key:
            group["line"] = line_key
            if line_key in line_limits:
                group["limit_line"] = line_limits[str(line_key)]
        if disabled:
            group["n_disabled"] = len(disabled)
            group["goals_disabled"] = disabled
        if gid in pairs:
            group["pair"] = pairs[gid]
        groups.append(group)

    catalog = {
        "_definition": (
            "Inventario board/line de Combined: por cada categoria, "
            "n_goals y objectives[] ({goal, range, progression}). "
            "Cats/icons/tooltip → bingo_lineas (este archivo) / goal_icons / "
            "goals_referencia. No son tags de luna ni pools de moons. "
            "orden = 1..N tras ordenar por id (slug). "
            "Cada cat existe en board y line (mismo slug)."
        ),
        "_note": (
            "Campos: id, orden (1..N alfa), n_goals, "
            "objectives[{goal,range,progression,…}], board/line, "
            "limit_board/limit_line, pair (si claves difieren), "
            "n_disabled/goals_disabled. "
            "objectives desactivados llevan disabled=true."
        ),
        "n_categories": len(groups),
        "groups": groups,
    }
    write_catalog_json(LINEAS_OUT_JSON, catalog)

    print(
        f"Exportado: {LINEAS_OUT_JSON.relative_to(ROOT)} "
        f"({len(groups)} categories)"
    )


# ---------------------------------------------------------------------------
# icons: inventario de iconos SMO (oficiales lockout + uso en Combined).
# ---------------------------------------------------------------------------

ICONS_OUT_JSON = CATALOG_DIR / "goal_icons.json"
LOCKOUT_SMO_MANIFEST = "https://lockout.live/manifests/smo.json"


def fetch_official_smo_icons() -> list[str] | None:
    """Lista oficial smo/*.webp desde lockout.live; None si falla la red."""
    req = urllib.request.Request(
        LOCKOUT_SMO_MANIFEST,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; BingoCatalog/1.0; "
                "+https://lockout.live)"
            ),
            "Referer": "https://lockout.live/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        print(f"AVISO: no se pudo leer manifest oficial SMO ({exc})")
        return None
    images = data.get("images") if isinstance(data, dict) else None
    if not isinstance(images, list):
        print("AVISO: manifest SMO sin images[]")
        return None
    return sorted(f"smo/{name}" for name in images if isinstance(name, str) and name)


def export_icons() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    by_icon: dict[str, list[str]] = defaultdict(list)
    by_icon_disabled: dict[str, list[str]] = defaultdict(list)
    no_icon: list[str] = []
    no_icon_disabled: list[str] = []

    for obj in data.get("objectives") or []:
        goal = str(obj.get("goal") or "")
        if not goal:
            continue
        disabled = bool(obj.get("disabled"))
        icons = [str(i) for i in (obj.get("icons") or []) if i]
        if not icons:
            (no_icon_disabled if disabled else no_icon).append(goal)
            continue
        for icon in icons:
            (by_icon_disabled if disabled else by_icon)[icon].append(goal)

    used_icons = set(by_icon) | set(by_icon_disabled)
    official = fetch_official_smo_icons()
    if official is not None:
        all_icons = list(official)
        extra = sorted(used_icons - set(official))
        if extra:
            print(f"AVISO: {len(extra)} icons en Combined fuera del manifest")
            all_icons.extend(extra)
    else:
        all_icons = sorted(used_icons)

    icons_out: list[dict] = []
    goals_with_icon: set[str] = set()
    n_unused = 0
    for orden, icon in enumerate(all_icons, start=1):
        active = _uniq(by_icon.get(icon, []))
        disabled = _uniq(
            [g for g in by_icon_disabled.get(icon, []) if g not in set(active)]
        )
        goals_with_icon.update(active)
        entry: dict = {
            "icon": icon,
            "orden": orden,
            "n_goals": len(active),
            "goals": active,
        }
        if disabled:
            entry["n_disabled"] = len(disabled)
            entry["goals_disabled"] = disabled
        if not active and not disabled:
            n_unused += 1
        icons_out.append(entry)

    catalog: dict = {
        "_definition": (
            "Inventario completo de iconos SMO: icons[] mezcla usados en "
            "Combined y oficiales lockout aun sin goal (n_goals=0, ideas "
            "futuras). Fuente oficial: lockout.live/manifests/smo.json. "
            "orden = 1..N alfa por path. Una goal con varias icons cuenta "
            "en todas. Range/progression → goals_referencia / Combined."
        ),
        "_note": (
            "Campos: icon, orden, n_goals, goals[]. "
            "n_disabled/goals_disabled si hay objectives desactivados. "
            "n_official / n_used / n_unused = conteos. "
            "no_icon = goals Combined sin icons[]."
        ),
        "n_icons": len(icons_out),
        "n_used": len(used_icons),
        "n_unused": n_unused,
        "n_goals_with_icon": len(goals_with_icon),
        "icons": icons_out,
    }
    if official is not None:
        catalog["n_official"] = len(official)
    if no_icon:
        catalog["no_icon"] = {
            "n_goals": len(no_icon),
            "goals": no_icon,
        }
    if no_icon_disabled:
        catalog["no_icon_disabled"] = {
            "n_goals": len(no_icon_disabled),
            "goals": no_icon_disabled,
        }

    write_catalog_json(ICONS_OUT_JSON, catalog)
    shared = sum(1 for e in icons_out if e["n_goals"] > 1)
    print(
        f"Exportado: {ICONS_OUT_JSON.relative_to(ROOT)} "
        f"({len(icons_out)} icons, {len(used_icons)} used, "
        f"{n_unused} unused, {shared} compartidos)"
    )


# ---------------------------------------------------------------------------
# tooltips: inventario de tooltips unicos de Combined (para revision).
# ---------------------------------------------------------------------------

TOOLTIPS_OUT_JSON = CATALOG_DIR / "goal_tooltips.json"


def export_tooltips() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    objectives = list(data.get("objectives") or [])

    counts: Counter[str] = Counter()
    n_goals = 0
    no_tooltip: list[str] = []

    for obj in objectives:
        goal = str(obj.get("goal") or "")
        if not goal:
            continue
        n_goals += 1
        tip = obj.get("tooltip")
        tip_s = str(tip).strip() if tip is not None else ""
        if not tip_s:
            no_tooltip.append(goal)
            continue
        counts[tip_s] += 1

    tips_out: list[dict] = [
        {"tooltip": tip, "n_goals": n}
        for tip, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    ]

    catalog: dict = {
        "_definition": (
            "Tooltips unicos de Combined (mismo texto → muchas goals). "
            "Solo tooltips[]; sin lista de goals. Editar en Combined y "
            "regenerar (export_combined_meta tooltips / regenerate_all)."
        ),
        "_note": (
            "Campos tooltips[]: tooltip, n_goals (cuantas goals lo reusan). "
            "n_unique / n_goals / n_missing = conteos."
        ),
        "n_unique": len(tips_out),
        "n_goals": n_goals,
        "n_missing": len(no_tooltip),
        "tooltips": tips_out,
    }
    if no_tooltip:
        catalog["no_tooltip"] = sorted(no_tooltip)

    write_catalog_json(TOOLTIPS_OUT_JSON, catalog)
    print(
        f"Exportado: {TOOLTIPS_OUT_JSON.relative_to(ROOT)} "
        f"({len(tips_out)} tooltips unicos / {n_goals} goals"
        f"{f', {len(no_tooltip)} sin tooltip' if no_tooltip else ''})"
    )


# ---------------------------------------------------------------------------
# remap: reasigna icons Combined: 1 goal → 1 icono unico cuando hay icono
# oficial coherente.
# ---------------------------------------------------------------------------

# goal → icon. Combined es fuente de verdad (edicion manual).
# Remap solo sugiere defaults; --remap NO pisa icons ya puestos en Combined.
# Regionals: purple*/regional* (no icono de la goal de lunas hermana).
# Multi-icon (8-Bit Regional, Switch Moons, Hybrid 2D, …) no van aqui.
GOAL_ICON_REMAP: dict[str, str] = {
    # Capturas / enemigos
    "{{X}} Goomba Moon[[s]]": "smo/moongoomba.webp",
    "{{X}} Snow Goomba Moons": "smo/moongoomba.webp",
    "{{X}} Paragoomba Moons": "smo/captureparagoomba.webp",
    "{{X}} Cascade Chain Chomp Moons": "smo/capturechainchomp.webp",
    "Capture Big Chain Chomp": "smo/capturebigchainchomp.webp",
    "{{X}} Bullet Bill Moons": "smo/capturebulletbill.webp",
    "{{X}} Sand Moe-Eye Moons": "smo/capturemoe-eye.webp",
    "{{X}} Glydon Moon[[s]]": "smo/captureglydon.webp",
    "{{X}} Sherm Moons": "smo/capturesherm.webp",
    "{{X}} Wooded Uproot Moons": "smo/captureuproot.webp",
    "{{X}} Seaside Uproot Moons": "smo/captureuproot.webp",
    "Capture Boulder": "smo/captureboulder.webp",
    "Capture Poison Piranha Plant": "smo/capturepoisonpiranhaplant.webp",
    "{{X}} Cheep Cheep Moons": "smo/capturecheepcheep.webp",
    "{{X}} Lake Zipper Moons": "smo/capturezipper.webp",
    "{{X}} Seaside Gushen Moons": "smo/capturegushen.webp",
    "Capture Snow Cheep Cheep": "smo/capturesnowcheepcheep.webp",
    "{{X}} Luncheon Lava Bubble Moons": "smo/capturelavabubble.webp",
    "{{X}} Luncheon Fire Piranha Plant Moons": "smo/capturefirepiranhaplant.webp",
    "{{X}} Fire Bro Moon[[s]]": "smo/capturefirebro.webp",
    "{{X}} Hammer Bro Moon[[s]]": "smo/capturehammerbro.webp",
    "{{X}} Luncheon Volbonan Moons": "smo/capturevolbonan.webp",
    "{{X}} Bowser's Pokio Moons": "smo/capturepokio.webp",
    "{{X}} Bowser's Stairface Ogre Moons": "smo/moongroundpoundbowser.webp",
    "{{X}} Pokio Hole Moon[[s]]": "smo/moonpokio.webp",
    "Capture Chargin' Chuck": "smo/capturecharginchuck.webp",
    "{{X}} Moon Banzai Bill Moon[[s]]": "smo/capturebanzaibill.webp",
    "Moon Parabones Moon": "smo/captureparabones.webp",
    "Bowser Statue Moon": "smo/capturebowserstatue.webp",
    "{{X}} Lost Tropical Wiggler Moons": "smo/capturetropicalwiggler.webp",
    "{{X}} T-Rex Moons": "smo/capturetrex.webp",
    "{{X}} Spark Pylon Moons": "smo/capturepylon.webp",
    "{{X}} Mini Rocket Moons": "smo/subareamoonrocket.webp",
    "{{X}} Metro Manhole Moons": "smo/capturemanhole.webp",
    "{{X}} Metro Taxi Moons": "smo/capturetaxi.webp",
    "{{X}} Swinging Pole Moon[[s]]": "smo/capturepole.webp",
    "{{X}} Metro Motor Scooter Moon[[s]]": "smo/moonscooter.webp",
    "{{X}} Snow Shiverian Racer Moon[[s]]": "smo/captureshiverianracer.webp",
    "{{X}} Snow Ty-Foo Moons": "smo/capturetyfoo.webp",
    "{{X}} Lakitu-Fishing Moon[[s]]": "smo/moonfishing.webp",
    "{{X}} Poochy Moon[[s]]": "app-game-icons/sniffing-dog.webp",
    "{{X}} Dog Moon[[s]]": "smo/moondog.webp",
    "Capture {{X}} Binoculars": "smo/capturebinoculars.webp",
    "{{X}} Cactus/Tree Moons": "smo/cactustree.webp",
    "{{X}} Cap Frog Moons": "smo/capturefrog.webp",
    "{{X}} Flora Moons": "mkwo/fire_flower.webp",
    "{{X}} Metro RC Car Moons": "smo/moonrccar.webp",
    "{{X}} Bowser's Jizo Moons": "smo/moonjizo.webp",
    "{{X}} Moon Rocks": "smo/moonrock.webp",
    "{{X}} Seaside Komboo Moons": "smo/souvenir6.webp",
    "Mushroom Warp-Painting Moon": "smo/moonpaintingmushroom.webp",
    "{{X}} Unique Captures": "smo/captures.webp",
    "{{X}} Cap Moons": "smo/mooncap.webp",
    "{{X}} Cascade Moons": "smo/mooncascade.webp",
    "{{X}} Lake Moons": "smo/moonlake.webp",
    "{{X}} Sand Moons": "smo/moonsand.webp",
    "{{X}} Wooded Moons": "smo/moonwooded.webp",
    "{{X}} Lost Moons": "smo/moonlost.webp",
    "{{X}} Metro Moons": "smo/moonmetro.webp",
    "{{X}} Snow Moons": "smo/moonsnow.webp",
    "{{X}} Seaside Moons": "smo/moonseaside.webp",
    "{{X}} Luncheon Moons": "smo/moonluncheon.webp",
    "{{X}} Ruined Moons": "smo/moonruined.webp",
    "{{X}} Bowser's Moons": "smo/moonbowser.webp",
    "{{X}} Moon Moons": "smo/moonmoon.webp",
    # Sub-areas
    "{{X}} Cap Sub-Area Moons": "smo/subareamooncap.webp",
    "{{X}} Cascade Sub-Area Moons": "smo/subareamooncascade.webp",
    "{{X}} Lake Sub-Area Moons": "smo/subareamoonlake.webp",
    "{{X}} Wooded Sub-Area Moons": "smo/subareamoonwooded.webp",
    "{{X}} Metro Sub-Area Moons": "smo/subareamoonmetro.webp",
    "{{X}} Snow Sub-Area Moons": "smo/subareamoonsnow.webp",
    "{{X}} Seaside Sub-Area Moons": "smo/subareamoonseaside.webp",
    "{{X}} Luncheon Sub-Area Moons": "smo/subareamoonluncheon.webp",
    "{{X}} Sand Sub-Area Moons": "smo/subareamoonsand.webp",
    "{{X}} Bowser's Sub-Area Moons": "smo/subareamoonbowser.webp",
    # 8-bit / pixels
    "{{X}} Pixel Luigis": "smo/pixelluigi.webp",
    "Metro Festival Moon": "smo/moonpauline.webp",
    # Seeds / flora (plantedseed{reino} no: goals cruzan reinos)
    "{{X}} Bloom Flower Moon[[s]]": "smo/moonflowerbloom.webp",
    "{{X}} Wooded Flower Road Moons": "mkwo/flower_cup.webp",
    "{{X}} Nature Moons": "smo/souvenir5.webp",
    "{{X}} Seeds Planted": "smo/plantedseed.webp",
    "{{X}} Seed Moon (No Time Travel)": "smo/moonseed.webp",
    "{{X}} Special Seed Moon[[s]]": "smo/moonseed.webp",
    "{{X}} Rocket Flower Moons": "dkbananza/banana_bloomintone.webp",
    "Purchase {{X}} Costume Sets": "smo/outfits.webp",
    "Purchase {{X}} Hats": "smo/hats.webp",
    # Chests
    "{{X}} Cage Moon[[s]]": "smo/mooncage.webp",
    # GP / lurker
    "{{X}} Ground Pound Moons": "smo/moongroundpound.webp",
    "{{X}} Lurker/Rumble Moon[[s]]": "smo/moonenemydefeat.webp",
    "{{X}} Critter Moons": "smo/lifeupgoomba.webp",
    "Activate {{X}} Ground-Pound Switch[[es]]": "smgalaxy/groundpound_switch.webp",
    "Activate {{X}} P-Switch[[es]]": "mkwo/p_switch.webp",
    # Cap / Cappy (hats.webp = Purchase Hats)
    "{{X}} Cappy Moons": "smo/moonhatspin.webp",
    "{{X}} Mario Moons": "smo/moonmatch2.webp",
    "Save Cappy From Klepto": "sm64/klepto_ssl.webp",
    # Bosses / story / refights
    "Defeat Bowser in Cloud Kingdom": "smo/refightbowser.webp",
    "Defeat Madame Broode in Moon Kingdom": "smo/broodals.webp",
    "Defeat Ruined Dragon": "smo/refightdragon.webp",
    "{{X}} Wooded Story Moon[[s]]": "smo/storywooded.webp",
    "{{X}} Bowser's Story Moons": "smo/storybowser.webp",
    "{{X}} Roulette Tower Moons": "smo/subareamoonruined.webp",
    # Temas por reino
    "{{X}} Metro Night Moons": "smo/moondark.webp",
    "{{X}} Metro Girder Moon[[s]]": "smo/kingdommetro.webp",
    "{{X}} Metro Trash Moon[[s]]": "app-iso/trash-can.webp",
    "{{X}} Snow Shiveria Moons": "smo/moonshiveria.webp",
    "{{X}} Snow Overworld Moons": "smo/kingdomsnow.webp",
    "{{X}} Snow Bitefrost Moons": "smo/moongroundpoundsnow.webp",
    "{{X}} Deep Woods Regional Coins": "smo/purpledeepwoods.webp",
    "{{X}} Snow Shiveria Regional Coins": "smo/purpleshiveria.webp",
    "{{X}} Snow Overworld Regional Coins": "smo/purplesnow.webp",
    "{{X}} Cascade Chasm Lifts Moons": "totk/chasm.webp",
    "{{X}} Sand Ice Moon[[s]]": "smo/kingdomsnow.webp",
    "{{X}} Sand Ice Regional Coins": "smo/purplesand.webp",
    "{{X}} Sand Tostarena Moons": "smo/sticker3.webp",
    "{{X}} Sand Tostarena Regional Coins": "smo/purplesand.webp",
    "{{X}} Sand Ruins Moons": "smo/refightknucklotec.webp",
    "{{X}} Sand Ruins Regional Coins": "smo/purplesand.webp",
    "{{X}} Sand Oasis Moons": "smo/souvenir11.webp",
    "{{X}} Sand Pyramid Moons": "smo/kingdomsand.webp",
    "{{X}} Sand Jaxi Regional Coins": "smo/purplesand.webp",
    "{{X}} Sub-Area Regional Coins": "smo/purplemushroom.webp",
    "{{X}} Sand Bird Moons": "smo/moonbird.webp",
    "{{X}} Fauna Moons": "app-game-icons/paw-print.webp",
    "{{X}} Ledge Grab Moons": "app-game-icons/grab.webp",
    "{{X}} Dorrie Moon[[s]]": "smo/souvenir4.webp",
    "{{X}} Lost Butterfly Moons": "smo/souvenir12.webp",
    "{{X}} Lost Trapeetle Moon[[s]]": "smo/kingdomlost.webp",
    "{{X}} Seaside Maw-Ray Moon[[s]]": "smgalaxy/kingfin.webp",
    "{{X}} Wooded Pipe Moons": "smgalaxy/pipe.webp",
    "{{X}} Luncheon Lantern Moon[[s]]": "smo/moonlantern.webp",
    "{{X}} Luncheon Golden Turnip Moon[[s]]": "smo/moonturnip.webp",
    "{{X}} NPC Moons": "smo/moonhinttoad.webp",
    "{{X}} Tourist Moons": "smo/mooncapturemeet.webp",
    "{{X}} Koopa Trace-Walking Moon[[s]]": "mkwo/koopa.webp",
    "Look at {{X}} Hint-Arts": "smo/lookhintart.webp",
    # Checkpoints aggregate
    "{{X}} Total Checkpoints": "smo/checkpointnone.webp",
    "All Checkpoints in {{X}} Kingdom[[s]]": "smo/checkpointall.webp",
    # Familias sin variante / shop rotating (souvenir/sticker tambien en {{X}} Souvenirs/Stickers)
    "Call Jaxi from {{X}} Stands": "smo/jaxicall.webp",
    "{{X}} Sand Jaxi Moons": "smo/souvenir3.webp",
    "Correct Wooded Sphynx Question": "smo/sphynxquestions.webp",
    "{{X}} Sphynx Moons": "smo/sphynxquestions.webp",
    "{{X}} Timer Challenge Moons": "smo/moontimer.webp",
    "{{X}} Hidden Timer Moon[[s]]": "smo/moontimer.webp",
    "Activate {{X}} Levers": "smgalaxy/lever.webp",
    "{{X}} Key Moon[[s]]": "smo/moonkey.webp",
    "{{X}} Treasure Chest Moons": "smo/moonchest.webp",
    "{{X}} Traped Chest Moon[[s]]": "totk/chestlock.webp",
    "{{X}} Boss Fights": "smo/bosses.webp",
    "{{X}} Kingdom Boss Fight[[s]]": "smo/bosses.webp",
    # Warp-paintings por reino (hay icono moonpainting{kingdom})
    "{{X}} Warp-Painting Moons": "smo/moonpainting.webp",
    "Cascade Warp-Painting Moon": "smo/moonpaintingcascade.webp",
    "Lake Warp-Painting Moon": "smo/moonpaintinglake.webp",
    "Luncheon Warp-Painting Moon": "smo/moonpaintingluncheon.webp",
    "Metro Warp-Painting Moon": "smo/moonpaintingmetro.webp",
    "Sand Warp-Painting Moon": "smo/moonpaintingsand.webp",
    "Wooded Warp-Painting Moon": "smo/moonpaintingwooded.webp",
}


def fetch_official_icons() -> set[str]:
    req = urllib.request.Request(
        "https://lockout.live/manifests/smo.json",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    data = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return {f"smo/{n}" for n in data.get("images") or []}


def simulate_icons(obj: dict) -> list[str]:
    goal = str(obj.get("goal") or "")
    if goal in GOAL_ICON_REMAP:
        return [GOAL_ICON_REMAP[goal]]
    return list(obj.get("icons") or [])


def remap_icons(*, apply: bool) -> int:
    official = fetch_official_icons()
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    goals_in_combined = {
        str(o.get("goal") or "") for o in data.get("objectives") or []
    }

    bad = sorted({ic for ic in GOAL_ICON_REMAP.values() if ic not in official})
    if bad:
        print("ERROR: icons no oficiales:")
        for i in bad:
            print(" ", i)
        return 1

    unknown = sorted(g for g in GOAL_ICON_REMAP if g not in goals_in_combined)
    if unknown:
        print("WARN: goals del remap ausentes en Combined:")
        for g in unknown:
            print(" ", g)

    changes: list[tuple[str, list[str], list[str]]] = []
    for obj in data.get("objectives") or []:
        goal = str(obj.get("goal") or "")
        if goal not in GOAL_ICON_REMAP:
            continue
        old = list(obj.get("icons") or [])
        # Combined manual: no pisar si ya hay iconos.
        if old:
            continue
        new = [GOAL_ICON_REMAP[goal]]
        if old == new:
            continue
        changes.append((goal, old, new))
        if apply:
            obj["icons"] = new

    print(f"Cambios: {len(changes)}")
    for goal, old, new in changes:
        print(f"  {goal}\n    {old} → {new}")

    by_icon: dict[str, list[str]] = defaultdict(list)
    for obj in data.get("objectives") or []:
        if obj.get("disabled"):
            continue
        goal = str(obj.get("goal") or "")
        for i in simulate_icons(obj) if not apply else (obj.get("icons") or []):
            by_icon[str(i)].append(goal)

    shared = {i: g for i, g in by_icon.items() if len(g) > 1}
    print(f"\nResultado: {len(by_icon)} icons unicos, {len(shared)} compartidos")
    print(f"Goals en iconos compartidos: {sum(len(g) for g in shared.values())}")
    print("\nCompartidos restantes:")
    for i, g in sorted(shared.items(), key=lambda x: (-len(x[1]), x[0])):
        print(f"  {i} ({len(g)})")
        for goal in g:
            print(f"    - {goal}")

    if apply:
        JSON_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nEscrito: {JSON_PATH.relative_to(ROOT)}")
        export_icons()
        return 0

    print("\n(dry-run; pasa --apply para escribir)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["lineas", "icons", "tooltips", "all"],
        help="Export a generar (default: all = lineas+icons+tooltips).",
    )
    parser.add_argument(
        "--remap", action="store_true", help="Reasigna icons unicos (GOAL_ICON_REMAP)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Con --remap: escribe Combined y regenera goal_icons.json.",
    )
    args = parser.parse_args()

    if args.remap:
        return remap_icons(apply=args.apply)

    if args.command == "lineas":
        export_lineas()
    elif args.command == "icons":
        export_icons()
    elif args.command == "tooltips":
        export_tooltips()
    else:
        export_lineas()
        export_icons()
        export_tooltips()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
