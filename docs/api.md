# API Reference — PharmaAssistant

Esta guía documenta la API HTTP expuesta por **PharmaAssistant** (FastAPI). Incluye autenticación, cuotas, endpoints, ejemplos `curl` y códigos de error.

---

## Base URL

- Local (por defecto): `http://localhost:8080`
- Producción: `https://<tu-host>` (detrás de LB/Ingress si aplica)

Todas las rutas documentadas a continuación se **anexan** a la Base URL.

---

## Autenticación y cuota

- **Autenticación**: API key por tenant
  - Header: `x-api-key: <API_KEY_DEL_TENANT>`
  - Query: `client_id=<ID_DEL_TENANT>`
- **Cuotas**: límite de peticiones **diario** por tenant (configurado en `service/tenants.yaml`).
  - Cabeceras en respuestas:
    - `X-RateLimit-Limit`: límite diario configurado
    - `X-RateLimit-Remaining`: peticiones restantes en la ventana actual

**Errores comunes**:
- `401 Unauthorized` → `client_id` desconocido o API key inválida
- `429 Too Many Requests` → cuota diaria superada

> **Nota:** no envíes la API key en la URL; usa el header `x-api-key` siempre que sea posible.

---

## Formato general

- **Content-Type**: `application/json` salvo `/metrics` (Prometheus exposition) y salud.
- **Errores**: objeto con `{"detail": "<mensaje>"}` (estándar FastAPI).
- **CORS**: restringido por `ALLOWED_ORIGINS` (ver `docs/configuration.md`).

---

## Endpoints

### 1) Health & Readiness

#### `GET /healthz`
Comprueba que el proceso está vivo y lista los `client_id` registrados.

**Respuesta 200**
```json
{
  "ok": true,
  "tenants": ["client_1", "client_2"]
}
```

**Ejemplo**
```bash
curl -s http://localhost:8080/healthz | jq .
```

---

#### `GET /readyz`
Indica si el servicio está **listo** para recibir tráfico. Si configuraste `PRELOAD_TENANTS`, intentará precargar perfiles/índices en el `startup` y devolverá su estado.

**200 OK (listo)**
```json
{
  "ok": true,
  "preloaded": ["client_1"],
  "index": { "client_1": { "count": 123, "dim": 1536 } }
}
```

**503 Service Unavailable (no listo)**
```text
{"ok": false, "errors": {"client_1": "assistant: <motivo>"}}
```

**Ejemplo**
```bash
curl -i http://localhost:8080/readyz
```

---

### 2) Tenants (salud e índice)

> Estos endpoints pueden usarse para diagnosis por tenant. `index/status` requiere autenticación (o el guard que tengas configurado).

#### `GET /tenants/{client_id}/healthz`
Valida que el **tenant** puede cargar correctamente (perfiles, prompts, etc.).

**200 OK**
```json
{ "client_id": "client_1", "ok": true }
```

**500 Error**
Respuesta genérica (los detalles quedan en logs):
```json
{ "detail": "Tenant failed to load" }
```

**Ejemplo**
```bash
curl -s http://localhost:8080/tenants/client_1/healthz | jq .
```

---

#### `GET /tenants/{client_id}/index/status`
Devuelve el estado del **índice** del tenant (existencia, tamaño, dimensión, ruta). Requiere `x-api-key` y `client_id` válidos (según tu guard).

**200 OK (índice encontrado)**
```json
{
  "tenant_id": "client_1",
  "exists": true,
  "count": 123,
  "dim": 1536,
  "bytes": 753664,
  "path": "/abs/path/storage/client_1"
}
```

**200 OK (no existe índice)**
```json
{
  "tenant_id": "client_1",
  "exists": false,
  "error": "Index files not found for tenant client_1 in storage/client_1",
  "path": "/abs/path/storage/client_1"
}
```

**Ejemplo**
```bash
curl -s "http://localhost:8080/tenants/client_1/index/status?client_id=client_1"   -H "x-api-key: secret_key_client_1" | jq .
```

---

### 3) Funcionales (greet / answer)

#### `GET /greet?client_id=<id>`
Devuelve un saludo generado por el asistente del tenant.

