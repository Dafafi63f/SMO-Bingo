# Tests

Suite `unittest` (stdlib) para helpers y consistencia Combined ↔ `Catalog/`.

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s Tests -t . -v
mypy .
pre-commit run --all-files
```

En GitHub: `.github/workflows/tests.yml` (+ SonarCloud si hay `SONAR_TOKEN`).
