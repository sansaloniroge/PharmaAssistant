# Release & Versionado — PharmaAssistant

Guía para planificar, crear y verificar **releases**. Cubre versionado (SemVer), el flujo con **GitHub Actions** (build & push a ECR), checklist, **rollback** y **hotfixes**.

---

## 1) Política de versionado (SemVer)

Usamos **SemVer** `MAJOR.MINOR.PATCH`:

- **MAJOR**: cambios incompatibles (rompen contratos de API o datos).
- **MINOR**: funcionalidades nuevas compatibles.
- **PATCH**: corrección de bugs / mejoras internas sin cambios de contrato.

**Cuándo subir cada dígito:**
- Cambios en el **contrato de `/answer`** o en **formato de índices** → MAJOR.
- Nuevos endpoints / flags mantenidos compatibles → MINOR.
- Ajustes internos, rendimiento, docs → PATCH.

> Mantén el `CHANGELOG.md` sincronizado con cada incremento.

---

## 2) Flujo de release (resumen)

1. Abre PR con cambios → CI: **ruff**, **mypy**, **pytest**, **build Docker** (sin push).
2. **Bump** de versión en `pyproject.toml`.
3. Merge a `main` → workflow **Publish Docker Image** **empuja** a ECR tags: `:sha7`, `:latest`, `:<pyproject_version>`.
4. (Opcional) Crea tag Git `vX.Y.Z` → también se publicará `:vX.Y.Z`.
5. Verifica en ECR / despliegue que todo responde correctamente.
6. Actualiza `CHANGELOG.md` y documentación si aplica.

---

## 3) Preparar un release

### 3.1 Bump de versión
Edita `pyproject.toml`:

```toml
[tool.poetry]
version = "0.2.0"  # <- actualiza aquí
```

### 3.2 Changelog
Actualiza `CHANGELOG.md` (formato sugerido):
```markdown
## [0.2.0] - 2025-09-18
### Added
- Endpoint /tenants/{id}/index/status
- Métrica recommendations_total

### Changed
- Logs en JSON con latencia y tenant

### Fixed
- Manejo de 429 con cabeceras X-RateLimit-*
```

### 3.3 Merge a `main`
- Asegúrate de que CI esté **verde**.
- El workflow `Publish Docker Image` subirá las etiquetas:
  - `:sha7`
  - `:latest`
  - `:<pyproject_version>` (p. ej., `:0.2.0`)

### 3.4 (Opcional) Tag anotado
```bash
git tag -a v0.2.0 -m "Release 0.2.0"
git push origin v0.2.0
```
El workflow añadirá la imagen `:v0.2.0`.

---

## 4) Verificación post-publicación

### 4.1 Consultar ECR y tirar de la imagen
```bash
aws ecr get-login-password --region eu-west-1 \
| docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.eu-west-1.amazonaws.com

docker pull <ACCOUNT>.dkr.ecr.eu-west-1.amazonaws.com/pharmaassistant:0.2.0
```

### 4.2 Smoke test local rápido
```bash
docker run --rm -p 8080:8080 \
  -e LOG_LEVEL=INFO \
  -e PRELOAD_TENANTS=client_1 \
  -v $PWD/data:/app/data:ro \
  -v $PWD/profiles:/app/profiles:ro \
  -v $PWD/storage:/app/storage \
  -v $PWD/service/tenants.yaml:/app/service/tenants.yaml:ro \
  <ACCOUNT>.dkr.ecr.eu-west-1.amazonaws.com/pharmaassistant:0.2.0

# En otra terminal:
curl -s http://localhost:8080/healthz | jq .
curl -s "http://localhost:8080/greet?client_id=client_1" -H "x-api-key: secret_key_client_1" | jq .
curl -s http://localhost:8080/metrics | head
```

### 4.3 Checklist
- [ ] `/healthz` 200 y lista de tenants correcta.  
- [ ] `/readyz` 200 (si hay `PRELOAD_TENANTS`).  
- [ ] `/greet` y `/answer` 200 con `x-api-key` válida.  
- [ ] Métricas visibles en `/metrics`.  
- [ ] Logs JSON con latencia y tenant.  
- [ ] Sin incrementos inesperados de 5xx.

---

## 5) Rollback

Si un release falla, vuelve a la **imagen previa conocida**:

### 5.1 Usando etiquetas de imagen
- Actualiza el despliegue para usar `:<versión_anterior>` (por ejemplo `:0.1.5`).  
- O retaggea `latest` al tag estable:
  ```bash
  # ejemplo: retag local y volver a publicar si lo controlas fuera de CI
  docker pull <ECR>/pharmaassistant:0.1.5
  docker tag <ECR>/pharmaassistant:0.1.5 <ECR>/pharmaassistant:latest
  docker push <ECR>/pharmaassistant:latest
  ```

### 5.2 Validación posterior
- Repite **smoke tests** y revisión de métricas.
- Registra un **postmortem** (ver `docs/templates/postmortem.md`).

> Consejo: conserva al menos 3–5 versiones anteriores disponibles en ECR.

---

## 6) Hotfixes

Para arreglos urgentes sobre un release en producción:

1. Crea una rama desde `main` (o desde el tag si es necesario):
   ```bash
   git checkout -b hotfix/fix-500-on-answer
   ```
2. Aplica el fix y sube **PATCH** en `pyproject.toml` (p. ej., `0.2.1`).  
3. PR → CI verde → merge a `main`.  
4. El workflow publicará `:0.2.1` (y `:latest`), y si creas `v0.2.1`, también `:v0.2.1`.  
5. Despliega y verifica como en el punto 4.

---

## 7) Pre-releases (rc/beta)

Si quieres liberar candidatas sin pisar `latest`:

- Etiqueta Git como `v0.3.0-rc1` y ajusta workflow para publicar `:v0.3.0-rc1` (sin `latest`).  
- O usa una rama `release/0.3.0` y publica imágenes con tags `:0.3.0-rc1`, `:0.3.0-rc2`, etc.  
- En despliegues de staging, referencia explícitamente esos tags.

> Actualmente el workflow estándar publica `latest` en `main`. Si no quieres eso para RCs, usa ramas separadas o modifica la condición de publicación en el workflow.

---

## 8) Recomendaciones operativas

- **Congela cambios** no críticos 24h antes de una release mayor.
- **Monitorea** error rate y p95 tras cada release (ver `docs/observability.md`).
- **Backups** de `data/` y `storage/` si no son reconstruibles fácilmente.
- **Automatiza** el bump de versión y generación de changelog si quieres (p. ej., `python-semantic-release`).

---

## 9) Plantilla de PR de release

Incluye esta checklist en la descripción del PR:

```markdown
### Release v0.2.0 — Checklist
- [ ] Bump en pyproject.toml
- [ ] CHANGELOG.md actualizado
- [ ] CI verde (ruff, mypy, pytest, build)
- [ ] Imagen en ECR (:sha7, :latest, :0.2.0)
- [ ] Smoke test local OK
- [ ] Observabilidad revisada (errores/latencia)
- [ ] Documentación actualizada (si aplica)
```

---

## 10) Referencias

- CI/CD: `docs/ci-cd.md`
- Observabilidad: `docs/observability.md`
- Getting Started: `docs/getting-started.md`
- Añadir un cliente: `docs/adding-a-client.md`
- Plantillas: `docs/templates/adr.md`, `docs/templates/postmortem.md`
- Runbooks: `ops/`
