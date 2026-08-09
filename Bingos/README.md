# Bingos (sets lockout.live)

JSON importables en [lockout.live](https://lockout.live/) para Super Mario Odyssey.

| Archivo | Rol |
|---|---|
| `Super Mario Odyssey-Combined-YYYY-MM-DD.json` | **Fuente de verdad** (fecha = última update del repo; al regenerar se renombra a hoy) |
| `Super Mario Odyssey-Short Goals-YYYY-MM-DD.json` | Referencia lockout (91 goals) |
| `Super Mario Odyssey-Default-YYYY-MM-DD.json` | Referencia lockout (108 goals) |
| `Super Mario Odyssey-Long Goals-YYYY-MM-DD.json` | Referencia lockout (126 goals) |
| `Super Mario Odyssey-All Kingdoms-YYYY-MM-DD.json` | Referencia lockout (más completo; umbrales altos) |

Las cuatro referencias comparten la misma fecha: `LOCKOUT_REFERENCE_DATE` en `Files/catalog_lib.py` (última update de los sets oficiales en lockout.live). Al re-exportar desde lockout, subir esa constante y renombrar los JSON.

Tras cambiar Combined: `python Files/regenerate_all.py`

Descarga estable (Release GitHub): [Super-Mario-Odyssey-Combined.json](https://github.com/Dafafi63f/SMO-Bingo/releases/latest/download/Super-Mario-Odyssey-Combined.json)

Datos derivados (grupos, líneas, icons, referencia): `Catalog/`.

## Restricciones al crear una goal (lockout.live)

Referencia oficial: [Schema Reference](https://wiki.lockout.live/lockout/creators/schema). Resumen práctico para Combined / cualquier set SMO:

### Campos obligatorios (objetivo)

| Campo | Límites | Notas |
|---|---|---|
| `goal` | ≤ 60 chars; como máximo un `{{X}}` | Texto en el tablero. Sin `{{X}}` = goal binaria (sin `range`). |
| `range` | 1–12 enteros positivos, **ascendentes** | Obligatorio **si y solo si** el texto lleva `{{X}}` (y viceversa). |
| `board_categories` | ≤ 4; keys en `limits.board` | Cupos a nivel de tablero. |
| `line_categories` | ≤ 4; keys en `limits.line` | Cupos por línea de bingo. |
| `icons` | ≤ 12; solo `.webp` | Mutuamente excluyente con `emoji`. |
| `progression` | 1–4 de `e`/`m`/`l`/`n`, **únicas** | Zonas Early/Mid/Late/Endgame. En **Bingo** no afectan a la colocación; sí en Rush/Ascend/Summit. |

### Campos opcionales relevantes

| Campo | Límites | Notas |
|---|---|---|
| `individual_limit` | 1–99; **≤ `len(range)`** | Cuántas veces puede salir la misma goal (cada copia usa un valor distinto de `range`). Sin `range` ⇒ efectivo 1. |
| `progressive_ranges` | bool | Si true: umbrales bajos en posiciones tempranas, altos en tardías. Solo tiene sentido con **varios** valores en `range` (y en Combined solo lo activamos si además hay 2+ `progression`). |
| `weighting` | 1–100 (default 100) | Probabilidad de entrar al pool de generación. |
| `tooltip` | ≤ 120 chars; admite `{{X}}` | Texto al hover. |
| `tag` | ≤ 20, `snake_case`, en `tag_names` | Exclusión: como máximo una goal del tag en el tablero. |
| `overlay_icon` / `text_color` / `emoji` / `shiny` / `disabled` | ver wiki | Cosmética o exclusión del pool. |

### Reglas cruzadas (validación dura)

- `{{X}}` ↔ `range` (ambos o ninguno).
- Un solo `{{X}}` por goal.
- `individual_limit` ≤ número de valores en `range`.
- `emoji` XOR `icons`.
- Categorías y `tag` deben existir en `limits` / `tag_names`.
- `forced_positions` solo en schema `dedicated` / `relaxed` (Combined no lo usa).

### Avisos del editor (no invalidan el JSON)

| Aviso | Regla | Notas |
|---|---|---|
| **High Range Variance** | `max(range) > 3 × min_efectivo` | Si `1` está en `range`, el mínimo se cuenta como **2** (“excluding 1”). Ej.: `[1,3,5,7]` → 7 > 3×2; `[3,6,9,12]` → 12 > 3×3. Combined tiene ~37 goals así (4 escalones ×4 a propósito). |

### Range vs progression (puentes entre reinos)

**`range` y `progression` son independientes.** No hace falta `len(range) == len(progression)`.

En este repo, reinos frontera llevan **puente** en `progression` (Sand/Lake `e,m`; Lost/Metro `m,l`; Seaside/Luncheon `l,n`) aunque el umbral sea fijo:

| Ejemplo | `range` | `progression` | Lectura |
|---|---|---|---|
| Lost Butterfly Moons | `[3]` | `m,l` | Cantidad fija 3; puede ir Mid **o** Late |
| Metro Taxi Moons | `[2]` | `m,l` | Idem, puente Mid↔Late |
| Sand Story Moons | `[2]` | `e,m` | Idem, puente Early↔Mid |
| Seaside Uproot Moons | `[2]` | `l,n` | Idem, puente Late↔Endgame |
| All Regional Coins… Large/Small Kingdom | `[1]` / `[1,2]` | `e,m,l,n` | Totales multi-zona |

Eso **no es un error de schema**. El puente vive en `progression` (y weighting), no en la longitud de `range`.

#### Totales y moontype multi-reino → `e,m,l,n`

Independiente de `len(range)`:

1. **Totales / agregados** (`Total Moons`, `Unique Captures`, `All … in {{X}} Kingdoms`, Large/Small Regional, …) → siempre `e,m,l,n` (weighting ~55).
2. **Moontype** (u otros pools transversales) con reinos en las **4 zonas naturales** → `e,m,l,n` (ej. Ground Pound, Treasure Chest), **salvo** si el min del `range` no es completable en Early (Blocks / Outfit Door / Hint-Arts / Warp-Painting → `m,l,n`).
3. Moontype con muchos reinos pero solo 2–3 zonas naturales → progression = esas zonas (Poochy/Rocket Flower `l,n`; Rabbit Chase `m,l,n`).
4. Prefijo de reino (`Sand Ground Pound`, …) → puente mono-reino, no global. Excepción: `Lake Hint Art Moon` → solo `m` (Hint Art no es contenido Early).
5. Overrides narrativos/jugabilidad ganan (Tourist, Minigame, Seeds, Warp-Painting, …).

**No hacer** para “arreglar” avisos/UX:

- Colapsar `progression` a una sola zona (rompe el puente).
- Rellenar `range` con duplicados (`[2,2]`) para igualar longitudes.
- Partir la goal en dos (una por zona) sin rediseñar pool/peso.

**Sí hacer:** dejar el umbral fijo si el pool no admite más escalones; meter la goal en `SINGLE_VALUE_OK` (`Files/ranges_tools.py`) para que `fix_bingo_group_ranges` no invente 4 umbrales. Solo ampliar `range` (p. ej. `[2,3]`) si el balance de juego lo justifica; entonces se puede activar `progressive_ranges`.

Detalle: `Files/apply_progression_accessibility.py` (`KINGDOM_BORDER_PROGRESSION`, `PROGRESSION_OVERRIDES`).
