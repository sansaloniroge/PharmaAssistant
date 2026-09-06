# Release & Versionado — PharmaAssistant

Guía de versionado interno. **No hay pipeline de publicación de imágenes** (ver `docs/ci-cd.md` — el workflow de publicación a AWS ECR nunca funcionó y se eliminó junto con el chart de Helm asociado). Esto documenta cómo versionar el código hoy, no un flujo de release a producción que no existe todavía.

---

## 1) Política de versionado (SemVer)

`MAJOR.MINOR.PATCH` en `pyproject.toml`:

- **MAJOR**: cambios incompatibles (rompen el contrato de `/answer` o el formato de índices).
- **MINOR**: funcionalidades nuevas compatibles.
- **PATCH**: corrección de bugs / mejoras internas.

---

## 2) Al preparar un cambio versionable

1. Actualiza `pyproject.toml`:
   ```toml
   [tool.poetry]
   version = "0.2.0"
   ```
2. Actualiza `CHANGELOG.md` si el proyecto lo mantiene (ver plantilla más abajo).
3. Abre PR → CI verde (`ruff`, `mypy`, `pytest`, build de Docker sin push).
4. Merge a `dev` (y a `master` cuando Roge lo decida manualmente — ver flujo de ramas en `CLAUDE.md`).
5. (Opcional) Tag Git anotado para marcar el punto en el historial:
   ```bash
   git tag -a v0.2.0 -m "Release 0.2.0"
   git push origin v0.2.0
   ```
   Esto es solo un marcador en el historial — no dispara ninguna publicación automática hoy.

### Plantilla de CHANGELOG
```markdown
## [0.2.0] - 2026-08-31
### Added
- ...
### Changed
- ...
### Fixed
- ...
```

---

## 3) Verificación local tras un bump de versión

Sin registry al que hacer pull, la verificación es local, contra la imagen que acabas de construir:

```bash
docker compose up --build -d
curl -s http://localhost:8080/healthz | jq .
curl -s "http://localhost:8080/greet?client_id=farmacia_carmen_sanjuan" -H "x-api-key: <su api key>" | jq .
curl -s http://localhost:8080/metrics | head
```

Checklist:
- [ ] `/healthz` 200 y tenant esperado en la lista.
- [ ] `/greet` y `/answer` 200 con `x-api-key` válida.
- [ ] Métricas visibles en `/metrics`.
- [ ] Sin 5xx inesperados en los logs.

---

## 4) Si en el futuro se añade un destino de despliegue real

Cuando exista un sitio real donde desplegar (Render/Fly.io/registry propio/etc.), esta guía debería ampliarse con: publicación de imagen, pull/verificación en el entorno real, y rollback. No se documenta de antemano un flujo hipotético — se escribe cuando exista el destino real, siguiendo el mismo criterio que el resto del proyecto: no describir como hecho algo que no se ha probado.

---

## 5) Referencias

- CI: `docs/ci-cd.md`
- Observabilidad: `docs/observability.md`
- Getting Started: `docs/getting-started.md`
- Añadir un cliente: `docs/adding-a-client.md`
