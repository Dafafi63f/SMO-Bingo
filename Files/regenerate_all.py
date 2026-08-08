"""Regenera Combined sync + todos los exports del proyecto.

Uso:
  python Files/regenerate_all.py
  # o desde Files/: python regenerate_all.py

Cuándo:
  Tras cambios en Combined, progressions, ranges, grupos, tags o lunas.
  Al terminar una tarea de catálogo, lanzar esto antes de darla por cerrada.
  No asumir que un export puntual basta.

Por qué:
  El workflow habitual mira catalog/bingo_groups.json. Si solo se actualiza
  Combined u un export suelto, los grupos se quedan desfasados.
  Combined es la fuente de verdad: el sync de grupos sobrescribe
  range/progression/etc. obsoletos del JSON de grupos.

Qué hace (en orden):
  0. stamp Combined → renombra a Combined-YYYY-MM-DD (hoy)
  1. sync_objective_moon_groups.py → specs → bingo_groups (goals Combined)
  2. sync_kingdom_groups → reinos Combined → bingo_groups
  3. apply_progression_accessibility.py → Combined + normalize bingo_groups
     (objectives[] siempre regeneradas desde Combined activo; al final
     ordena Combined {{X}}+alfa + campo orden 1..N)
  4. export_combined_meta.py all → bingo_lineas / goal_icons / goal_tooltips
  5. export_capturas_lunas.py → catalog/capturas_lunas.json
  6. export_lunas_tags.py --lunas-only → catalog/lunas-objetivos.json (+ .csv)
  7. export_goals_referencia.py → catalog/goals_referencia.json
  8. export_lunas_tags.py --tags-only → catalog/tags_inventario.json
     (goals[] por tag desde pools de goals_referencia)
  9. Re-export lunas + goals_referencia (tags nuevas ya permitidas)
 10. clear_runtime_caches() (catalog_lib)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent
ROOT = FILES_DIR.parent
# Fuerza UTF-8 en los subprocesos: varios scripts imprimen “→” y en consola
# Windows (cp1252) sin esto revienta con UnicodeEncodeError.
SUBPROCESS_ENV = dict(os.environ)
SUBPROCESS_ENV.setdefault("PYTHONIOENCODING", "utf-8")
# Imports entre scripts (catalog_lib, …) con cwd=Files.
_path = SUBPROCESS_ENV.get("PYTHONPATH", "")
SUBPROCESS_ENV["PYTHONPATH"] = (
    str(FILES_DIR) if not _path else str(FILES_DIR) + os.pathsep + _path
)

EXPORT_LUNAS_TAGS_PY = "export_lunas_tags.py"

# Orden importa: sync grupos → progression/normalize (+ sort Combined) → exports.
# capturas_lunas antes que lunas-objetivos (tags de captura leen el JSON).
# goals_referencia antes que tags_inventario (goals[] por tag desde pools).
STEPS: list[tuple[str, list[str]]] = [
    (
        "stamp Combined filename (fecha hoy)",
        [
            sys.executable,
            "-c",
            "from catalog_lib import stamp_combined_filename_today; "
            "p=stamp_combined_filename_today(); print(p.name)",
        ],
    ),
    ("sync objective moon groups", [sys.executable, "sync_objective_moon_groups.py"]),
    (
        "sync kingdom groups",
        [
            sys.executable,
            "-c",
            "from catalog_lib import sync_kingdom_groups; "
            "c=sync_kingdom_groups(); print(f'kingdom groups: {c}')",
        ],
    ),
    (
        "progression + bingo_groups + sort Combined",
        [sys.executable, "apply_progression_accessibility.py"],
    ),
    ("combined meta (lineas/icons/tooltips)", [sys.executable, "export_combined_meta.py", "all"]),
    ("capturas_lunas", [sys.executable, "export_capturas_lunas.py"]),
    ("lunas-objetivos", [sys.executable, EXPORT_LUNAS_TAGS_PY, "--lunas-only"]),
    ("goals_referencia", [sys.executable, "export_goals_referencia.py"]),
    ("tags_inventario", [sys.executable, EXPORT_LUNAS_TAGS_PY, "--tags-only"]),
    # Segunda pasada: tags nuevas (p. ej. fire_bro) ya estan en inventario.
    ("lunas-objetivos (retag)", [sys.executable, EXPORT_LUNAS_TAGS_PY, "--lunas-only"]),
    ("goals_referencia (retag)", [sys.executable, "export_goals_referencia.py"]),
    (
        "clear caches",
        [
            sys.executable,
            "-c",
            "from catalog_lib import clear_runtime_caches; "
            "clear_runtime_caches(); print('ok')",
        ],
    ),
]


def main() -> int:
    for label, cmd in STEPS:
        print(f"\n=== {label} ===")
        r = subprocess.run(cmd, cwd=FILES_DIR, env=SUBPROCESS_ENV)
        if r.returncode != 0:
            print(f"FALLO ({r.returncode}): {label}", file=sys.stderr)
            return r.returncode

    print("\nRegeneracion completa (incluye catalog/bingo_groups.json).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
