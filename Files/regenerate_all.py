"""Regenera Combined sync + todos los exports del proyecto.

Uso:
  python Files/regenerate_all.py           # 1ª corrida: todo; luego: incremental
  python Files/regenerate_all.py --force   # forzar todo (ignorar caché)
  python Files/regenerate_all.py --dry-run # qué pasos correrían

Cuándo:
  Tras cambios en Combined, progressions, ranges, grupos, tags o lunas.
  Al terminar una tarea de catálogo, lanzar esto antes de darla por cerrada.

Comportamiento por defecto:
  Sin Files/.regenerate_state.json (primera vez o tras borrarlo) → pipeline
  completo, lento. Tras una corrida exitosa, las siguientes omiten pasos cuyas
  entradas no cambiaron (rápido). write_catalog_json no toca disco si el JSON
  serializado es idéntico.

Qué hace (en orden): ver regenerate_lib.build_steps().
"""
from __future__ import annotations

import argparse
import sys

from regenerate_lib import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forzar todos los pasos aunque el estado incremental diga al día.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar pasos que se ejecutarían sin correrlos.",
    )
    args = parser.parse_args()
    code, ran, skipped, total = run_pipeline(
        force=args.force, dry_run=args.dry_run
    )
    if code != 0:
        return code
    if args.dry_run:
        print(f"\nDry-run: {ran}/{total} paso(s) pendientes, {skipped} al día.")
    elif ran == 0:
        print(f"\nCatálogo al día ({skipped}/{total} pasos omitidos).")
    elif ran == total:
        print(f"\nRegeneración completa ({total} pasos).")
    else:
        print(
            f"\nRegeneración parcial: {ran} ejecutado(s), {skipped} omitido(s) "
            f"(de {total})."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
