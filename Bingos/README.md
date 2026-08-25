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
| `progressive_ranges` | bool | Si true: umbrales bajos en posiciones tempranas, altos en tardías. Solo tiene sentido con **varios** valores en `range` (y en Combined solo lo activamos si además hay 2+ `progression`). Lockout reparte umbrales↔zonas por **solape de intervalos** en `[0,1)`: zona `e` de `m` cubre `[e/m,(e+1)/m)` y umbral `r` de `n` cubre `[r/n,(r+1)/n)`; entran si se solapan. Ejemplos: `n=3,m=2` → e={0,1}, m={1,2} (el del medio en overlap); `n=4,m=2` → e={0,1}, m={2,3} (**sin** overlap). En `goals_individuales`: `progression` = avail→borde; `lockout` = este emparejado (str o lista). Sin reino → `blank_reino` (aunque `progression` vaya vacío). Con reino, overlap en `progression` → lista. Multi-reino con `max(range) <` pool → kingdom blank; `max(range)==pool` sella el último umbral blank al reino final. Warp-Painting con varias entradas → `blank_reino` + progression de entrada (lista); Metro/Mushroom conservan reino. |
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

En este repo, el borde de reino usa puentes continuos
(`e` → `e,m` → `m,l` → `l,n` → `n`). Eso **no** obliga a que cada goal
lleve el puente completo: el tramo Mid “Lost + Cloud + Metro noche” suele
ir solo en `m` (p. ej. Lost Moons, Metro Night, City Hall). Metro día /
Snow/Seaside van en `l,n`; Ruined/Bowser/Moon en `n`.
En `goals_individuales` hay dos campos: **`progression`** (avail→borde del
catálogo) y **`lockout`** (emparejado Lockout de Combined con
`progressive_ranges`; str o lista si overlap). Pueden diferir (Cheep
`m`/`l`/`l` vs `m`/`["m","l"]`/`l`) o coincidir (Lake Moons todo `e`).
Combined compacta las letras de `progression` (p. ej. Cheep → `["m","l"]`).
Cap/Cascade `e` (2); Sand/Lake/Wooded `e,m` (3);
Lost (+Cloud Kingdom + Metro noche hasta 1ª multi) borde `m,l` (goals del
tramo Mid a menudo solo `m`);
Metro día / Snow/Seaside/Luncheon(+Mushroom) `l,n`;
Ruined/Bowser/Moon `n`.
Techo Mid (`run_tier_ceiling.m`) = **lost** para que Rush tras Wooded
siga en ese tramo (no salte a Metro día).
Lake/Wooded conservan el puente `e,m` pero con **weighting 70** (Sand/Cap/Cascade a 100) para no abrir Rush Early.
Luncheon/Mushroom en `l,n` van a **75** (Snow/Seaside/Metro día a 95): mismo rol de fork Late.
Dentro de un mismo `progression`, el peso baja según disponibilidad del umbral mínimo del pool: **base → mid_story (−10) → world_peace (−20)** (más peso = más probable en el pool).
`revisit` = **base del siguiente reino** (Cap/Cascade→Sand; Lost→Metro): Cap/Cascade pesan con Sand; Lost revisit usa el puente Metro (`l,n`) para el peso.

| Ejemplo | `range` | `progression` | Lectura |
|---|---|---|---|
| Lost Butterfly / Metro Night Moons | fijo / `[2,4,6]` | `m` | Tramo Mid (Lost / Cloud / Metro noche) → board **lost** |
| Metro Taxi / Moons (día) | … | `l,n` | Metro día (Late↔Endgame) |
| Sand Story Moons | `[2]` | `e,m` | Puente Early↔Mid (weight 100) |
| Lake / Wooded … | fijo/`{{X}}` | `e,m` | Mismo puente; weight 70 (no primer Rush) |
| Seaside Uproot Moons | `[2]` | `l,n` | Puente Late↔Endgame (Snow/Seaside/…) |
| Luncheon / Mushroom … | fijo/`{{X}}` | `l,n` | Mismo puente |
| All Regional Coins… Large/Small Kingdom | `[1]` / `[1,2]` | `e,m,l,n` | Totales multi-zona |

Eso **no es un error de schema**. El puente vive en `progression` (y weighting), no en la longitud de `range`.

#### Totales y moontype multi-reino → `e,m,l,n`

Independiente de `len(range)`:

1. **Totales / agregados** (`Total Moons`, `Unique Captures`, `All … in {{X}} Kingdoms`, Large/Small Regional, …) → siempre `e,m,l,n` (weighting ~55).
2. **Moontype** (u otros pools transversales) con reinos en las **4 zonas naturales** → `e,m,l,n` (ej. Ground Pound, Treasure Chest, Destructible Blocks, Outfit Door), **salvo** si el min del `range` no es completable en Early (Hint-Arts / Warp-Painting → `m,l,n`).
3. Moontype con muchos reinos pero solo 2–3 zonas naturales → progression = esas zonas (Poochy/Rocket Flower `l,n`; Rabbit Chase `m,l,n`).
4. Prefijo de reino (`Sand Ground Pound`, …) → puente mono-reino, no global.
5. Overrides narrativos/jugabilidad ganan (Tourist, Minigame, Seeds, Warp-Painting, Lake Hint Art → `m`, …).

**No hacer** para “arreglar” avisos/UX:

- Colapsar `progression` a una sola zona (rompe el puente).
- Rellenar `range` con duplicados (`[2,2]`) para igualar longitudes.
- Partir la goal en dos (una por zona) sin rediseñar pool/peso.

**Sí hacer:** dejar el umbral fijo si el pool no admite más escalones; meter la goal en `SINGLE_VALUE_OK` (`Files/ranges_tools.py`) para que `fix_bingo_group_ranges` no invente 4 umbrales. Solo ampliar `range` (p. ej. `[2,3]`) si el balance de juego lo justifica; entonces se puede activar `progressive_ranges`.

Detalle: `Files/apply_progression_accessibility.py` (`KINGDOM_BORDER_PROGRESSION`, `PROGRESSION_OVERRIDES`).

## goals_individuales.json (Catalog/)

Export derivado de `goals_referencia.json` para consultar cada template con reino y zonas Rush/Lockout.

| Grupo | Contenido |
|---|---|
| `cap`, `sand`, … | Goals mono-reino: `goal`, `progression`, `lockout` |
| `blank_reino` | Totales/globales/multi-zona: añade `kingdom` por fila |
| `early`, `mid`, `late`, `endgame` | Índice por zona e/m/l/n (copia goals cuya progression toca esa letra) |

- **`progression`**: avail→borde del catálogo (`disponibilidad` + reglas de reino).
- **`lockout`**: emparejado `progressive_ranges` del Combined (puede ser lista si hay overlap).
- **`n_goals`**: templates únicas; los grupos de zona duplican filas a propósito.
- Regenerar: `python Files/export_goals_individuales.py` o `regenerate_all.py`.
- Índice de catálogos: `Catalog/README.md`.
