"""Mapeo de iconos merchandising en lockout.live (souvenirs y stickers).

``id_list`` en ``goal_lists.json`` = índice del juego. Los archivos
``smo/souvenirN.webp`` del CDN **no** siguen ese índice (solo hay 1–13).
Los stickers sí: ``sticker1.webp`` … ``sticker17.webp`` en lockout.
``goal_lists`` solo lista id_list 1–11; 12–17 son postgame (Moon + Mushroom) y solo
aparecen fuera de la lista (p. ej. ``sticker17`` en Pipe Moons). Lockout admite
como máximo **12** iconos por goal: ``{{X}} Souvenirs`` rota ``souvenir1``–``12``;
``{{X}} Stickers`` rota ``sticker1``–``12`` (sin ``13``–``17``).

Dos capas para souvenirs:
- **Slot por reino** (``lists.shops``): ``souvenir1``=Cap … ``souvenir11``=Bowser
  en ``goal_lists`` y ``{{X}} Souvenirs`` (más ``souvenir12`` solo en Combined).
- **Ítem concreto** (``SOUVENIR_ICON_BY_ID_LIST``): qué archivo lockout representa
  cada ``id_list`` del juego en otras goals (p. ej. palmera→``souvenir6``).

Fuente: ``https://assets.lockout.live/smo/`` + manifest ``smo.json``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from catalog_lib import CATALOG_DIR

SOUVENIR_LOCKOUT_COUNT = 13
SOUVENIR_GAME_COUNT = 22
STICKER_LOCKOUT_COUNT = 17
STICKER_GAME_COUNT = 17
MERCH_ROTATION_ICON_LIMIT = 12
STICKER_GOAL_LISTS_COUNT = 11
STICKER_POSTGAME_ID_LISTS: frozenset[int] = frozenset(range(12, STICKER_GAME_COUNT + 1))

# lockout file N → metadatos (game_id_list = id_list en goal_lists)
SOUVENIR_BY_LOCKOUT: dict[int, dict] = {
    1: {"name": "Plush Frog", "game_id_list": 1},
    2: {"name": "Triceratops Trophy", "game_id_list": 4},
    3: {"name": "T-Rex Model", "game_id_list": 3},
    4: {"name": "Rubber Dorrie", "game_id_list": 7},
    5: {"name": "Steam Gardener Watering Can", "game_id_list": 10},
    6: {"name": "Potted Palm Tree", "game_id_list": 11},
    7: {"name": "Pauline Statue", "game_id_list": 14},
    8: {"name": "Shiverian Nesting Dolls", "game_id_list": 16},
    9: {"name": "Paper Lantern", "game_id_list": 21},
    10: {"name": "Vegetable Plate", "game_id_list": 20},
    11: {"name": "Jizo Statue", "game_id_list": 22},
    12: {"name": "Butterfly Mobile / Inverted Pyramid display", "game_id_list": (6, 12)},
    13: {"name": "New Donk City Hall Model", "game_id_list": 13},
}

SOUVENIR_MISSING_ID_LISTS: frozenset[int] = frozenset({2, 5, 8, 9, 15, 17, 18, 19})

SOUVENIR_MISSING: tuple[dict[str, int | str], ...] = (
    {"game_id_list": 2, "name": "Bonneton Tower Model"},
    {"game_id_list": 5, "name": "Jaxi Statue"},
    {"game_id_list": 8, "name": "Underwater Dome"},
    {"game_id_list": 9, "name": "Flowers from Steam Gardens"},
    {"game_id_list": 15, "name": "Shiverian Rug"},
    {"game_id_list": 17, "name": "Glass Tower Model"},
    {"game_id_list": 18, "name": "Sand Jar"},
    {"game_id_list": 19, "name": "Souvenir Forks"},
)

# id_list del juego → icono lockout (None = sin asset en CDN)
SOUVENIR_ICON_BY_ID_LIST: dict[int, str | None] = {
    1: "smo/souvenir1.webp",
    2: None,
    3: "smo/souvenir3.webp",
    4: "smo/souvenir2.webp",
    5: None,
    6: "smo/souvenir12.webp",
    7: "smo/souvenir4.webp",
    8: None,
    9: None,
    10: "smo/souvenir5.webp",
    11: "smo/souvenir6.webp",
    12: "smo/souvenir12.webp",
    13: "smo/souvenir13.webp",
    14: "smo/souvenir7.webp",
    15: None,
    16: "smo/souvenir8.webp",
    17: None,
    18: None,
    19: None,
    20: "smo/souvenir10.webp",
    21: "smo/souvenir9.webp",
    22: "smo/souvenir11.webp",
}

# Crazy Cap por reino (lists.shops) → souvenirN en lockout y ``{{X}} Souvenirs``.
SOUVENIR_SHOP_KINGDOMS: tuple[str, ...] = (
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
    "bowser",
)
SOUVENIR_KINGDOM_FILE: dict[str, int] = {
    kingdom: index for index, kingdom in enumerate(SOUVENIR_SHOP_KINGDOMS, start=1)
}

# id_list en goal_lists que lleva el icon del slot lockout del reino.
# Si un ítem tiene asset lockout propio (SOUVENIR_ICON_BY_ID_LIST), ese manda;
# si no, el primer barato del reino (p. ej. Sand Jaxi → souvenir3).
SOUVENIR_GOAL_LIST_ICON_BY_KINGDOM: dict[str, int] = {
    "cap": 1,       # 5 — Plush Frog
    "cascade": 4,   # 25 — Triceratops (souvenir2)
    "sand": 5,      # 5 — Jaxi (sin asset propio; slot souvenir3)
    "lake": 7,      # 5 — Dorrie
    "wooded": 10,   # 25 — Watering Can (souvenir5)
    "lost": 11,     # 5 — Potted Palm Tree (souvenir6)
    "metro": 14,    # 25 — Pauline Statue (souvenir7)
    "snow": 16,     # 25 — Nesting Dolls (souvenir8)
    "seaside": 17,  # 5 — Glass Tower (sin asset; slot souvenir9)
    "luncheon": 20, # 25 — Vegetable Plate (souvenir10)
    "bowser": 22,   # 25 — Jizo (souvenir11)
}
SOUVENIR_GOAL_LIST_ICON_ID_LISTS: frozenset[int] = frozenset(
    SOUVENIR_GOAL_LIST_ICON_BY_KINGDOM.values()
)

STICKER_BY_LOCKOUT: dict[int, dict] = {
    1: {"name": "Cap Kingdom Sticker", "kingdom": "cap", "game_id_list": 1},
    2: {"name": "Cascade Kingdom Sticker", "kingdom": "cascade", "game_id_list": 2},
    3: {"name": "Sand Kingdom Sticker", "kingdom": "sand", "game_id_list": 3},
    4: {"name": "Lake Kingdom Sticker", "kingdom": "lake", "game_id_list": 4},
    5: {"name": "Wooded Kingdom Sticker", "kingdom": "wooded", "game_id_list": 5},
    6: {"name": "Lost Kingdom Sticker", "kingdom": "lost", "game_id_list": 6},
    7: {"name": "Metro Kingdom Sticker", "kingdom": "metro", "game_id_list": 7},
    8: {"name": "Snow Kingdom Sticker", "kingdom": "snow", "game_id_list": 8},
    9: {"name": "Seaside Kingdom Sticker", "kingdom": "seaside", "game_id_list": 9},
    10: {"name": "Luncheon Kingdom Sticker", "kingdom": "luncheon", "game_id_list": 10},
    11: {"name": "Bowser's Kingdom Sticker", "kingdom": "bowser", "game_id_list": 11},
    12: {"name": "Moon Kingdom Sticker", "kingdom": "moon", "game_id_list": 12, "postgame": True},
    13: {"name": "Mushroom Kingdom Sticker", "kingdom": "mushroom", "game_id_list": 13, "postgame": True},
    14: {"name": "Block Sticker", "kingdom": "mushroom", "game_id_list": 14, "postgame": True},
    15: {"name": "? Block Sticker", "kingdom": "mushroom", "game_id_list": 15, "postgame": True},
    16: {"name": "Coin Sticker", "kingdom": "mushroom", "game_id_list": 16, "postgame": True},
    17: {"name": "Pipe Sticker", "kingdom": "mushroom", "game_id_list": 17, "postgame": True},
}

STICKER_ICON_BY_ID_LIST: dict[int, str] = {
    n: f"smo/sticker{n}.webp" for n in range(1, STICKER_GAME_COUNT + 1)
}

# Catálogo kingdom para entradas en goal_lists (solo id_list 1–11).
STICKER_KINGDOM_BY_ID_LIST: dict[int, str] = {
    1: "cap",
    2: "cascade",
    3: "sand",
    4: "lake",
    5: "wooded",
    6: "lost",
    7: "metro",
    8: "snow",
    9: "seaside",
    10: "luncheon",
    11: "bowser",
}


def souvenir_icon(id_list: int) -> str | None:
    """Icono lockout del ítem concreto (goals/moons), no el slot por reino."""
    return SOUVENIR_ICON_BY_ID_LIST.get(id_list)


def souvenir_kingdom_icon(kingdom: str) -> str:
    try:
        return f"smo/souvenir{SOUVENIR_KINGDOM_FILE[kingdom]}.webp"
    except KeyError as exc:
        raise KeyError(f"reino sin slot souvenir lockout: {kingdom}") from exc


def sticker_icon(id_list: int) -> str:
    try:
        return STICKER_ICON_BY_ID_LIST[id_list]
    except KeyError as exc:
        raise KeyError(f"sticker id_list fuera de rango: {id_list}") from exc


def sticker_kingdom(id_list: int) -> str:
    try:
        return STICKER_KINGDOM_BY_ID_LIST[id_list]
    except KeyError as exc:
        raise KeyError(f"sticker id_list fuera de rango: {id_list}") from exc


def all_sticker_icons() -> list[str]:
    return [STICKER_ICON_BY_ID_LIST[i] for i in range(1, STICKER_GAME_COUNT + 1)]


def goal_list_souvenir_icons() -> list[str]:
    return [f"smo/souvenir{n}.webp" for n in range(1, MERCH_ROTATION_ICON_LIMIT + 1)]


def goal_list_sticker_icons() -> list[str]:
    """Iconos rotativos de ``{{X}} Stickers`` (tope lockout = 12)."""
    return [f"smo/sticker{n}.webp" for n in range(1, MERCH_ROTATION_ICON_LIMIT + 1)]


def naive_souvenir_icon(id_list: int) -> str:
    """Patrón incorrecto que asumía 1:1 con lockout (provoca 404 o icono erróneo)."""
    return f"smo/souvenir{id_list}.webp"


def collect_goal_lists_icon_mismatches(
    goal_lists_path: Path | None = None,
) -> list[str]:
    """Compara iconos de souvenirs/stickers en goal_lists con este mapeo."""
    path = goal_lists_path or (CATALOG_DIR / "goal_lists.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    lists = data.get("lists") or {}
    out: list[str] = []

    for entry in lists.get("stickers") or []:
        if not isinstance(entry, dict):
            continue
        id_list = int(entry["id_list"])
        if id_list in STICKER_POSTGAME_ID_LISTS:
            out.append(
                f"stickers id_list={id_list} ({entry.get('name')}): "
                "postgame; no debe estar en goal_lists"
            )
            continue
        expected = sticker_icon(id_list)
        actual = str(entry.get("icon") or "")
        if actual != expected:
            out.append(
                f"stickers id_list={id_list} ({entry.get('name')}): "
                f"icon={actual!r}, esperado {expected!r}"
            )
        expected_kingdom = sticker_kingdom(id_list)
        actual_kingdom = str(entry.get("kingdom") or "")
        if actual_kingdom != expected_kingdom:
            out.append(
                f"stickers id_list={id_list} ({entry.get('name')}): "
                f"kingdom={actual_kingdom!r}, esperado {expected_kingdom!r}"
            )

    for entry in lists.get("souvenirs") or []:
        if not isinstance(entry, dict):
            continue
        id_list = int(entry["id_list"])
        kingdom = str(entry.get("kingdom") or "")
        actual = entry.get("icon")
        if id_list not in SOUVENIR_GOAL_LIST_ICON_ID_LISTS:
            if actual:
                out.append(
                    f"souvenirs id_list={id_list} ({entry.get('name')}): "
                    f"solo un icon por reino en goal_lists; quitar {actual!r}"
                )
            continue
        expected_id = SOUVENIR_GOAL_LIST_ICON_BY_KINGDOM.get(kingdom)
        if expected_id != id_list:
            out.append(
                f"souvenirs id_list={id_list} ({entry.get('name')}): "
                f"icon solo en id_list {expected_id} del reino {kingdom!r}"
            )
            continue
        expected = souvenir_kingdom_icon(kingdom)
        if str(actual or "") != expected:
            out.append(
                f"souvenirs id_list={id_list} ({entry.get('name')}): "
                f"icon={actual!r}, esperado {expected!r}"
            )

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-goal-lists",
        action="store_true",
        help="Valida iconos en Catalog/goal_lists.json",
    )
    args = parser.parse_args()
    if args.check_goal_lists:
        mismatches = collect_goal_lists_icon_mismatches()
        if mismatches:
            for line in mismatches:
                print(line)
            return 1
        print("goal_lists: iconos souvenirs/stickers OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
