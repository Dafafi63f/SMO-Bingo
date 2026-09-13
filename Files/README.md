# Files

Scripts Python del bingo (stdlib). El Combined vive en [`Bingos/`](../Bingos/); los exports en [`Catalog/`](../Catalog/README.md).

Restricciones de goals lockout + patrón fija/`range` + puentes `progression`: [`Bingos/README.md`](../Bingos/README.md). Umbrales fijos protegidos: `SINGLE_VALUE_OK` en `ranges_tools.py`.

```bash
python Files/regenerate_all.py              # 1ª vez: todo; luego: omite pasos al día
python Files/regenerate_all.py --force      # forzar pipeline completo
python Files/regenerate_all.py --dry-run    # ver qué pasos correrían
# o: cd Files && python regenerate_all.py
```

Estado incremental en `Files/.regenerate_state.json` (gitignored). Borrarlo para
volver a forzar una corrida completa sin `--force`.

## Pipeline (`regenerate_all.py` / `regenerate_lib.py`)

| Script | Rol |
|--------|-----|
| `catalog_lib.py` | Helpers compartidos (paths, Combined, tags, caches) |
| `goal_list_lib.py` | `goal_lists.json` (ids, zone strip, listas contables) |
| `ranges_tools.py` | Rangos progresivos (`reasonable_range`, `SINGLE_VALUE_OK`) |
| `sync_objective_moon_groups.py` | Specs → `bingo_groups` (goals Combined ↔ lunas); incl. grupos `wedding`, `bloom_flower`, `cappy`, … |
| `apply_progression_accessibility.py` | `progression`/`weighting` Combined + normalize grupos |
| `export_combined_meta.py` | `bingo_lineas` / `goal_icons` / `goal_tooltips` (+ `GOAL_ICON_REMAP`) |
| `export_capturas_lunas.py` | `capturas_lunas.json` |
| `export_lunas_tags.py` | `lunas-objetivos` + `tags_inventario` |
| `export_goals_referencia.py` | Hub `goals_referencia.json` |
| `export_goals_individuales.py` | `goals_individuales.json` (+ enriquece el hub) |
| `export_zonas_inventario.py` | `zonas_inventario.json` |
| `export_items_goals.py` | `items_goals.json` (ítem → goals Combined) |
| `export_palabras_inventario.py` | `palabras_inventario.json` (slugs × usos) |
| `enrich_goals_referencia.py` | `individuales[]` en el hub (también al exportar individuales) |
| `regenerate_lib.py` | Pipeline incremental (huellas blake2b) |
| `mariowiki_guides.py` | Caché `mariowiki_capture_guides.json` |

## Ocasionales / revisión local

No van en `regenerate_all`. Salidas gitignored (temporales).

```bash
python Files/audit_catalog_consistency.py
python Files/export_zona_revision.py
python Files/review_findings.py --front zones,items
python Files/review_findings.py --write
```

| Script | Rol |
|--------|-----|
| `export_zona_revision.py` | Cola local `zonas_revision.json` |
| `review_findings.py` | Detectores → `review_findings.json` |
| `audit_catalog_consistency.py` | CRITICAL/WARN entre catálogos derivados |
| `fill_captures_cappy.py` | Tags captures/cappy/mario desde Mario Wiki |
| `rebuild_sub_area_bingo.py` | Grupo `sub_area` + pares Level |
| `sub_area_levels_data.py` | Datos de pares Level (no viven en `goal_lists`) |
| `fix_bingo_group_ranges.py` | Recalcula `range` de objectives en `bingo_groups` |
| `lockout_merch_icons.py` | Icons souvenirs/stickers lockout |

Cambios, pendientes y mapa de revisión: [`README.md`](../README.md#revisar-híbrido-auto--manual).
