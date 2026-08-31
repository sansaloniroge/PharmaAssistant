# CI/CD — PharmaAssistant (NO‑Kubernetes)

Esta guía documenta los **workflows de GitHub Actions** para: linting, type-check, tests con cobertura, build de imagen Docker y **publicación en AWS ECR** con OIDC. Incluye secretos requeridos, políticas mínimas, caché y verificación.

---

## 1) Visión general

- **CI (PRs)** → Lint (`ruff`), type-check (`mypy`), tests (`pytest` + cobertura) y **build de imagen** sin publicar.
- **Publish (main/tags)** → Build & push a **AWS ECR eu‑west‑1** con etiquetas `:sha7`, `:latest`, `:<pyproject_version>` y `:v*`.
- **Data checks (opcional)** → Validar cambios en `data/**` (CSV/YAML).
- **Security (opcional)** → Escaneo de imagen con Trivy.

> El despliegue a Kubernetes (Helm) está documentado aparte; esta guía cubre la parte **agnóstica de infraestructura** (aplicable también a ECS/Fargate, etc.).

---

## 2) Workflows

Crea estos archivos en `.github/workflows/`:

### 2.1 `ci.yml` — Lint/Typecheck/Tests + Build

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
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Poetry
        uses: abatilo/actions-poetry@v3
        with:
          poetry-version: "1.8.3"

      - name: Cache Poetry
        uses: actions/cache@v4
        with:
          path: |
            ~/.cache/pypoetry
            ~/.cache/pip
          key: poetry-${{ runner.os }}-${{ hashFiles('**/poetry.lock') }}

      - name: Install deps
        run: poetry install --no-interaction --no-root

      - name: Ruff (lint)
        run: poetry run ruff check .

      - name: mypy (typecheck)
        run: poetry run mypy .

      - name: Pytest (with coverage)
        run: poetry run pytest -q --cov --cov-report=xml

      - name: Upload coverage XML
        uses: actions/upload-artifact@v4
        with:
          name: coverage-xml
          path: coverage.xml

  docker-build:
    name: Build Docker (no push)
    runs-on: ubuntu-latest
    needs: lint-test

    steps:
      - uses: actions/checkout@v4

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build image (test only)
        uses: docker/build-push-action@v6
        with:
          context: .
          push: false
          tags: test/pharmaassistant:pr-${{ github.event.pull_request.number || github.run_id }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```
**Notas**:
- Cache de Poetry acelera instalaciones.
- Buildx prepara el entorno multi‑arch (útil si quieres `linux/arm64` más adelante).

---

### 2.2 `publish-image.yml` — Publicación a ECR

```yaml
name: Publish Docker Image

on:
  push:
    branches: [ "main" ]
    tags: [ "v*" ]

permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: eu-west-1
  ECR_REPO: pharmaassistant

jobs:
  build-and-push:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Read version from pyproject
        id: ver
        run: |
          python - <<'PY'
import tomllib
with open('pyproject.toml','rb') as f:
    ver = tomllib.load(f)['tool']['poetry']['version']
print(f"::set-output name=py_ver::{ver}")
PY
          echo "sha_short=${GITHUB_SHA::7}" >> $GITHUB_OUTPUT

      - name: Configure AWS (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Set image tags
        id: tags
        run: |
          REG="${{ steps.ecr.outputs.registry }}"
          IMG="$REG/${{ env.ECR_REPO }}"
          SHA="${GITHUB_SHA::7}"
          VER="${{ steps.ver.outputs.py_ver }}"
          TAGS="$IMG:${SHA}"
          if [[ "${GITHUB_REF}" == refs/heads/main ]]; then
            TAGS="$TAGS,$IMG:latest,$IMG:${VER}"
          fi
          if [[ "${GITHUB_REF}" == refs/tags/v* ]]; then
            TAG="${GITHUB_REF#refs/tags/}"
            TAGS="$TAGS,$IMG:${TAG}"
          fi
          echo "tags=$TAGS" >> $GITHUB_OUTPUT
          echo "image=$IMG" >> $GITHUB_OUTPUT

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build & Push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.tags.outputs.tags }}
          cache-from: type=registry,ref=${{ steps.tags.outputs.image }}:buildcache
          cache-to: type=registry,ref=${{ steps.tags.outputs.image }}:buildcache,mode=max

      - name: Output image list
        run: echo "Pushed: ${{ steps.tags.outputs.tags }}"
