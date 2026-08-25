# Files

Scripts Python del bingo (stdlib). El Combined vive en [`Bingos/`](../Bingos/); los exports en [`Catalog/`](../Catalog/README.md).

Restricciones de goals lockout + patrón fija/`range` + puentes `progression`: [`Bingos/README.md`](../Bingos/README.md). Umbrales fijos protegidos: `SINGLE_VALUE_OK` en `ranges_tools.py`.

```bash
python Files/regenerate_all.py
# o: cd Files && python regenerate_all.py
```

Auditoría opcional: `python Files/audit_catalog_consistency.py`

## Pipeline (`regenerate_all.py`)

| Script | Rol |
|--------|-----|
| `catalog_lib.py` | Helpers compartidos (paths, Combined, tags, caches) |
| `goal_list_lib.py` | `goal_lists.json` (ids, zone strip, listas contables) |
| `ranges_tools.py` | Rangos progresivos (`reasonable_range`, `SINGLE_VALUE_OK`) |
| `sync_objective_moon_groups.py` | Specs → `bingo_groups` (goals Combined ↔ lunas) |
| `apply_progression_accessibility.py` | `progression`/`weighting` Combined + normalize grupos |
| `export_combined_meta.py` | `bingo_lineas` / `goal_icons` / `goal_tooltips` |
| `export_capturas_lunas.py` | `capturas_lunas.json` |
| `export_lunas_tags.py` | `lunas-objetivos` + `tags_inventario` |
| `export_goals_referencia.py` | Hub `goals_referencia.json` |
| `export_goals_individuales.py` | `goals_individuales.json` (+ enriquece el hub) |
| `export_zonas_reino.py` | `zonas_reino.json` + `zonas_inventario.json` |
| `enrich_goals_referencia.py` | `individuales[]` en el hub (también al exportar individuales) |

## Ocasionales

| Script | Rol |
|--------|-----|
| `sync_lunas.py` | Pasada parcial (grupos + tags + exports básicos); preferir `regenerate_all` |
| `fill_captures_cappy.py` | Tags captures/cappy/mario desde Mario Wiki |
| `rebuild_sub_area_bingo.py` | Grupo `sub_area` + pares Level |
| `sub_area_levels_data.py` | Datos de pares Level (no viven en `goal_lists`) |
| `fix_bingo_group_ranges.py` | Recalcula `range` de objectives en `bingo_groups` |
| `audit_catalog_consistency.py` | CRITICAL/WARN entre catálogos derivados |
