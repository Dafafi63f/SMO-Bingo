"""Inventario de tags de lunas + export de Catalog/lunas-objetivos.{json,csv}.

Dos pasos relacionados (las lunas usan las tags permitidas del inventario):
  1. tags  -> Catalog/tags_inventario.json (unica fuente de tags permitidas)
  2. lunas -> Catalog/lunas-objetivos.json (+ CSV derivado del JSON)

El CSV no es fuente de verdad: se regenera desde lunas-objetivos.json
(mismo contenido; vista ; para Excel). Formato:
id;luna;nombre;disponibilidad;tags  (tags=[reino,...] resto alfa).

Reglas de tags (incompatibles, multi-obtain, implica) viven en
catalog_lib.py (INCOMPATIBLE_TAG_PAIRS, ALLOWED_MULTI_OBTAIN,
IMPLIED_TAGS); no se duplican en el JSON. Concurrencia y resumen de
reglas: consola al regenerar. Avisos de balance van en el JSON solo
cuando aplican.

goals[] (Combined): goals relacionadas con la tag via bingo_groups
(solo las que usan >=1 luna de la tag en su pool).
moons[].goal: true si la luna cuenta para alguna de esas goals;
false si solo tiene la tag (p. ej. tag_only_moons).

Usage:
  python export_lunas_tags.py                 # tags, luego lunas (+csv)
  python export_lunas_tags.py --tags-only
  python export_lunas_tags.py --lunas-only
  python export_lunas_tags.py --csv-only      # solo CSV desde el JSON
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from catalog_lib import (
    ALLOWED_MULTI_OBTAIN,
    BINGO_GROUPS_PATH,
    CATALOG_DIR,
    IMPLIED_TAGS,
    INCOMPATIBLE_TAG_PAIRS,
    KINGDOM_COLUMNS,
    LUNAS_CATALOG_EXCLUDE,
    LUNAS_CATALOG_SYNTHETIC,
    PRIMARY_TAGS,
    ROOT,
    TAG_ACTION,
    TAG_CONTEXT,
    TAG_KINGDOM,
    TAG_OBTAIN,
    TAG_STORY,
    apply_lunas_catalog_tags,
    build_matrix_moon_registry,
    collect_allowed_moon_tags,
    collect_availability_violations,
    collect_tag_combination_violations,
    group_moon_tags,
    kingdom_availability_summary,
    load_bingo_groups,
    load_catalog,
    load_combined_objectives_by_goal,
    load_group_context_tags,
    load_kingdom_availability,
    lunas_catalog_ref,
    normalize_moon_tags,
    objective_goal_sort_key,
    rebuild_untyped_moons,
    strip_kingdom_prefix_from_id,
    write_catalog_json,
)

# ---------------------------------------------------------------------------
# tags: inventario de tags de lunas (unica fuente de tags permitidas).
# ---------------------------------------------------------------------------

TAGS_OUTPUT_JSON = CATALOG_DIR / "tags_inventario.json"
GOALS_REFERENCIA_JSON = CATALOG_DIR / "goals_referencia.json"

# Umbrales de balance (avisos en JSON solo si aplican).
RARE_MOONS = 3
COMMON_MOON_PCT = 15.0
# Top N co-ocurrencias globales al imprimir.
COOCURE_TOP_PAIRS = 15


def moon_tag_role(tag: str) -> str:
    if tag in TAG_KINGDOM:
        return "kingdom"
    if tag in TAG_CONTEXT or tag in load_group_context_tags():
        return "context"
    if tag in TAG_STORY:
        return "story"
    if tag in TAG_ACTION:
        return "action"
    if tag in TAG_OBTAIN or tag in set(PRIMARY_TAGS.values()):
        return "obtain"
    return "context"


def balance_avisos(
    *,
    lunas: int,
    pct: float,
    role: str,
    n_goals: int,
) -> list[str]:
    """Avisos de frecuencia / cobertura."""
    avisos: list[str] = []
    if lunas <= RARE_MOONS and role != "kingdom":
        avisos.append(f"rara_luna(<={RARE_MOONS})")
    if pct >= COMMON_MOON_PCT and role != "kingdom":
        avisos.append(f"muy_comun(>={COMMON_MOON_PCT:.0f}%)")
    if role == "obtain" and n_goals == 0:
        avisos.append("sin_goal_combined")
    return avisos


def _moon_sort_key(ref: dict) -> tuple:
    k = str(ref.get("kingdom") or "")
    ki = KINGDOM_COLUMNS.index(k) if k in KINGDOM_COLUMNS else 99
    return (ki, int(ref.get("moon") or 0))


def _group_related_tags(group: dict) -> set[str]:
    """Tags tematicas asociadas a un bingo_group (aunque apply_moon_tag=False)."""
    tags = set(group_moon_tags(group))
    particular = group.get("moon_tag") or group.get("tag")
    if particular:
        tags.add(str(particular))
    concrete = strip_kingdom_prefix_from_id(str(group.get("id") or ""))
    if concrete and concrete not in TAG_KINGDOM:
        tags.add(concrete)
    return {t for t in tags if t}


def _add_moons_to_goal_pool(
    out: dict[tuple[str, int], set[str]],
    goal: str,
    moons: list,
) -> None:
    for moon in moons:
        if not isinstance(moon, dict):
            continue
        if "kingdom" not in moon or "moon" not in moon:
            continue
        key = (str(moon["kingdom"]), int(moon["moon"]))
        out[key].add(goal)


def _rebuild_by_kingdom_pools(
    out: dict[tuple[str, int], set[str]], need_rebuild: list[str]
) -> None:
    from export_goals_referencia import (
        collect_membership,
        pick_moons_for_goal,
    )

    membership = collect_membership()
    registry = build_matrix_moon_registry()
    combined = load_combined_objectives_by_goal(include_disabled=True)
    for goal in need_rebuild:
        entries = membership.get(goal) or []
        if not entries:
            continue
        obj = combined.get(goal) or {}
        board = list(obj.get("board_categories") or [])
        _, moons, _ = pick_moons_for_goal(goal, entries, board, registry)
        _add_moons_to_goal_pool(out, goal, moons)


def load_moon_goal_pools() -> dict[tuple[str, int], set[str]]:
    """(kingdom, moon) → goals Combined cuyo pool moons[] incluye la luna.

    Si la goal usa by_kingdom (sin moons[]), se reconstruye el pool vía
    bingo_groups / pick_moons_for_goal.
    """
    out: dict[tuple[str, int], set[str]] = defaultdict(set)
    if not GOALS_REFERENCIA_JSON.exists():
        return out
    data = load_catalog(GOALS_REFERENCIA_JSON)
    need_rebuild: list[str] = []
    for entry in data.get("goals") or []:
        goal = str(entry.get("goal") or "")
        if not goal:
            continue
        moons = entry.get("moons") or []
        if moons:
            _add_moons_to_goal_pool(out, goal, moons)
        elif entry.get("pool") == "by_kingdom" and entry.get("n_moons"):
            need_rebuild.append(goal)

    if need_rebuild:
        _rebuild_by_kingdom_pools(out, need_rebuild)
    return out


def load_tag_related_goals() -> dict[str, set[str]]:
    """tag → goals Combined ligadas via bingo_groups."""
    out: dict[str, set[str]] = defaultdict(set)
    if not BINGO_GROUPS_PATH.exists():
        return out
    for group in load_bingo_groups():
        goals = [
            str(obj.get("goal") or "")
            for obj in (group.get("objectives") or [])
            if isinstance(obj, dict) and obj.get("goal")
        ]
        if not goals:
            continue
        for tag in _group_related_tags(group):
            out[tag].update(goals)
    return out


def _index_moons_by_tag(
    catalog_reg: dict,
    allowed: frozenset[str],
) -> tuple[dict[str, list[dict]], Counter[tuple[str, str]]]:
    moons_by_tag: dict[str, list[dict]] = {tag: [] for tag in allowed}
    pair_counts: Counter[tuple[str, str]] = Counter()
    for (kingdom, moon), entry in catalog_reg.items():
        tags = apply_lunas_catalog_tags(
            entry.get("tags") or [], kingdom=kingdom, moon=moon, allowed=allowed
        )
        ref = {
            "kingdom": kingdom,
            "moon": int(moon),
            "name": entry.get("name") or f"Moon {moon}",
            "disponibilidad": str(entry.get("availability") or "base"),
        }
        for tag in tags:
            if tag in moons_by_tag:
                moons_by_tag[tag].append(dict(ref))
        ordered = sorted(tags)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                pair_counts[(a, b)] += 1
    for tag in moons_by_tag:
        moons_by_tag[tag].sort(key=_moon_sort_key)
    return moons_by_tag, pair_counts


def _build_tag_row(
    *,
    orden: int,
    tag: str,
    moons_by_tag: dict[str, list[dict]],
    tag_goals: dict[str, set[str]],
    moon_pools: dict[tuple[str, int], set[str]],
    total_moons: int,
) -> tuple[dict, list[str] | None]:
    related_set = set(tag_goals.get(tag) or [])
    moons_out: list[dict] = []
    used_goals: set[str] = set()
    for ref in moons_by_tag.get(tag) or []:
        key = (str(ref["kingdom"]), int(ref["moon"]))
        moon_goals = (moon_pools.get(key) or set()) & related_set
        used_goals.update(moon_goals)
        entry = dict(ref)
        entry["goal"] = bool(moon_goals)
        moons_out.append(entry)

    related = sorted(used_goals, key=objective_goal_sort_key)
    lunas = len(moons_out)
    pct = (100.0 * lunas / total_moons) if total_moons else 0.0
    role = moon_tag_role(tag)
    n_goals = len(related)
    avisos = balance_avisos(lunas=lunas, pct=pct, role=role, n_goals=n_goals)
    row: dict = {
        "id": orden,
        "tag": tag,
        "rol": role,
        "lunas": lunas,
        "pct_lunas": round(pct, 1),
        "n_goals": n_goals,
        "goals": related,
        "moons": moons_out,
    }
    if avisos:
        row["avisos"] = avisos
    return row, avisos or None


def build_rows() -> tuple[list[dict], dict, frozenset[str]]:
    registry = build_matrix_moon_registry()
    catalog_reg = {
        k: v for k, v in registry.items() if k not in LUNAS_CATALOG_EXCLUDE
    }
    total_moons = len(catalog_reg)
    allowed = collect_allowed_moon_tags(catalog_reg)
    tag_goals = load_tag_related_goals()
    moon_pools = load_moon_goal_pools()
    moons_by_tag, pair_counts = _index_moons_by_tag(catalog_reg, allowed)

    rows: list[dict] = []
    avisos_by_tag: dict[str, list[str]] = {}
    for orden, tag in enumerate(sorted(allowed), start=1):
        row, avisos = _build_tag_row(
            orden=orden,
            tag=tag,
            moons_by_tag=moons_by_tag,
            tag_goals=tag_goals,
            moon_pools=moon_pools,
            total_moons=total_moons,
        )
        if avisos:
            avisos_by_tag[tag] = avisos
        rows.append(row)

    meta = {
        "total_moons": total_moons,
        "untagged_moons": sum(
            1
            for (k, m), e in catalog_reg.items()
            if not normalize_moon_tags(e.get("tags") or [], kingdom=k, moon=m) - {k}
        ),
        "n_tags": len(allowed),
        "pair_counts": pair_counts,
        "avisos_by_tag": avisos_by_tag,
    }
    return rows, meta, allowed


def write_json(path: Path, rows: list[dict]) -> None:
    payload = {
        "_definition": (
            "Inventario de tags de Power Moons in-scope. "
            "Fuente de tags permitidas para Catalog/lunas-objetivos.json. "
            "Campos: id, tag, rol, lunas, pct_lunas, n_goals, goals[] "
            "(Combined con >=1 luna de la tag en su pool), "
            "moons[{kingdom,moon,name,disponibilidad,goal}] "
            "(goal=true si cuenta para alguna de goals[]; false = solo tag), "
            "avisos (solo si aplican). "
            "Reglas incompatibles/multi/implica: catalog_lib.py. "
            "Concurrencia: consola al regenerar."
        ),
        "n_tags": len(rows),
        "tags": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_catalog_json(
        path,
        payload,
        multiline_string_list_keys=frozenset({"goals"}),
    )


def print_tag_rules() -> None:
    """Resumen de reglas canónicas (fuente: catalog_lib.py)."""
    print("\nReglas (catalog_lib.py):")
    print("  Incompatibles:")
    for pair in sorted(INCOMPATIBLE_TAG_PAIRS, key=lambda p: tuple(sorted(p))):
        print(f"    {' + '.join(sorted(pair))}")
    print("  Multi-obtain permitidas:")
    for combo in sorted(ALLOWED_MULTI_OBTAIN, key=lambda c: tuple(sorted(c))):
        print(f"    {'+'.join(sorted(combo))}")
    if IMPLIED_TAGS:
        print("  Implica:")
        for tag, req in sorted(IMPLIED_TAGS.items()):
            print(f"    {tag} → {', '.join(sorted(req))}")
    else:
        print("  Implica: (ninguna)")


def load_allowed_tags_from_inventario(path: Path | None = None) -> frozenset[str] | None:
    """Lee tags permitidas desde Catalog/tags_inventario.json (si existe)."""
    path = path or TAGS_OUTPUT_JSON
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    tags: set[str] = set()
    for row in data.get("tags") or []:
        tag = (row.get("tag") or "").strip()
        if tag:
            tags.add(tag)
    return frozenset(tags) if tags else None


def export_tags() -> frozenset[str]:
    rows, meta, allowed = build_rows()
    write_json(TAGS_OUTPUT_JSON, rows)

    legacy_csv = ROOT / "tags-inventario.csv"
    if legacy_csv.exists():
        legacy_csv.unlink()
        print(f"Eliminado: {legacy_csv.name}")

    avisos_by_tag: dict[str, list[str]] = meta["avisos_by_tag"]
    print(f"Exportado: {TAGS_OUTPUT_JSON.relative_to(ROOT).as_posix()} ({meta['n_tags']} tags)")
    print(f"Lunas en alcance: {meta['total_moons']} (solo reino: {meta['untagged_moons']})")
    print(f"Con avisos de balance: {len(avisos_by_tag)}")

    print("\nTop tags (excl. reino):")
    luna_rows = [r for r in rows if r["rol"] != "kingdom"]
    luna_rows.sort(key=lambda r: (-int(r["lunas"]), r["tag"]))
    for r in luna_rows[:20]:
        avisos = ", ".join(avisos_by_tag.get(str(r["tag"]), []))
        print(f"  {int(r['lunas']):3}  {r['tag']:20}  {r['rol']:10}  {avisos}")

    print("\nPares mas frecuentes (concurrencia):")
    pair_counts: Counter[tuple[str, str]] = meta["pair_counts"]
    for (a, b), n in pair_counts.most_common(COOCURE_TOP_PAIRS):
        print(f"  {n:3}  {a}+{b}")

    print_tag_rules()

    return allowed


# ---------------------------------------------------------------------------
# lunas: export cataloged moons with their tags (JSON + CSV derivado).
# ---------------------------------------------------------------------------

OUTPUT_LUNAS_JSON = CATALOG_DIR / "lunas-objetivos.json"
OUTPUT_LUNAS_CSV = CATALOG_DIR / "lunas-objetivos.csv"

CSV_FIELDNAMES = ["id", "luna", "nombre", "disponibilidad", "tags"]
CSV_PADDED_COLUMNS = {"id", "luna", "nombre", "disponibilidad"}
CSV_DELIMITER = ";"


def ordered_tags(kingdom: str, tags: set[str] | list[str]) -> list[str]:
    """Reino primero, resto alfabetico."""
    return [kingdom] + sorted(t for t in set(tags) if t != kingdom)


def format_tags_cell(tags: list[str]) -> str:
    """Misma forma legado: [reino,tag,...]."""
    return "[" + ",".join(tags) + "]"


def safe_nombre(name: str) -> str:
    return name.replace(", ", " - ")


def _csv_cell_text(value: object, field: str) -> str:
    if field == "nombre":
        return safe_nombre(str(value))
    return str(value)


def _csv_column_widths(rows: list[dict]) -> dict[str, int]:
    widths: dict[str, int] = {}
    for field in CSV_PADDED_COLUMNS:
        max_data = max(
            (len(_csv_cell_text(row[field], field)) for row in rows), default=0
        )
        widths[field] = max(len(field), max_data)
    return widths


def _csv_format_row(values: dict[str, object], widths: dict[str, int]) -> list[str]:
    cells: list[str] = []
    for field in CSV_FIELDNAMES:
        text = _csv_cell_text(values[field], field)
        width = widths.get(field)
        if width is not None:
            text = text.ljust(width)
        cells.append(text)
    return cells


def write_lunas_csv(path: Path, rows: list[dict]) -> None:
    """Escribe CSV legado (; + columnas alineadas)."""
    widths = _csv_column_widths(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=CSV_DELIMITER, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(
            _csv_format_row({f: f for f in CSV_FIELDNAMES}, widths)
        )
        for row in rows:
            writer.writerow(_csv_format_row(row, widths))


def moons_to_csv_rows(moons: list[dict]) -> list[dict]:
    """JSON moons[] -> filas CSV (id global; luna = nº reino; reino = tags[0])."""
    rows: list[dict] = []
    for m in moons:
        tags = list(m.get("tags") or [])
        kingdom = str(tags[0]) if tags else str(m.get("kingdom") or "")
        if kingdom and (not tags or tags[0] != kingdom):
            tags = ordered_tags(kingdom, tags)
        rows.append(
            {
                "id": int(m["id"]),
                "luna": int(m["moon"]),
                "nombre": m.get("name") or "",
                "disponibilidad": m.get("disponibilidad") or "",
                "tags": format_tags_cell(tags),
            }
        )
    return rows


def export_lunas_csv_from_json(json_path: Path | None = None) -> int:
    """Regenera Catalog/lunas-objetivos.csv leyendo el JSON (fuente)."""
    src = json_path or OUTPUT_LUNAS_JSON
    if not src.exists():
        raise FileNotFoundError(f"No existe {src}; genera el JSON antes.")
    data = json.loads(src.read_text(encoding="utf-8"))
    moons = list(data.get("moons") or [])
    rows = moons_to_csv_rows(moons)
    write_lunas_csv(OUTPUT_LUNAS_CSV, rows)
    print(
        f"Exportado: Catalog/{OUTPUT_LUNAS_CSV.name} "
        f"({len(rows)} lunas; desde {src.name})"
    )
    return len(rows)


def resolve_allowed_tags(registry: dict) -> frozenset[str]:
    """Prefer Catalog/tags_inventario.json; si no, tags del registro."""
    from_file = load_allowed_tags_from_inventario()
    if from_file is not None:
        return from_file
    return collect_allowed_moon_tags(registry)


def _print_availability_violations(violations: list) -> None:
    if not violations:
        return
    print("AVISO: disponibilidad incoherente con project.json (availability):")
    for catalog, key, issues in violations:
        for issue in issues:
            print(f"  {catalog} {key}: {issue}")
    print()


def _print_tag_violations(tag_violations: list) -> None:
    if not tag_violations:
        return
    print("AVISO: combinaciones de tags invalidas:")
    for kingdom, moon, name, issues in tag_violations:
        for issue in issues:
            print(f"  {kingdom}#{moon} ({name}): {issue}")
    print()


def _build_lunas_moon_rows(
    registry: dict, allowed: frozenset[str]
) -> tuple[list[dict], Counter[str]]:
    dropped: Counter[str] = Counter()
    moons: list[dict] = []
    rows: list[tuple[str, int, str, int, dict]] = []
    for (kingdom, moon), entry in registry.items():
        if (kingdom, int(moon)) in LUNAS_CATALOG_EXCLUDE:
            continue
        catalog_k, catalog_m = lunas_catalog_ref(kingdom, moon)
        rows.append((catalog_k, catalog_m, str(kingdom), int(moon), entry))
    rows.sort(
        key=lambda row: (
            KINGDOM_COLUMNS.index(row[0]) if row[0] in KINGDOM_COLUMNS else 99,
            row[1],
        )
    )
    for catalog_k, catalog_m, kingdom, moon, entry in rows:
        raw = set(entry.get("tags") or []) | {kingdom}
        normalized = apply_lunas_catalog_tags(raw, kingdom=kingdom, moon=moon)
        filtered = apply_lunas_catalog_tags(
            raw, kingdom=kingdom, moon=moon, allowed=allowed
        )
        for t in normalized - filtered:
            dropped[t] += 1
        moons.append(
            {
                "id": len(moons) + 1,
                "moon": int(catalog_m),
                "name": entry["name"],
                "disponibilidad": entry["availability"],
                "tags": ordered_tags(catalog_k, filtered),
            }
        )
    return moons, dropped


def _format_kingdom_availability_line(
    kingdom: str, summary: dict, rules: dict
) -> str | None:
    if kingdom not in summary:
        return None
    order = rules.get("kingdoms", {}).get(kingdom, {}).get("tier_order", [])
    parts = [f"{tier}={summary[kingdom].get(tier, 0)}" for tier in order]
    extra = [t for t in summary[kingdom] if t not in order]
    parts.extend(f"{tier}={summary[kingdom][tier]}" for tier in sorted(extra))
    pattern = rules.get("kingdoms", {}).get(kingdom, {}).get("pattern", "?")
    return f"  {kingdom} [{pattern}]: {', '.join(parts)}"


def _print_lunas_stats(
    moons: list[dict],
    allowed: frozenset[str],
    dropped: Counter[str],
    registry: dict,
    rules: dict,
) -> None:
    if dropped:
        print("AVISO: tags omitidas (no estan en inventario permitido):")
        for tag, n in sorted(dropped.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {tag}: {n} lunas")

    tag_counts: Counter[str] = Counter()
    multi = sum(1 for row in moons if len(row["tags"]) > 1)
    for row in moons:
        tag_counts.update(row["tags"])

    lunas_only = set(tag_counts) - set(allowed)
    inv_unused = set(allowed) - set(tag_counts)
    if lunas_only:
        print(f"AVISO: tags en lunas no listadas en inventario: {sorted(lunas_only)}")
    if inv_unused:
        print(f"AVISO: tags en inventario sin lunas: {sorted(inv_unused)}")

    print(f"Exportado: Catalog/{OUTPUT_LUNAS_JSON.name} ({len(moons)} lunas)")
    print("Alcance: base/mid_story/revisit/world_peace")
    print(f"Con 2+ tags: {multi}")
    summary = kingdom_availability_summary(registry)
    print("\nDisponibilidad por reino (orden = tier_order del reino):")
    for kingdom in KINGDOM_COLUMNS:
        line = _format_kingdom_availability_line(kingdom, summary, rules)
        if line:
            print(line)
    print("\nTags:")
    for tag, count in sorted(tag_counts.items()):
        print(f"  {tag}: {count}")

def export_lunas() -> None:
    n_untyped = rebuild_untyped_moons()
    print(f"Lunas sin tags extra (solo reino): {n_untyped}")
    _print_availability_violations(collect_availability_violations())
    _print_tag_violations(collect_tag_combination_violations())

    registry = build_matrix_moon_registry()
    allowed = resolve_allowed_tags(registry)
    print(f"Tags permitidas: {len(allowed)} (desde tags_inventario.json o registro)")

    rules = load_kingdom_availability()
    moons, dropped = _build_lunas_moon_rows(registry, allowed)

    write_catalog_json(
        OUTPUT_LUNAS_JSON,
        {
            "_definition": (
                "Lunas in-scope con disponibilidad y tags filtradas "
                "(inventario en tags_inventario.json). "
                "moons[]: {id,moon,name,disponibilidad,tags[]}. "
                "id = 1..n_moons global (historia + nº luna); moon = nº reino. "
                "Sin campo kingdom: tags[0] = reino, resto alfa. "
                "CSV hermano (lunas-objetivos.csv) se deriva de este JSON. "
                "mushroom#39 (Secret Path) → luncheon#50 sintético "
                "(LUNAS_CATALOG_SYNTHETIC; evita choque con luncheon#39)."
            ),
            "_note": (
                "Regenerar con export_lunas_tags.py o regenerate_all.py. "
                "CSV: python export_lunas_tags.py --csv-only (desde este JSON). "
                f"Sintéticos: {dict((f'{a}#{b}', f'{c}#{d}') for (a, b), (c, d) in LUNAS_CATALOG_SYNTHETIC.items())}."
            ),
            "n_moons": len(moons),
            "moons": moons,
        },
    )

    export_lunas_csv_from_json(OUTPUT_LUNAS_JSON)
    _print_lunas_stats(moons, allowed, dropped, registry, rules)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--tags-only", action="store_true", help="Solo tags_inventario.json"
    )
    group.add_argument(
        "--lunas-only",
        action="store_true",
        help="Solo lunas-objetivos.json (+ CSV derivado)",
    )
    group.add_argument(
        "--csv-only",
        action="store_true",
        help="Solo lunas-objetivos.csv desde el JSON existente",
    )
    args = parser.parse_args()

    if args.csv_only:
        export_lunas_csv_from_json()
    elif args.lunas_only:
        export_lunas()
    elif args.tags_only:
        export_tags()
    else:
        export_tags()
        export_lunas()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
