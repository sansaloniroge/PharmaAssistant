# Arquitectura — PharmaAssistant

Documento de referencia para entender **cómo está organizado** el sistema, sus **componentes**, **flujos de datos**, contratos y decisiones clave. Útil para desarrollo, operaciones y onboarding.

---

## Visión general

- **API (serving online):** FastAPI en `service/main.py`. Expone endpoints `/healthz`, `/readyz`, `/metrics`, `/greet`, `/answer`, y utilidades por tenant.
- **Core de dominio (app):** lógica de negocio y utilidades en `app/` (carga de perfiles, patrones, parsers, asistentes).
- **Ingesta offline:** `scripts/` para construir índices (`embeddings.npy` + `meta.json`) desde los catálogos CSV de cada cliente.
- **Multi-tenant:** configuración, prompts y catálogos por cliente en `data/clients/<id>/`; perfiles en `profiles/clients/<id>.yaml`; índices en `storage/<id>/`.
- **Observabilidad:** logs JSON (middleware) y métricas Prometheus en `/metrics`.
- **Despliegue:** local con Docker Compose, y (opcional) Helm/Kubernetes en `deploy/helm/`.

---

## Diagrama de componentes (alto nivel)

```
+----------------------+        +-------------------+          +----------------------+
|   Frontend / Caller  | <----> |  FastAPI Service  | <------> |  Core (app/*)        |
|  (clientes/operador) |  HTTP  | (service/main.py) |          |  - PharmaAssistant   |
+----------------------+        +-------------------+          |  - loaders/parsers   |
                                  ^         ^                  +----------+-----------+
                                  |         |                             |
                                  |         |                             |
                                  |         |                 +-----------v------------+
                                  |         +-----------------+   Index Loader         |
                                  |                           | (service/index_loader) |
                                  |                           +-----------+------------+
                                  |                                       |
                                  |                                       |
                                  |                           +-----------v------------+
                                  |                           |   Storage por tenant   |
                                  |                           | storage/<id>/          |
                                  |                           |  - embeddings.npy      |
                                  |                           |  - meta.json           |
                                  |                           +------------------------+
                                  |
                                  +---------------------------+
                                                              |
                                      +-----------------------v------------------+
                                      |         Data & Config por tenant         |
                                      | data/clients/<id>/{catalogo,prompts}     |
                                      | profiles/clients/<id>.yaml               |
                                      +------------------------------------------+
```

---

## Estructura del repositorio (resumen)

```
app/                     # Núcleo de dominio (PharmaAssistant, loaders/parsers)
service/                 # API (FastAPI), seguridad CORS/headers, cuotas, métricas
scripts/                 # Ingesta offline: build/rebuild índices, validadores
data/                    # Patrones globales y datos por cliente (catálogos, prompts)
profiles/                # Perfiles por cliente (YAML)
storage/                 # Artefactos de índice por cliente (generado)
deploy/helm/             # (Opcional) Helm chart para Kubernetes
docs/, ops/              # Documentación y runbooks
```

---

## Flujos de datos

### 1) Ingesta / Construcción de índices (offline)
1. `data/clients/<id>/products_catalog.csv` — CSV por cliente.
2. `python scripts/build_index.py --client-id <id>`
3. El script crea:
   - `storage/<id>/embeddings.npy` (`float32` `[N,D]`)
   - `storage/<id>/meta.json` (lista de `N` filas con las columnas del CSV)
   - `storage/<id>/index_info.json` (conteo, dim, bytes, versión)
4. (Opcional) `python -m scripts.rebuild_all` para todos los clientes.

**Contrato:** el número de filas de `meta.json` debe coincidir con `embeddings.npy.shape[0]`.

### 2) Serving / Respuesta online
1. Cliente llama a `/answer?client_id=<id>` con header `x-api-key`.
2. `service/main.py` aplica **auth** (`auth_guard`) y **cuotas** (`quota_guard`).
3. Carga el asistente del cliente (`get_assistant_for` → `app/`).
4. Si hace falta, carga índice en caliente (`service/index_loader.py`).
5. Ejecuta la lógica del asistente y devuelve la respuesta.
6. Observabilidad: incrementa métricas (`http_*`, `recommendations_total`) y emite logs JSON.

---

## Diseño multi-tenant

- **Identidad de tenant:** `client_id` (query param), `x-api-key` (header).
- **Configuración por tenant:**
  - `profiles/clients/<id>.yaml` (locale, tono, rutas, overrides).
  - `data/clients/<id>/prompts/*.txt` (prompts específicos).
  - `data/clients/<id>/patterns/*.yaml` (overrides opcionales).
- **Catálogo por tenant:** `data/clients/<id>/products_catalog.csv`.
- **Almacenamiento:** `storage/<id>/{embeddings.npy, meta.json, index_info.json}`.
- **Tenants y cuotas:** `service/tenants.yaml` (API key y `max_requests_per_day`).

> El endpoint `/readyz` puede precalentar (`PRELOAD_TENANTS`) para mejorar el primer acceso.

---

