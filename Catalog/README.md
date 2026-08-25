# Catalog/

JSON derivados y fuentes manuales del proyecto SMO Bingo. **No editar a mano** los exports salvo `goal_lists.json` y `project.json` (y grupos en `bingo_groups.json` cuando aplique).

## Fuente de verdad del juego

| Ruta | Rol |
|---|---|
| `../Bingos/Super Mario Odyssey-Combined-YYYY-MM-DD.json` | Objetivos lockout.live (editar aquí) |

## Revisión vs fuente (agentes)

`goals_referencia.json` es **superficie de revisión** (no editar a mano; regenerar).

`zonas_reino.json` es fuente de **`zone`** (ubicación): editar zone ahí; el export preserva zone al regenerar identidad/ids desde `goal_lists` + lunas.

Si se pide un cambio en `goals_referencia`:

1. Aplicarlo en la **fuente** que corresponda (Combined, `goal_lists.json`, y/o specs de grupos/lunas en `Files/`).
2. **Propagar**: regenerar el resto de JSON relevantes (`python Files/regenerate_all.py`, o exports puntuales + derivados).
3. No dejar solo el JSON de revisión editado a mano: el siguiente regen lo sobrescribe.

Si se pide un cambio de **ubicación (`zone`)**: editar `zonas_reino.json` (no `goal_lists`).

Contadores útiles: `goal_lists` / `zonas_reino` → `n_items` (iguales); `zonas_reino` → `n_moons` + `n_total`; `bingo_lineas` → `n_goals_1_cat` / `n_goals_2_cats`; `bingo_groups` → `n_groups_both` / `n_groups_moons` / `n_groups_lista` (`kind`).

## Configuración

| Archivo | Rol |
|---|---|
| `project.json` | Meta, availability por reino, range_tiers e/m/l/n |
| `goal_lists.json` | Listas contables curadas (checkpoints, life-ups, levers, pixels, `regionals`, `shops`, …) |
| `bingo_groups.json` | Grupos: `objectives[]` + `moons[]` (`kingdom`+`moon`+`name`+`disponibilidad`) y/o `lista[]` (`id` + `id_list`) |

## Derivados (regenerar)

| Archivo | Generado por |
|---|---|
| `zonas_reino.json` | **Fuente de `zone`** (ubicación POI **y lunas**). Inventario kingdom (lists + `source=moon`). Regenerar preserva zone por (kingdom, source, name); lunas nuevas se infieren de lists / fallback. |
| `zonas_inventario.json` | Vista de revisión por zone (alfa global). Generado con `export_zonas_reino.py`. Incluye `id` / `id_kingdom` de `zonas_reino`. No editar: curar zone en `zonas_reino`. |
| `goals_referencia.json` | `Files/export_goals_referencia.py` (hub bingo Combined) |
| `goals_individuales.json` | `Files/export_goals_individuales.py` |
| `capturas_lunas.json` | `Files/export_capturas_lunas.py` (hub captura↔lunas/goals; identidad Unique Captures vía CAPTURE_LIST) |
| `lunas-objetivos.json` | `Files/export_lunas_tags.py --lunas-only` |
| `tags_inventario.json` | `Files/export_lunas_tags.py --tags-only` |
| `bingo_lineas.json`, `goal_icons.json`, `goal_tooltips.json` | `Files/export_combined_meta.py` |
| `moon_names_wiki.json` | wiki / scripts de sync |

## Pipeline

```text
Combined → sync_objective_moon_groups → sync_kingdom_groups
        → apply_progression_accessibility → export_combined_meta
        → capturas_lunas → lunas-objetivos → goals_referencia
        → goals_individuales → zonas_reino (+ zonas_inventario) → tags_inventario
        → (re-export lunas + goals_referencia + individuales) → enrich_goals_referencia
```

Comando único: `python Files/regenerate_all.py`

Auditoría opcional: `python Files/audit_catalog_consistency.py`

`project.in_scope_moon_count` (434) = `lunas-objetivos` / `zonas_reino` (mushroom#39 entra como **luncheon#50** sintético, última luna de luncheon antes de ruined). Totales: `zonas_reino.n_total` = 434+n_items.

## Ubicación (`zone`)

Solo en **`zonas_reino.json`** (ítems de lists + lunas). Sin `zone` en `goal_lists`, `goals_referencia.lista[]`, `bingo_groups.lista[]` ni capturas.

Para revisar asignación zona↔contenido: **`zonas_inventario.json`** (zones[] en alfa; una fila = `(zone, kingdom)`).

| Campo | Usar en | Ejemplo |
|---|---|---|
| **`zone`** (+ `sub_area` / `eight_bit` opcionales en curación de regionals) | `zonas_reino` (zone); flags de filtro en `goal_lists.regionals` | `zone: "sphynx"`, `zone: "tostarena"` |

`lists.shops` = Crazy Cap por reino; merchandise sin zone en lists (mirar `zonas_reino`). Capturas: solo `capturas_lunas.json` (no en `goal_lists`).

Lunas: `zone` solo al curar/ver en `zonas_reino` (no en `lunas-objetivos`).

## goals_referencia.json — hub de revisión

Por cada template Combined (bloques en orden):

1. **Identidad** — `orden`, `goal`
2. **Combined/Rush** — `range`, `progression`, …
3. **Tablero** — categorías, icons
4. **Pool** — `bingo_groups`, `notas`, `individuales[]`, **`pool`**
5. **Detalle pool** — `pool_summary` / `lista_summary` (incl. `n_moons`) → `moons[]` o `lista[]` al final

Regenerar resúmenes: `python Files/export_goals_referencia.py` + `enrich_goals_referencia.py`.

## goals_individuales.json — grupos

- **Por reino** (`cap`, `sand`, …): `goal` + `progression` + `lockout`
- **`blank_reino`**: totales/globales sin reino fijo; incluye `kingdom` en cada fila
- **`early` / `mid` / `late` / `endgame`**: índices; copian goals cuya `progression` toca esa zona (puede repetir entradas de reino/blank)
- `n_goals` = templates únicas; las entradas en grupos de zona no cuentan para ese total

Ver también `Bingos/README.md` (schema Lockout y puentes e/m/l/n).