```

**Requisitos**:
- Secret `AWS_ROLE_ARN` en el repo (ARN del rol con permisos ECR).

**Etiquetas resultantes**:
- `:sha7` siempre.
- En `main`: `:latest` y `:<pyproject_version>`.
- Con tag `v*`: añade `:vX.Y.Z`.

---

### 2.3 `data-checks.yml` (opcional)

Valida datos en PRs que modifiquen `data/**`.

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
        with: { poetry-version: "1.8.3" }
      - run: poetry install --no-interaction --no-root
      - name: Validate catalogs & patterns
        run: |
          python scripts/validate_patterns.py
          python scripts/validate_profiles.py
          # Ajusta por cliente si aplica
          python scripts/validate_catalog.py --client-id client_1 || true
```

---

### 2.4 Trivy (opcional, seguridad)

```yaml
  trivy-scan:
    name: Trivy Scan
    runs-on: ubuntu-latest
    needs: build-and-push
    steps:
      - uses: aquasecurity/trivy-action@0.24.0
        with:
          image-ref: ${{ steps.tags.outputs.image }}:latest
          format: table
          exit-code: "0"     # pon "1" para endurecer
          severity: CRITICAL,HIGH
```

---

## 3) Configuración de AWS OIDC + ECR

### 3.1 Crear repositorio ECR
```bash
aws ecr create-repository --repository-name pharmaassistant --region eu-west-1
```

### 3.2 Rol IAM con OIDC (GitHub)

1. Habilita el **proveedor OIDC** `token.actions.githubusercontent.com` (si no existe).
2. Crea un **rol** que pueda ser asumido por repos de tu organización/proyecto.

**Trust policy (ejemplo mínimo):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com" },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<ORG>/<REPO>:*"
        }
      }
    }
  ]
}
```

**Policy ECR (mínima) adjunta al rol:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:CompleteLayerUpload",
        "ecr:GetDownloadUrlForLayer",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart",
        "ecr:BatchGetImage",
        "ecr:DescribeRepositories",
        "ecr:ListImages"
    ], "Resource": "*" }
  ]
}
```

3. Copia el ARN del rol y configúralo como secret en GitHub: **`AWS_ROLE_ARN`**.

---

## 4) Buenas prácticas

- **Versionado**: actualiza `tool.poetry.version` en `pyproject.toml`; el workflow usará esa versión como tag.
- **Cache de build**: usa `cache-from/to` (GHA o registry) para acelerar builds.
- **Dockerfile**: multi‑stage, no‑root, dependencias separadas (ver Dockerfile del proyecto).
- **.dockerignore**: excluye `tests/`, `data/`, `storage/` si no son necesarios en la imagen.
- **Artefactos**: sube `coverage.xml` como artifact; integra con Codecov si lo deseas.
- **Fail fast**: que CI falle antes de publicar si `ruff/mypy/pytest` no pasan.

---

## 5) Verificación de punta a punta

1) Empuja un PR → debe correr `CI` y quedar en verde.  
2) Merge a `main` → `Publish Docker Image` debe pushear a ECR.  
3) Comprueba en ECR los tags: `latest`, `<sha7>`, `<pyproject_version>`.  
4) **Pull local** para confirmar:
```bash
aws ecr get-login-password --region eu-west-1 \
| docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.eu-west-1.amazonaws.com

docker pull <ACCOUNT>.dkr.ecr.eu-west-1.amazonaws.com/pharmaassistant:latest
```

---

## 6) Troubleshooting

- **`AccessDenied: Not authorized to perform: sts:AssumeRoleWithWebIdentity`**  
  → Revisa **trust policy** (sub debe coincidir `repo:<ORG>/<REPO>:*`) y secret `AWS_ROLE_ARN`.
- **`no basic auth credentials`** al pushear/pullar  
  → Asegúrate de ejecutar el paso `amazon-ecr-login` o de loguearte en local.
- **Builds lentos**  
  → Verifica `cache-from`/`cache-to` y que `poetry.lock` no cambie innecesariamente.
- **Imagen pesada**  
  → Revisa layers en Dockerfile; evita incluir `tests/`, `.git`, `data/` dentro de la imagen.
- **Tags no coinciden con versión**  
  → Asegúrate de actualizar `pyproject.toml` antes de mergear a `main`.

---

## 7) Referencias cruzadas

- **Dockerfile** y **docker-compose.yml** optimizados (ver raíz del repo).
- **Observabilidad**: `docs/observability.md` (métricas, logs, dashboards).
- **Getting Started**: `docs/getting-started.md`.
- **Añadir cliente e indexar**: `docs/adding-a-client.md` y `scripts/build_index.py`.
