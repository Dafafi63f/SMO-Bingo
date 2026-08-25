"""Añade individuales[] a goals_referencia.json (hub cross-file).

Correr después de export_goals_referencia + export_goals_individuales
(p. ej. al final de regenerate_all.py).

Uso: python Files/enrich_goals_referencia.py
"""
from __future__ import annotations

from catalog_lib import CATALOG_DIR, load_catalog, write_catalog_json
from export_goals_individuales import individuales_by_template
from export_goals_referencia import finalize_goal_record_order

REF = CATALOG_DIR / "goals_referencia.json"


def enrich_referencia_with_individuales() -> int:
    data = load_catalog(REF)
    templates = list(data.get("goals") or [])
    by_template = individuales_by_template(templates)
    n_attached = 0
    ordered: list[dict] = []
    for record in templates:
        rows = by_template.get(str(record.get("goal") or ""))
        if rows:
            record["individuales"] = rows
            n_attached += 1
        else:
            record.pop("individuales", None)
        ordered.append(finalize_goal_record_order(record))
    data["goals"] = ordered
    write_catalog_json(REF, data)
    return n_attached


def main() -> None:
    n = enrich_referencia_with_individuales()
    print(f"Enriquecido {REF.name}: individuales[] en {n} templates")


if __name__ == "__main__":
    main()
