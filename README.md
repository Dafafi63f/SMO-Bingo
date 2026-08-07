# SMO Bingo

Respaldo personal del bingo de **Super Mario Odyssey** para [lockout.live](https://lockout.live/).

Repo: https://github.com/Dafafi63f/SMO-Bingo

## Flujo habitual

1. Editar goals en el Combined (`bingos/`).
2. Regenerar catálogo y exports:

```bash
python regenerate_all.py
```

Python 3 estándar; no hace falta `pip install` (solo librería estándar).

## Estructura

| Ruta | Rol |
|------|-----|
| [`bingos/`](bingos/README.md) | JSONs lockout; Combined = **fuente de verdad** |
| [`catalog/`](catalog/) | Datos derivados (grupos, líneas, icons, lunas, tags, referencia) |
| [`tests/`](tests/README.md) | Unit + integridad Combined/catálogo |
| `*.py` | Sync, ranges, progression y exports |

```bash
python -m unittest discover -s tests -t . -v
```

Detalle de cada set lockout: [`bingos/README.md`](bingos/README.md).
