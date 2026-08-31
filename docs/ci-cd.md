# CI/CD — PharmaAssistant

Esta guía documenta el workflow real de GitHub Actions: lint, type-check, tests con cobertura, y build de la imagen Docker (sin publicar). No hay pipeline de publicación a ningún registry — ver la nota al final.

---

## 1) Visión general

- **CI (PRs)** → Lint (`ruff`), type-check (`mypy`), tests (`pytest` + cobertura) y **build de imagen** sin publicar. Es lo único que corre hoy en CI, y es real: se puede verificar en la pestaña Actions del repo.

> **Nota honesta**: en una versión anterior de este documento se describía también un workflow de publicación a AWS ECR con OIDC. Se quitó — ese workflow falló el 100% de las veces que se disparó (siempre en 0 segundos, por falta de configuración de AWS) y nunca llegó a publicar una imagen real. En vez de mantener una plantilla nunca probada, se eliminó junto con el chart de Helm asociado (`deploy/helm/`). El despliegue real y verificado de este proyecto es `docker compose up` (ver `docs/getting-started.md`).

---

## 2) Workflow: `ci.yml` — Lint/Typecheck/Tests + Build

```yaml
name: CI

on:
  pull_request:
    branches: [ "*" ]

permissions:
  contents: read

jobs:
  lint-test:
    name: Lint / Typecheck / Tests
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - uses: abatilo/actions-poetry@v3
        with:
          poetry-version: "2.1.3"

      - uses: actions/cache@v4
        with:
          path: |
            ~/.cache/pypoetry
            ~/.cache/pip
          key: poetry-${{ runner.os }}-${{ hashFiles('**/poetry.lock') }}

      - run: poetry install --no-interaction --no-root --sync
      - run: poetry run mypy .
      - run: poetry run ruff check .
      - run: poetry run pytest -q --cov --cov-report=xml

      - uses: actions/upload-artifact@v4
        with:
          name: coverage-xml
          path: coverage.xml

  docker-build:
    name: Build Docker (no push)
    runs-on: ubuntu-latest
    needs: lint-test
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: false
          tags: test/pharmaassistant:pr-${{ github.event.pull_request.number || github.run_id }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**Notas**:
- Cache de Poetry acelera instalaciones.
- El build de Docker valida que la imagen se construye, pero nunca se publica a ningún sitio.

---

## 3) `data-checks.yml` (opcional, no implementado todavía)

Si en algún momento se quiere validar cambios en `data/**` en PRs:

```yaml
name: Data Checks

on:
  pull_request:
    paths:
      - "data/**"

jobs:
  validate-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: abatilo/actions-poetry@v3
        with: { poetry-version: "2.1.3" }
      - run: poetry install --no-interaction --no-root
      - run: |
          python scripts/validate_patterns.py
          python scripts/validate_profiles.py
          python scripts/validate_catalog.py --client-id farmacia_carmen_sanjuan || true
```

Este workflow no existe todavía en `.github/workflows/` — es una propuesta, marcada explícitamente como tal.

---

## 4) Buenas prácticas

- **Versionado**: `tool.poetry.version` en `pyproject.toml` como referencia interna (sin pipeline de publicación que lo consuma automáticamente por ahora).
- **Cache de build**: `cache-from/to` con GHA acelera los builds.
- **Dockerfile**: multi-stage, no-root, dependencias separadas (ver `Dockerfile`).
- **`.dockerignore`**: excluye `tests/`, `data/`, `storage/` del build.
- **Fail fast**: CI falla si `ruff`/`mypy`/`pytest` no pasan.

---

## 5) Verificación

1. Abre un PR → debe correr `CI` (lint-test + docker-build) y quedar en verde.
2. Merge a `dev` (o `master` cuando corresponda) → sin publicación automática de imagen; si se necesita una imagen para desplegar, se construye manualmente (`docker build .`) o se reintroduce un pipeline de publicación cuando haya un destino real configurado.

---

## 6) Referencias cruzadas

- **Dockerfile** y **docker-compose.yml** (raíz del repo).
- **Getting Started**: `docs/getting-started.md`.
- **Observabilidad**: `docs/observability.md`.
