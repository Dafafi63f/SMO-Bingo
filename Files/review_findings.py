"""Detectores → cola de revisión manual (no auto-arregla).

Salida típica `Catalog/review_findings.json` es **local / gitignored**.
Los scripts listan sospechos; curas a mano en Combined / goal_lists /
zonas_inventario / …

Uso:
  python Files/review_findings.py
  python Files/review_findings.py --front zones,items,goals
  python Files/review_findings.py --list-fronts
  python Files/review_findings.py --write
  python Files/review_findings.py --json          # solo JSON a stdout

Cada finding: front, severity (info|review|warn), code, summary, detail, fix_hint.
severity=warn merecen prioridad; review = mirar; info = contexto/conteos.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Callable

from catalog_lib import CATALOG_DIR, JSON_PATH, load_catalog, write_catalog_json
from export_combined_meta import GOAL_ICON_REMAP

# Reutiliza la auditoría CRITICAL/WARN existente.
import audit_catalog_consistency as _audit

SEVERITY_INFO = "info"
SEVERITY_REVIEW = "review"
SEVERITY_WARN = "warn"

DEFAULT_WRITE = CATALOG_DIR / "review_findings.json"


@dataclass
class Finding:
    front: str
    severity: str
    code: str
    summary: str
    detail: dict = field(default_factory=dict)
    fix_hint: str = ""


FrontFn = Callable[[], list[Finding]]


def _front_consistency() -> list[Finding]:
    _audit.CRITICAL.clear()
    _audit.WARN.clear()
    _audit._check_moon_availability()
    _audit._check_goal_lists_disponibilidad()
    _audit._check_lista_location_fields()
    _audit._check_individuales_vs_referencia()
    _audit._check_lockout_inverted()
    out: list[Finding] = []
    for line in _audit.CRITICAL:
        out.append(
            Finding(
                front="consistency",
                severity=SEVERITY_WARN,
                code="critical",
                summary=line,
                fix_hint="Corregir fuente y regenerar; exit!=0 en audit_catalog_consistency.",
            )
        )
    for line in _audit.WARN:
        out.append(
            Finding(
                front="consistency",
                severity=SEVERITY_REVIEW,
                code="warn",
                summary=line,
                fix_hint="Revisar progression/lockout en goals_individuales / Combined.",
            )
        )
    if not out:
        out.append(
            Finding(
                front="consistency",
                severity=SEVERITY_INFO,
                code="ok",
                summary="Sin CRITICAL ni WARN de audit_catalog_consistency.",
            )
        )
    return out


def _kingdom_from_item_id(row_id: object) -> str | None:
    """id tipo kingdom/source/nº → reino (sin nulls en samples)."""
    parts = str(row_id or "").split("/")
    return parts[0] if parts and parts[0] else None


def _zone_review_sample(it: dict, group: dict) -> dict:
    """Sample de cola zones: kingdom/zone rellenados; nunca null."""
    sample: dict = {"id": it.get("id"), "name": it.get("name")}
    kingdom = (
        it.get("kingdom")
        or group.get("kingdom")
        or _kingdom_from_item_id(it.get("id"))
    )
    zone = it.get("zone")
    if not zone and group.get("kind") == "zone":
        zlabel = group.get("zone")
        if zlabel and zlabel != "sin_zone":
            zone = zlabel
    if kingdom:
        sample["kingdom"] = kingdom
    if zone:
        sample["zone"] = zone
    return sample


def _front_zones() -> list[Finding]:
    """Cola de heurísticas de zone (cola local; sin reportar sin_zone)."""
    zr_path = CATALOG_DIR / "zonas_revision.json"
    if not zr_path.is_file():
        return [
            Finding(
                front="zones",
                severity=SEVERITY_INFO,
                code="missing",
                summary="Falta zonas_revision.json (local; regenerar export_zona_revision).",
                fix_hint="python Files/export_zona_revision.py",
            )
        ]
    zr = load_catalog(zr_path)
    by_method_raw = dict(zr.get("by_method") or {})
    # sin_zone / n_without_zone: curar en zonas_inventario; aquí no se listan.
    by_method_view = {
        k: v for k, v in by_method_raw.items() if k != "sin_zone"
    }
    out: list[Finding] = [
        Finding(
            front="zones",
            severity=SEVERITY_INFO,
            code="summary",
            summary=(
                f"zonas_revision: {zr.get('n_pendiente')} pendiente / "
                f"{zr.get('n_ok')} ok"
            ),
            detail={"by_method": by_method_view},
            fix_hint=(
                "Curar heurísticas en zonas_inventario; regenerar "
                "zonas_revision (local). n_without_zone debe ser 0 "
                "(no se lista aquí)."
            ),
        )
    ]
    by_method = Counter(by_method_view)
    # Heurísticas / discrepancias a curar (sin_zone fuera de alcance aquí).
    priority = (
        "heuristic_shop",
        "heuristic_toad",
        "heuristic_art",
        "distinto_curado",
        "fallback_curado",
    )
    for method in priority:
        n = int(by_method.get(method) or 0)
        if n <= 0:
            continue
        samples: list[dict] = []
        # Preferir grupos por zone para rellenar zone en el sample (sin nulls).
        groups = [g for g in (zr.get("groups") or []) if isinstance(g, dict)]
        groups.sort(key=lambda g: 0 if g.get("kind") == "zone" else 1)
        for group in groups:
            for it in group.get("items") or []:
                if not isinstance(it, dict):
                    continue
                if it.get("status") != "pendiente":
                    continue
                if str(it.get("method") or "") != method:
                    continue
                samples.append(_zone_review_sample(it, group))
                if len(samples) >= 8:
                    break
            if len(samples) >= 8:
                break
        out.append(
            Finding(
                front="zones",
                severity=SEVERITY_REVIEW,
                code=f"method:{method}",
                summary=f"{n} items method={method}",
                detail={"samples": samples},
                fix_hint="Editar zone en zonas_inventario (misma id/name/source).",
            )
        )
    return out


def _front_items() -> list[Finding]:
    ig = load_catalog(CATALOG_DIR / "items_goals.json")
    out: list[Finding] = []
    without = [
        {"id": it.get("id"), "name": it.get("name")}
        for it in ig.get("items") or []
        if isinstance(it, dict) and not (it.get("goals") or [])
    ]
    n_without = int(ig.get("n_without_goals") or len(without))
    out.append(
        Finding(
            front="items",
            severity=SEVERITY_WARN if n_without else SEVERITY_INFO,
            code="without_goals",
            summary=f"Items sin goals: {n_without}",
            detail={"samples": without[:20]},
            fix_hint="Revisar export_items_goals / moons[] o lista[] en goals_referencia.",
        )
    )
    # Outliers: muchas goals en un solo POI (posible inflacion).
    heavy = sorted(
        (
            it
            for it in ig.get("items") or []
            if isinstance(it, dict) and int(it.get("n_goals") or 0) >= 5
        ),
        key=lambda it: int(it.get("n_goals") or 0),
        reverse=True,
    )
    out.append(
        Finding(
            front="items",
            severity=SEVERITY_REVIEW if heavy else SEVERITY_INFO,
            code="many_goals",
            summary=f"Items con >=5 goals: {len(heavy)}",
            detail={
                "samples": [
                    {
                        "id": it.get("id"),
                        "name": it.get("name"),
                        "n_goals": it.get("n_goals"),
                        "goals": it.get("goals"),
                    }
                    for it in heavy[:15]
                ]
            },
            fix_hint="Paraguas + concretas? prune_umbrella / reglas shops.",
        )
    )
    shops = [
        it
        for it in ig.get("items") or []
        if isinstance(it, dict) and "/shops/" in str(it.get("id") or "")
    ]
    out.append(
        Finding(
            front="items",
            severity=SEVERITY_INFO,
            code="shops",
            summary=f"Crazy Cap: {len(shops)} tiendas",
            detail={
                "samples": [
                    {
                        "id": it.get("id"),
                        "n_goals": it.get("n_goals"),
                        "goals": it.get("goals"),
                    }
                    for it in shops[:5]
                ]
            },
            fix_hint="Shop Moon del reino + merchandise (sin Shop Moons / Boxer).",
        )
    )
    return out


def _front_goals() -> list[Finding]:
    ref = load_catalog(CATALOG_DIR / "goals_referencia.json")
    out: list[Finding] = []
    tag_false: list[tuple[float, int, int, str]] = []
    goal_false: list[tuple[float, int, int, str]] = []
    empty_pool: list[str] = []
    for g in ref.get("goals") or []:
        if not isinstance(g, dict):
            continue
        name = str(g.get("goal") or "")
        pool = str(g.get("pool") or "")
        moons = [m for m in (g.get("moons") or []) if isinstance(m, dict)]
        lista = [m for m in (g.get("lista") or []) if isinstance(m, dict)]
        if pool == "moons" and not moons:
            empty_pool.append(name)
        if pool == "lista" and not lista:
            empty_pool.append(name)
        if len(moons) >= 4:
            n_tf = sum(1 for m in moons if m.get("tag") is False)
            n_gf = sum(1 for m in moons if m.get("goal") is False)
            if n_tf:
                tag_false.append((n_tf / len(moons), n_tf, len(moons), name))
            if n_gf:
                goal_false.append((n_gf / len(moons), n_gf, len(moons), name))
    tag_false.sort(reverse=True)
    goal_false.sort(reverse=True)
    if empty_pool:
        out.append(
            Finding(
                front="goals",
                severity=SEVERITY_WARN,
                code="empty_pool",
                summary=f"Goals con pool vacio: {len(empty_pool)}",
                detail={"goals": empty_pool[:30]},
                fix_hint="Combined + sync grupos / goal_lists; regenerar referencia.",
            )
        )
    out.append(
        Finding(
            front="goals",
            severity=SEVERITY_REVIEW if tag_false else SEVERITY_INFO,
            code="tag_false_ratio",
            summary="Top goals con moons[].tag=false (pool sin tag tematica)",
            detail={
                "samples": [
                    {
                        "goal": name,
                        "tag_false": n_tf,
                        "n_moons": n,
                        "ratio": round(r, 2),
                    }
                    for r, n_tf, n, name in tag_false[:12]
                ]
            },
            fix_hint="Paraguas Nature/Fauna o luna mal en el grupo? tags_inventario.",
        )
    )
    out.append(
        Finding(
            front="goals",
            severity=SEVERITY_REVIEW if goal_false else SEVERITY_INFO,
            code="goal_false_ratio",
            summary="Top goals con moons[].goal=false (en pool pero no cuentan)",
            detail={
                "samples": [
                    {
                        "goal": name,
                        "goal_false": n_gf,
                        "n_moons": n,
                        "ratio": round(r, 2),
                    }
                    for r, n_gf, n, name in goal_false[:12]
                ]
            },
            fix_hint="Normal en tours/NPC; raro si casi todo el pool es goal:false.",
        )
    )
    return out


def _front_icons() -> list[Finding]:
    icons = load_catalog(CATALOG_DIR / "goal_icons.json")
    non_smo: list[dict] = []
    for entry in icons.get("icons") or []:
        if not isinstance(entry, dict):
            continue
        ic = str(entry.get("icon") or "")
        if ic.startswith("smo/"):
            continue
        non_smo.append(
            {
                "icon": ic,
                "n_goals": entry.get("n_goals"),
                "goals": entry.get("goals"),
            }
        )
    remap_goals = sorted(GOAL_ICON_REMAP.keys())
    return [
        Finding(
            front="icons",
            severity=SEVERITY_INFO,
            code="non_smo",
            summary=f"Goals con icon no-smo/: {icons.get('n_goals_non_smo')} ({len(non_smo)} icons)",
            detail={"icons": non_smo, "remap_goals_n": len(remap_goals)},
            fix_hint="Intencional salvo asset malo; remap en export_combined_meta.",
        )
    ]


def _front_palabras() -> list[Finding]:
    pal = load_catalog(CATALOG_DIR / "palabras_inventario.json")
    uso_fijo = set(pal.get("uso_fijo") or [])
    singles: list[dict] = []
    for row in pal.get("palabras") or []:
        if not isinstance(row, dict):
            continue
        if int(row.get("n_usos") or 0) != 1:
            continue
        usos = row.get("usos") or {}
        if not isinstance(usos, dict) or len(usos) != 1:
            continue
        uso = next(iter(usos))
        # zona/grupo con n=1 suele ser esperado (uso_fijo).
        if uso in uso_fijo:
            continue
        singles.append(
            {"palabra": row.get("palabra"), "uso": uso, "id": row.get("id")}
        )
    return [
        Finding(
            front="palabras",
            severity=SEVERITY_REVIEW if singles else SEVERITY_INFO,
            code="single_use_non_fijo",
            summary=f"Slugs con un solo uso (no zona/grupo fijo): {len(singles)}",
            detail={"samples": singles[:40]},
            fix_hint="Alias mal canonico o lista huerfana? export_palabras_inventario.",
        )
    ]


def _front_capturas() -> list[Finding]:
    cap = load_catalog(CATALOG_DIR / "capturas_lunas.json")
    n_pool = int(cap.get("n_moons_pool") or 0)
    n_listed = int(cap.get("n_moons_listed") or 0)
    n_blank = int(cap.get("n_blank_moons") or 0)
    blanks = [
        {"capture": c.get("capture") or c.get("name"), "id": c.get("id")}
        for c in cap.get("captures") or []
        if isinstance(c, dict) and not (c.get("moons") or [])
    ]
    sev = SEVERITY_REVIEW if n_blank else SEVERITY_INFO
    # listed < pool: faltan del pool wiki; listed > pool: extras OK.
    if n_listed < n_pool:
        sev = SEVERITY_WARN
    return [
        Finding(
            front="capturas",
            severity=sev,
            code="pool_vs_listed",
            summary=(
                f"pool wiki~={n_pool}, listed={n_listed}, "
                f"blank_moons={n_blank}, goal_false={cap.get('n_goal_false')}"
            ),
            detail={"blank_captures": blanks[:20]},
            fix_hint=(
                "listed < pool: falta asignar; listed >= pool con extras curados OK. "
                "Capturas sin moons: binoculars/special?"
            ),
        )
    ]


def _front_combined_meta() -> list[Finding]:
    """Goals Combined vs cabeceras de catalogo (conteo rapido)."""
    combined = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    n_obj = len(
        [o for o in combined.get("objectives") or [] if isinstance(o, dict) and o.get("goal")]
    )
    ref = load_catalog(CATALOG_DIR / "goals_referencia.json")
    n_ref = int(ref.get("n_goals") or len(ref.get("goals") or []))
    lineas = load_catalog(CATALOG_DIR / "bingo_lineas.json")
    n_lineas = int(lineas.get("n_goals") or 0)
    sev = SEVERITY_WARN if n_obj != n_ref else SEVERITY_INFO
    return [
        Finding(
            front="combined",
            severity=sev,
            code="goal_counts",
            summary=f"Combined objectives={n_obj}, referencia={n_ref}, bingo_lineas goals={n_lineas}",
            detail={"combined": n_obj, "referencia": n_ref, "bingo_lineas": n_lineas},
            fix_hint="Si Combined != referencia: regenerate_all; lineas puede filtrar.",
        )
    ]


FRONTS: dict[str, FrontFn] = {
    "consistency": _front_consistency,
    "zones": _front_zones,
    "items": _front_items,
    "goals": _front_goals,
    "icons": _front_icons,
    "palabras": _front_palabras,
    "capturas": _front_capturas,
    "combined": _front_combined_meta,
}

FRONT_HELP: dict[str, str] = {
    "consistency": "CRITICAL/WARN de audit_catalog_consistency",
    "zones": "Cola local zonas_revision (heurísticas de zone)",
    "items": "items_goals: sin goals, >=5 goals, shops",
    "goals": "goals_referencia: pool vacio, tag/goal false ratios",
    "icons": "Icons no-smo/",
    "palabras": "Slugs de un solo uso (no zona/grupo fijo)",
    "capturas": "Pool wiki vs listed / capturas en blanco",
    "combined": "Conteos Combined vs referencia vs bingo_lineas",
}


def run_fronts(names: list[str] | None = None) -> list[Finding]:
    selected = list(names) if names else list(FRONTS)
    unknown = [n for n in selected if n not in FRONTS]
    if unknown:
        raise SystemExit(f"Frentes desconocidos: {unknown}. Válidos: {sorted(FRONTS)}")
    findings: list[Finding] = []
    for name in selected:
        findings.extend(FRONTS[name]())
    return findings


def findings_payload(findings: list[Finding], fronts: list[str]) -> dict:
    by_sev: dict[str, int] = defaultdict(int)
    by_front: dict[str, int] = defaultdict(int)
    for f in findings:
        by_sev[f.severity] += 1
        by_front[f.front] += 1
    return {
        "_definition": (
            "Cola LOCAL de hallazgos de revisión (gitignored; detectores "
            "automáticos). No corrige nada: sirve para priorizar curación "
            "manual. Regenerar: python Files/review_findings.py --write"
        ),
        "_note": (
            "Local / gitignored; no forma parte de regenerate_all. "
            "severity: warn > review > info. Ver README § Revisar. "
            "No lista sin_zone ni kingdom null."
        ),
        "fronts": fronts,
        "n_findings": len(findings),
        "n_by_severity": dict(sorted(by_sev.items())),
        "n_by_front": dict(sorted(by_front.items())),
        "findings": [asdict(f) for f in findings],
    }


def _print_human(payload: dict) -> None:
    print("=== review_findings (auto -> cola manual) ===\n")
    print(
        f"findings={payload['n_findings']}  "
        f"by_severity={payload['n_by_severity']}  "
        f"fronts={payload['fronts']}\n"
    )
    for raw in payload["findings"]:
        sev = raw["severity"]
        mark = {"warn": "!", "review": "?", "info": "-"}.get(sev, "-")
        print(f"[{mark}{sev}] {raw['front']}/{raw['code']}: {raw['summary']}")
        if raw.get("fix_hint"):
            print(f"         -> {raw['fix_hint']}")
    print()


def _configure_stdout() -> None:
    """Windows cp1252 no traga flechas/≥; evitar crash al imprimir."""
    reconf = getattr(sys.stdout, "reconfigure", None)
    if callable(reconf):
        try:
            reconf(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="Detectores de revision (no auto-fix). Cola para curacion manual."
    )
    parser.add_argument(
        "--front",
        default="",
        help="Frentes separados por coma (default: todos). Ej: zones,items",
    )
    parser.add_argument(
        "--list-fronts",
        action="store_true",
        help="Lista frentes disponibles y sale.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"Escribe JSON en {DEFAULT_WRITE} (ruta fija bajo Catalog/).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime solo el payload JSON (sin resumen humano).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 si hay algún finding severity=warn (útil en CI opcional).",
    )
    args = parser.parse_args(argv)

    if args.list_fronts:
        for name in sorted(FRONTS):
            print(f"  {name:12} {FRONT_HELP.get(name, '')}")
        return 0

    names = [p.strip() for p in args.front.split(",") if p.strip()] or list(FRONTS)
    findings = run_fronts(names)
    payload = findings_payload(findings, names)

    if args.write:
        write_catalog_json(DEFAULT_WRITE, payload)
        print(
            f"Wrote {DEFAULT_WRITE} ({payload['n_findings']} findings)",
            flush=True,
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(payload)

    if args.strict and any(f.severity == SEVERITY_WARN for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