## Contratos y formatos

### Catálogo CSV
- Columnas “lógicas” requeridas: **producto**, **precio**, **categoría** (con alias aceptados).
- Precios normalizables a `float` (soporta `12,50`, `€12.50`, etc.).
- Sin duplicados de producto.

### Índice
- `embeddings.npy`: matriz `[N,D]` tipo `float32`.
- `meta.json`: longitud `N`; cada elemento es un dict con las columnas del CSV.
- `index_info.json`: `{"count": N, "dim": D, "bytes": ..., "version": "v1"}`.

### Perfiles y prompts
- `profiles/clients/<id>.yaml`: claves recomendadas `id`, `name`, `locale`, `tone`.
- `data/clients/<id>/prompts/*.txt`: `system`, `compose`, `greeting`, `few_shot`, `no_match`.

---

## API (resumen)

Base: `http://HOST:8080`

- `GET /healthz` → estado básico del servicio.
- `GET /readyz` → readiness (incluye resultado de preload si se configuró).
- `GET /tenants/{id}/healthz` → valida carga de ese tenant (respuesta genérica en error; detalle en logs).
- `GET /tenants/{id}/index/status` → estado del índice (existe, `count`, `dim`, `path`).
- `GET /greet?client_id=<id>` (+ `x-api-key`) → saludo.
- `POST /answer?client_id=<id>` (+ `x-api-key`, body `{"message": "..."}`) → respuesta del asistente.
- `GET /metrics` → métricas Prometheus (`http_requests_total`, `http_request_duration_seconds`, `recommendations_total`).

Autenticación: **API key** por tenant (`service/tenants.yaml`).  
Cuotas: **límite diario** con cabeceras `X-RateLimit-Limit` y `X-RateLimit-Remaining`.

---

## Observabilidad

- **Logs JSON**: configurados en `service/logging_setup.py` y middleware de acceso en `service/main.py`. Incluyen método, ruta, estado, latencia y `tenant`.
- **Métricas Prometheus** (`service/metrics.py`):
  - `http_requests_total{method,path,status}`
  - `http_request_duration_seconds_bucket/sum/count{method,path}`
  - `recommendations_total{client_id}` (métrica de negocio)
- **Trazas (opcional)**: OpenTelemetry con exportador a consola (`service/tracing.py`).

---

## Seguridad

- **Auth**: API key por tenant; rechazo genérico en errores (`401`/`403`/`429`).
- **Cuotas**: protección frente a abuso (rate-limit diario).
- **CORS**: restringido por `ALLOWED_ORIGINS`.
- **Security headers**: configurados en `service/cors_security.py`.
- **No filtrar internals** en respuestas (los stacktraces van a logs).
- **Secretos**: no versionar; inyectar por entorno o secret manager.

---

## Errores y resiliencia

- Respuestas 5xx **genéricas** (detalle en logs).
- `PodDisruptionBudget`/HPA/NetworkPolicy disponibles si despliegas en Kubernetes (ver Helm).
- `PRELOAD_TENANTS` para calentar perfiles/índices críticos y mejorar errores de primer acceso.

---

## Rendimiento y escalabilidad

- **Separación de ingesta** (offline) → el serving es ligero.
- **Cache por tenant** (`lru_cache`) para asistentes y carga de perfiles.
- **Embeddings**: tamaño `N` y dimensión `D` impactan memoria/tiempo de carga (ver `index_info.json`).
- **Autoescalado** (si K8s): HPA por CPU/latencia y PDB para alta disponibilidad.
- **Cold start**: mitigable con preload y warmup.

---

## Desarrollo local vs Producción

- **Local**: Docker Compose (`pharmaassistant`), volúmenes para `data/`, `profiles/`, `storage/`, `service/tenants.yaml`.
- **Prod**: Contenedor no-root, logs a stdout, métricas en `/metrics`, secretos por gestor (AWS/GCP/Azure) o variables de entorno. Opcional Kubernetes/Helm.

---

## ADRs (decisiones de arquitectura)

Usa `docs/templates/adr.md` para registrar decisiones importantes:
- Elección de modelo de embeddings
- Cambio de estructura de índices o storage
- New endpoints/contratos
- Política de autenticación/cuotas

---

## Roadmap / Mejoras futuras (ideas)

- Sustituir embedding “hash” por un modelo local determinista de mayor calidad en dev.
- Añadir **Paginated Search**/RAG con FAISS/ScaNN y filtros por categoría/brand.
- Integración de **caché de respuestas** por tenant/pregunta.
- Alertas automáticas sobre métricas de error/latencia y cuotas al 90%.
- `Great Expectations` o `Pandera` para validaciones más formales de datos.

---

## Referencias cruzadas

- **Getting Started:** `docs/getting-started.md`
- **Observabilidad:** `docs/observability.md`
- **CI/CD:** `docs/ci-cd.md`
- **Añadir un cliente:** `docs/adding-a-client.md`
- **Runbooks:** `ops/`

---

_Última actualización: mantenla en sincronía con cambios de código y despliegue._
