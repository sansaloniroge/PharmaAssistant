# Getting Started (Local)

Guía paso a paso para levantar **PharmaAssistant** en tu máquina: instalación, datos mínimos de un cliente, construcción del índice y ejecución de la API. Al final tienes una sección con **Docker Compose**.

---

## Requisitos

- **Python** 3.11 (Poetry recomendado)
- **git**, **curl** (o `wget`), y opcionalmente **jq** para formatear JSON
- (Opcional) **Docker** + **Docker Compose** si quieres levantarlo en contenedores

---

## Estructura de carpetas (referencia)

Tu repo debería parecerse a esto:

```
PharmaAssistant/
├── app/
├── service/
├── data/
│   └── clients/
│       └── client_1/
│           ├── products_catalog.csv
│           ├── prompts/
│           │   ├── compose_prompt.txt
│           │   ├── few_shot_prompt.txt
│           │   ├── greeting_prompt.txt
│           │   ├── no_match_prompt.txt
│           │   └── system_prompt.txt
│           └── patterns/         # (opcional: overrides por cliente)
├── profiles/
│   └── clients/
│       └── client_1.yaml
├── storage/
│   └── client_1/                 # (generados) embeddings.npy, meta.json, index_info.json
├── scripts/
│   ├── build_index.py
│   ├── rebuild_all.py
│   ├── validate_catalog.py
│   ├── validate_patterns.py
│   └── validate_profiles.py
└── service/
    ├── main.py
    ├── tenants.yaml
    ├── metrics.py
    └── logging_setup.py
```

---

## 1) Instalar dependencias

```bash
# Dentro del repo
poetry install
```

> Si no usas Poetry, crea un venv y `pip install -r` con `poetry export -f requirements.txt -o req.txt`.

---

## 2) Configura tenants y variables

Crea `service/tenants.yaml`:

```yaml
tenants:
  client_1:
    api_key: "secret_key_client_1"
    max_requests_per_day: 1000
# Añade más tenants según necesites
```

Variables útiles (puedes exportarlas en tu shell o en un `.env`):
- `LOG_LEVEL` — INFO/DEBUG…
- `ALLOWED_ORIGINS` — orígenes CORS (coma-separado)
- `PRELOAD_TENANTS` — lista de tenants a precargar en startup (opcional)
- `OPENAI_API_KEY` — activa embeddings OpenAI en el build del índice (si no, se usa embedding determinista “hash” para pruebas)
- `STORAGE_BASE` — base para leer índices (por defecto `storage/`)

---

## 3) Prepara datos del cliente

### 3.1 Catálogo mínimo

Crea `data/clients/client_1/products_catalog.csv` con, al menos, columnas equivalentes a **producto**, **precio** y **categoría** (hay alias aceptados). Ejemplo:

```csv
Product,Price (€),Category,Description,Benefits,Brand
Crema Hidratante,12.50,Facial,"Hidratación diaria","Piel suave; rápida absorción",MarcaX
Protector Solar SPF50,14,Facial,"Alta protección UVA/UVB","Resistente al agua",MarcaY
Gel de Ducha,5.20,Cuerpo,"Limpieza suave","pH neutro",MarcaZ
```

### 3.2 Prompts del cliente

Crea `data/clients/client_1/prompts/` con los siguientes archivos (texto plano):

```
compose_prompt.txt
few_shot_prompt.txt
greeting_prompt.txt
no_match_prompt.txt
system_prompt.txt
```

*(Contenido libre; puedes empezar con borradores y ajustarlos después.)*

### 3.3 Perfil del cliente

Crea `profiles/clients/client_1.yaml` (ejemplo básico):

```yaml
id: client_1
name: "Farmacia Demo"
locale: "es-ES"
tone: "profesional"
# paths y otros overrides según tu implementación
```

---

## 4) Validar datos (recomendado)

Antes de construir el índice, ejecuta las validaciones:

```bash
# Patrones globales YAML
python scripts/validate_patterns.py

# Perfiles y assets del cliente
python scripts/validate_profiles.py

# Catálogo del cliente
python scripts/validate_catalog.py --client-id client_1
```

