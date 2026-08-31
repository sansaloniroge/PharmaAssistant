# Añadir un cliente — Paso a paso

Este runbook explica cómo **incorporar un nuevo cliente** a PharmaAssistant: crear su perfil y prompts, preparar el catálogo, validar, **construir el índice** y probar la API. Incluye ejemplos listos para copiar y una checklist final.

---

## Requisitos previos

- Estructura del repo estándar (`data/`, `profiles/`, `storage/`, `service/`).
- Scripts del proyecto instalados (ver `docs/getting-started.md`).
- Acceso para modificar `service/tenants.yaml` (API keys/cuotas).
- (Opcional) `OPENAI_API_KEY` si quieres embeddings semánticos reales en el indexado.

> Si no tienes `OPENAI_API_KEY`, puedes usar `--backend hash` al construir el índice (embedding determinista para desarrollo).

---

## Estructura a crear

Sustituye `<id>` por el identificador del cliente (sin espacios).

```
data/clients/<id>/
├── products_catalog.csv
├── prompts/
│   ├── compose_prompt.txt
│   ├── few_shot_prompt.txt
│   ├── greeting_prompt.txt
│   ├── no_match_prompt.txt
│   └── system_prompt.txt
└── patterns/                  # (opcional: overrides)
    ├── category_patterns.yaml
    ├── price_patterns.yaml
    └── schema_map.yaml

profiles/clients/<id>.yaml

storage/<id>/                  # (generado por scripts/build_index.py)
```

---

## 1) Perfil del cliente

Crea `profiles/clients/<id>.yaml`:

```yaml
id: <id>
name: "Nombre Comercial"
locale: "es-ES"          # o "ca-ES", "en-GB", etc.
tone: "profesional"      # libre: "amable", "técnico", ...
# (opcional) overrides o rutas si tu loader los usa
# data_paths:
#   catalog: "data/clients/<id>/products_catalog.csv"
#   prompts: "data/clients/<id>/prompts"
# top_k: 5
```

Recomendaciones:
- Mantén `id` = nombre de carpeta en `data/clients/<id>` y `storage/<id>`.
- Define `locale` correcto (impacta mensajes y formateos).
- Usa `tone` acorde a la marca del cliente.

---

## 2) Prompts del cliente

Crea los 5 archivos en `data/clients/<id>/prompts/`:
```
compose_prompt.txt
few_shot_prompt.txt
greeting_prompt.txt
no_match_prompt.txt
system_prompt.txt
```

Pautas rápidas:
- **system**: reglas generales (tono, seguridad, límites).
- **greeting**: saludo inicial (usado por `/greet`).
- **compose**: cómo estructurar recomendaciones (bullets, fuentes, etc.).
- **few_shot**: 2–5 ejemplos Q/A del dominio del cliente.
- **no_match**: mensaje cuando no haya resultados relevantes.

> Puedes arrancar con contenido mínimo y refinar tras las primeras pruebas.

---

## 3) Catálogo `products_catalog.csv`

Columnas lógicas requeridas: **producto**, **precio**, **categoría** (se aceptan **alias**; ver validación). Recomendado añadir **description**, **benefits**, **brand**.

Ejemplo mínimo:
```csv
Product,Price (€),Category,Description,Benefits,Brand
Crema Hidratante,12.50,Facial,"Hidratación diaria","Piel suave; rápida absorción",MarcaX
Protector Solar SPF50,14,Facial,"Alta protección UVA/UVB","Resistente al agua",MarcaY
```

Consejos:
- Precios como texto o numéricos; el validador normaliza `12,50`, `€12.50`, etc.
- Evita duplicados de producto; si existen SKUs, añade una columna `sku` y úsala como ID canónico.

---

## 4) Overrides de patrones (opcional)

Si el cliente requiere taxonomías o parsing distintos a los globales (`data/patterns/*`), crea:
```
data/clients/<id>/patterns/
  category_patterns.yaml
  price_patterns.yaml
  schema_map.yaml
```

Si no existen, el sistema usa **fallback global**.

---

## 5) Registrar el tenant (API key + cuota)

Edita `service/tenants.yaml`:
```yaml
tenants:
  <id>:
    api_key: "secret_key_<id>"
    max_requests_per_day: 1000
```

> No versionar claves reales. En entornos con contenedores, monta este archivo por volumen o usa un gestor de secretos.

