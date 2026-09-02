# Configuración — PharmaAssistant

Este documento resume **todas las opciones de configuración**, **archivos clave** y **precedencias** para ejecutar PharmaAssistant en local, Docker/Compose o cualquier PaaS. Incluye ejemplos listos para copiar.

---

## 1) Variables de entorno (runtime)

Estas variables se leen en `service/main.py` y afectan al comportamiento del servicio.

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `LOG_LEVEL` | Nivel de logs (`DEBUG`, `INFO`, `WARNING`, …) | `INFO` |
| `ALLOWED_ORIGINS` | Lista CORS separada por comas (URLs completas) | vacío (CORS cerrado) |
| `PRELOAD_TENANTS` | Lista separada por comas de tenants que se **precargan** en startup (perfiles/índices) | vacío |
| `OPENAI_API_KEY` | Habilita embeddings OpenAI en `scripts/build_index.py` (modo `auto`) | — |
| `STORAGE_BASE` | Directorio base donde se leen índices (`embeddings.npy`, `meta.json`) | `storage/` |
| `PORT` | Puerto HTTP (si usas un entrypoint distinto a uvicorn por defecto) | `8080` |
| `UVICORN_WORKERS` | Nº de workers si ejecutas `uvicorn` en modo multiworker | `1` |

> Sugerencia: usa un archivo `.env` en desarrollo y `docker-compose.yml` lee automáticamente `ENV=valor` si lo referencian con `${VAR}`.

### Ejemplo `.env` (desarrollo)
```dotenv
LOG_LEVEL=INFO
ALLOWED_ORIGINS=https://tu-frontend.com,https://admin.tu-frontend.com
PRELOAD_TENANTS=client_1
OPENAI_API_KEY=sk-***
STORAGE_BASE=/app/storage
```

---

## 2) Archivos de configuración (proyecto)

### 2.1 `service/tenants.yaml` (requerido)
Define **API keys** y **cuotas diarias** por tenant.

```yaml
tenants:
  client_1:
    api_key: "secret_key_client_1"
    max_requests_per_day: 1000
  client_2:
    api_key: "secret_key_client_2"
    max_requests_per_day: 500
```

- **No** lo versionees con claves reales. Monta este archivo por volumen en Docker o usa un gestor de secretos en producción.
- La API expone cabeceras `X-RateLimit-Limit` y `X-RateLimit-Remaining`.

### 2.2 Datos por cliente (`data/clients/<id>/`)

```
data/clients/<id>/
├── products_catalog.csv           # catálogo (CSV)
├── prompts/                       # prompts específicos
│   ├── compose_prompt.txt
│   ├── few_shot_prompt.txt
│   ├── greeting_prompt.txt
│   ├── no_match_prompt.txt
│   └── system_prompt.txt
└── patterns/ (opcional, overrides)
    ├── category_patterns.yaml
    ├── price_patterns.yaml
    └── schema_map.yaml
```

### 2.3 Patrones globales (`data/patterns/`)

Valores **por defecto** (fallback) si el cliente no define overrides en `data/clients/<id>/patterns/`:

- `category_patterns.yaml`
- `price_patterns.yaml`
- `schema_map.yaml`
- `skin_types.yaml`
- `medical_terms.yaml`

### 2.4 Perfiles (`profiles/clients/<id>.yaml`)

Perfil del cliente (idioma, tono, rutas personalizadas). Claves mínimas recomendadas:

```yaml
id: client_1
name: "Farmacia Demo"
locale: "es-ES"
tone: "profesional"
# Ejemplo de overrides caminos si tu app los usa:
# data_paths:
#   catalog: "data/clients/client_1/products_catalog.csv"
#   prompts: "data/clients/client_1/prompts"
# top_k: 5
```

### 2.5 Storage de índices (`storage/<id>/index/`)

Directorio **generado automáticamente** en el primer request de un tenant por `app/pharma_assistant.py`/`app/index_cache.py` (no por `scripts/build_index.py` — ver nota abajo):

```
storage/<id>/index/
├── embeddings.npy      # float32 [N, D], normalizado
├── meta.json           # {signature, embedding_model, dim, count, has_faiss}
└── faiss.index         # si FAISS está disponible
```

> `service/index_loader.py` lee este mismo directorio (solo lectura, para `/readyz` y `/tenants/{id}/index/status`) — no construye nada. El path base se controla con `STORAGE_BASE` (por defecto `storage/`).
>
> `scripts/build_index.py` (con backend `hash` determinista sin OpenAI) escribe en `storage/<id>/` directamente, sin subcarpeta `index/` y sin `signature` en `meta.json` — un formato distinto, no conectado hoy a lo que lee `PharmaAssistant` ni `index_loader.py`. Ver "Known limitations" en el README raíz.

