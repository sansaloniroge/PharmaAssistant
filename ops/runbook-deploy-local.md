# Runbook — Despliegue Local (Dev)

Guía paso a paso para levantar **PharmaAssistant** en local, con y sin Docker Compose, generar índices, probar endpoints y verificar observabilidad. Pensada para *onboarding* y para reproducir problemas.

---

## 1) Requisitos

- **Python 3.11** (Poetry recomendado)  
- **curl** y opcionalmente **jq**  
- (Opcional) **Docker** + **Docker Compose**  
- Acceso a los datos del tenant (CSV + prompts) y a `service/tenants.yaml`

---

## 2) Estructura esperada (resumen)

```
PharmaAssistant/
├── app/
├── service/
│   ├── main.py
│   ├── tenants.yaml
│   ├── metrics.py
│   └── logging_setup.py
├── data/clients/<id>/{products_catalog.csv,prompts/*}
├── profiles/clients/<id>.yaml
├── storage/<id>/               # (generado por scripts/build_index.py)
└── scripts/*.py
```

---

## 3) Variables de entorno útiles

Crea un archivo `.env` en la raíz (usado por Docker Compose y útil como referencia):

```dotenv
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:3000
PRELOAD_TENANTS=client_1
OPENAI_API_KEY=           # opcional (para indexado con OpenAI)
STORAGE_BASE=/app/storage # para contenedor; en local usa ./storage
```

> En ejecución local sin contenedor, `STORAGE_BASE` por defecto es `storage/` (no es necesario definirlo).

---

## 4) Tenants y cuotas

Edita `service/tenants.yaml` (no subas claves reales al repo):

```yaml
tenants:
  client_1:
    api_key: "secret_key_client_1"
    max_requests_per_day: 1000
```

---

## 5) Construir el índice (previo al arranque)

### 5.1 Validaciones
```bash
python scripts/validate_patterns.py
python scripts/validate_profiles.py
python scripts/validate_catalog.py --client-id client_1
```

### 5.2 Indexado
- Con OpenAI (si defines `OPENAI_API_KEY`):
  ```bash
  python scripts/build_index.py --client-id client_1
  ```
- Sin OpenAI (modo determinista de desarrollo):
  ```bash
  python scripts/build_index.py --client-id client_1 --backend hash
  ```

### 5.3 Verificación de artefactos
```bash
ls -lh storage/client_1
cat storage/client_1/index_info.json | jq .
```

---

## 6) Arranque **sin Docker** (Poetry + Uvicorn)

```bash
poetry install
poetry run uvicorn service.main:app --host 0.0.0.0 --port 8080 --reload
```

**Smoke tests:**
```bash
curl -s http://localhost:8080/healthz | jq .
curl -i  http://localhost:8080/readyz

curl -s "http://localhost:8080/greet?client_id=client_1" \
  -H "x-api-key: secret_key_client_1" | jq .

curl -s "http://localhost:8080/answer?client_id=client_1" \
  -H "x-api-key: secret_key_client_1" -H "content-type: application/json" \
  -d '{"message":"hola"}' | jq .

curl -s http://localhost:8080/metrics | head
```

---

## 7) Arranque **con Docker Compose**

### 7.1 Build de la imagen
```bash
docker compose build --no-cache
```

### 7.2 Subir el servicio
```bash
docker compose up -d
docker compose logs -f pharmaassistant
```

**Volúmenes montados (recomendado):**
- `./data:/app/data:ro`
- `./profiles:/app/profiles:ro`
- `./storage:/app/storage`
- `./service/tenants.yaml:/app/service/tenants.yaml:ro`

**Variables (usando `.env`):**
- `LOG_LEVEL`, `ALLOWED_ORIGINS`, `PRELOAD_TENANTS`, `OPENAI_API_KEY`, `STORAGE_BASE`

**Smoke tests (idénticos):**
```bash
curl -s http://localhost:8080/healthz | jq .
curl -s "http://localhost:8080/greet?client_id=client_1" -H "x-api-key: secret_key_client_1" | jq .
curl -s http://localhost:8080/metrics | head
```

---

## 8) Observabilidad local (opcional)

Añade `docker-compose.override.yml` con Prometheus + Grafana (ver `docs/observability.md`).  
Arranque:
```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
# Prometheus: http://localhost:9090  Grafana: http://localhost:3000 (admin/admin)
```

---

## 9) Troubleshooting rápido

- **`RuntimeError: service/tenants.yaml not found`**  
  → Crea el archivo y monta por volumen en Docker.

- **401 en `/greet`**  
  → Revisa `x-api-key` y `client_id` existen en `tenants.yaml`.

- **429 “Daily quota exceeded”**  
  → Aumenta `max_requests_per_day` en `tenants.yaml` o espera al reset.

- **Índice no encontrado / corrupto**  
  → Repite validaciones y `scripts/build_index.py`; verifica `storage/<id>/` e `index_info.json`.

- **CORS bloquea el frontend**  
  → Ajusta `ALLOWED_ORIGINS` (URLs exactas, con esquema).

- **Permisos en `storage/` dentro de Docker**  
  ```bash
  chmod -R 777 storage  # o chown al uid/gid del contenedor
  ```

- **Latencia alta en primer acceso**  
  → Usa `PRELOAD_TENANTS=client_1` y verifica `/readyz`.

---

## 10) Makefile opcional

```makefile
.PHONY: venv run build-index smoke

venv:
\tpoetry install

run:
\tpoetry run uvicorn service.main:app --host 0.0.0.0 --port 8080 --reload

build-index:
\tpython scripts/validate_catalog.py --client-id client_1 && \\\n\tpython scripts/build_index.py --client-id client_1

smoke:
\tcurl -s http://localhost:8080/healthz | jq . && \\\n\tcurl -s "http://localhost:8080/greet?client_id=client_1" -H "x-api-key: secret_key_client_1" | jq .
```

---

## 11) Checklist de salida

- [ ] Índice creado (`storage/<id>/*`).  
- [ ] `/healthz`, `/readyz` 200.  
- [ ] `/greet` y `/answer` 200 con `x-api-key` correcta.  
- [ ] `/metrics` accesible.  
- [ ] Logs JSON visibles en consola/Compose.

---

## 12) Anexos

### 12.1 Datos mínimos de ejemplo
```csv
# data/clients/client_1/products_catalog.csv
Product,Price (€),Category,Description
Crema Hidratante,12.50,Facial,Hidratación diaria
```

### 12.2 Perfil mínimo
```yaml
# profiles/clients/client_1.yaml
id: client_1
name: "Farmacia Demo"
locale: "es-ES"
tone: "profesional"
```

### 12.3 Tenants mínimo
```yaml
tenants:
  client_1:
    api_key: "secret_key_client_1"
    max_requests_per_day: 1000
```

---

Con esto tienes un despliegue local reproducible y verificable, apto para desarrollo diario y demos.
