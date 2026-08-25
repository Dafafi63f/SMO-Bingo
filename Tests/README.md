# Tests

Suite `unittest` (stdlib) para helpers y consistencia Combined ↔ `Catalog/`
(`test_catalog_files`, `test_combined_integrity`, `test_goals_individuales`,
rango/progression, etc.).

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s Tests -t . -v
mypy .
pre-commit run --all-files
```

En GitHub: `.github/workflows/tests.yml` (+ SonarCloud si hay `SONAR_TOKEN`).
