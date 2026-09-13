# SMO Bingo

Respaldo personal del bingo de **Super Mario Odyssey** para [lockout.live](https://lockout.live/).

## Descargar Combined

JSON listo para importar en lockout (siempre la última versión del repo):

**[Descargar Super-Mario-Odyssey-Combined.json](https://github.com/Dafafi63f/SMO-Bingo/releases/latest/download/Super-Mario-Odyssey-Combined.json)**

También en [Releases](https://github.com/Dafafi63f/SMO-Bingo/releases/tag/combined) (tag `combined`, se actualiza al cambiar el Combined en `main`).

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
| [`Catalog/`](Catalog/README.md) | Datos derivados (grupos, líneas, icons, lunas, tags, referencia, zonas) |
| [`Files/`](Files/README.md) | Scripts Python (sync, ranges, progression, exports) |
| [`Tests/`](Tests/README.md) | Unit + integridad Combined/catálogo |

## CI

GitHub Actions:

| Workflow | Jobs |
|----------|------|
| **Tests** | Pre-Commits, Unit + integrity, MyPy, tests-summary |
| **SonarCloud** | Análisis (requiere `SONAR_TOKEN`; si falta, el job se omite) |
| **Release Combined** | Al cambiar Combined en `main`, actualiza el release `combined` |

Ficheros: `.github/workflows/tests.yml`, `sonarcloud.yml`, `release-combined.yml`, `.pre-commit-config.yaml`, `mypy.ini`, `sonar-project.properties`, `.python-version`.

**SonarCloud (una vez):** en [SonarCloud](https://sonarcloud.io) importa `SMO-Bingo` → confirma `sonar.organization` / `sonar.projectKey` en `sonar-project.properties` → crea token → secreto `SONAR_TOKEN` en GitHub.

Detalle de sets lockout, schema de goals y puentes `range`/`progression`: [`Bingos/README.md`](Bingos/README.md).

## Cambios recientes (2026-09)

Fuente única de changelog del repo (no repetir en otros README).

- Combined `2026-09-13`: **`{{X}} Wedding Moons`** — `range: [2]`, Lake `#21` + Wooded `#27`, `moontype`, prog `m`, icon `heartflowerbloom`; en grupo `cappy`.
- **`{{X}} Lost Trapeetle Moons`**: `[1,2]` → `[2]`, sin `[[s]]` (cada luna ya cuenta en Cage / Blocks).
- Naming: `Moon[[s]]` solo si `1 ∈ range`; mínimo ≥2 → `Moons` fijo (detalle en Bingos README). Ambas en `SINGLE_VALUE_OK`.
- Zone: solo **`zonas_inventario.json`** (eliminado `zonas_reino.json`); script `export_zonas_inventario.py`.
- Multi-obtain de tags: solo `TAG_OBTAIN`; capturas: aviso solo si asignadas &lt; pool wiki.
- Lake Warp-Painting / pintura Sand→Lake: availability **base**.
- Icons: `purpletotal` / rotación Sub-Area Regional.
- Catálogo activo: `items_goals`, `zonas_revision`, `palabras_inventario`, `mariowiki_capture_guides`. Fuera: `moon_names_wiki.json`, `sync_lunas.py`.

## Pendiente / futuro

Fuente única de pendientes (no repetir en otros README).

- Simulador del **modo Rush** de lockout.live.
- Curar cola **`zonas_revision.json`** (muchos `pendiente`).

## Decisiones (no reabrir sin criterio nuevo)

- **Wedding** weighting `80` (vs Bloom implícito/`100`): a propósito — set mid entre Lake+Wooded; Bloom es local Wooded.
- **Tema boda**: no ampliar el set sin criterio nuevo (retornos postgame fuera de alcance).
- **Tours / paraguas** (Captain Toad, transport, fauna/flora…): dejar salvo rediseño explícito.
- **Icons no-`smo/`** (~15–17 goals): intencionados (assets de otros packs / remap); el catálogo lleva `n_goals_non_smo`.
- **Capturas vs pool wiki**: asignadas ≥ pool es OK (extras curados); aviso solo si faltan lunas del pool.
- **Multi-obtain de tags**: solo métodos en `TAG_OBTAIN` (no criatura+método).
