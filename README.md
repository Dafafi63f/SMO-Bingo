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
- Zone: solo **`zonas_inventario.json`** (`export_zonas_inventario.py`).
- Multi-obtain de tags: solo `TAG_OBTAIN`; capturas: aviso solo si asignadas &lt; pool wiki.
- Lake Warp-Painting / pintura Sand→Lake: availability **base**.
- Icons: `purpletotal` / rotación Sub-Area Regional.
- Catálogo activo: `items_goals`, `palabras_inventario`, `mariowiki_capture_guides`. Fuera: `moon_names_wiki.json`, `sync_lunas.py`.
- Colas de revisión **locales** (gitignored): `zonas_revision.json`, `review_findings.json` — se regeneran y se borran al terminar.

## Pendiente / futuro

Fuente única de pendientes (no repetir en otros README).

- Simulador del **modo Rush** de lockout.live.
- Curar cola local **`zonas_revision.json`** (gitignored; muchos `pendiente`).

## Revisar (híbrido: auto + manual)

No hace falta hacerlo todo a mano ni confiar en un auto-fix ciego. Flujo:

1. **Detectar** (rápido, varios frentes a la vez) → cola de hallazgos.
2. **Priorizar** por `severity` (`warn` > `review` > `info`).
3. **Curar a mano** en la fuente que gane (tablas abajo).
4. **Regenerar** y volver a detectar.

```bash
python Files/review_findings.py                      # todos los frentes
python Files/review_findings.py --front zones,items  # solo algunos
python Files/review_findings.py --list-fronts
python Files/review_findings.py --write              # → Catalog/review_findings.json
python Files/audit_catalog_consistency.py            # CRITICAL/WARN (también es un frente)
python Files/regenerate_all.py --dry-run
```

`review_findings` **no arregla** datos: solo lista sospechos con `fix_hint`.
Puedes atacar frentes distintos en paralelo (zones un día, goals/tags otro).

Colas temporales (solo local, **no van a GitHub**): `Catalog/zonas_revision.json` y `Catalog/review_findings.json`. Regenerar con los scripts; borrar cuando la revisión acabe.

### Un archivo / cola

| Qué | Dónde | Qué mirar |
|-----|--------|-----------|
| Zones dudosas | `Catalog/zonas_revision.json` *(local)* | `status=pendiente`; curar en `zonas_inventario` y regenerar la cola |
| Hallazgos auto | `Catalog/review_findings.json` *(local)* | `severity` + `fix_hint`; regenerar con `review_findings.py --write` |
| Hub de una goal | `Catalog/goals_referencia.json` | `pool` / `moons[]` / `lista[]` / `tags` vs Combined (solo lectura; no editar a mano) |
| Ítem → goals | `Catalog/items_goals.json` | `n_without_goals`, goals raras en un POI (p. ej. Crazy Cap) |
| Slugs / usos | `Catalog/palabras_inventario.json` | palabra con un solo uso raro o alias mal canónico |
| Capturas | `Catalog/capturas_lunas.json` (+ caché wiki) | luna en pool wiki sin asignar; extras curados son OK |
| Icons raros | `Catalog/goal_icons.json` | `n_goals_non_smo`; remap en `export_combined_meta.GOAL_ICON_REMAP` |
| Disponibilidad | `Catalog/project.json` + Combined | availability base/revisit por reino |

### Varios a la vez (si A ≠ B)

| Cruce | Archivos | Gana si chocan | Síntoma típico |
|-------|----------|----------------|----------------|
| Goal en tablero | Combined ↔ `goals_referencia` / `bingo_groups` | **Combined** (+ specs en `sync_objective_moon_groups`) | rango/prog/icon distinto tras regen |
| Contar qué cuenta | Combined + `goal_lists` ↔ `goals_referencia.lista[]` / `moons[]` | **Combined** (pool) + **`goal_lists`** (ítems) | lista vacía, shop sin merchandise, luna de más/menos |
| Ubicación POI/luna | `zonas_inventario` ↔ `zonas_revision` *(local)* | **`zonas_inventario.zone`** | `pendiente` / heurística dudosa en la cola |
| Ítem y sus goals | `zonas_inventario` + `items_goals` ↔ `goals_referencia` | **referencia** (moons/lista) + reglas en `export_items_goals` | POI sin goals, o goal en ítem que no debería |
| Tags de luna | `lunas-objetivos` / `tags_inventario` ↔ `goals_referencia.tags` / `moons[].tag` | **pipeline tags** (`export_lunas_tags` + grupos) | tag en goal pero `tag:false` en la luna |
| Captura ↔ luna | `capturas_lunas` ↔ wiki cache ↔ tags captures | **capturas_lunas** (curado) si extras; wiki si falta del pool | aviso “asignadas &lt; pool” |
| Individuales | `goals_individuales` ↔ `goals_referencia` | mismos `n_templates` / `n_goals`; regen si drift | conteos distintos; lockout invertido (WARN del audit) |
| Líneas / icons | Combined ↔ `bingo_lineas` / `goal_icons` / `goal_tooltips` | **Combined** (+ remap icons) | icon o categoría que no sale en el tablero |
| Grupos bingo | `bingo_groups` ↔ Combined objectives | **specs sync** → regenerar grupos | objective huérfano o moons[] desfasado |

Detalle de qué es editable a mano vs derivado: [`Catalog/README.md`](Catalog/README.md).

## Decisiones (no reabrir sin criterio nuevo)

- **Wedding** weighting `80` (vs Bloom implícito/`100`): a propósito — set mid entre Lake+Wooded; Bloom es local Wooded.
- **Tema boda**: no ampliar el set sin criterio nuevo (retornos postgame fuera de alcance).
- **Tours / paraguas** (Captain Toad, transport, fauna/flora…): dejar salvo rediseño explícito.
- **Nature**: paraguas de 2º orden (fauna+flora); **sin tag `nature`** ni `tags[]` inventada en el hub.
- **Tags raras** (`TAG_RARE_FALLBACK`: rc_car/volbonan→captures, slots→minigame, …): no persistir la forma rara en lunas; el hub no inventa tags ausentes en el pool.
- **`luna` en palabras_inventario**: solo slugs que aparecen como tag en `lunas-objetivos` (no moons[] de un grupo paraguas).
- **Icons no-`smo/`** (~15–17 goals): intencionados (assets de otros packs / remap); el catálogo lleva `n_goals_non_smo`.
- **Capturas vs pool wiki**: asignadas ≥ pool es OK (extras curados); aviso solo si faltan lunas del pool.
- **Multi-obtain de tags**: solo métodos en `TAG_OBTAIN` (no criatura+método).