---

## 6) Validaciones (recomendado)

Ejecuta los scripts de **Paso 9** antes de indexar:

```bash
# Patrones globales YAML
python scripts/validate_patterns.py

# Perfiles y assets del cliente
python scripts/validate_profiles.py

# Catálogo del cliente
python scripts/validate_catalog.py --client-id <id>
```

> Si ves **warnings**, puedes seguir; si hay **errors**, corrígelos antes de continuar (exit code != 0).

---

## 7) Construir el índice (offline)

Genera `embeddings.npy`, `meta.json` y `index_info.json` en `storage/<id>/`.

```bash
# Con OpenAI si tienes OPENAI_API_KEY
python scripts/build_index.py --client-id <id>

# O sin OpenAI (embedding determinista de pruebas)
python scripts/build_index.py --client-id <id> --backend hash
```

Verificación:
```bash
ls -lh storage/<id>
cat storage/<id>/index_info.json | jq .
```

---

## 8) Preload (opcional) y readiness

Puedes precalentar el tenant al arrancar la API:
```bash
export PRELOAD_TENANTS="<id>"
poetry run uvicorn service.main:app --port 8080 --reload
curl -s http://localhost:8080/readyz | jq .
```

---

## 9) Probar la API

```bash
API=http://localhost:8080
CID=<id>
KEY=secret_key_<id>

# Salud
curl -s $API/healthz | jq .

# Estado del índice
curl -s "$API/tenants/$CID/index/status?client_id=$CID" -H "x-api-key: $KEY" | jq .

# Greet
curl -s "$API/greet?client_id=$CID" -H "x-api-key: $KEY" | jq .

# Answer
curl -s "$API/answer?client_id=$CID" \
  -H "x-api-key: $KEY" -H "content-type: application/json" \
  -d '{"message":"hola"}' | jq .
```

> Las respuestas incluyen cabeceras `X-RateLimit-Limit` y `X-RateLimit-Remaining` para control de cuotas.

---

## 10) CI/CD (opcional, NO-Kubernetes)

- Añade el cliente a tus **data checks** si quieres validar su CSV en PRs:
  ```yaml
  # .github/workflows/data-checks.yml
  - name: Validate catalogs
    run: |
      python scripts/validate_catalog.py --client-id <id> || true
  ```
- Versiona `pyproject.toml` para que la imagen publicada incluya la etiqueta de versión.

---

## 11) Checklist rápida

- [ ] `profiles/clients/<id>.yaml` creado y coherente (`id`, `locale`, `tone`).  
- [ ] `data/clients/<id>/prompts/*.txt` presentes.  
- [ ] `data/clients/<id>/products_catalog.csv` válido (sin duplicados, precios normalizados).  
- [ ] (Opcional) `data/clients/<id>/patterns/*` si necesita overrides.  
- [ ] `service/tenants.yaml` con `api_key` y `max_requests_per_day`.  
- [ ] `scripts/validate_*` sin **errors**.  
- [ ] `scripts/build_index.py --client-id <id>` generó `storage/<id>/*`.  
- [ ] `/tenants/<id>/index/status` y `/greet` responden 200 con `x-api-key` correcto.  

---

## Solución de problemas

- **401 Unauthorized** → `client_id` no existe en `tenants.yaml` o `x-api-key` incorrecta.
- **429 Daily quota exceeded** → aumenta `max_requests_per_day` o espera al reset.
- **Índice no encontrado** → ejecuta de nuevo el build o corrige la ruta de `STORAGE_BASE`.
- **500 en `/answer`** → revisa logs; valida catálogo y reindexa. Comprueba `/tenants/<id>/healthz`.
- **CORS bloqueado** → ajusta `ALLOWED_ORIGINS` en entorno.

---

## Plantillas rápidas

### Perfil
```yaml
id: <id>
name: "Nombre Comercial"
locale: "es-ES"
tone: "profesional"
```

### Tenants
```yaml
tenants:
  <id>:
    api_key: "secret_key_<id>"
    max_requests_per_day: 1000
```

### CSV mínimo
```csv
Product,Price (€),Category,Description
Crema Hidratante,12.50,Facial,"Hidratación diaria"
```

---

**Siguiente paso:** refinar prompts y probar consultas reales; si el cliente tiene gran catálogo, valora filtros por categoría/brand y paginación de resultados en el asistente.