> Estos scripts detectan columnas faltantes, precios inválidos, duplicados y la presencia de prompts/perfiles.

---

## 5) Construir el índice (offline)

Genera `embeddings.npy`, `meta.json` e `index_info.json` en `storage/client_1/`.

```bash
# Con OpenAI si tienes OPENAI_API_KEY (backend automático)
python scripts/build_index.py --client-id client_1

# O forzando embedding determinista (sin OpenAI, útil para desarrollo)
python scripts/build_index.py --client-id client_1 --backend hash
```

Verifica artefactos:

```bash
ls -lh storage/client_1
cat storage/client_1/index_info.json | jq .
```

---

## 6) Arrancar la API (local)

```bash
poetry run uvicorn service.main:app --host 0.0.0.0 --port 8080 --reload
```

### Smoke test

```bash
# Salud
curl -s http://localhost:8080/healthz | jq .

# Readiness (si configuraste PRELOAD_TENANTS)
curl -i http://localhost:8080/readyz

# Greet (auth + quota; usa la API key del tenant)
curl -s "http://localhost:8080/greet?client_id=client_1"   -H "x-api-key: secret_key_client_1" | jq .

# Answer
curl -s "http://localhost:8080/answer?client_id=client_1"   -H "x-api-key: secret_key_client_1" -H "content-type: application/json"   -d '{"message":"hola"}' | jq .

# Métricas Prometheus
curl -s http://localhost:8080/metrics | head
```

---

## 7) (Alternativa) Docker Compose

Con el `Dockerfile` y `docker-compose.yml` del repo, puedes levantar todo en contenedores:

```bash
docker compose up --build -d
```

Volúmenes montados:
- `./data:/app/data:ro`
- `./profiles:/app/profiles:ro`
- `./storage:/app/storage`
- `./service/tenants.yaml:/app/service/tenants.yaml:ro`

Variables (puedes definirlas en `.env`):
- `LOG_LEVEL`, `OPENAI_API_KEY`, `ALLOWED_ORIGINS`, `PRELOAD_TENANTS`, `STORAGE_BASE`

Pruebas:
```bash
curl -s http://localhost:8080/healthz | jq .
curl -s "http://localhost:8080/greet?client_id=client_1" -H "x-api-key: secret_key_client_1" | jq .
curl -s http://localhost:8080/metrics | head
```

Logs:
```bash
docker compose logs -f pharmaassistant
```

---

## 8) Consejos y pasos siguientes

- **Ajusta prompts** por cliente en `data/clients/<id>/prompts/`.
- **Valida** y **reindexa** cuando cambie el catálogo (ver `scripts/validate_*` y `scripts/build_index.py`).
- Consulta:
  - [`docs/adding-a-client.md`](./adding-a-client.md)
  - [`docs/observability.md`](./observability.md)
  - [`docs/ci-cd.md`](./ci-cd.md)
  - Runbooks en `ops/` (reindex, cuotas, incidentes, etc.)

---

## Solución de problemas (FAQ)

**1) `RuntimeError: service/tenants.yaml not found`**  
→ Crea el archivo `service/tenants.yaml` con los tenants y sus API keys. Móntalo por volumen si usas Docker.

**2) `/greet` devuelve 401**  
→ Revisa `x-api-key` y `client_id`. Asegúrate de que `client_id` existe en `service/tenants.yaml`.

**3) 429 “Daily quota exceeded”**  
→ Se alcanzó el límite diario del tenant. Ajusta `max_requests_per_day` o espera al reset (según tu implementación).

**4) `/answer` devuelve 500**  
→ Mira los logs (JSON) en consola/Compose. Reindexa (`scripts/build_index.py`) y verifica `/tenants/<id>/index/status`.

**5) `/metrics` vacío o error**  
→ Asegúrate de que `service/metrics.py` está registrado desde `service/main.py` con `register_metrics(app)`.

**6) El contenedor no puede escribir en "/app/storage"**  
→ Ajusta permisos del volumen en host (`chmod -R 777 storage` o `chown -R $(id -u):$(id -g) storage`).

---

¡Listo! Con esto deberías poder levantar PharmaAssistant localmente y empezar a iterar.