---

## 3) Precedencia y resolución de configuración

Cuando existen valores duplicados en diferentes niveles, se aplican estas **reglas de precedencia** (de mayor a menor):

1. **Variables de entorno** (e.g., `STORAGE_BASE`, `PRELOAD_TENANTS`).
2. **Overrides por cliente** (`data/clients/<id>/patterns/*`, rutas en `profiles/clients/<id>.yaml` si tu loader lo soporta).
3. **Patrones globales** (`data/patterns/*`).
4. **Valores por defecto** en código (p. ej., `DEFAULT_DAILY_LIMIT=1000` en `main.py`).

---

## 4) Configuración por entorno

### 4.1 Local / Docker Compose

`docker-compose.yml` (ejemplo simplificado):
```yaml
services:
  pharmaassistant:
    image: pharmaassistant:local
    ports: ["8080:8080"]
    environment:
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      ALLOWED_ORIGINS: ${ALLOWED_ORIGINS:-}
      PRELOAD_TENANTS: ${PRELOAD_TENANTS:-client_1}
      STORAGE_BASE: /app/storage
    volumes:
      - ./data:/app/data:ro
      - ./profiles:/app/profiles:ro
      - ./storage:/app/storage
      - ./service/tenants.yaml:/app/service/tenants.yaml:ro
```

### 4.2 Producción (genérico)

- Inyecta secretos por **variables de entorno** o un **Secret Manager** (no empaquetes claves en la imagen).
- Monta `tenants.yaml` o reemplázalo por una fuente centralizada.
- Logs a **stdout** (JSON) y métricas en `/metrics`.
- Controla `UVICORN_WORKERS` según CPU (p. ej., `workers = 2 * CPU + 1`).

> No hay todavía un despliegue de producción real verificado — solo `docker compose up` local. Cuando exista un entorno real, esta sección debería documentarlo con lo que de verdad se use, no con una plataforma hipotética.

---

## 5) Validación de configuración y datos

Scripts útiles (Paso 9) para validar antes de indexar/desplegar:

```bash
# Patrones globales YAML
python scripts/validate_patterns.py

# Perfiles y assets por cliente
python scripts/validate_profiles.py

# Catálogo de un cliente concreto
python scripts/validate_catalog.py --client-id client_1
```

---

## 6) Ejemplos rápidos

### 6.1 Tenant mínimo y prueba

```yaml
# service/tenants.yaml
tenants:
  client_1:
    api_key: "secret_key_client_1"
    max_requests_per_day: 1000
```

```bash
export PRELOAD_TENANTS=client_1
poetry run uvicorn service.main:app --port 8080

curl -s "http://localhost:8080/greet?client_id=client_1"   -H "x-api-key: secret_key_client_1" | jq .
```

### 6.2 Construir índice con backend “hash” (sin OpenAI)
```bash
python scripts/build_index.py --client-id client_1 --backend hash
```

---

## 7) Seguridad y buenas prácticas

- **No** expongas `service/tenants.yaml` en repos públicos.
- **No** loguees secretos ni payloads sensibles.
- **Restringe CORS** con `ALLOWED_ORIGINS`.
- **Cuotas**: ajusta `max_requests_per_day` por tenant según contrato.
- **Versiona** cambios en el índice (`index_info.json: version`).
- **Backups**: `data/` y `storage/` deben tener respaldo si no se pueden reconstruir fácilmente.

---

## 8) Solución de problemas

- **`RuntimeError: service/tenants.yaml not found`** → crea el archivo o móntalo por volumen.
- **401 en `/greet` o `/answer`** → revisa `x-api-key` y `client_id` existan en `tenants.yaml`.
- **429 “Daily quota exceeded”** → superaste la cuota; aumenta `max_requests_per_day` o espera el reset.
- **CORS bloqueado** → ajusta `ALLOWED_ORIGINS` (URLs exactas, incluyendo esquema `https://`).
- **`/metrics` vacío** → asegúrate de llamar `register_metrics(app)` y que el endpoint esté accesible.
- **El servicio no “arranca listo”** → usa `PRELOAD_TENANTS` y comprueba `/readyz` para investigar errores de precarga.
- **El contenedor no puede escribir en `/app/storage`** → corrige permisos del volumen en host (e.g., `chmod -R 777 storage`).

---

Mantén esta documentación sincronizada con cambios en el código y en los procesos de despliegue.
