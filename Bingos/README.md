# Bingos (sets lockout.live)

JSON importables en [lockout.live](https://lockout.live/) para Super Mario Odyssey.

| Archivo | Rol |
|---|---|
| `Super Mario Odyssey-Combined-2026-08-07.json` | **Fuente de verdad** del proyecto (editar goals aquí) |
| `Super Mario Odyssey-Short Goals-2026-07-27.json` | Referencia lockout (91 goals) |
| `Super Mario Odyssey-Default-2026-07-27.json` | Referencia lockout (108 goals) |
| `Super Mario Odyssey-Long Goals-2026-07-27.json` | Referencia lockout (126 goals) |
| `Super Mario Odyssey-All Kingdoms-2026-07-24.json` | Referencia lockout (más completo; umbrales altos) |

Tras cambiar Combined: `python Files/regenerate_all.py`

Datos derivados (grupos, líneas, icons, referencia): `Catalog/`.

## Avisos del editor lockout.live (schema)

Al editar/importar goals, lockout puede mostrar avisos de esquema. No rompen el JSON del repo, pero conviene conocerlos:

| Aviso | Regla | Notas |
|---|---|---|
| **High Range Variance** | `max(range) ≤ 3 × min(range)` | p. ej. `[3,6,9,12]` avisa (12 = 4×3). Muchos goals Combined usan 4 escalones aritméticos a propósito; si el aviso molesta, subir el mínimo o acortar el último umbral. |
| **`[[s]]` / `[[es]]`** | Solo si `1` puede salir en `range` | Si `min(range) ≥ 2`, plural fijo (`Moons`, `Switches`, …). |
