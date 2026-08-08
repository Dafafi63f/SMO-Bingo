# SMO Bingo

Respaldo personal del bingo de **Super Mario Odyssey** para [lockout.live](https://lockout.live/).

## Flujo habitual

1. Editar goals en el Combined (`Bingos/`).
2. Regenerar catálogo y exports:

```bash
python Files/regenerate_all.py
```

Python 3 estándar para el bingo; herramientas de CI:

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s Tests -t . -v
mypy .
pre-commit run --all-files
```

## Estructura

| Ruta | Rol |
|------|-----|
| [`Bingos/`](Bingos/README.md) | JSONs lockout; Combined = **fuente de verdad** |
| [`Catalog/`](Catalog/) | Datos derivados (grupos, líneas, icons, lunas, tags, referencia) |
| [`Files/`](Files/) | Scripts Python (sync, ranges, progression, exports) |
| [`Tests/`](Tests/README.md) | Unit + integridad Combined/catálogo |

## CI

GitHub Actions:

| Workflow | Jobs |
|----------|------|
| **Tests** | Pre-Commits, Unit + integrity, MyPy, tests-summary |
| **SonarCloud** | Análisis (requiere `SONAR_TOKEN`; si falta, el job se omite) |

Ficheros: `.github/workflows/tests.yml`, `sonarcloud.yml`, `.pre-commit-config.yaml`, `mypy.ini`, `sonar-project.properties`, `.python-version`.

**SonarCloud (una vez):** en [SonarCloud](https://sonarcloud.io) importa `SMO-Bingo` → confirma `sonar.organization` / `sonar.projectKey` en `sonar-project.properties` → crea token → secreto `SONAR_TOKEN` en GitHub.

Detalle de cada set lockout: [`Bingos/README.md`](Bingos/README.md).
