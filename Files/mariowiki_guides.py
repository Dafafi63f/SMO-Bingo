"""Caché Mario Wiki (nombre, tipo, prerequisite, descripción).

Por defecto lee ``Catalog/mariowiki_capture_guides.json`` (rápido, sin red).
Solo hace HTTP si el caché no existe o si se pasa ``refresh=True`` /
``--refresh-wiki`` en los scripts que lo usan.

Regenerar caché:
  python Files/mariowiki_guides.py --refresh
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from html import unescape
from pathlib import Path

from catalog_lib import (
    CATALOG_DIR,
    KINGDOM_COLUMNS,
    KINGDOM_DISPLAY,
    register_cache_clear,
    write_catalog_json,
)

USER_AGENT = "BingoMoonTagger/1.1 (captures/cappy; +https://www.mariowiki.com)"
GUIDES_JSON = CATALOG_DIR / "mariowiki_capture_guides.json"

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
    "ruined": "https://www.mariowiki.com/List_of_Power_Moons_in_the_Ruined_Kingdom",
}

_GUIDES_MEM: dict[str, dict[int, dict[str, str]]] | None = None


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read().decode("utf-8", "replace")


def strip_tags(html: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _extract_wikitable_body(html: str) -> str | None:
    lower = html.lower()
    pos = 0
    while True:
        marker = lower.find("wikitable", pos)
        if marker < 0:
            return None
        table_open = lower.rfind("<table", 0, marker)
        if table_open < 0:
            pos = marker + 1
            continue
        gt = lower.find(">", table_open)
        if gt < 0 or "wikitable" not in lower[table_open:gt]:
            pos = marker + 1
            continue
        end = lower.find("</table>", gt)
        if end < 0:
            return None
        return html[gt + 1 : end]


def _parse_mariowiki_row(cells: list[str]) -> tuple[int, dict[str, str]] | None:
    if len(cells) < 3:
        return None
    num_match = re.match(r"(\d+)", strip_tags(cells[0]))
    if not num_match:
        return None
    moon = int(num_match.group(1))
    # Tabla wiki: # | imagen | nombre | tipo | prerequisite | descripción
    if len(cells) >= 6:
        name = strip_tags(cells[2])
        moon_type = strip_tags(cells[3])
        prerequisite = strip_tags(cells[4])
        description = strip_tags(cells[5])
    elif len(cells) >= 5:
        name = strip_tags(cells[2])
        moon_type = strip_tags(cells[3])
        prerequisite = ""
        description = strip_tags(cells[4])
    else:
        name = strip_tags(cells[2] if len(cells) >= 4 else cells[1])
        moon_type = ""
        prerequisite = ""
        description = strip_tags(cells[3] if len(cells) >= 4 else cells[2])
    name = name.rstrip("❸②①").strip()
    return moon, {
        "name": name,
        "type": moon_type,
        "prerequisite": prerequisite,
        "description": description,
    }


def parse_mariowiki_table(html: str) -> dict[int, dict[str, str]]:
    table_html = _extract_wikitable_body(html)
    if table_html is None:
        return {}

    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, flags=re.S | re.I)
    result: dict[int, dict[str, str]] = {}
    for row in rows[1:]:
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)
        parsed = _parse_mariowiki_row(cells)
        if parsed is None:
            continue
        moon, data = parsed
        result[moon] = data
    return result


def _guides_to_json(guides: dict[str, dict[int, dict[str, str]]]) -> dict:
    kingdoms = {
        kingdom: {str(moon): data for moon, data in sorted(table.items())}
        for kingdom, table in sorted(guides.items())
        if table
    }
    n_moons = sum(len(v) for v in kingdoms.values())
    return {
        "_definition": (
            "Caché local de tablas Mario Wiki (nombre, tipo, prerequisite, "
            "descripción) para availability y capturas/cappy sin red."
        ),
        "_note": "Regenerar: python Files/mariowiki_guides.py --refresh",
        "n_kingdoms": len(kingdoms),
        "n_moons": n_moons,
        **kingdoms,
    }


def _guides_from_json(raw: dict) -> dict[str, dict[int, dict[str, str]]]:
    guides: dict[str, dict[int, dict[str, str]]] = {}
    for kingdom, table in raw.items():
        if str(kingdom).startswith("_") or not isinstance(table, dict):
            continue
        parsed: dict[int, dict[str, str]] = {}
        for num, value in table.items():
            try:
                moon = int(num)
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                parsed[moon] = {
                    "name": str(value.get("name") or ""),
                    "type": str(value.get("type") or ""),
                    "prerequisite": str(value.get("prerequisite") or ""),
                    "description": str(value.get("description") or ""),
                }
        guides[kingdom] = parsed
    return guides


def merge_legacy_wiki_meta(
    guides: dict[str, dict[int, dict[str, str]]],
    legacy_path: Path,
) -> dict[str, dict[int, dict[str, str]]]:
    """Fusiona type/prerequisite (y nombre) desde un JSON wiki legado opcional."""
    if not legacy_path.is_file():
        return guides
    raw = json.loads(legacy_path.read_text(encoding="utf-8"))
    merged = {k: dict(v) for k, v in guides.items()}
    for kingdom, moons in raw.items():
        if str(kingdom).startswith("_") or not isinstance(moons, dict):
            continue
        table = dict(merged.get(kingdom, {}))
        for num, value in moons.items():
            try:
                moon = int(num)
            except (TypeError, ValueError):
                continue
            entry = dict(table.get(moon, {}))
            if isinstance(value, str):
                if value and not entry.get("name"):
                    entry["name"] = value
            else:
                for field in ("name", "type", "prerequisite"):
                    legacy_val = str(value.get(field) or "")
                    if legacy_val and not entry.get(field):
                        entry[field] = legacy_val
            table[moon] = entry
        merged[kingdom] = table
    return merged


def fetch_capture_guides_from_network(
    *,
    quiet: bool = False,
    sleep_s: float = 0.25,
) -> dict[str, dict[int, dict[str, str]]]:
    guides: dict[str, dict[int, dict[str, str]]] = {}
    for kingdom in KINGDOM_COLUMNS:
        url = MARIOWIKI_URLS.get(kingdom)
        if not url:
            guides[kingdom] = {}
            continue
        if not quiet:
            print(f"  Mario Wiki: {KINGDOM_DISPLAY.get(kingdom, kingdom)}...")
        try:
            guides[kingdom] = parse_mariowiki_table(fetch(url))
        except Exception as exc:  # noqa: BLE001
            if not quiet:
                print(f"    AVISO: {exc}")
            guides[kingdom] = {}
        if sleep_s > 0:
            time.sleep(sleep_s)
    return guides


def write_capture_guides_cache(
    guides: dict[str, dict[int, dict[str, str]]],
    path: Path | None = None,
) -> Path:
    path = path or GUIDES_JSON
    write_catalog_json(path, _guides_to_json(guides))
    return path


def refresh_capture_guides(*, quiet: bool = False) -> dict[str, dict[int, dict[str, str]]]:
    """Descarga wiki, escribe caché y devuelve las guías."""
    global _GUIDES_MEM
    guides = fetch_capture_guides_from_network(quiet=quiet)
    write_capture_guides_cache(guides)
    _GUIDES_MEM = guides
    return guides


def clear_capture_guides_cache() -> None:
    global _GUIDES_MEM
    _GUIDES_MEM = None


def load_capture_guides(
    *,
    refresh: bool = False,
    quiet: bool = True,
) -> dict[str, dict[int, dict[str, str]]]:
    """Guías en memoria; por defecto desde JSON local (sin HTTP)."""
    global _GUIDES_MEM
    if refresh:
        return refresh_capture_guides(quiet=quiet)
    if _GUIDES_MEM is not None:
        return _GUIDES_MEM
    if GUIDES_JSON.is_file():
        raw = json.loads(GUIDES_JSON.read_text(encoding="utf-8"))
        _GUIDES_MEM = _guides_from_json(raw)
        return _GUIDES_MEM
    if not quiet:
        print(f"Sin caché en {GUIDES_JSON.name}; descargando Mario Wiki…")
    return refresh_capture_guides(quiet=quiet)


register_cache_clear(clear_capture_guides_cache)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Forzar descarga Mario Wiki y reescribir el JSON de caché.",
    )
    args = parser.parse_args()
    guides = load_capture_guides(refresh=args.refresh, quiet=False)
    n = sum(len(t) for t in guides.values())
    print(f"\nGuias: {len(guides)} reinos, {n} lunas -> {GUIDES_JSON.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
