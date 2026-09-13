# Tests

Suite `unittest` (stdlib) para helpers y consistencia Combined ↔ `Catalog/`
(`test_catalog_files`, `test_combined_integrity`, `test_goals_individuales`,
`test_lockout_merch_icons`, `test_regenerate_lib`, rango/progression, etc.).

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s Tests -t . -v
mypy .
pre-commit run --all-files
```

En GitHub: `.github/workflows/tests.yml` (+ SonarCloud si hay `SONAR_TOKEN`).

## Notas de convención

- Combined: glob `Super Mario Odyssey-Combined-*.json` (no fijar fecha en el test).
- Zone: asserts contra **`zonas_inventario.json`**.

Cambios y pendientes del repo: [`README.md`](../README.md#cambios-recientes-2026-09).
