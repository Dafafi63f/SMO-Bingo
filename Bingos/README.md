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

## Avisos del editor lockout.live (schema)

Al editar/importar goals, lockout puede mostrar avisos de esquema. No rompen el JSON del repo, pero conviene conocerlos:

| Aviso | Regla | Notas |
|---|---|---|
| **High Range Variance** | `max(range) > 3 × min_efectivo` | Si `1` está en `range`, el mínimo se cuenta como **2** (“excluding 1”). Ej.: `[1,3,5,7]` → 7 > 3×2; `[3,6,9,12]` → 12 > 3×3. Combined tiene ~37 goals así (4 escalones ×4 a propósito). |