**Headers**: `x-api-key: ...`  
**Respuesta 200**
```json
{
  "client_id": "client_1",
  "greeting": "¡Hola! ¿En qué puedo ayudarte hoy?"
}
```

**Errores**
- `401` API key inválida / tenant desconocido
- `429` cuota diaria superada

**Ejemplo**
```bash
curl -s "http://localhost:8080/greet?client_id=client_1"   -H "x-api-key: secret_key_client_1" | jq .
```

---

#### `POST /answer?client_id=<id>`
Genera una **respuesta** ante un mensaje del usuario, usando el perfil/índice del tenant.

**Headers**: `x-api-key: ...`  
**Body**:
```json
{ "message": "Tengo la piel sensible, ¿qué crema me recomiendas?" }
```

**Respuesta 200**
El contenido exacto depende de tu implementación de `PharmaAssistant.answer`. Ejemplo genérico:
```json
{
  "client_id": "client_1",
  "answer": "Para piel sensible te recomiendo...",
  "sources": [
    { "product": "Crema Hidratante", "score": 0.82 },
    { "product": "Crema Calmante", "score": 0.77 }
  ]
}
```

**Errores**
- `401` API key inválida / tenant desconocido
- `429` cuota diaria superada
- `500` error interno (detalle en logs)

**Ejemplo**
```bash
curl -s "http://localhost:8080/answer?client_id=client_1"   -H "x-api-key: secret_key_client_1"   -H "content-type: application/json"   -d '{"message":"hola"}' | jq .
```

> Métrica de negocio: `recommendations_total{client_id="<id>"}` incrementa con cada llamada exitosa.

---

### 4) Observabilidad

#### `GET /metrics`
Exposición en formato **Prometheus** (texto). Incluye métricas HTTP y de negocio.

**Tipos**
- `http_requests_total{method,path,status}`
- `http_request_duration_seconds_bucket/sum/count{method,path}`
- `recommendations_total{client_id}`

**Ejemplo**
```bash
curl -s http://localhost:8080/metrics | head -n 20
```

> Requiere que `service/metrics.py` haya sido registrado con `register_metrics(app)` en `service/main.py`.

---

## Códigos de estado (resumen)

| Código | Significado | Cuándo |
|---|---|---|
| 200 | OK | Petición exitosa |
| 401 | Unauthorized | `client_id` desconocido o API key inválida |
| 429 | Too Many Requests | Cuota diaria superada |
| 500 | Internal Server Error | Error interno (ver logs) |
| 503 | Service Unavailable | Readiness no alcanzado (`/readyz`) |

---

## Ejemplos avanzados

### Pasar API key de forma segura
```bash
API_KEY="secret_key_client_1"
curl -s "http://localhost:8080/answer?client_id=client_1"   -H "x-api-key: ${API_KEY}"   -H "content-type: application/json"   -d '{"message":"hola"}' | jq .
```

### Script en bash para probar varios endpoints
```bash
#!/usr/bin/env bash
HOST=${1:-http://localhost:8080}
CID=${2:-client_1}
KEY=${3:-secret_key_client_1}

curl -s ${HOST}/healthz | jq .
curl -s "${HOST}/tenants/${CID}/healthz" | jq .
curl -s "${HOST}/tenants/${CID}/index/status?client_id=${CID}" -H "x-api-key: ${KEY}" | jq .
curl -s "${HOST}/greet?client_id=${CID}" -H "x-api-key: ${KEY}" | jq .
curl -s "${HOST}/answer?client_id=${CID}" -H "x-api-key: ${KEY}" -H "content-type: application/json" -d '{"message":"hola"}' | jq .
curl -s ${HOST}/metrics | head
```

---

## Notas de seguridad

- **No** expongas `service/tenants.yaml` con claves reales en repos públicos.
- Limita `ALLOWED_ORIGINS` para CORS en producción.
- Evita loguear contenido sensible de usuarios o secretos.
- Usa HTTPS en producción (TLS gestionado por tu LB/Ingress).

---

_Actualiza este documento cuando cambien los contratos de `PharmaAssistant.answer` o se incorporen nuevos endpoints._
