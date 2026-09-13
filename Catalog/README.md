# Catalog/

JSON derivados y fuentes manuales del proyecto SMO Bingo. **No editar a mano** los exports salvo `goal_lists.json` y `project.json` (y grupos en `bingo_groups.json` cuando aplique).

## Fuente de verdad del juego

| Ruta | Rol |
|---|---|
| `../Bingos/Super Mario Odyssey-Combined-YYYY-MM-DD.json` | Objetivos lockout.live (editar aquí; actual ≈ `2026-09-13`) |

## Revisión vs fuente (agentes)

`goals_referencia.json` es **superficie de revisión** (no editar a mano; regenerar).

`zonas_inventario.json` es fuente de **`zone`** (ubicación): cada `list[].zone`; el export preserva zone al regenerar por (kingdom, source, name).

Si se pide un cambio en `goals_referencia`:

1. Aplicarlo en la **fuente** que corresponda (Combined, `goal_lists.json`, y/o specs de grupos/lunas en `Files/`).
2. **Propagar**: regenerar el resto de JSON relevantes (`python Files/regenerate_all.py`, o exports puntuales + derivados).
3. No dejar solo el JSON de revisión editado a mano: el siguiente regen lo sobrescribe.

Si se pide un cambio de **ubicación (`zone`)**: editar `zonas_inventario.json` (no `goal_lists`).

Contadores útiles: `goal_lists` / `zonas_inventario` → `n_items`; `zonas_inventario` → `n_moons` + `n_total`; `bingo_lineas` → `n_goals_1_cat` / `n_goals_2_cats`; `bingo_groups` → `n_groups_both` / `n_groups_moons` / `n_groups_lista` (`kind`).

## Configuración

| Archivo | Rol |
|---|---|
| `project.json` | Meta, availability por reino, range_tiers e/m/l/n |
| `goal_lists.json` | Listas contables curadas (checkpoints, life-ups, levers, pixels, `regionals`, `shops`, …; no capturas ni binoculars) |
| `bingo_groups.json` | Grupos: `objectives[]` + `moons[]` (`kingdom`+`moon`+`name`+`disponibilidad`) y/o `lista[]` (`id` + `id_list`) |

## Derivados (regenerar)

| Archivo | Generado por |
|---|---|
| `zonas_inventario.json` | **Fuente de `zone`** (ubicación POI **y lunas**). Vista por zone (alfa). Regenerar preserva zone por (kingdom, source, name). |
| `zonas_revision.json` | Cola de revisión: `groups[]` kind=kingdom\|zone\|source; `status` por ítem; grupos 100% ok no se muestran. |
| `items_goals.json` | Ítem → goals Combined; recorta paraguas si hay concreta (Nature/Sand/…). |
| `goals_referencia.json` | `Files/export_goals_referencia.py` (hub bingo Combined) |
| `goals_individuales.json` | `Files/export_goals_individuales.py` |
| `capturas_lunas.json` | `Files/export_capturas_lunas.py` (hub captura↔lunas/goals; identidad Unique Captures vía CAPTURE_LIST) |
| `lunas-objetivos.json` | `Files/export_lunas_tags.py --lunas-only` |
| `tags_inventario.json` | `Files/export_lunas_tags.py --tags-only` |
| `palabras_inventario.json` | `Files/export_palabras_inventario.py` (slugs × usos: bingo/grupo/tag/…) |
| `bingo_lineas.json`, `goal_icons.json`, `goal_tooltips.json` | `Files/export_combined_meta.py` |
| `mariowiki_capture_guides.json` | `Files/mariowiki_guides.py --refresh` (caché wiki) |

## Pipeline

```text
Combined → sync_objective_moon_groups → sync_kingdom_groups
        → apply_progression_accessibility → export_combined_meta
        → capturas_lunas → lunas-objetivos → goals_referencia
        → goals_individuales → zonas_inventario → items_goals → tags_inventario
        → (re-export lunas + goals_referencia + individuales) → enrich_goals_referencia
        → palabras_inventario
```

Comando único: `python Files/regenerate_all.py`

Auditoría opcional: `python Files/audit_catalog_consistency.py`

`project.in_scope_moon_count` (434) = `lunas-objetivos` / lunas en `zonas_inventario` (mushroom#39 entra como **luncheon#50** sintético, última luna de luncheon antes de ruined). Totales: `zonas_inventario.n_total` = 434+n_items.

## Ubicación (`zone`)

Solo en **`zonas_inventario.json`** (ítems de lists + lunas). Sin `zone` en `goal_lists`, `goals_referencia.lista[]`, `bingo_groups.lista[]` ni capturas.

Para revisar asignación zona↔contenido: **`zonas_inventario.json`** (zones[] en alfa; una fila = `(zone, kingdom)`).

| Campo | Usar en | Ejemplo |
|---|---|---|
| **`zone`** (+ `sub_area` / `eight_bit` opcionales en curación de regionals) | `zonas_inventario` (zone); flags de filtro en `goal_lists.regionals` | `zone: "sphynx"`, `zone: "tostarena"` |

`lists.shops` = Crazy Cap por reino; merchandise sin zone en lists (mirar `zonas_inventario`). Capturas y ubicaciones Binoculars: solo `capturas_lunas.json` (no en `goal_lists`).

Lunas: `zone` solo al curar/ver en `zonas_inventario` (no en `lunas-objetivos`).

## goals_referencia.json — hub de revisión

Por cada template Combined (bloques en orden):

1. **Identidad** — `orden`, `goal`
2. **Combined/Rush** — `range`, `progression`, …
3. **Tablero** — categorías, icons
4. **Pool** — `bingo_groups`, `notas`, `individuales[]`, **`pool`**
5. **Tags (solo `pool=moons`)** — `tags[]` = intersección temática del pool
   (o `moon_tag` del grupo si `apply_moon_tag=False`). En cada fila de
   `moons[]`, `tag` (bool, al final): `true` si la luna lleva esas tags;
   `false` = está en el pool pero sin la tag (espejo de `goal=false` en
   capturas/tags cuando la luna es solo-tag).
6. **Detalle pool** — `pool_summary` / `lista_summary` (incl. `n_moons`) → `moons[]` o `lista[]` al final

Regenerar resúmenes: `python Files/export_goals_referencia.py` + `enrich_goals_referencia.py`.

## goals_individuales.json — grupos

- **Por reino** (`cap`, `sand`, …): `goal` + `progression` + `lockout`
- **`blank_reino`**: totales/globales sin reino fijo; incluye `kingdom` en cada fila
- **`early` / `mid` / `late` / `endgame`**: índices; copian goals cuya `progression` toca esa zona (puede repetir entradas de reino/blank)
- `n_goals` = templates únicas; las entradas en grupos de zona no cuentan para ese total

Ver también `Bingos/README.md` (schema Lockout y puentes e/m/l/n).

### Reordenar regionals a GuiasNintendo (hecho)

Regionals ya están alineados a letras del mapa GN (`total` = marcador). Merges
históricos: Lost 18→16, Seaside 33→32, Sand 31→26, Metro 36→31. Los scripts
one-shot de apply/reorder se eliminaron; el estado vive en `goal_lists.json`.

Cambios y pendientes del repo: [`README.md`](../README.md#cambios-recientes-2026-09).
