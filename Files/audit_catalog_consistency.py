"""Auditoría rápida de coherencia entre catálogos derivados.

Uso: python Files/audit_catalog_consistency.py
Exit 0 = sin CRITICAL; exit 1 = hay incoherencias graves.
"""
from __future__ import annotations

from catalog_lib import (
    CATALOG_DIR,
    collect_availability_violations,
    load_catalog,
)
from export_goals_individuales import lockout_inverted_vs_progression
from goal_list_lib import (
    collect_disponibilidad_list_violations,
    collect_goal_lists_referencia_mismatches,
    collect_location_field_violations,
)

CRITICAL: list[str] = []
WARN: list[str] = []


def _check_moon_availability() -> None:
    for path, key, issues in collect_availability_violations():
        CRITICAL.append(f"{path} {key}: {'; '.join(issues)}")


def _check_goal_lists_disponibilidad() -> None:
    for list_name, key, issue in collect_disponibilidad_list_violations():
        CRITICAL.append(f"goal_lists.{list_name} {key}: {issue}")
    for list_name, key, issue in collect_goal_lists_referencia_mismatches():
        CRITICAL.append(f"goal_lists↔referencia {list_name} {key}: {issue}")


def _check_lista_location_fields() -> None:
    for source, key, issue in collect_location_field_violations():
        CRITICAL.append(f"ubicación {source} {key}: {issue}")


def _check_individuales_vs_referencia() -> None:
    ref = load_catalog(CATALOG_DIR / "goals_referencia.json")
    ind = load_catalog(CATALOG_DIR / "goals_individuales.json")
    ref_n = int(ref.get("n_goals") or len(ref.get("goals") or []))
    ind_n = int(ind.get("n_templates") or 0)
    if ind_n != ref_n:
        CRITICAL.append(
            f"goals_individuales n_templates={ind_n} ≠ goals_referencia n_goals={ref_n}"
        )
    flat_n = int(ind.get("n_goals") or 0)
    if flat_n <= 0:
        CRITICAL.append("goals_individuales n_goals inválido o vacío")


def _check_lockout_inverted() -> None:
    ind = load_catalog(CATALOG_DIR / "goals_individuales.json")
    for group in ind.get("groups") or []:
        if group.get("id") in {"early", "mid", "late", "endgame"}:
            continue
        for row in group.get("goals") or []:
            prog = row.get("progression", "")
            lock = row.get("lockout", prog)
            if lockout_inverted_vs_progression(prog, lock):
                gid = group["id"]
                kingdom = (
                    gid
                    if gid not in {"blank_reino", "blank_progresion"}
                    else row.get("kingdom", "")
                )
                WARN.append(
                    f"lockout invertido vs progression: {row['goal']!r} "
                    f"(kingdom={kingdom!r}, prog={prog!r}, lock={lock!r})"
                )


def main() -> int:
    _check_moon_availability()
    _check_goal_lists_disponibilidad()
    _check_lista_location_fields()
    _check_individuales_vs_referencia()
    _check_lockout_inverted()

    print("=== Auditoría catálogos SMO Bingo ===\n")
    if CRITICAL:
        print(f"CRITICAL ({len(CRITICAL)}):")
        for line in CRITICAL:
            print(f"  - {line}")
        print()
    else:
        print("CRITICAL: 0\n")

    if WARN:
        print(f"WARN ({len(WARN)}):")
        for line in WARN[:20]:
            print(f"  - {line}")
        if len(WARN) > 20:
            print(f"  ... y {len(WARN) - 20} más")
        print()
    else:
        print("WARN: 0\n")

    if CRITICAL:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
